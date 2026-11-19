"""Replay historical documentation findings through the author's same-PR command."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "evals/docs-review-catch-rate/same-pr/corpus.json"
CHECK = ROOT / "src/claude/skills/doc-accuracy/scripts/doc_accuracy.py"


def checker_hashes() -> dict[str, str]:
    """Bind results to the exact detector bytes, including uncommitted edits."""
    paths = [CHECK, CHECK.with_name("same_pr.py"), ROOT / "scripts/validation/nl_cardinality.py"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def command(args: list[str], cwd: Path = ROOT) -> str:
    """Run a bounded command, preserving failures for the replay receipt."""
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{args[:3]}: {result.stderr[-1500:]}")
    return result.stdout.strip()


def matches(expected: dict[str, Any], finding: dict[str, Any]) -> bool:
    """Match file, defect class, and a line within three of the corpus line."""
    prose = finding["prose"]
    checks = (
        prose["file"] == expected["file"],
        finding["rule"] == expected["class"],
        abs(int(prose["line"]) - int(expected["line"])) <= 3,
    )
    return all(item is True for item in checks)


def replay(case: dict[str, Any], run_id: str, worktree_root: Path, output: Path) -> dict[str, Any]:
    """Fetch one PR, resolve its historical base, and remove owned state afterward."""
    pr = case["pr"]
    ref = f"refs/doc-accuracy-replay/{run_id}/{pr}"
    worktree = worktree_root / f"doc-accuracy-replay-{run_id}-{pr}"
    added = False
    try:
        command(["git", "fetch", "--no-write-fetch-head", "origin", f"pull/{pr}/head:{ref}"])
        metadata = json.loads(
            command(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr),
                    "--repo",
                    "rjmurillo/ai-agents",
                    "--json",
                    "baseRefOid,headRefOid,url",
                ]
            )
        )
        sha = command(["git", "rev-parse", f"{case.get('sha') or ref}^{{commit}}"])
        base_oid = metadata["baseRefOid"]
        command(["git", "fetch", "--no-write-fetch-head", "origin", base_oid])
        base = command(["git", "merge-base", sha, base_oid])
        command(["git", "worktree", "add", "--detach", str(worktree), sha])
        added = True
        artifacts = output / case["id"]
        artifacts.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                sys.executable,
                str(CHECK),
                "--target",
                str(worktree),
                "--same-pr",
                "--diff-base",
                base,
                "--phases",
                "1",
                "--format",
                "summary",
                "--output-dir",
                str(artifacts),
            ],
            cwd=worktree,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
        if result.returncode not in (0, 10):
            raise RuntimeError(f"Check exited {result.returncode}: {result.stderr[-1500:]}")
        findings = json.loads((artifacts / "same-pr-findings.json").read_text(encoding="utf-8"))[
            "findings"
        ]
        checklist = json.loads((artifacts / "same-pr-checklist.json").read_text(encoding="utf-8"))[
            "entries"
        ]
        expected = case.get("expected", [])
        caught = [any(matches(e, f) for f in findings) for e in expected]
        return {
            "id": case["id"],
            "pr": pr,
            "sha": sha,
            "baseRefOid": base_oid,
            "merge_base": base,
            "scope": case["scope"],
            "why": case.get("why"),
            "manual_claims": case.get("manual_claims", []),
            "expected": expected,
            "caught": caught,
            "findings_count": len(findings),
            "checklist_count": len(checklist),
            "matched": [
                {
                    "file": finding["prose"]["file"],
                    "line": finding["prose"]["line"],
                    "rule": finding["rule"],
                }
                for finding in findings
                if any(matches(item, finding) for item in expected)
            ],
        }
    finally:
        if added:
            # The check writes outside this detached checkout. No author files change.
            command(["git", "worktree", "remove", str(worktree)])
        command(["git", "update-ref", "-d", ref])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="Run selected corpus IDs.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--worktree-root",
        type=Path,
        default=Path.home() / "worktrees/ai-agents",
    )
    args = parser.parse_args()
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    cases = [c for c in corpus["cases"] if not args.case or c["id"] in args.case]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    artifacts = ROOT / ".project-toolkit/scratch" / f"same-pr-replay-{uuid.uuid4().hex[:10]}"
    run_id = uuid.uuid4().hex[:10]
    results = []
    hashes = checker_hashes()
    for case in cases:
        row = replay(case, run_id, args.worktree_root, artifacts)
        results.append(row)
        print(
            f"{row['id']}: {row['caught']}, {row['findings_count']} findings, "
            f"{row['checklist_count']} checklist entries",
            flush=True,
        )
    positives = [r for r in results if r["scope"] == "automatic"]
    negatives = [r for r in results if r["scope"] == "negative"]
    manual = [r for r in results if r["scope"] == "manual"]
    manual_count = len(manual) + sum(len(r["manual_claims"]) for r in results)
    total = sum(len(r["caught"]) for r in positives)
    caught = sum(sum(r["caught"]) for r in positives)
    fp = sum(r["findings_count"] for r in negatives)
    score = (
        f"caught {caught} of {total} in-scope positives, {fp} FP on "
        f"{len(negatives)} negatives, {manual_count} manual with reasons"
    )
    receipt = {
        "schema_version": 1,
        "date": datetime.now(UTC).isoformat(),
        "checker_head": command(["git", "rev-parse", "HEAD"]),
        "checker_sha256": hashes,
        "checker_diff": command(["git", "diff", "--stat", "--", str(CHECK.parent)]),
        "score": score,
        "passed": caught == total and fp == 0,
        "results": results,
    }
    if hashes != checker_hashes():
        raise RuntimeError("Detector files changed during replay; rerun against stable bytes.")
    args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(score)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
