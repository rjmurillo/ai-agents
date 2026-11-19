#!/usr/bin/env python3
"""Replay historical documentation reviews against the current link and style checks."""

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
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "evals/docs-review-catch-rate/links/corpus.json"
CHECK = ROOT / "scripts/validation/check_md_links.py"
PROSE = ROOT / "src/claude/skills/prose-self-check/scripts/prose_lint.py"
CONTEXT = "skills/github/scripts/pr/get_pr_context.py"
STYLE_KINDS = {"heading-case", "link-text", "vague-opener", "example-email", "token-shaped"}
FINDING = re.compile(r"^(.+?):(\d+): (missing-target|missing-anchor|stale-allowance): (.*)$")
HUNK = re.compile(r"^@@ .*? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


def command(args: list[str], cwd: Path = ROOT, *, codes: tuple[int, ...] = (0,)) -> str:
    """Run a bounded command and preserve errors."""
    result = subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    if result.returncode not in codes:
        raise RuntimeError(f"{args[0]} exited {result.returncode}: {result.stderr[-2000:]}")
    return result.stdout


def git(*args: str, cwd: Path = ROOT) -> str:
    """Run git against the named checkout."""
    return command(["git", *args], cwd)


def metadata(pr: int) -> dict[str, Any]:
    """Use the repository GitHub helper, including its baseRefOid query."""
    payload = json.loads(
        command(
            [
                sys.executable,
                str(ROOT / "src/claude/lib/ptk_run.py"),
                CONTEXT,
                "--pull-request",
                str(pr),
                "--owner",
                "rjmurillo",
                "--repo",
                "ai-agents",
            ]
        )
    )
    if not payload.get("Success"):
        raise RuntimeError(f"PR {pr}: {payload.get('Error')}")
    return cast("dict[str, Any]", payload["Data"])


def changed_lines(worktree: Path, base: str) -> dict[str, set[int]]:
    """Return added lines in changed documentation files."""
    names = git("diff", "--name-only", "-z", "--diff-filter=ACMR", base, "HEAD", cwd=worktree)
    lines: dict[str, set[int]] = {}
    for name in names.split("\0"):
        if not name.startswith("docs/") or not name.endswith(".md"):
            continue
        patch = git("diff", "--no-ext-diff", "--unified=0", base, "HEAD", "--", name, cwd=worktree)
        added: set[int] = set()
        for match in HUNK.finditer(patch):
            start = int(match[1])
            count = int(match[2]) if match[2] is not None else 1
            added.update(range(start, start + count))
        lines[name] = added
    return lines


def findings(worktree: Path, base: str, mode: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Invoke the same CLIs authors run, then restrict style to added lines."""
    args = [sys.executable, "-B", str(CHECK), "--repo-root", str(worktree), "--base-ref", base]
    if mode == "tree":
        args.append("--tree")
    output = command(args, worktree, codes=(0, 1))
    found = []
    for line in output.splitlines():
        match = FINDING.match(line)
        if match:
            found.append(
                {
                    "file": match[1],
                    "line": int(match[2]),
                    "defect_class": match[3],
                    "target": match[4],
                }
            )
    commands = [" ".join(args)]
    if mode == "tree":
        return found, commands
    changed = changed_lines(worktree, base)
    if changed:
        payload = json.loads(
            command(
                [
                    sys.executable,
                    str(PROSE),
                    "--docs-style",
                    "--json",
                    *sorted(changed),
                ],
                worktree,
                codes=(0, 1, 2),
            )
        )
        for name, report in payload["files"].items():
            for hit in report["findings"]:
                if hit["kind"] in STYLE_KINDS and hit["line"] in changed[name]:
                    found.append(
                        {
                            "file": name,
                            "line": hit["line"],
                            "defect_class": hit["kind"],
                            "note": hit["note"],
                        }
                    )
        commands.append("prose_lint.py --docs-style --json " + " ".join(sorted(changed)))
    return found, commands


def matched(expected: dict[str, Any], actual: list[dict[str, Any]]) -> bool:
    """Match path, class, and a line window of three."""
    return any(
        hit["file"] == expected["file"]
        and hit["defect_class"] == expected["defect_class"]
        and abs(hit["line"] - expected["line"]) <= 3
        and ("target" not in expected or hit.get("target") == expected["target"])
        for hit in actual
    )


def replay(case: dict[str, Any], info: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Fetch, replay in an isolated worktree, and clean up owned resources."""
    ref = f"refs/docs-review-links/{prefix}/{case['id']}"
    path = Path.home() / "worktrees/ai-agents" / f"docs-link-replay-{prefix}-{case['id']}"
    added = False
    try:
        git("fetch", "--no-tags", "origin", f"pull/{case['pr']}/head:{ref}")
        sha = git("rev-parse", case.get("sha") or ref).strip()
        fetched_head = git("rev-parse", ref).strip()
        base = git("merge-base", sha, info["base_sha"]).strip()
        git("worktree", "add", "--quiet", "--detach", str(path), sha)
        added = True
        actual, commands = findings(path, base, case.get("mode", "pre-pr"))
        expected = case.get("expected", [])
        return {
            "id": case["id"],
            "pr": case["pr"],
            "sha": sha,
            "fetched_head": fetched_head,
            "baseRefOid": info["base_sha"],
            "merge_base": base,
            "scope": case["scope"],
            "why": case.get("why"),
            "expected": expected,
            "findings": actual,
            "caught": sum(matched(item, actual) for item in expected),
            "false_positives": len(actual) if case["scope"] == "negative" else 0,
            "commands": commands,
        }
    finally:
        try:
            if added:
                # Old commits contain CRLF blobs normalized during checkout.
                git("diff", "--ignore-space-at-eol", "--exit-code", cwd=path)
                if git("ls-files", "--others", "--exclude-standard", cwd=path).strip():
                    raise RuntimeError(f"unexpected untracked replay files: {path}")
                git("worktree", "remove", "--force", str(path))
        finally:
            git("update-ref", "-d", ref)


def main(argv: list[str] | None = None) -> int:
    """Write an auditable result and enforce the acceptance bar."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.case and args.output is None:
        parser.error("partial replays require --output to preserve the full result")
    if not Path.cwd().resolve().is_relative_to(ROOT):
        parser.error("run from this repository")
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    selected = [case for case in corpus["cases"] if not args.case or case["id"] in args.case]
    if not selected or set(args.case) - {case["id"] for case in selected}:
        parser.error("unknown case")
    results = []
    context: dict[int, dict[str, Any]] = {}
    prefix = uuid.uuid4().hex[:10]
    for case in selected:
        if case["pr"] not in context:
            context[case["pr"]] = metadata(case["pr"])
        row = replay(case, context[case["pr"]], prefix)
        results.append(row)
        print(f"{row['id']}: caught={row['caught']}, FP={row['false_positives']}", flush=True)
    positives = [row for row in results if row["scope"] == "positive"]
    caught = sum(row["caught"] for row in positives)
    total = sum(len(row["expected"]) for row in positives)
    fp = sum(row["false_positives"] for row in results)
    negatives = sum(row["scope"] == "negative" for row in results)
    manual = sum(row["scope"] == "manual" for row in results)
    score = (
        f"caught {caught} of {total} in-scope positives, {fp} FP on {negatives} negatives, "
        f"{manual} manual with reasons"
    )
    today = datetime.now(UTC).date().isoformat()
    output = args.output or CORPUS.parent / "results" / f"{today}.json"
    artifact = {
        "schema_version": 1,
        "date": today,
        "head": git("rev-parse", "HEAD").strip(),
        "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        "inputs_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                CHECK,
                PROSE,
                Path(__file__),
                CHECK.with_name("check_adr_links.py"),
                CHECK.with_name("md_anchors.py"),
                CHECK.with_name("md_link_parse.py"),
                PROSE.with_name("docs_style.py"),
            )
        },
        "score": score,
        "recall": caught / total if total else None,
        "false_positives": fp,
        "negatives": negatives,
        "manual": manual,
        "passed": caught == total and fp == 0 and (negatives == 12 or bool(args.case)),
        "cases": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    header = json.dumps({k: v for k, v in artifact.items() if k != "cases"}, indent=2)
    rows = ",\n".join("    " + json.dumps(row) for row in results)
    rendered = header[:-2] + ',\n  "cases": [\n' + rows + "\n  ]\n}\n"
    output.write_text(rendered, encoding="utf-8")
    print(score)
    return 0 if artifact["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
