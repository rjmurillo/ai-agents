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


def _uv(*tail: str) -> list[str]:
    return ["uv", "run", "python", *tail]


INSTRUMENTS: list[dict] = [
    {
        "id": "description-budget",
        "answers": "How much standing context do skill descriptions cost?",
        "argv": _uv("./scripts/skill_description_budget.py", "--top", "10"),
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "skill-size",
        "answers": "Which SKILL.md files pass the line and byte limits? (exit 0 unless --ci)",
        "argv": _uv("./scripts/validation/skill_size.py"),
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "orphan-refs",
        "answers": "Do specs, evals, and manifests reference entities that no longer exist?",
        "argv": ["python3", f"{SK}/orphan-ref-validator/scripts/scan.py"],
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "golden-principles",
        "answers": "Where does the repo violate the mechanical golden principles? (exit 10 on violations)",
        "argv": ["python3", f"{SK}/golden-principles/scripts/scan_principles.py"],
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "agent-drift",
        "answers": "Do generated agent files match their templates?",
        "argv": _uv("build/generate_agents.py", "--validate"),
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "build-check",
        "answers": "Do generated mirror and lib trees match canonical sources? Writes build/audit/GENERATION-AUDIT.md.",
        "argv": _uv("build/scripts/build_all.py", "--check"),
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "install-parity",
        "answers": "Does the install surface stay in parity across hosts (ADR-035)?",
        "argv": _uv("scripts/validation/run_install_parity_ci.py"),
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "eval-prompt-change",
        "answers": "Did a prompt change alter behavior? Pass --prompt and --scenarios; --dry-run spends nothing.",
        "argv": _uv("./scripts/eval/eval-prompt-change.py", "--dry-run"),
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "eval-agent-vs-baseline",
        "answers": "Does an agent beat the baseline? Pass --agent and --fixtures; --dry-run is already set.",
        "argv": _uv("./scripts/eval/eval-agent-vs-baseline.py", "--dry-run"),
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "coverage",
        "answers": "Is changed code exercised by tests? With no target it runs the whole suite; pass a test path and --cov=<dotted module> after --.",
        "argv": ["uv", "run", "pytest", "--cov-branch"],
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "commit-count",
        "answers": "How many commits is HEAD ahead of origin/main? Advisory only.",
        "argv": ["git", "rev-list", "--count", "HEAD", "^origin/main"],
        "source": "SKILL.md Instrument Index",
    },
    {
        "id": "baseline-snapshot",
        "answers": "What are the current headline numbers of the four read-only instruments?",
        "argv": ["python3", f"{SK}/{SKILL}/scripts/baseline_snapshot.py", "--repo", "."],
        "source": "SKILL.md Baselines",
    },
    {
        "id": "drift-self-check",
        "answers": "Has this skill drifted from its reverify.json checks?",
        "argv": [
            "python3",
            f"{SK}/skill-bootstrap/scripts/bootstrap_drift.py",
            "check",
            "--repo",
            ".",
            "--skills-root",
            SK,
            "--name",
            SKILL,
            "--require",
        ],
        "source": "SKILL.md Provenance and Maintenance",
    },
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
