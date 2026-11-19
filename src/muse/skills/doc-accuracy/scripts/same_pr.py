"""Same-PR doc accuracy: catch prose that drifts from code changed in the same diff.

Activated by `doc_accuracy.py --same-pr --diff-base REF`. It reads the changed
hunks of every text file in the diff, not only documentation globs, and sorts
each changed line into prose (Markdown and `.tmpl` lines, Python docstrings and
comments, JSON and YAML string values) or code (with its enclosing symbol).

Three deterministic rules (`same_pr_rules.py`) emit findings that can fail the
gate: R1 exit-code sets, R2 enumeration subsets, R3 JSON key contents. Every other
changed prose line that looks like a verifiable claim goes to the checklist with
the code locations it was paired with, for the Phase 4 reviewer. Nothing that
looks checkable is dropped silently.

Artifacts: `same-pr-findings.json`, `same-pr-checklist.json`.

Exit codes belong to `doc_accuracy.py`: 0 no finding at or above the threshold,
10 a finding at or above it, 2 `--same-pr` without `--diff-base`, 3 git failed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from same_pr_rules import check_enumeration_subset, check_exit_codes, check_json_key
from same_pr_source import (
    CODE_SUFFIXES,
    DATA_SUFFIXES,
    PROSE_SUFFIXES,
    CodeIndex,
    CodeRegion,
    ProseLine,
    classify_file,
)

MAX_PAIRS = 6
MAX_FILE_BYTES = 1_000_000
SCANNED_SUFFIXES = PROSE_SUFFIXES | DATA_SUFFIXES | CODE_SUFFIXES
LIMITS = [
    "Only changed lines are read, and only code files changed in this diff are paired.",
    "A claim contradicted by an unchanged file, such as a rule in a sibling document, "
    "is not found here; the Phase 4 reviewer has to look for it.",
    "Prose in a changed file that no rule matches is listed, not judged.",
]

_COUNT_WORDS = (
    r"two|three|four|five|six|seven|eight|nine|ten|twice|"
    r"second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth"
)
_NUMBER_WORD = re.compile(rf"\b(?:{_COUNT_WORDS})\b", re.IGNORECASE)
_DIGITS = re.compile(r"(?<![\w#./:-])\d+(?![\w./-])")
_LEADING_COUNTER = re.compile(r"^\s*(?:\|\s*\d+\s*\||\d+[.)]\s|#+\s+\d+[.)]?\s)")
_QUANTIFIER = re.compile(
    r"\b(only|identical|every|never|always|exactly|none|same)\b", re.IGNORECASE
)
_BACKTICKED = re.compile(r"`([^`\s]{2,})`")
_VOCABULARY = {
    "exit": re.compile(r"\bexit(?:\s+codes?)?\b", re.IGNORECASE),
    "json": re.compile(r"\bjson\b", re.IGNORECASE),
    "raises": re.compile(r"\braises?\b", re.IGNORECASE),
    "returns": re.compile(r"\breturns?\b", re.IGNORECASE),
}
_TOKEN = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def claim_reasons(text: str) -> list[str]:
    """Why a prose line looks like a verifiable claim; empty when it does not."""
    body = _LEADING_COUNTER.sub("", text)
    reasons: list[str] = []
    if _NUMBER_WORD.search(body) or _DIGITS.search(body):
        reasons.append("number")
    reasons += [m.lower() for m in dict.fromkeys(_QUANTIFIER.findall(body))]
    reasons += [f"symbol:`{s}`" for s in dict.fromkeys(_BACKTICKED.findall(body))]
    reasons += [name for name, pattern in _VOCABULARY.items() if pattern.search(body)]
    return list(dict.fromkeys(reasons))


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text) if len(t) >= 3}


def _shared_prefix(a: str, b: str) -> int:
    count = 0
    for left, right in zip(a.split("/")[:-1], b.split("/")[:-1], strict=False):
        if left != right:
            break
        count += 1
    return count


def pair_code(prose: ProseLine, regions: dict[str, list[CodeRegion]]) -> list[dict[str, Any]]:
    """Code symbols changed in this diff: same file first, then by overlap and path closeness."""
    words = _tokens(prose.text)
    ranked = []
    for path, found in regions.items():
        close = _shared_prefix(prose.file, path)
        for region in found:
            overlap = len(words & _tokens(region.symbol))
            ranked.append(((path != prose.file, -overlap, -close, path, region.line), region))
    ranked.sort(key=lambda item: item[0])
    return [{"file": r.file, "line": r.line, "symbol": r.symbol} for _, r in ranked[:MAX_PAIRS]]


def _read_scannable(target: Path, rel: str, is_unsafe: Callable[[Path], bool]) -> str | None:
    path = target / rel
    if Path(rel).suffix.lower() not in SCANNED_SUFFIXES or is_unsafe(path):
        return None
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _proximity(prose_file: str, paths: list[str]) -> list[str]:
    return sorted(paths, key=lambda p: (-_shared_prefix(prose_file, p), p))


def _file_findings(
    rel: str,
    text: str,
    prose: list[ProseLine],
    index: CodeIndex,
) -> tuple[list[dict[str, Any]], dict[tuple[str, int], list[str]]]:
    """Findings for one file's prose, plus extra checklist reasons keyed by prose line."""
    findings = check_exit_codes(rel, text, {p.line for p in prose}, index)
    notes: dict[tuple[str, int], list[str]] = {}
    order = _proximity(rel, list(index.sources))
    for line in prose:
        found = check_enumeration_subset(line, index, order)
        r3, r3_notes = check_json_key(line, index)
        findings += found + r3
        if r3_notes:
            notes[(rel, line.line)] = r3_notes
    return findings, notes


