#!/usr/bin/env python3
"""Deterministic Layer 1 and Layer 2 checks for the prose-self-check skill.

Layers 1 (lexical) and 2 (structural) are pattern matches over text. The
agent used to run them by eye, which is both expensive and unreliable: a
scan of a 400-line artifact for nineteen banned words plus five structural
shapes is exactly the work a regex does perfectly and a reader does not.
This script runs those two layers so the agent's attention goes to Layer 4
(the emptiness gate), which no scanner can do.

Layer 3 stays in `burstiness.py`; it was already deterministic.

The banned-word list is NOT duplicated here. It is parsed out of the
"Banned Vocabulary" section of the voice rule at runtime, so the rule stays
the single authoritative copy (SKILL.md anti-pattern: "Copying the
banned-word list into this skill"). What this script owns is the TIERING
that SKILL.md describes: which of those words are high-signal (scrub on
sight) and which are low-signal (reported as info, never a failure, because
a blanket scrub reads worse than the tell it removes).

Severity maps to the skill's own weighting, not to ease of detection:

- `high`   a tell the empirical ranking says readers actually cite, or a
           hard repo rule (the dash ban). Fails the run.
- `info`   a low-signal keyword. Reported for Layer 4 adjudication: it stays
           if its paragraph makes a real claim, and goes with the filler if
           it does not. Never fails the run on its own.

Fenced code blocks and inline code spans are skipped. Prose rules do not
apply to code, and the rule files themselves quote every banned word in
backticks. An inline span that wraps across a line break is skipped too:
masking runs over the whole document, not line by line, because a wrapped
``code span`` is exactly how a document that DOCUMENTS these tells writes
them.

EXIT CODES (ADR-035):
  0 - No high-severity findings. Info findings may still be present.
  1 - At least one high-severity finding.
  2 - Configuration error: a named file does not exist or cannot be read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

HIGH = "high"
INFO = "info"

EM_DASH = "—"
EN_DASH = "–"

# Tiering from SKILL.md Layer 1. These words top keyword scans but are
# ~0% reader-cited, so presence alone is not a finding.
LOW_SIGNAL_WORDS = frozenset(
    {"however", "thus", "moreover", "additionally", "nuanced", "comprehensive"},
)

# Where the voice rule can live, in resolution order. The plugin ships the
# rule under its own root; a consumer checkout has one of the two mirrors.
_RULE_CANDIDATES: tuple[tuple[str | None, str], ...] = (
    ("CLAUDE_PLUGIN_ROOT", "rules/voice.md"),
    ("COPILOT_PLUGIN_ROOT", "instructions/voice.instructions.md"),
    (None, ".claude/rules/voice.md"),
    (None, ".github/instructions/voice.instructions.md"),
)
_PLUGIN_MARKER = Path(".claude-plugin") / "plugin.json"

_BANNED_HEADING = re.compile(r"^#{1,6}\s+Banned Vocabulary\s*$", re.MULTILINE)
_NEXT_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_CODE_TOKEN = re.compile(r"`([^`]+)`")
_WORD_ONLY = re.compile(r"^[a-z][a-z'-]*$")

_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_INLINE_CODE = re.compile(r"`[^`]*`", re.DOTALL)

# Layer 2 structural tells. Each pattern targets one shape SKILL.md names.
_STRUCTURAL_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "contrast_framing",
        re.compile(
            r"\b(?:it|this|that|there)(?:'s| is) not (?:just )?[^,.;\n]{1,60},\s*"
            r"(?:it|this|that)(?:'s| is)\b",
            re.IGNORECASE,
        ),
        "contrast framing; state the claim directly",
    ),
    (
        "contrast_framing",
        re.compile(
            r"\b(?:is|are)n(?:'|)t about [^,.;\n]{1,60},\s*(?:it|they)(?:'s|'re| is| are)"
            r" about\b",
            re.IGNORECASE,
        ),
        "contrast framing; state the claim directly",
    ),
    (
        "contrast_framing",
        re.compile(r"\bnot [^,.;\n]{1,60},\s*but (?:rather )?\b", re.IGNORECASE),
        "contrast framing; state the claim directly",
    ),
    (
        "trailing_offer",
        re.compile(
            r"\b(?:want me to|would you like me to|i could also|let me know if you'd like"
            r"|shall i also)\b",
            re.IGNORECASE,
        ),
        "manufactured trailing offer; delete it",
    ),
    (
        "signposting",
        re.compile(
            r"(?:^|\n)\s*(?:>\s*|[-*+]\s+|\d+\.\s+)?"
            r"(?:Honestly,|Look,|Let's dive in|It's worth noting that|In today's landscape)",
        ),
        "signposting opener; lead with the point",
    ),
    (
        "model_identity",
        re.compile(r"\bas an AI(?: language model| assistant)?\b|\bI'm just an AI\b", re.IGNORECASE),
        "model-identity phrase; remove it",
    ),
)


@dataclass(frozen=True)
class Finding:
    """One prose tell located in an artifact."""

    line: int
    column: int
    kind: str
    severity: str
    match: str
    note: str


def _plugin_install_root() -> Path | None:
    """Return the plugin root discovered by walking up from this file."""
    current = Path(__file__).resolve().parent
    while True:
        if (current / _PLUGIN_MARKER).is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent


def discover_rules_file() -> Path | None:
    """Return the voice rule file, or None when no copy is reachable."""
    for env_var, relpath in _RULE_CANDIDATES:
        if env_var is None:
            candidate = Path.cwd() / relpath
        else:
            root = os.environ.get(env_var)
            if not root:
                continue
            candidate = Path(root) / relpath
        if candidate.is_file():
            return candidate

    install_root = _plugin_install_root()
    if install_root is None:
        return None
    for relpath in ("rules/voice.md", "instructions/voice.instructions.md"):
        candidate = install_root / relpath
        if candidate.is_file():
            return candidate
    return None


def parse_banned_words(rules_text: str) -> set[str]:
    """Extract the banned-word list from the voice rule's own section.

    Reads the backticked tokens under the "Banned Vocabulary" heading and
    stops at the next heading, so the replacement examples that follow the
    list are not mistaken for entries.
    """
    heading = _BANNED_HEADING.search(rules_text)
    if heading is None:
        return set()
    body_start = heading.end()
    following = _NEXT_HEADING.search(rules_text, body_start)
    body = rules_text[body_start : following.start() if following else len(rules_text)]
    return {
        token.lower()
        for token in _CODE_TOKEN.findall(body)
        if _WORD_ONLY.match(token.strip().lower())
    }


def _blank_fenced_blocks(text: str) -> list[str]:
    """Return the lines of *text* with every fenced code block blanked out.

    Blanking rather than dropping keeps line numbers aligned with the source.
    Fence markers go too, so their backticks cannot pair with an inline span.
    """
    lines: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        match = _FENCE.match(line)
        if fence is None:
            if match is None:
                lines.append(line)
                continue
            fence = match.group(1)
            lines.append("")
            continue
        lines.append("")
        if match is not None and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence):
            fence = None
    return lines


def _mask_inline_code(text: str) -> str:
    """Blank out inline code spans, preserving every column and newline.

    Runs over the whole document so a span that wraps across a line break is
    masked. Masking line by line pairs the wrong backticks on the wrapped
    line and leaves quoted examples exposed.
    """
    return _INLINE_CODE.sub(
        lambda m: "".join(c if c == "\n" else " " for c in m.group(0)),
        text,
    )


def _prose_lines(text: str) -> list[tuple[int, str]]:
    """Return (line_number, masked_line) for prose outside code."""
    masked = _mask_inline_code("\n".join(_blank_fenced_blocks(text)))
    return [
        (number, line)
        for number, line in enumerate(masked.split("\n"), start=1)
        if line.strip()
    ]


def _lexical_findings(lines: list[tuple[int, str]], banned: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in lines:
        for dash, name in ((EM_DASH, "em_dash"), (EN_DASH, "en_dash")):
            start = line.find(dash)
            while start != -1:
                findings.append(
                    Finding(
                        line=number,
                        column=start + 1,
                        kind=name,
                        severity=HIGH,
                        match=dash,
                        note="banned by the universal rule; restructure or use a comma",
                    ),
                )
                start = line.find(dash, start + 1)
        for match in re.finditer(r"[A-Za-z][A-Za-z'-]*", line):
            word = match.group(0).lower()
            if word not in banned:
                continue
            low = word in LOW_SIGNAL_WORDS
            findings.append(
                Finding(
                    line=number,
                    column=match.start() + 1,
                    kind="banned_word_low_signal" if low else "banned_word",
                    severity=INFO if low else HIGH,
                    match=match.group(0),
                    note=(
                        "low-signal; cut only if this paragraph also fails Layer 4"
                        if low
                        else "banned vocabulary; be specific instead"
                    ),
                ),
            )
    return findings


def _structural_findings(lines: list[tuple[int, str]]) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in lines:
        for kind, pattern, note in _STRUCTURAL_PATTERNS:
            for match in pattern.finditer(line):
                findings.append(
                    Finding(
                        line=number,
                        column=match.start() + 1,
                        kind=kind,
                        severity=HIGH,
                        match=match.group(0).strip(),
                        note=note,
                    ),
                )
    return findings


def lint_prose(text: str, banned: set[str]) -> list[Finding]:
    """Return every Layer 1 and Layer 2 finding in *text*, in file order."""
    lines = _prose_lines(text)
    findings = _lexical_findings(lines, banned) + _structural_findings(lines)
    return sorted(findings, key=lambda f: (f.line, f.column, f.kind))


def _read(name: str) -> str:
    if name == "-":
        return sys.stdin.read()
    return Path(name).read_text(encoding="utf-8")


def _emit_text(results: dict[str, list[Finding]], rules_note: str | None) -> None:
    if rules_note:
        print(rules_note, file=sys.stderr)
    total_high = 0
    for name, findings in results.items():
        for finding in findings:
            total_high += finding.severity == HIGH
            print(
                f"{name}:{finding.line}:{finding.column}: {finding.severity}: "
                f"{finding.kind}: {finding.match!r} ({finding.note})",
            )
    if not any(results.values()):
        print("Layers 1-2 clean. Layer 4 (emptiness gate) is still yours to run.")
        return
    total = sum(len(f) for f in results.values())
    print(f"\n{total} finding(s), {total_high} high severity")
    print("Layer 4 (emptiness gate) is still yours to run.")


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Run prose-self-check Layers 1 and 2 over an artifact",
    )
    parser.add_argument("files", nargs="+", help="Files to check, or - for stdin")
    parser.add_argument("--rules", help="Path to the voice rule (default: auto-discover)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    args = parser.parse_args(argv)

    rules_path = Path(args.rules) if args.rules else discover_rules_file()
    rules_note: str | None = None
    banned: set[str] = set()
    if rules_path is None:
        rules_note = (
            "Warning: no voice rule found; running dash and structural checks only. "
            "Pass --rules PATH to enable the banned-word check."
        )
    else:
        try:
            banned = parse_banned_words(rules_path.read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"Error: cannot read rules file {rules_path}: {exc}", file=sys.stderr)
            return 2
        if not banned:
            rules_note = (
                f"Warning: no 'Banned Vocabulary' section in {rules_path}; "
                "running dash and structural checks only."
            )

    results: dict[str, list[Finding]] = {}
    for name in args.files:
        try:
            text = _read(name)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"Error: cannot read {name}: {exc}", file=sys.stderr)
            return 2
        results[name] = lint_prose(text, banned)

    if args.json:
        print(
            json.dumps(
                {
                    "rules_file": str(rules_path) if rules_path else None,
                    "banned_word_count": len(banned),
                    "files": {n: [asdict(f) for f in fs] for n, fs in results.items()},
                    "high_severity_count": sum(
                        1 for fs in results.values() for f in fs if f.severity == HIGH
                    ),
                },
                indent=2,
                sort_keys=True,
            ),
        )
    else:
        _emit_text(results, rules_note)

    has_high = any(f.severity == HIGH for fs in results.values() for f in fs)
    return 1 if has_high else 0


if __name__ == "__main__":
    sys.exit(main())
