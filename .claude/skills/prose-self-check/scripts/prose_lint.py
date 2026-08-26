#!/usr/bin/env python3
# taste-lint: ignore file-size
# 504 lines against a 500 ceiling. The rule wants extraction, and extraction
# is the wrong trade here: this ships inside a vendored plugin and is invoked
# as a standalone script, so a second module needs a sys.path bootstrap and
# adds a consumer-install failure mode for the sake of four lines. The cheap
# reductions are already taken (the module docstring no longer restates
# SKILL.md, the repeated finding notes are keyed by kind, and main() is split
# into _resolve_banned_words and _emit_json). Scoped to file-size only;
# complexity and every other rule still apply.
"""Deterministic Layer 1 and Layer 2 checks for the prose-self-check skill.

Both layers are pattern matches over text that the agent used to run by eye.
SKILL.md is the reference for what each layer covers and why; this module is
the engine. Layer 3 stays in `burstiness.py`, Layer 4 stays with the agent.

The banned-word list is parsed from the voice rule at runtime, never copied
here. Every run reports what it examined, not only what it found: a document
whose unterminated fence hid most of its prose must not read as clean.

EXIT CODES (ADR-035):
  0 - No high-severity findings. Info findings may still be present.
  1 - At least one high-severity finding.
  2 - Configuration error: a named file does not exist or cannot be read.
"""

from __future__ import annotations

import argparse
import bisect
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

HIGH = "high"
INFO = "info"

UNTERMINATED_FENCE = "unterminated_fence"

# Written as escapes, not literals: this file ships in the plugin tree,
# where the dash ban is enforced at the byte level (Issue #4079).
EM_DASH = "\u2014"
EN_DASH = "\u2013"

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
_TOKEN = re.compile(r"[A-Za-z]+(?:['-][A-Za-z]+)*")
# A token touching one of these is part of a URL slug, an identifier, or
# a tag, not prose. `robust` inside `https://x.com/robust` is not a word
# choice anyone can rewrite.
_NON_PROSE_NEIGHBORS = frozenset("/_>=\\")

