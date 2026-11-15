#!/usr/bin/env python3
"""Replay Cursor Bugbot learned-rule findings against this repository's own checks.

Each corpus row is a Cursor Bugbot finding the author fixed: a file, a line,
the commit Bugbot reviewed, and the rule it applied. For each row this reads
the file at the reviewed commit and asks two questions with no model call:

1. Baseline: would a check this repository ran at that time have flagged the
   line? The baseline is ``check_subprocess_encoding.py`` (scoped as it is,
   to ``scripts/``) plus ``ruff`` with the repository's own configuration.
2. Treatment: does ``scripts/validation/check_io_portability.py`` flag it?

A row counts as caught when the check reports a violation of the matching
kind within ``LINE_WINDOW`` lines of the Bugbot line. A negative control reads
the same file at the pull request's final head and counts rows where the
treatment finds no fewer violations of that rule than at the reviewed commit,
which means the author's fix did not remove what the checker flags.

Corpus: evals/third-party-review-gap/io-portability-corpus.json.

Exit codes: 0 ok, 2 config or corpus error.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_io_portability as treatment  # noqa: E402
import check_subprocess_encoding as legacy  # noqa: E402
from _adr_catch_rate_stats import wilson_interval  # noqa: E402

DEFAULT_CORPUS = "evals/third-party-review-gap/io-portability-corpus.json"
LINE_WINDOW = 3
RUFF_CODES_BY_RULE = {
    "file-text-encoding": {"PLW1514"},
    "subprocess-text-encoding": {"PLW1510", "PLW1514"},
    "unguarded-symlink": set(),
}


def git_show(commit: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=str(REPO_ROOT),
        timeout=60,
    )
    return result.stdout if result.returncode == 0 else None


def near(lines: list[int], target: int) -> bool:
    return any(abs(line - target) <= LINE_WINDOW for line in lines)


def legacy_lines(path: str, source: str) -> list[int]:
    """Lines the subprocess encoding gate flags, honoring its scripts/-only scope."""
    if not path.startswith("scripts/"):
        return []
    import ast

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[int] = legacy._violations_in_tree(tree, source)
    return found


def ruff_lines(path: str, source: str, codes: set[str]) -> list[int]:
    """Lines ruff flags under the repository configuration, filtered to ``codes``."""
    if not codes:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [
                "uv",
                "run",
                "--frozen",
                "ruff",
                "check",
                "--config",
                str(REPO_ROOT / "pyproject.toml"),
                "--output-format",
                "json",
                "--exit-zero",
                str(target),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            cwd=str(REPO_ROOT),
            timeout=120,
        )
    try:
        rows = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [r["location"]["row"] for r in rows if r.get("code") in codes]


def treatment_lines(path: str, source: str, rule: str) -> list[int]:
    """Every line a flagged call covers. Bugbot anchors some findings on the closing line."""
    return [
        line
        for v in treatment.scan_source(path, source)
        if v.rule == rule
        for line in range(v.line, max(v.line, v.end_line) + 1)
    ]


def evaluate(row: dict[str, Any]) -> dict[str, Any]:
    before = git_show(row["reviewed"], row["path"])
    if before is None:
        return {**row, "error": "file unreadable at reviewed commit"}
    rule = row["rule"]
    baseline = legacy_lines(row["path"], before) + ruff_lines(
        row["path"], before, RUFF_CODES_BY_RULE[rule]
    )
    caught = near(treatment_lines(row["path"], before, rule), row["line"])
    after = git_show(row["final_head"], row["path"])
    before_count = rule_count(row["path"], before, rule)
    after_count = None if after is None else rule_count(row["path"], after, rule)
    return {
        **row,
        "baseline_caught": near(baseline, row["line"]),
        "treatment_caught": caught,
        "rule_count_reviewed": before_count,
        "rule_count_final_head": after_count,
        # Line numbers drift between commits, so the control compares counts:
        # the author's fix should leave fewer violations of this rule in the file.
        "final_head_not_lower": after_count is not None and after_count >= before_count,
    }


def rule_count(path: str, source: str, rule: str) -> int:
    return sum(1 for v in treatment.scan_source(path, source) if v.rule == rule)


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    def cell(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
        hits = sum(1 for r in rows if r.get(key))
        low, high = wilson_interval(hits, len(rows)) if rows else (0.0, 0.0)
        return {"hits": hits, "n": len(rows), "ci": [round(low, 3), round(high, 3)]}

    scored = [r for r in results if "error" not in r]
    out: dict[str, Any] = {"errors": len(results) - len(scored)}
    for split in ("all", "derive", "heldout"):
        rows = [r for r in scored if split == "all" or r["split"] == split]
        out[split] = {
            "baseline": cell(rows, "baseline_caught"),
            "treatment": cell(rows, "treatment_caught"),
            "final_head_not_lower": cell(rows, "final_head_not_lower"),
        }
    for rule in sorted({r["rule"] for r in scored}):
        rows = [r for r in scored if r["rule"] == rule]
        out[rule] = {
            "baseline": cell(rows, "baseline_caught"),
            "treatment": cell(rows, "treatment_caught"),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", default=DEFAULT_CORPUS)
    parser.add_argument("--rows", type=Path, help="write per-row results as JSON here")
    parser.add_argument("--output", type=Path, help="write the summary JSON here")
    args = parser.parse_args(argv)
    try:
        corpus = json.loads((REPO_ROOT / args.corpus).read_text(encoding="utf-8"))
        rows = corpus["rows"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: cannot read corpus: {exc}", file=sys.stderr)
        return 2
    results = [evaluate(row) for row in rows]
    summary = summarize(results)
    if args.rows:
        args.rows.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8")
    if args.output:
        args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
