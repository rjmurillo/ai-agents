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
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
CASES = Path(__file__).resolve().parent / "cases"
PONYTAIL_VERSION = "4.9.0"
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


def build_root(plugin_dir: Path, cases: Path, work: Path, corpus: str) -> Path:
    """Copy the plugin and the cases into a scratch plugin root."""
    manifest = json.loads(
        (plugin_dir / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    if manifest.get("version") != PONYTAIL_VERSION:
        raise ValueError(f"expected Ponytail {PONYTAIL_VERSION}, found {manifest.get('version')}")
    root = work / "root"
    shutil.copytree(plugin_dir, root, ignore=shutil.ignore_patterns(".in_use", "evals"))
    shutil.copytree(cases, root / "evals")
    for prompt in (root / "evals").rglob("prompt.md"):
        prompt.write_text(
            inject_corpus(prompt.read_text(encoding="utf-8"), corpus), encoding="utf-8"
        )
    return root


def summarize(result: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per case and arm: acceptance, correction burden, cost, time."""
    rows = []
    for case in result["cases"]:
        tags = case.get("tags") or []
        for arm, runs in case["arms"].items():
            graded = [[g for g in run["graders"] if g.get("scored", True)] for run in runs]
            rows.append(
                {
                    "case": case["name"],
                    "tags": tags,
                    "arm": arm,
                    "runs": len(runs),
                    "errors": sum(1 for run in runs if run.get("error")),
                    "accepted": sum(1 for gs in graded if gs and all(g["passed"] for g in gs)),
                    "failed_graders": sum(sum(not g["passed"] for g in gs) for gs in graded),
                    "cost_usd": round(sum(run.get("costUsd") or 0 for run in runs), 4),
                    "seconds": sum(run.get("durationSeconds") or 0 for run in runs),
                }
            )
    return rows


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| case | arm | accepted | failed graders | errors | cost USD | seconds |",
        "|---|---|--:|--:|--:|--:|--:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['case']} | {r['arm']} | {r['accepted']}/{r['runs']} | {r['failed_graders']} "
            f"| {r['errors']} | {r['cost_usd']:.4f} | {r['seconds']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plugin-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--judge-model", default="claude-opus-5-5")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--max-cost-usd", type=float, default=40.0)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    root = build_root(args.plugin_dir, CASES, args.out, load_corpus(REPO))
    result_path = args.out / "result.json"
    command = [
        "claude",
        "plugin",
        "eval",
        str(root),
        "--trust-plugin",
        "--no-publish",
        "--ablation",
        "with-without",
        "--threshold",
        "0",
        "--model",
        args.model,
        "--judge-model",
        args.judge_model,
        "--runs",
        str(args.runs),
        "--max-cost-usd",
        str(args.max_cost_usd),
        "--concurrency",
        str(args.concurrency),
        "--json",
        str(result_path),
    ]
    completed = subprocess.run(command, check=False)
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
