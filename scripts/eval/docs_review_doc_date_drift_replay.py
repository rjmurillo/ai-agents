#!/usr/bin/env python3
"""Replay the doc-date-drift gate on pinned PR revisions, without model scoring.

Each case fetches its pull ref and checks out its pinned revision.
The current validator reads that worktree with normal pre-PR diff scope.
Temporary worktrees live outside the clone and are removed after each case.
Temporary refs are deleted even when a scan fails. Exit codes: 0 pass,
1 missed positives or false positives, 2 external or configuration errors.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.validation.check_doc_date_drift import find_doc_date_drift  # noqa: E402

CORPUS = ROOT / "evals/docs-review-catch-rate/doc_date_drift/corpus.json"


def plain_env(source: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment that cannot colorize captured JSON."""
    env = dict(os.environ if source is None else source)
    env["NO_COLOR"] = "1"
    env["GH_NO_COLOR"] = "1"
    env.pop("GH_FORCE_TTY", None)
    env.pop("CLICOLOR_FORCE", None)
    return env


@functools.cache
def _gh_accepts_color_never() -> bool:
    """Return whether this gh accepts a global --color flag."""
    try:
        result = subprocess.run(
            ["gh", "pr", "view", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env=plain_env(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "--color" in f"{result.stdout}\n{result.stderr}"


def _argv(args: list[str]) -> list[str]:
    """Pass --color=never only when the command documents that flag."""
    if args and args[0] == "gh" and _gh_accepts_color_never():
        return ["gh", "--color=never", *args[1:]]
    return list(args)


def command(root: Path, args: list[str]) -> str:
    """Run one bounded command; include stderr in a failure."""
    result = subprocess.run(
        _argv(args),
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        env=plain_env(),
    )
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {result.stderr[-2000:]}")
    return result.stdout.strip()


def matches(expected: dict[str, Any], finding: dict[str, Any], tolerance: int = 3) -> bool:
    """Match the defect class and either reported source location."""
    if expected["rule"] != finding["rule"]:
        return False
    locations = ((finding["path"], finding["line"]), (finding["other_path"], finding["other_line"]))
    return any(
        path == expected["path"] and abs(line - expected["line"]) <= tolerance
        for path, line in locations
    )


def score(cases: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Require every expected positive location and count every negative finding."""
    indexed = {r["id"]: r for r in rows}
    positives = [c for c in cases if c["kind"] == "positive" and c["scope"] == "automatic"]
    negatives = [c for c in cases if c["kind"] == "negative"]
    manual = [c for c in cases if c["scope"] == "manual"]
    if any(not c.get("why", "").strip() for c in manual):
        raise ValueError("Every manual case needs a reason.")
    caught = sum(
        all(any(matches(e, f) for f in indexed[c["id"]]["findings"]) for e in c["expected"])
        for c in positives
    )
    false_positives = sum(len(indexed[c["id"]]["findings"]) for c in negatives)
    return {
        "caught": caught,
        "in_scope_positives": len(positives),
        "false_positives": false_positives,
        "negatives": len(negatives),
        "manual": len(manual),
        "recall": caught / len(positives) if positives else None,
        "passed": caught == len(positives) and false_positives == 0,
        "score_line": f"caught {caught} of {len(positives)} in-scope positives, "
        f"{false_positives} FP on {len(negatives)} negatives, "
        f"{len(manual)} manual with reasons",
    }


def replay(root: Path, repository: str, case: dict[str, Any]) -> dict[str, Any]:
    """Run the current gate at one historical HEAD and clean up its checkout."""
    metadata = json.loads(
        command(
            root,
            ["gh", "pr", "view", str(case["pr"]), "--repo", repository, "--json", "baseRefOid"],
        )
    )
    if metadata["baseRefOid"] != case["baseRefOid"]:
        raise ValueError(f"{case['id']}: baseRefOid changed; inspect before repinning.")
    ref = f"refs/doc-date-drift-replay/{uuid.uuid4().hex}"
    worktree_parent = Path.home() / "worktrees" / "ai-agents"
    worktree_parent.mkdir(parents=True, exist_ok=True)
    worktree = Path(tempfile.mkdtemp(prefix="doc-date-replay-", dir=worktree_parent))
    registered = False
    try:
        command(
            root,
            ["git", "fetch", "--quiet", "--no-tags", "origin", f"pull/{case['pr']}/head:{ref}"],
        )
        for sha in (case["sha"], case["baseRefOid"]):
            known = subprocess.run(
                ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                cwd=root,
                capture_output=True,
                timeout=30,
                env=plain_env(),
            )
            if known.returncode:
                command(root, ["git", "fetch", "--quiet", "--no-tags", "origin", sha])
        base = command(root, ["git", "merge-base", case["sha"], case["baseRefOid"]])
        command(
            root,
            [
                "git",
                "worktree",
                "add",
                "--quiet",
                "--detach",
                str(worktree),
                case["sha"],
            ],
        )
        registered = True
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            outcome = find_doc_date_drift(worktree, base)
        if outcome is None:
            raise RuntimeError(f"{case['id']}: validator could not read historical tree")
        findings, scope, lines, files = outcome
        return {
            "id": case["id"],
            "pr": case["pr"],
            "sha": case["sha"],
            "baseRefOid": case["baseRefOid"],
            "merge_base": base,
            "scope": scope,
            "examined_lines": lines,
            "examined_files": files,
            "findings": [asdict(f) for f in findings],
        }
    finally:
        try:
            if registered:
                command(root, ["git", "worktree", "remove", str(worktree)])
            elif worktree.is_dir():
                worktree.rmdir()
        finally:
            command(root, ["git", "update-ref", "-d", ref])


def main(argv: list[str] | None = None) -> int:
    """Write a reproducible receipt and print the deterministic score."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", action="append", help="Replay selected case IDs for diagnosis.")
    args = parser.parse_args(argv)
    try:
        payload = args.corpus.read_bytes()
        corpus = json.loads(payload)
        cases = [c for c in corpus["cases"] if not args.case or c["id"] in args.case]
        if not cases:
            raise ValueError("No replay cases selected.")
        rows = []
        for case in cases:
            row = replay(ROOT, corpus["repository"], case)
            rows.append(row)
            print(f"{case['id']}: {len(row['findings'])} finding(s)", flush=True)
        summary = score(cases, rows)
        sources = ["check_doc_date_drift.py", "doc_date_claims.py", "doc_date_adr.py"]
        receipt = {
            "schema_version": 1,
            "recorded_at": datetime.now(UTC).isoformat(),
            "corpus_sha256": hashlib.sha256(payload).hexdigest(),
            "validator_sha256": {
                name: hashlib.sha256((ROOT / "scripts/validation" / name).read_bytes()).hexdigest()
                for name in sources
            },
            "summary": summary,
            "cases": rows,
        }
        output = args.output or args.corpus.parent / "results" / f"{datetime.now(UTC).date()}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print(summary["score_line"])
        return 0 if summary["passed"] else 1
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"doc-date-drift replay: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
