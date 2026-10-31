#!/usr/bin/env python3
"""Print the headline numbers of the read-only diagnostics instruments as JSON.

Runs the description budget, skill size, orphan-ref scan, and golden-principles scan,
then prints their counts with the HEAD SHA and the ISO date. It never runs
`build_all.py --check`, which rewrites build/audit/GENERATION-AUDIT.md.

Exit codes: 0 every instrument produced numbers, 1 an instrument ran but its output
could not be read, 2 bad arguments or not a repository, 3 git or an instrument failed to start.
The snapshot records a baseline, it does not gate one: an instrument's own nonzero exit
(a scan that found violations) is kept in that instrument's `exit` field and its name is
listed under `failing`, while the snapshot itself still exits 0.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SK = ".claude/skills"
INSTRUMENT_ARGV: dict[str, list[str]] = {
    "description_budget": [
        "uv",
        "run",
        "python",
        "./scripts/skill_description_budget.py",
        "--output-format",
        "json",
    ],
    "skill_size": ["uv", "run", "python", "./scripts/validation/skill_size.py"],
    "orphan_refs": ["python3", f"{SK}/orphan-ref-validator/scripts/scan.py"],
    "golden_principles": [
        "python3",
        f"{SK}/golden-principles/scripts/scan_principles.py",
        "--format",
        "json",
    ],
}


class StartError(Exception):
    """An external command could not be started or timed out."""


def _run(argv: list[str], repo: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StartError(f"{argv[0]}: {exc}") from exc


def _description_budget(out: str) -> dict[str, Any]:
    d = json.loads(out)
    return {
        "skills": d["skills"],
        "total_chars": d["total_chars"],
        "total_tokens_est": d["total_tokens_est"],
    }


def _skill_size(out: str) -> dict[str, Any]:
    def grab(label: str) -> int:
        m = re.search(rf"^\s*{label}:\s+(\d+)", out, re.M)
        if m is None:
            raise ValueError(f"missing '{label}' line")
        return int(m.group(1))

    limit = re.search(r"Limit:\s+(\d+) lines / (\d+) bytes", out)
    if limit is None:
        raise ValueError("missing 'Limit' line")
    return {
        "skills": grab("Passed") + grab("Failed"),
        "warnings": grab("Warnings"),
        "failed": grab("Failed"),
        "line_limit": int(limit.group(1)),
        "byte_limit": int(limit.group(2)),
    }


def _orphan_refs(out: str) -> dict[str, Any]:
    marker = out.rfind("VERDICT:")
    if marker < 0:
        raise ValueError("missing VERDICT line")
    counts = json.loads(out[:marker])["Data"]["counts"]
    return {
        "files_scanned": counts["files_scanned"],
        "refs_checked": counts["refs_checked"],
        "findings_total": counts["findings_total"],
        "directive_suppressed": counts["directive_suppressed"],
        "verdict": out[marker:].split()[1],
    }


def _golden_principles(out: str) -> dict[str, Any]:
    d = json.loads(out)
    return {
        "files_scanned": d["files_scanned"],
        "errors": d["error_count"],
        "warnings": d["warning_count"],
    }


PARSERS = {
    "description_budget": _description_budget,
    "skill_size": _skill_size,
    "orphan_refs": _orphan_refs,
    "golden_principles": _golden_principles,
}


def snapshot(repo: Path) -> tuple[dict[str, Any], int]:
    head = _run(["git", "rev-parse", "--short=9", "HEAD"], repo)
    if head.returncode != 0:
        raise StartError(f"git rev-parse failed: {head.stderr.strip()}")
    result: dict[str, Any] = {
        "head": head.stdout.strip(),
        "date": datetime.date.today().isoformat(),
        "instruments": {},
    }
    unreadable: list[str] = []
    for name, argv in INSTRUMENT_ARGV.items():
        proc = _run(argv, repo)
        try:
            entry = PARSERS[name](proc.stdout)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            entry = {"error": f"unreadable output: {exc}"}
            unreadable.append(name)
        entry["exit"] = proc.returncode
        result["instruments"][name] = entry
    result["examined"] = len(INSTRUMENT_ARGV)
    result["unreadable"] = unreadable
    result["failing"] = [
        name for name, entry in result["instruments"].items() if entry["exit"] != 0
    ]
    return result, (1 if unreadable else 0)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", default=".", help="repository root (default: .)")
    a = p.parse_args(argv)
    repo = Path(a.repo).resolve()
    if not (repo / ".git").exists():
        print(json.dumps({"error": f"not a git repository: {repo}"}), file=sys.stderr)
        return 2
    try:
        result, code = snapshot(repo)
    except StartError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 3
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
