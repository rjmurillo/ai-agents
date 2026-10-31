#!/usr/bin/env python3
"""Instrument table for ai-agents-diagnostics-toolkit.

`list` prints every instrument row with exists true/false (exit 1 if any is missing).
`run <id> [-- args]` execs the instrument from the repo root and passes its exit code through.
Exit codes: 0 ok, 1 missing instrument, 2 bad arguments or unknown id, 3 run target failed to start.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SKILL = "ai-agents-diagnostics-toolkit"
SK = ".claude/skills"


def _row(id_: str, answers: str, argv: str, source: str = "SKILL.md Instrument Index") -> dict:
    """Build one instrument row from a space-separated command line."""
    return {"id": id_, "answers": answers, "argv": argv.split(), "source": source}


INSTRUMENTS: list[dict] = [
    _row(
        "description-budget",
        "How much standing context do skill descriptions cost?",
        "uv run python ./scripts/skill_description_budget.py --top 10",
    ),
    _row(
        "skill-size",
        "Which SKILL.md files pass the line and byte limits? (exit 0 unless --ci)",
        "uv run python ./scripts/validation/skill_size.py",
    ),
    _row(
        "orphan-refs",
        "Do specs, evals, and manifests reference entities that no longer exist?",
        f"python3 {SK}/orphan-ref-validator/scripts/scan.py",
    ),
    _row(
        "golden-principles",
        "Where does the repo violate the mechanical golden principles? (exit 10 on violations)",
        f"python3 {SK}/golden-principles/scripts/scan_principles.py",
    ),
    _row(
        "agent-drift",
        "Do generated agent files match their templates?",
        "uv run python build/generate_agents.py --validate",
    ),
    _row(
        "build-check",
        "Do generated mirror and lib trees match canonical sources? Writes build/audit/GENERATION-AUDIT.md.",
        "uv run python build/scripts/build_all.py --check",
    ),
    _row(
        "install-parity",
        "Does the install surface stay in parity across hosts (ADR-035)?",
        "uv run python scripts/validation/run_install_parity_ci.py",
    ),
    _row(
        "eval-prompt-change",
        "Did a prompt change alter behavior? Pass --prompt and --scenarios; --dry-run spends nothing.",
        "uv run python ./scripts/eval/eval-prompt-change.py --dry-run",
    ),
    _row(
        "eval-agent-vs-baseline",
        "Does an agent beat the baseline? Pass --agent and --fixtures; --dry-run is already set.",
        "uv run python ./scripts/eval/eval-agent-vs-baseline.py --dry-run",
    ),
    _row(
        "coverage",
        "Is changed code exercised by tests? With no target it runs the whole suite; pass a test path and --cov=<dotted module> after --.",
        "uv run pytest --cov-branch",
    ),
    _row(
        "commit-count",
        "How many commits is HEAD ahead of origin/main? Advisory only.",
        "git rev-list --count HEAD ^origin/main",
    ),
    _row(
        "baseline-snapshot",
        "What are the current headline numbers of the four read-only instruments?",
        f"python3 {SK}/{SKILL}/scripts/baseline_snapshot.py --repo .",
        "SKILL.md Baselines",
    ),
    _row(
        "drift-self-check",
        "Has this skill drifted from its reverify.json checks?",
        f"python3 {SK}/skill-bootstrap/scripts/bootstrap_drift.py check --repo . --skills-root {SK} --name {SKILL} --require",
        "SKILL.md Provenance and Maintenance",
    ),
]


def _exists(repo: Path, argv: list[str]) -> bool:
    for tok in argv[1:]:
        if tok.endswith(".py"):
            return (repo / tok).is_file()
    return True


def cmd_list(repo: Path) -> int:
    rows = [{**r, "exists": _exists(repo, r["argv"])} for r in INSTRUMENTS]
    missing = [r["id"] for r in rows if not r["exists"]]
    print(
        json.dumps(
            {"skill": SKILL, "instruments": rows, "examined": len(rows), "missing": missing},
            indent=2,
        )
    )
    return 1 if missing else 0


def cmd_run(repo: Path, ident: str, extra: list[str]) -> int:
    row = next((r for r in INSTRUMENTS if r["id"] == ident), None)
    if row is None:
        print(json.dumps({"error": f"unknown instrument id: {ident}"}), file=sys.stderr)
        return 2
    try:
        return subprocess.run(row["argv"] + extra, cwd=repo, check=False).returncode
    except OSError as exc:
        print(json.dumps({"error": f"failed to start: {exc}"}), file=sys.stderr)
        return 3


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="List or run this skill's instruments.")
    p.add_argument("--repo", default=".", help="repository root (default: .)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="print every instrument row")
    r = sub.add_parser("run", help="run one instrument")
    r.add_argument("id")
    r.add_argument("args", nargs=argparse.REMAINDER)
    a = p.parse_args(argv)
    repo = Path(a.repo).resolve()
    if a.cmd == "list":
        return cmd_list(repo)
    extra = a.args[1:] if a.args[:1] == ["--"] else a.args
    return cmd_run(repo, a.id, extra)


if __name__ == "__main__":
    sys.exit(main())
