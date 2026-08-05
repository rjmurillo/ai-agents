#!/usr/bin/env python3
"""Grade CodeQL SARIF findings and gate the merge on critical ones.

Extracted from ``.github/workflows/codeql-analysis.yml`` under ADR-006 (no
logic in workflow YAML). Issue #3529.

The step this replaces reads every SARIF file produced by the matrix legs,
counts findings by severity, writes a job summary, and fails the job when a
critical finding is present.

One behavior deliberately changed: issue #3926. The PowerShell original
compared ``security-severity`` with ``-ge 9.0``. SARIF encodes that property
as a JSON string, and PowerShell coerces the right operand to the left
operand's type, so the test was the string comparison ``"10.0" -ge "9"``,
which is false. A CVSS 10.0 finding, the maximum possible, was graded HIGH
and merged. This parses the value as a float, so 10.0 blocks like 9.3 does.

The original's ``-ge 7.0`` branch was dead: its body was byte-identical to the
``else`` branch. Only the critical threshold has ever been observable, so only
that threshold survives here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_CRITICAL_SEVERITY = 9.0


@dataclass
class Tally:
    """Counts and log lines produced by grading a set of SARIF files."""

    critical: int = 0
    high: int = 0
    total: int = 0
    lines: list[str] = field(default_factory=list)


def _severity(rules: list[dict[str, object]], rule_id: object) -> float | None:
    """Return the numeric ``security-severity`` for a rule id, if it has one."""
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("id") != rule_id:
            continue
        properties = rule.get("properties")
        if not isinstance(properties, dict):
            return None
        raw = properties.get("security-severity")
        # A bool is an int in Python; a boolean severity is nonsense, not 0.0/1.0.
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            return None
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _message(result: dict[str, object]) -> str:
    message = result.get("message")
    if isinstance(message, dict):
        text = message.get("text")
        if isinstance(text, str):
            return text
    return ""


def _dig(container: object, *keys: str) -> object:
    """Walk nested mappings, returning None as soon as a level is not a mapping."""
    for key in keys:
        if not isinstance(container, dict):
            return None
        container = container.get(key)
    return container


def grade(documents: list[tuple[str, dict[str, object]]]) -> Tally:
    """Count findings by severity across parsed SARIF documents."""
    tally = Tally()
    for name, sarif in documents:
        tally.lines.append(f"Analyzing: {name}")
        runs = sarif.get("runs")
        if not isinstance(runs, list):
            continue
        for run in runs:
            raw_rules = _dig(run, "tool", "driver", "rules")
            rules = (
                [r for r in raw_rules if isinstance(r, dict)] if isinstance(raw_rules, list) else []
            )
            results = run.get("results") if isinstance(run, dict) else None
            if not isinstance(results, list):
                continue
            for result in results:
                if not isinstance(result, dict):
                    continue
                tally.total += 1
                level = result.get("level")
                rule_id = result.get("ruleId")
                if level == "error":
                    severity = _severity(rules, rule_id)
                    if severity is not None and severity >= _CRITICAL_SEVERITY:
                        tally.critical += 1
                        tally.lines.append(f"  CRITICAL: {rule_id} - {_message(result)}")
                    else:
                        tally.high += 1
                        tally.lines.append(f"  HIGH: {rule_id} - {_message(result)}")
                elif level == "warning":
                    tally.lines.append(f"  MEDIUM: {rule_id} - {_message(result)}")
    return tally


def render_summary(tally: Tally) -> str:
    """Render the job summary markdown."""
    verdict = "> [!TIP]\n> No critical or high severity findings.\n"
    if tally.critical > 0:
        verdict = "> [!CAUTION]\n> Critical security findings detected! Merge blocked.\n"
    elif tally.high > 0:
        verdict = "> [!WARNING]\n> High severity findings detected. Review before merging.\n"
    return (
        "## CodeQL Analysis Summary\n\n"
        "| Severity | Count |\n"
        "|----------|-------|\n"
        f"| Critical | {tally.critical} |\n"
        f"| High | {tally.high} |\n"
        f"| **Total** | **{tally.total}** |\n\n"
        f"{verdict}"
    )


def load_documents(sarif_dir: Path) -> list[tuple[str, dict[str, object]]]:
    """Read every SARIF file under a directory, skipping unparseable ones."""
    documents: list[tuple[str, dict[str, object]]] = []
    for path in sorted(sarif_dir.rglob("*.sarif")):
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"::warning::Could not parse {path.name}: {exc}")
            continue
        if isinstance(parsed, dict):
            documents.append((path.name, parsed))
    return documents


def find_sarif_files(sarif_dir: Path) -> list[Path]:
    """Find SARIF files under a directory."""
    if not sarif_dir.is_dir():
        return []
    return sorted(sarif_dir.rglob("*.sarif"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sarif-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    sarif_files = find_sarif_files(args.sarif_dir)
    if not sarif_files:
        print("No SARIF files found - analysis may have failed")
        return 1

    documents = load_documents(args.sarif_dir)
    if len(documents) != len(sarif_files):
        print("::error::One or more SARIF files could not be parsed")
        return 1

    tally = grade(documents)
    for line in tally.lines:
        print(line)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as handle:
            handle.write(render_summary(tally))

    if tally.critical > 0:
        print(
            f"::error::CodeQL analysis detected {tally.critical} critical "
            "security findings. Merge blocked."
        )
        return 1

    print("")
    print(
        f"CodeQL analysis complete: {tally.total} findings "
        f"({tally.critical} critical, {tally.high} high)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
