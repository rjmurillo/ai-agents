#!/usr/bin/env python3
"""End-to-end delivery eval: plan-rubric proxy (issue #2859).

Feeds each agent a deliberately vague germ, captures the plan it emits, and
has an LLM judge score that plan against hidden acceptance criteria derived
from a real merged PR. This measures whether an agent can carry an
under-specified ask toward done, not just whether it picks the right lane (the
routing eval already showed both agents tie at the routing ceiling).

This is harness shape 2 from the issue (cheaper, weaker proxy). It scores
plan quality, NOT delivered code. It cannot prove the change compiles or
passes tests; graduate to the trace-based shape (#2859 shape 1) for that.

Usage:
    # Validate fixtures and resolve prompts without any API call:
    python scripts/eval/eval-e2e-delivery.py \\
        --fixtures scripts/eval/examples/e2e-delivery-fixtures.json --dry-run

    # Live run, 3 runs per cell (flakiness protocol), write a report:
    python scripts/eval/eval-e2e-delivery.py \\
        --fixtures scripts/eval/examples/e2e-delivery-fixtures.json \\
        --runs 3 --output artifacts/e2e-delivery.json

Ground-truth discipline: fixture criteria come from real merged PRs, so they
are independent of the agent prompts. They are still single-author curated,
so absolute scores are directional; trust relative deltas that clear the
run-to-run noise band. The report header restates this.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# eval-* scripts import sibling helpers by bare name, so the eval dir must be
# importable when this file runs as a script.
_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from _anthropic_api import (  # noqa: E402
    DEFAULT_MODEL,
    call_api,
    load_api_key,
    verify_model_available,
)
from _e2e_delivery_core import (  # noqa: E402
    MAX_SCORE,
    aggregate,
    build_agent_user_message,
    build_judge_system,
    build_judge_user_message,
    load_fixtures,
    parse_judge_response,
)

_REPO_ROOT = _EVAL_DIR.parents[1]

# Agent prompt sources, relative to the repo root. autoplan is a SKILL
# (SKILL.md read into context); orchestrator is a subagent system prompt.
# The issue notes autoplan once lived only on the PR #2829 branch; it has
# since merged to main, so a file path resolves. `--ref` still lets a run
# load either prompt from an arbitrary git ref if needed.
AGENT_REGISTRY: dict[str, str] = {
    "orchestrator": ".claude/agents/orchestrator.md",
    "autoplan": ".claude/skills/autoplan/SKILL.md",
}


def _load_prompt(rel_path: str, ref: str | None) -> str:
    """Load an agent prompt from the working tree or a git ref."""
    if ref:
        import subprocess

        try:
            out = subprocess.run(
                ["git", "show", f"{ref}:{rel_path}"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=True,
                timeout=30,
                cwd=_REPO_ROOT,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"cannot load {rel_path} from ref {ref!r}: {exc.stderr.strip()}"
            ) from exc
        return out.stdout
    path = _REPO_ROOT / rel_path
    if not path.exists():
        raise RuntimeError(f"agent prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def _resolve_agents(names: list[str], ref: str | None) -> dict[str, str]:
    """Map each requested agent name to its prompt text."""
    resolved: dict[str, str] = {}
    for name in names:
        rel = AGENT_REGISTRY.get(name)
        if rel is None:
            raise RuntimeError(
                f"unknown agent {name!r}; known: {sorted(AGENT_REGISTRY)}"
            )
        resolved[name] = _load_prompt(rel, ref)
    return resolved


def _run_cell(
    api_key: str,
    agent_prompt: str,
    fixture: dict,
    model: str,
    provider: str | None,
) -> dict:
    """One (fixture, agent) run: emit a plan, then judge it."""
    plan = call_api(
        api_key,
        [{"role": "user", "content": build_agent_user_message(fixture["prompt"])}],
        system=agent_prompt,
        model=model,
        max_tokens=2048,
        provider=provider,
    )
    verdict = call_api(
        api_key,
        [
            {
                "role": "user",
                "content": build_judge_user_message(fixture, plan),
            }
        ],
        system=build_judge_system(),
        model=model,
        max_tokens=1024,
        provider=provider,
    )
    scored = parse_judge_response(verdict)
    scored["plan_chars"] = len(plan)
    return scored


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="End-to-end delivery eval (plan-rubric proxy, #2859)."
    )
    parser.add_argument(
        "--fixtures", required=True, help="Path to fixtures JSON file"
    )
    parser.add_argument(
        "--agents",
        default="orchestrator,autoplan",
        help="Comma-separated agent names (default: orchestrator,autoplan)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model id")
    parser.add_argument(
        "--runs", type=int, default=3, help="Runs per cell (default 3)"
    )
    parser.add_argument("--ref", default=None, help="Git ref for agent prompts")
    parser.add_argument(
        "--limit", type=int, default=None, help="Only run the first N fixtures"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate fixtures and resolve prompts; no API calls",
    )
    parser.add_argument("--output", default=None, help="Write JSON report here")
    return parser.parse_args(argv)


_CAVEAT = (
    "PROXY EVAL: scores plan quality, not delivered code. Criteria come from "
    "real merged PRs (independent of the agent prompts) but are single-author "
    "curated, so absolute scores are directional; trust deltas that clear the "
    "run-to-run noise band. Same-family judge. See issue #2859."
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    agent_names = [a.strip() for a in args.agents.split(",") if a.strip()]
    fixtures = load_fixtures(Path(args.fixtures).read_text(encoding="utf-8"))
    if args.limit is not None:
        fixtures = fixtures[: args.limit]
    agent_prompts = _resolve_agents(agent_names, args.ref)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "caveat": _CAVEAT,
                    "max_score": MAX_SCORE,
                    "fixtures": [f["id"] for f in fixtures],
                    "agents": agent_names,
                    "runs_per_cell": args.runs,
                    "planned_api_calls": len(fixtures)
                    * len(agent_names)
                    * args.runs
                    * 2,  # one generate + one judge per run
                    "model": args.model,
                },
                indent=2,
            )
        )
        return 0

    api_key = load_api_key()
    if not os.environ.get("EVAL_SKIP_MODEL_PREFLIGHT"):
        verify_model_available(api_key, model=args.model)
    provider = os.environ.get("EVAL_PROVIDER") or None

    records: list[dict] = []
    for fixture in fixtures:
        for agent in agent_names:
            for run_index in range(args.runs):
                scored = _run_cell(
                    api_key,
                    agent_prompts[agent],
                    fixture,
                    args.model,
                    provider,
                )
                records.append(
                    {
                        "fixture_id": fixture["id"],
                        "agent": agent,
                        "run_index": run_index,
                        "total": scored.get("total"),
                        "axes": scored.get("axes"),
                        "plan_chars": scored.get("plan_chars"),
                        "verdict": scored.get("verdict"),
                    }
                )

    report = aggregate(records)
    report["caveat"] = _CAVEAT
    report["model"] = args.model
    report["runs_per_cell"] = args.runs
    payload = {"report": report, "records": records}
    text = json.dumps(payload, indent=2)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
