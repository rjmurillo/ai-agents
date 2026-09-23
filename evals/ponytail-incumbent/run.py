#!/usr/bin/env python3
"""Run the Ponytail incumbent eval for issue #5457 through `claude plugin eval`.

`claude plugin eval` runs every case twice, with and without the plugin, in
the same isolated working directory. That directory has no project
instructions, so this runner appends the ai-agents always-on corpus to every
case prompt. Both arms get the same corpus. The only difference between arms
is the Ponytail plugin.

The harness reads cases only from below the plugin root, so the runner copies
the installed plugin and the committed cases into a scratch root first.

Run from the repository root:
    python3 evals/ponytail-incumbent/run.py \
        --plugin-dir <installed ponytail 4.9.0 directory> --out <result dir>
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CASES = Path(__file__).resolve().parent / "cases"
PONYTAIL_VERSION = "4.9.0"
PONYTAIL_SHA = "0a4dd63ad4541f4f655c4108a295916f3c1d8fda"
# Upper bound on one `claude plugin eval` call; the cost ceiling bounds spend only.
EVAL_TIMEOUT_SECONDS = 4 * 60 * 60
# `claude plugin eval` grader types that need no model. Every other type,
# including `llm` and `baseline`, is judge-backed and stays advisory.
DETERMINISTIC_GRADERS = frozenset({"regex", "tool_used", "tool_order", "file_exists"})
# Pre-registered models. Both arms must run the same pair.
MODEL = "claude-sonnet-5"
JUDGE_MODEL = "claude-opus-5-5"
CORPUS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".claude/CLAUDE.md",
    ".claude/rules/universal.md",
    ".claude/rules/builder-ethos.md",
    ".claude/rules/voice.md",
)


def load_corpus(repo: Path) -> str:
    """Concatenate the always-on instruction files, each under its path."""
    parts = [
        f"# Contents of {name}\n\n{(repo / name).read_text(encoding='utf-8')}" for name in CORPUS
    ]
    return "\n\n".join(parts)


def inject_corpus(prompt: str, corpus: str) -> str:
    """Add `append_system_prompt` to a prompt.md frontmatter block."""
    if not prompt.startswith("---\n"):
        raise ValueError("prompt.md must start with a frontmatter block")
    end = prompt.index("\n---\n", 4)
    block = "\n".join("  " + line if line else "" for line in corpus.splitlines())
    return f"{prompt[:end]}\nappend_system_prompt: |\n{block}{prompt[end:]}"


def verify_plugin(plugin_dir: Path, expected_sha: str) -> None:
    """Refuse a plugin directory that is not a clean checkout of the reviewed commit."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=plugin_dir, capture_output=True, text=True, timeout=30
    )
    if head.returncode != 0 or head.stdout.strip() != expected_sha:
        raise ValueError(f"plugin dir is not a git checkout at {expected_sha}")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--ignored"],
        cwd=plugin_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if status.returncode != 0 or status.stdout.strip():
        raise ValueError("plugin checkout has local changes or ignored files")


def build_root(plugin_dir: Path, cases: Path, work: Path, corpus: str) -> Path:
    """Copy the plugin and the cases into a scratch plugin root."""
    if work.resolve().is_relative_to(plugin_dir.resolve()):
        raise ValueError("--out must not be inside --plugin-dir")
    manifest = json.loads(
        (plugin_dir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    if manifest.get("version") != PONYTAIL_VERSION:
        raise ValueError(f"expected Ponytail {PONYTAIL_VERSION}, found {manifest.get('version')}")
    root = work / "root"
    shutil.copytree(plugin_dir, root, ignore=shutil.ignore_patterns(".git", ".in_use", "evals"))
    shutil.copytree(cases, root / "evals")
    for prompt in (root / "evals").rglob("prompt.md"):
        prompt.write_text(
            inject_corpus(prompt.read_text(encoding="utf-8"), corpus), encoding="utf-8"
        )
    return root


def summarize(result: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per case and arm: gated acceptance, failed checks, cost, time.

    ADR-058: only deterministic graders gate. Judge-backed graders are reported as
    an advisory count and never enter `accepted` or `failed_checks`.
    """
    rows = []
    for case in result["cases"]:
        gate = {
            g["name"] for g in case.get("graders", []) if g.get("type") in DETERMINISTIC_GRADERS
        }
        for arm, runs in case["arms"].items():
            scored = [[g for g in run["graders"] if g.get("scored", True)] for run in runs]
            gated = [[g for g in gs if g["name"] in gate] for gs in scored]
            judged = [[g for g in gs if g["name"] not in gate] for gs in scored]
            rows.append(
                {
                    "case": case["name"],
                    "arm": arm,
                    "runs": len(runs),
                    "errors": sum(1 for run in runs if run.get("error")),
                    "accepted": sum(
                        1
                        for run, gs in zip(runs, gated, strict=True)
                        if gs and not run.get("error") and all(g["passed"] for g in gs)
                    ),
                    "failed_checks": sum(sum(not g["passed"] for g in gs) for gs in gated),
                    "advisory_judge_passed": sum(
                        1 for gs in judged if gs and all(g["passed"] for g in gs)
                    ),
                    "cost_usd": round(sum(run.get("costUsd") or 0 for run in runs), 4),
                    "seconds": sum(run.get("durationSeconds") or 0 for run in runs),
                }
            )
    return rows


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| case | arm | accepted | failed checks | errors | cost USD | seconds | advisory judge |",
        "|---|---|--:|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['case']} | {r['arm']} | {r['accepted']}/{r['runs']} | {r['failed_checks']} "
            f"| {r['errors']} | {r['cost_usd']:.4f} | {r['seconds']} "
            f"| {r['advisory_judge_passed']}/{r['runs']} |"
        )
    lines.append("")
    lines.append("Advisory: not part of the gated signal. (the `advisory judge` column)")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plugin-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--max-cost-usd", type=float, default=40.0)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    verify_plugin(args.plugin_dir, PONYTAIL_SHA)
    if args.out.exists() and any(args.out.iterdir()):
        # A fresh directory means result.json can only come from this run.
        print(f"--out {args.out} is not empty; use a fresh directory", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    build_root(args.plugin_dir, CASES, args.out, load_corpus(REPO))
    result_path = args.out / "result.json"
    command = [
        "claude",
        "plugin",
        "eval",
        "root",
        "--trust-plugin",
        "--no-publish",
        "--ablation",
        "with-without",
        "--threshold",
        "0",
        "--model",
        MODEL,
        "--judge-model",
        JUDGE_MODEL,
        "--runs",
        shlex.quote(str(args.runs)),
        "--max-cost-usd",
        shlex.quote(str(args.max_cost_usd)),
        "--concurrency",
        shlex.quote(str(args.concurrency)),
        "--json",
        "result.json",
    ]
    # Paths stay relative to cwd and numbers pass through shlex.quote, so no
    # parsed argument reaches argv as raw text.
    try:
        completed = subprocess.run(command, cwd=args.out, check=False, timeout=EVAL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        print(f"claude plugin eval exceeded {EVAL_TIMEOUT_SECONDS}s", file=sys.stderr)
        return 3
    if not result_path.is_file():
        print(f"claude plugin eval wrote no result (exit {completed.returncode})", file=sys.stderr)
        return 3
    rows = summarize(json.loads(result_path.read_text(encoding="utf-8")))
    (args.out / "summary.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    (args.out / "summary.md").write_text(render(rows), encoding="utf-8")
    print(render(rows))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