_FENCE = re.compile(r"^[ \t]*(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_INLINE_CODE = re.compile(r"`[^`]*`", re.DOTALL)

# Layer 2 structural tells. Each pattern targets one shape SKILL.md names.
# A clause gap may cross one hard wrap but never a paragraph break, so a tell
# in prose wrapped near 80 columns is still seen.
_GAP = r"(?:[^,.;:|\n]|\n(?!\n)){1,60}"
# The comma may be followed by one hard wrap, never a paragraph break.
_WRAP = r",[ \t]*(?:\n(?!\n)[ \t]*)?"

_NOTES = {
    "contrast_framing": "contrast framing; state the claim directly",
    "trailing_offer": "manufactured trailing offer; delete it",
    "signposting": "signposting opener; lead with the point",
    "model_identity": "model-identity phrase; remove it",
}

_STRUCTURAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "contrast_framing",
        # The subject is any short noun phrase, not just a pronoun. SKILL.md
        # documents the shape as "not X, it's Y"; anchoring on it/this/that
        # missed every sentence with a real subject.
        re.compile(
            r"\b[A-Za-z][\w'-]*(?:\s+[\w'-]+){0,3}\s+"
            r"(?:is|was|are|were)n?(?:'t| not)\s+(?:just\s+)?" + _GAP + _WRAP + r"(?:it|this|that|they)(?:'s|'re| is| are)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "contrast_framing",
        re.compile(
            r"\b(?:is|are)n(?:'|)t about " + _GAP + _WRAP + r"(?:it|they)(?:'s|'re| is| are) about\b",
            re.IGNORECASE,
        ),
    ),
    (
        "contrast_framing",
        # `rather` is mandatory: "not X, but rather Y" is the contrast tell,
        # while "not X, but Y" is ordinary English and fired on 97 of 103
        # corpus matches, this repo's own rule files among them.
        re.compile(r"\bnot " + _GAP + _WRAP + r"but rather\b", re.IGNORECASE),
    ),
    (
        "trailing_offer",
        re.compile(
            r"\b(?:want me to|would you like me to|i could also|let me know if you'd like"
            r"|shall i also)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "signposting",
        re.compile(
            r"(?:^|\n)\s*(?:>\s*|[-*+]\s+|\d+\.\s+)?"
            r"(?:Honestly,|Look,|Let's dive in|It's worth noting that|In today's landscape)",
        ),
    ),
    (
        "model_identity",
        re.compile(r"\bas an AI(?: language model| assistant)?\b|\bI'm just an AI\b", re.IGNORECASE),
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
    """Return the backticked tokens under the "Banned Vocabulary" heading.

    Stops at the next heading so the replacement examples below the list
    are not mistaken for entries.
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


def _blank_fenced_blocks(text: str) -> tuple[list[str], int | None]:
    """Return the lines of *text* with every fenced code block blanked out.

    Blanking rather than dropping keeps line numbers aligned, and the fence
    markers go too so their backticks cannot pair with an inline span. Also
    returns the line of a fence still open at EOF; everything after it went
    unscanned.
    """
    lines: list[str] = []
    fence: str | None = None
    opened_at: int | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        match = _FENCE.match(line)
        if fence is None:
            if match is None:
                lines.append(line)
                continue
            fence = match.group("fence")
            opened_at = number
            lines.append("")
            continue
        lines.append("")
        # CommonMark: a closing fence carries no info string. Accepting one
        # inverted open and close for the rest of the document, so fenced
        # code was linted as prose and real prose was silently skipped.
        if (
            match is not None
            and match.group("fence")[0] == fence[0]
            and len(match.group("fence")) >= len(fence)
            and not match.group("info").strip()
        ):
            fence = None
            opened_at = None
    return lines, opened_at


def _mask_inline_code(text: str) -> str:
    """Blank out inline code spans, preserving every column and newline.

    Runs over the whole document: masking line by line pairs the wrong
    backticks on a wrapped span and leaves quoted examples exposed.
    """
    return _INLINE_CODE.sub(
        lambda m: "".join(c if c == "\n" else " " for c in m.group(0)),
        text,
    )


@dataclass(frozen=True)
class Scan:
    """The result of one artifact scan, with the coverage behind it."""

    findings: list[Finding]
    examined: int
    total: int
    unterminated_fence_line: int | None


def _prose_lines(text: str) -> tuple[list[tuple[int, str]], str, int, int | None]:
    """Return prose lines, the masked document, the source line count, and
    any fence still open at EOF."""
    blanked, opened_at = _blank_fenced_blocks(text)
    masked = _mask_inline_code("\n".join(blanked))
    lines = [
        (number, line)
        for number, line in enumerate(masked.split("\n"), start=1)
        if line.strip()
    ]
    return lines, masked, len(blanked), opened_at


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
        for match in _TOKEN.finditer(line):
            before = line[match.start() - 1] if match.start() else ""
            after = line[match.end()] if match.end() < len(line) else ""
            if before in _NON_PROSE_NEIGHBORS or after in _NON_PROSE_NEIGHBORS:
                continue
            word = match.group(0).lower()
            if word.endswith("'s"):
                word = word[:-2]
            # A hyphenated compound still uses the word it is built from, so
            # `landscape-level` counts as `landscape`.
            parts = {word, *(p for p in re.split(r"[-']", word) if p)}
            hits = parts & banned
            if not hits:
                continue
            low = hits <= LOW_SIGNAL_WORDS
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


def _locate(offset: int, starts: list[int]) -> tuple[int, int]:
    """Map a document offset to a 1-indexed (line, column)."""
    index = bisect.bisect_right(starts, offset) - 1
    return index + 1, offset - starts[index] + 1


def _structural_findings(masked: str) -> list[Finding]:
    """Find Layer 2 tells across the whole masked document.

    Matching per line missed every tell straddling a hard wrap, the common
    case in prose wrapped near 80 columns.
    """
    starts = [0]
    for index, char in enumerate(masked):
        if char == "\n":
            starts.append(index + 1)

    findings: list[Finding] = []
    for kind, pattern in _STRUCTURAL_PATTERNS:
        for match in pattern.finditer(masked):
            offset = match.start()
            # A pattern anchored on (?:^|\n) consumes the newline itself.
            if match.group(0).startswith("\n"):
                offset += 1
            line, column = _locate(offset, starts)
            findings.append(
                Finding(
                    line=line,
                    column=column,
                    kind=kind,
                    severity=HIGH,
                    match=" ".join(match.group(0).split()),
                    note=_NOTES[kind],
                ),
            )
    return findings


def scan_prose(text: str, banned: set[str]) -> Scan:
    """Scan *text* and report both the findings and the coverage behind them.

    A run that read almost nothing must not look like a clean one, so the
    caller also gets the coverage (`.claude/rules/ci-scripts.md` MUST-12).
    """
    lines, masked, total, opened_at = _prose_lines(text)
    findings = _lexical_findings(lines, banned) + _structural_findings(masked)
    if opened_at is not None:
        findings.append(
            Finding(
                line=opened_at,
                column=1,
                kind=UNTERMINATED_FENCE,
                severity=HIGH,
                match="",
                note=(
                    f"fence never closes; lines {opened_at} to EOF went "
                    "unscanned, so this run cannot clear Layers 1-2"
                ),
            ),
        )
    return Scan(
        findings=sorted(findings, key=lambda f: (f.line, f.column, f.kind)),
        examined=len(lines),
        total=total,
        unterminated_fence_line=opened_at,
    )


def lint_prose(text: str, banned: set[str]) -> list[Finding]:
    """Return every Layer 1 and Layer 2 finding in *text*, in file order."""
    return scan_prose(text, banned).findings


def _read(name: str) -> str:
    if name == "-":
        return sys.stdin.read()
    return Path(name).read_text(encoding="utf-8")


def _emit_text(results: dict[str, Scan], rules_note: str | None) -> None:
    if rules_note:
        print(rules_note, file=sys.stderr)
    total_high = 0
    for name, scan in results.items():
        for finding in scan.findings:
            total_high += finding.severity == HIGH
            print(
                f"{name}:{finding.line}:{finding.column}: {finding.severity}: "
                f"{finding.kind}: {finding.match!r} ({finding.note})",
            )
    examined = sum(scan.examined for scan in results.values())
    source = sum(scan.total for scan in results.values())
    total = sum(len(scan.findings) for scan in results.values())
    # Name what was read, not just the verdict: a run that scanned almost
    # nothing must not read as a clean one.
    coverage = f"{examined} prose line(s) of {source} in {len(results)} file(s)"
    if not total:
        print(f"Layers 1-2 clean: 0 findings in {coverage}.")
    else:
        print(f"\n{total} finding(s), {total_high} high severity, in {coverage}")
    print("Layer 4 (emptiness gate) is still yours to run.")


def _resolve_banned_words(
    rules_arg: str | None,
) -> tuple[set[str], Path | None, str | None] | None:
    """Load the banned-word list, or None when the rules file is unreadable.

    A missing rule degrades to the dash and structural checks; only an
    unreadable one is an error.
    """
    rules_path = Path(rules_arg) if rules_arg else discover_rules_file()
    if rules_path is None:
        return set(), None, (
            "Warning: no voice rule found; running dash and structural checks only. "
            "Pass --rules PATH to enable the banned-word check."
        )
    try:
        banned = parse_banned_words(rules_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"Error: cannot read rules file {rules_path}: {exc}", file=sys.stderr)
        return None
    if not banned:
        return banned, rules_path, (
            f"Warning: no 'Banned Vocabulary' section in {rules_path}; "
            "running dash and structural checks only."
        )
    return banned, rules_path, None


def _emit_json(results: dict[str, Scan], rules_path: Path | None, banned: set[str]) -> None:
    """Print the machine-readable report."""
    print(
        json.dumps(
            {
                "rules_file": str(rules_path) if rules_path else None,
                "banned_word_count": len(banned),
                "files": {
                    name: {
                        "findings": [asdict(f) for f in scan.findings],
                        "examined_lines": scan.examined,
                        "source_lines": scan.total,
                        "unterminated_fence_line": scan.unterminated_fence_line,
                    }
                    for name, scan in results.items()
                },
                "high_severity_count": sum(
                    1 for scan in results.values() for f in scan.findings if f.severity == HIGH
                ),
            },
            indent=2,
            sort_keys=True,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Run prose-self-check Layers 1 and 2 over an artifact",
    )
    parser.add_argument("files", nargs="+", help="Files to check, or - for stdin")
    parser.add_argument("--rules", help="Path to the voice rule (default: auto-discover)")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    args = parser.parse_args(argv)

    resolved = _resolve_banned_words(args.rules)
    if resolved is None:
        return 2
    banned, rules_path, rules_note = resolved

    results: dict[str, Scan] = {}
    for name in args.files:
        try:
            text = _read(name)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"Error: cannot read {name}: {exc}", file=sys.stderr)
            return 2
        results[name] = scan_prose(text, banned)

    if args.json:
        _emit_json(results, rules_path, banned)
    else:
        _emit_text(results, rules_note)

    return 1 if any(f.severity == HIGH for s in results.values() for f in s.findings) else 0


if __name__ == "__main__":
    sys.exit(main())
