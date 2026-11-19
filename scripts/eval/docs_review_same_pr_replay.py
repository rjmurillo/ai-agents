"""Replay historical documentation findings through the author's same-PR command."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "evals/docs-review-catch-rate/same-pr/corpus.json"
CHECK = ROOT / "src/claude/skills/doc-accuracy/scripts/doc_accuracy.py"
_WORKTREES = Path.home() / "worktrees/ai-agents"
_SHA = re.compile(r"[0-9a-fA-F]{7,40}")
_PR = re.compile(r"[1-9][0-9]{0,9}")
_TOKEN = re.compile(r"[A-Za-z0-9]{1,40}")
_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,40}")


def checker_hashes() -> dict[str, str]:
    """Bind results to the exact detector bytes, including uncommitted edits."""
    paths = [CHECK, CHECK.with_name("same_pr.py"), ROOT / "scripts/validation/nl_cardinality.py"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def git_sha(value: object) -> str:
    """Return a hex revision, rejecting option-shaped git arguments."""
    text = str(value)
    if _SHA.fullmatch(text) is None:
        raise ValueError(f"refusing non-hex revision {text!r}")
    return text


def pr_number(value: object) -> str:
    """Return a decimal pull request number with no leading zero."""
    text = str(value)
    if _PR.fullmatch(text) is None:
        raise ValueError(f"refusing pull request number {text!r}")
    return str(int(text))


def ref_token(value: object) -> str:
    """Return the disposable ref token. Slashes and flags are rejected."""
    text = str(value)
    if _TOKEN.fullmatch(text) is None:
        raise ValueError(f"refusing ref token {text!r}")
    return text


def case_id(value: object) -> str:
    """Return a corpus case id. Slashes and leading dashes are rejected."""
    text = str(value)
    if _CASE_ID.fullmatch(text) is None:
        raise ValueError(f"refusing case id {text!r}")
    return text


def command(cwd: Path, *argv: str) -> str:
    """Run one list-form command and return its stdout.

    shell stays off. Dynamic tokens must already be git_sha, pr_number,
    ref_token, or case_id results. shlex.quote would break this form.
    """
    result = subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"{argv[0]} exited {result.returncode}: {result.stderr[-1500:]}")
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


def replay(case: dict[str, Any], run_id: str, output: Path) -> dict[str, Any]:
    """Fetch one PR, resolve its historical base, and remove owned state afterward."""
    number = pr_number(case["pr"])
    token = ref_token(run_id)
    pinned = git_sha(case["sha"]) if str(case.get("sha") or "") else ""
    identity = case_id(case["id"])
    ref = f"refs/doc-accuracy-replay/{token}/{number}"
    worktree = _WORKTREES / f"doc-accuracy-replay-{token}-{number}"
    added = False
    try:
        command(
            ROOT, "git", "fetch", "--no-write-fetch-head", "origin", f"pull/{number}/head:{ref}"
        )
        metadata = json.loads(
            command(
                ROOT,
                "gh",
                "pr",
                "view",
                number,
                "--repo",
                "rjmurillo/ai-agents",
                "--json",
                "baseRefOid,headRefOid,url",
            )
        )
        revision = f"{pinned}^{{commit}}" if pinned else f"{ref}^{{commit}}"
        sha = git_sha(command(ROOT, "git", "rev-parse", "--verify", revision))
        base_oid = git_sha(metadata["baseRefOid"])
        command(ROOT, "git", "fetch", "--no-write-fetch-head", "origin", base_oid)
        base = git_sha(command(ROOT, "git", "merge-base", sha, base_oid))
        command(ROOT, "git", "worktree", "add", "--detach", str(worktree), sha)
        added = True
        artifacts = output / identity
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
        row = {
            "id": identity,
            "pr": int(number),
            "sha": sha,
            "baseRefOid": base_oid,
            "merge_base": base,
            "scope": case["scope"],
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
        # Empty fields stay off the receipt so it remains under the 500 line ceiling.
        if case.get("why"):
            row["why"] = case["why"]
        if case.get("manual_claims"):
            row["manual_claims"] = case["manual_claims"]
        return row
    finally:
        if added:
            # The check writes outside this detached checkout. No author files change.
            command(ROOT, "git", "worktree", "remove", str(worktree))
        command(ROOT, "git", "update-ref", "-d", ref)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="Run selected corpus IDs.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # The committed corpus is the only case input. A path flag would taint
    # every git argument built from those cases.
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    selected = {case_id(item) for item in args.case} if args.case else set()
    cases = [c for c in corpus["cases"] if not selected or c["id"] in selected]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    artifacts = ROOT / ".project-toolkit/scratch" / f"same-pr-replay-{uuid.uuid4().hex[:10]}"
    run_id = ref_token(uuid.uuid4().hex[:10])
    results = []
    hashes = checker_hashes()
    for case in cases:
        row = replay(case, run_id, artifacts)
        results.append(row)
        print(
            f"{row['id']}: {row['caught']}, {row['findings_count']} findings, "
            f"{row['checklist_count']} checklist entries",
            flush=True,
        )
    positives = [r for r in results if r["scope"] == "automatic"]
    negatives = [r for r in results if r["scope"] == "negative"]
    manual = [r for r in results if r["scope"] == "manual"]
    manual_count = len(manual) + sum(len(r.get("manual_claims", [])) for r in results)
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
        "checker_head": command(ROOT, "git", "rev-parse", "HEAD"),
        "checker_sha256": hashes,
        "checker_diff": command(ROOT, "git", "diff", "--stat", "--", str(CHECK.parent)),
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
