#!/usr/bin/env python3
"""Replay historical documentation findings through both author citation gates.

Each case uses its pinned PR commit and the PR base from GitHub.
Temporary worktrees and fetched refs are removed even when a check fails.
The checker code comes from this checkout; cited content comes from the case.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "validation"))
sys.path.insert(0, str(ROOT))

from check_citation_freshness import find_stale_citations  # noqa: E402
from citation_reverse_pass import find_reverse_stale_citations  # noqa: E402

CORPUS = ROOT / "evals/docs-review-catch-rate/citation_freshness/corpus.json"


def command(args: list[str], cwd: Path = ROOT) -> str:
    """Run a bounded command and retain its diagnostics on failure."""
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=180,
    )
    if result.returncode:
        raise RuntimeError(f"{args[0:3]}: {result.stderr[-3000:]}")
    return result.stdout.strip()


def check(root: Path, base: str) -> tuple[list[dict[str, Any]], str]:
    """Run the same two entry functions the pre-PR gate calls."""
    output = io.StringIO()
    findings: list[dict[str, Any]] = []
    with contextlib.redirect_stdout(output):
        for name, checker in (
            ("forward", find_stale_citations),
            ("reverse", find_reverse_stale_citations),
        ):
            rows = checker(root, base)
            if rows is None:
                raise RuntimeError(f"{name} gate could not read the case repository")
            findings.extend(
                dict(asdict(row), gate=name, defect_class="stale-citation") for row in rows
            )
    return findings, output.getvalue()


def matches(case: dict[str, Any], finding: dict[str, Any]) -> bool:
    """Match the pinned location and defect class without a model judge."""
    return (
        case.get("file") == finding["citing_file"]
        and case.get("defect_class") == finding["defect_class"]
        and abs(case.get("line", -100) - finding["citing_line"]) <= 3
    )


def replay(case: dict[str, Any], repository: str, run_id: str) -> dict[str, Any]:
    """Fetch a PR, check its pinned commit, and remove temporary state."""
    pr = str(case["pr"])
    ref = f"refs/docs-citation-replay/{run_id}/{pr}"
    parent = Path.home() / "worktrees" / ROOT.parent.name
    parent.mkdir(parents=True, exist_ok=True)
    worktree = parent / f"citation-replay-{run_id}-{pr}"
    added = False
    try:
        metadata = json.loads(
            command(
                [
                    "gh",
                    "pr",
                    "view",
                    pr,
                    "--repo",
                    repository,
                    "--json",
                    "baseRefOid,headRefOid",
                ]
            )
        )
        command(["git", "fetch", "--no-tags", "origin", f"pull/{pr}/head:{ref}"])
        sha = command(["git", "rev-parse", f"{case.get('sha') or ref}^{{commit}}"])
        base_ref = metadata["baseRefOid"]
        # A shallow checkout may not have the base object yet.
        probe = subprocess.run(
            ["git", "cat-file", "-e", f"{base_ref}^{{commit}}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if probe.returncode:
            command(["git", "fetch", "--no-tags", "origin", base_ref])
        base = command(["git", "merge-base", sha, base_ref])
        command(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "worktree",
                "add",
                "--detach",
                str(worktree),
                sha,
            ]
        )
        added = True
        findings, output = check(worktree, base)
        return dict(
            case,
            resolved_sha=sha,
            pr_base=base_ref,
            merge_base=base,
            findings=findings,
            output=output,
            caught=any(matches(case, row) for row in findings),
            false_positives=len(findings) if case["kind"] == "negative" else 0,
        )
    finally:
        if added:
            command(["git", "worktree", "remove", str(worktree)])
        command(["git", "update-ref", "-d", ref])


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Score every finding on negatives, including advisory findings."""
    positives = [r for r in rows if r["kind"] == "positive" and r["scope"] == "automatic"]
    negatives = [r for r in rows if r["kind"] == "negative"]
    manual = [dict(id=r["id"], why=r["why"]) for r in rows if r["scope"] == "manual"]
    caught = sum(bool(r.get("caught")) for r in positives)
    fp = sum(r.get("false_positives", 0) for r in negatives)
    errors = sum("error" in r for r in rows)
    return dict(
        caught=caught,
        in_scope=len(positives),
        false_positives=fp,
        negatives=len(negatives),
        manual=manual,
        errors=errors,
        passed=caught == len(positives) and fp == 0 and errors == 0 and len(negatives) == 12,
        score_line=(
            f"caught {caught} of {len(positives)} in-scope positives, "
            f"{fp} FP on {len(negatives)} negatives, {len(manual)} manual with reasons"
        ),
    )


def main(argv: list[str] | None = None) -> int:
    """Run all cases, or selected cases during development."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args(argv)
    corpus_bytes = args.corpus.read_bytes()
    corpus = json.loads(corpus_bytes)
    rows = []
    run_id = uuid.uuid4().hex[:12]
    for case in corpus["cases"]:
        if args.case and case["id"] not in args.case:
            continue
        try:
            row = replay(case, corpus["repository"], run_id)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            row = dict(case, error=str(error))
        rows.append(row)
        print(
            json.dumps(
                dict(
                    id=case["id"],
                    caught=row.get("caught"),
                    findings=len(row.get("findings", [])),
                    error=row.get("error"),
                )
            ),
            flush=True,
        )
    summary = score(rows)
    report = dict(
        schema_version=1,
        date=datetime.now(UTC).isoformat(),
        checker_sha=command(["git", "rev-parse", "HEAD"]),
        checker_files={
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "scripts/validation").glob("citation_*.py")
        }
        | {
            "check_citation_freshness.py": hashlib.sha256(
                (ROOT / "scripts/validation/check_citation_freshness.py").read_bytes()
            ).hexdigest()
        },
        corpus_sha256=hashlib.sha256(corpus_bytes).hexdigest(),
        summary=summary,
        cases=rows,
    )
    output = args.output or args.corpus.parent / "results" / "2026-11-19.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(summary["score_line"])
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
