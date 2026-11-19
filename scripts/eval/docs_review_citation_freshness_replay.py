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
import os
import re
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
_SHA = re.compile(r"[0-9a-fA-F]{7,40}")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_PR = re.compile(r"[1-9][0-9]{0,9}")
_TOKEN = re.compile(r"[A-Za-z0-9]{1,40}")


def git_sha(value: object) -> str:
    """Return a hex revision, or refuse anything option-shaped."""
    text = str(value)
    if _SHA.fullmatch(text) is None:
        raise ValueError(f"refusing non-hex revision {text!r}")
    return text


def repo_slug(value: object) -> str:
    """Return an owner/name slug, or refuse anything option-shaped."""
    text = str(value)
    if _REPO.fullmatch(text) is None:
        raise ValueError(f"refusing repository {text!r}")
    return text


def pr_number(value: object) -> str:
    """Return a pull request number, or refuse anything option-shaped."""
    text = str(value)
    if _PR.fullmatch(text) is None:
        raise ValueError(f"refusing pull request number {text!r}")
    return str(int(text))


def ref_token(value: object) -> str:
    """Return one safe ref token, or refuse slashes and options."""
    text = str(value)
    if _TOKEN.fullmatch(text) is None:
        raise ValueError(f"refusing ref token {text!r}")
    return text


def _plain_child_io() -> None:
    """Ask child processes for plain text without passing an environment map."""
    os.environ["NO_COLOR"] = "1"
    os.environ["GH_NO_COLOR"] = "1"
    for name in ("GH_FORCE_TTY", "CLICOLOR_FORCE", "FORCE_COLOR"):
        os.environ.pop(name, None)


def command(args: list[str], cwd: Path = ROOT) -> str:
    """Run one list-form command and return its stdout.

    Shell stays off. Dynamic tokens must already be git_sha, repo_slug,
    pr_number, or ref_token results. shlex.quote would break this form.
    The child inherits the process environment. This function does not
    pass env, so CLI and environment text cannot ride in as an argument.
    """
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
    return bool(
        case.get("file") == finding["citing_file"]
        and case.get("defect_class") == finding["defect_class"]
        and abs(case.get("line", -100) - finding["citing_line"]) <= 3
    )


def replay(case: dict[str, Any], repository: str, run_id: str) -> dict[str, Any]:
    """Fetch a PR, check its pinned commit, and remove temporary state."""
    _plain_child_io()
    pr = pr_number(case["pr"])
    token = ref_token(run_id)
    repository = repo_slug(repository)
    ref = f"refs/docs-citation-replay/{token}/{pr}"
    parent = Path.home() / "worktrees" / ROOT.parent.name
    parent.mkdir(parents=True, exist_ok=True)
    worktree = parent / f"citation-replay-{token}-{pr}"
    pinned = case.get("sha")
    revision = f"{git_sha(pinned)}^{{commit}}" if pinned else f"{ref}^{{commit}}"
    added = False
    try:
        metadata = json.loads(
            command(
                [
                    "gh",
                    "pr",
                    "view",
                    "--repo",
                    repository,
                    "--json",
                    "baseRefOid,headRefOid",
                    pr,
                ]
            )
        )
        command(["git", "fetch", "--no-tags", "origin", f"pull/{pr}/head:{ref}"])
        sha = git_sha(command(["git", "rev-parse", "--verify", "--end-of-options", revision]))
        base_ref = git_sha(metadata["baseRefOid"])
        # A shallow checkout may not have the base object yet.
        try:
            command(["git", "cat-file", "-e", "--end-of-options", f"{base_ref}^{{commit}}"])
        except RuntimeError:
            command(["git", "fetch", "--no-tags", "origin", base_ref])
        base = git_sha(command(["git", "merge-base", "--end-of-options", sha, base_ref]))
        command(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "worktree",
                "add",
                "--detach",
                "--end-of-options",
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


def write_report(report: dict[str, Any], output: Path) -> None:
    """Write a short index and one case file beside it."""
    shard_dir = output.parent / output.stem
    shard_dir.mkdir(parents=True, exist_ok=True)
    slim_cases: list[dict[str, Any]] = []
    for row in report["cases"]:
        case_id = str(row["id"])
        name = f"{case_id}.json"
        (shard_dir / name).write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        slim = {key: value for key, value in row.items() if key not in {"findings", "output"}}
        slim["record"] = f"{output.stem}/{name}"
        slim_cases.append(slim)
    output.write_text(json.dumps(dict(report, cases=slim_cases), indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Run all cases, or selected cases during development."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args(argv)
    if not Path.cwd().resolve().is_relative_to(ROOT):
        print(
            "[citation-freshness-replay] current directory is outside this checkout",
            file=sys.stderr,
        )
        return 2
    _plain_child_io()
    corpus_bytes = CORPUS.read_bytes()
    corpus = json.loads(corpus_bytes)
    rows = []
    run_id = uuid.uuid4().hex[:12]
    for case in corpus["cases"]:
        if args.case and case["id"] not in args.case:
            continue
        try:
            row = replay(case, repo_slug(corpus["repository"]), run_id)
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
        checker_sha=command(["git", "rev-parse", "--verify", "--end-of-options", "HEAD"]),
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
    output = args.output or CORPUS.parent / "results" / "2026-11-19.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    write_report(report, output)
    print(summary["score_line"])
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