def run_same_pr(
    target: Path,
    changed_files: set[str],
    ranges: dict[str, list[list[int]]],
    *,
    normalize: Callable[[str], str],
    is_unsafe: Callable[[Path], bool],
) -> dict[str, Any]:
    """Scan the changed hunks; return the findings and checklist documents."""
    texts: dict[str, str] = {}
    for rel in sorted(changed_files):
        text = _read_scannable(target, rel, is_unsafe)
        if text is not None:
            texts[rel] = text
    prose_by_file: dict[str, list[ProseLine]] = {}
    regions: dict[str, list[CodeRegion]] = {}
    code_lines = 0
    for rel, text in texts.items():
        prose, found, count = classify_file(rel, text, ranges.get(normalize(rel)))
        prose_by_file[rel], code_lines = prose, code_lines + count
        if found:
            regions[rel] = found
    index = CodeIndex(texts)
    findings: list[dict[str, Any]] = []
    notes: dict[tuple[str, int], list[str]] = {}
    for rel, prose in prose_by_file.items():
        file_findings, file_notes = _file_findings(rel, texts[rel], prose, index)
        findings += file_findings
        notes.update(file_notes)
    findings = _unique(findings)
    for number, finding in enumerate(findings, start=1):
        finding["id"] = f"same-pr-{number:04d}"
    flagged = {(f["prose"]["file"], f["prose"]["line"]) for f in findings}
    entries = _checklist(prose_by_file, regions, notes, flagged)
    examined = {
        "changed_files": len(changed_files),
        "scanned_files": len(texts),
        "skipped_files": len(changed_files) - len(texts),
        "prose_lines": sum(len(p) for p in prose_by_file.values()),
        "code_lines": code_lines,
    }
    return {
        "findings": {"status": "OK", "examined": examined, "findings": findings},
        "checklist": {"examined": examined, "limits": LIMITS, "entries": entries},
    }


def _unique(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    kept = []
    for finding in findings:
        key = json.dumps([finding["rule"], finding["prose"], finding["code"], finding["evidence"]])
        if key not in seen:
            seen.add(key)
            kept.append(finding)
    return kept


def _checklist(
    prose_by_file: dict[str, list[ProseLine]],
    regions: dict[str, list[CodeRegion]],
    notes: dict[tuple[str, int], list[str]],
    flagged: set[tuple[str, int]],
) -> list[dict[str, Any]]:
    entries = []
    for rel, prose in prose_by_file.items():
        for line in prose:
            reasons = [*claim_reasons(line.text), *notes.get((rel, line.line), [])]
            if reasons and (rel, line.line) not in flagged:
                entries.append(
                    {
                        "prose_file": rel,
                        "prose_line": line.line,
                        "text": line.text,
                        "reasons": reasons,
                        "pairs": pair_code(line, regions),
                    }
                )
    return entries


def write_artifacts(output_dir: Path, result: dict[str, Any]) -> None:
    for name, key in (
        ("same-pr-findings.json", "findings"),
        ("same-pr-checklist.json", "checklist"),
    ):
        (output_dir / name).write_text(json.dumps(result[key], indent=2), encoding="utf-8")


def fold_into_gate(
    gate: dict[str, Any],
    findings: list[dict[str, Any]],
    threshold: str,
    severity_order: dict[str, int],
) -> dict[str, Any]:
    """Add same-PR findings to a gate result; any at or above threshold makes it FAIL."""
    by_severity = dict(gate["by_severity"])
    blocking = gate["blocking_findings"]
    for finding in findings:
        sev = finding["severity"]
        by_severity[sev] = by_severity.get(sev, 0) + 1
        if severity_order.get(sev, 3) <= severity_order.get(threshold, 1):
            blocking += 1
    verdict = "FAIL" if blocking else gate["verdict"]
    return {
        **gate,
        "verdict": verdict,
        "blocking_findings": blocking,
        "total_findings": sum(by_severity.values()),
        "by_severity": by_severity,
        "same_pr_findings": len(findings),
    }


def summary_lines(result: dict[str, Any]) -> list[str]:
    findings = result["findings"]["findings"]
    by_rule: dict[str, int] = {}
    for finding in findings:
        by_rule[finding["rule"]] = by_rule.get(finding["rule"], 0) + 1
    rules = ", ".join(f"{rule}: {n}" for rule, n in sorted(by_rule.items())) or "none"
    seen = result["findings"]["examined"]
    return [
        f"Same-PR findings: {len(findings)} ({rules})",
        f"Same-PR checklist: {len(result['checklist']['entries'])} entries",
        f"Same-PR examined: {seen['scanned_files']} of {seen['changed_files']} changed files, "
        f"{seen['prose_lines']} prose lines, {seen['code_lines']} code lines",
    ]
