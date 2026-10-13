#!/usr/bin/env python3
"""Falsification harness: per-role catch rate of the adr-review panel (issue #5248).

ADR-101 abandons its Phase 2 unless a measured per-role catch rate justifies
it. This harness replays defects already on record against the six adr-review
roles on the text as it stood before each fix, and counts how often each role's
Phase 1 review flags the defect.

Corpus: evals/adr-review-catch-rate/corpus.json. Each entry names the pre-fix
commit, the fix commit, and a deterministic match rule. The selection method is
recorded in the corpus and in evals/adr-review-catch-rate/README.md.

Arms:
    unassisted  ADR text only, no repository access.
    assisted    ADR text plus the bounded repository excerpts a verifying
                reviewer would read. Only entries that carry evidence run.
    control     The post-fix text. A role that flags the defect here is
                flagging something the fix removed, so this is the false-flag
                floor.

Cost: one model call per (entry, arm, role, trial). `--dry-run` prints the count.

Exit codes:
    0 - ok
    2 - config, corpus, or credential invalid
    3 - external failure (every call failed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _adr_catch_rate_core as core
import _adr_catch_rate_stats as stats
from _anthropic_api import DEFAULT_MODEL, call_api, load_api_key_for_selected_provider

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = "evals/adr-review-catch-rate/corpus.json"
PROMPTS_PATH = ".claude/skills/adr-review/references/agent-prompts.md"
ROLE_TEMPLATE = "templates/agents/{role}.shared.md"
MAX_TOKENS = 6000
RAW_KEEP_CHARS = 12000

Caller = Callable[[str, str], str]


@dataclass(frozen=True)
class Job:
    entry: str
    arm: str
    role: str
    trial: int
    system: str
    user: str
    rule: core.MatchRule


def git_show(commit: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
        cwd=str(REPO_ROOT),
    )
    return result.stdout if result.returncode == 0 else None


def load_role_systems(roles: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for role in roles:
        path = REPO_ROOT / ROLE_TEMPLATE.format(role=role)
        out[role] = core.strip_frontmatter(path.read_text(encoding="utf-8"))
    return out


def plan_jobs(
    items: list[core.Materialized],
    arms: tuple[str, ...],
    roles: tuple[str, ...],
    trials: int,
    prompts_md: str,
    systems: dict[str, str],
) -> list[Job]:
    templates = core.parse_phase1_prompts(prompts_md)
    claim_block = core.parse_claim_block(prompts_md)
    jobs: list[Job] = []
    for item in items:
        for arm in arms:
            if arm == core.ARM_ASSISTED and not item.evidence_text:
                continue
            text = item.fixed_text if arm == core.ARM_CONTROL else item.base_text
            evidence = item.evidence_text if arm == core.ARM_ASSISTED else ""
            for role in roles:
                user = core.build_user_prompt(templates[role], claim_block, text, evidence)
                for trial in range(trials):
                    jobs.append(
                        Job(item.entry.id, arm, role, trial, systems[role], user, item.entry.match)
                    )
    return jobs


def run_job(job: Job, caller: Caller) -> dict[str, Any]:
    row: dict[str, Any] = {
        "entry": job.entry,
        "arm": job.arm,
        "role": job.role,
        "trial": job.trial,
    }
    try:
        raw = caller(job.system, job.user)
    except RuntimeError as exc:
        row.update(error=str(exc)[:300], flagged=False, blocked=False)
        return row
    outcome = core.score_review(core.parse_review(raw), job.rule)
    row.update(
        flagged=outcome.flagged,
        blocked=outcome.blocked,
        matched=outcome.matched,
        raw_chars=len(raw),
        raw_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        raw=raw[:RAW_KEEP_CHARS],
    )
    return row


def job_key(row: dict[str, Any]) -> tuple[str, str, str, int]:
    return (row["entry"], row["arm"], row["role"], int(row["trial"]))


def load_checkpoint(path: Path | None) -> list[dict[str, Any]]:
    """Rows already finished without error. Errored rows are retried."""
    if path is None or not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [row for row in rows if not row.get("error")]


def run_jobs(
    jobs: list[Job],
    caller: Caller,
    workers: int,
    done: list[dict[str, Any]] | None = None,
    checkpoint: Path | None = None,
) -> list[dict[str, Any]]:
    """Run jobs not already in `done`; append each finished row to `checkpoint`."""
    finished = list(done or [])
    seen = {job_key(row) for row in finished}
    pending = [job for job in jobs if (job.entry, job.arm, job.role, job.trial) not in seen]
    lock = threading.Lock()

    def work(job: Job) -> dict[str, Any]:
        row = run_job(job, caller)
        if checkpoint is not None:
            with lock, checkpoint.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
        return row

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return finished + list(pool.map(work, pending))


def make_caller(api_key: str, model: str, pause: float) -> Caller:
    def call(system: str, user: str) -> str:
        if pause:
            time.sleep(pause)
        text: str = call_api(
            api_key,
            [{"role": "user", "content": user}],
            system=system,
            model=model,
            max_tokens=MAX_TOKENS,
        )
        return text

    return call


def summarize(rows: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    arms = sorted({row["arm"] for row in rows})
    return {
        "meta": meta,
        "table": stats.aggregate(rows),
        "unions": {arm: stats.panel_union(rows, arm) for arm in arms},
        "rows": [{k: v for k, v in row.items() if k != "raw"} for row in rows],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--corpus", default=DEFAULT_CORPUS)
    parser.add_argument("--arms", default="unassisted,assisted", help="comma list of arms")
    parser.add_argument("--roles", default=",".join(core.ROLES), help="comma list of roles")
    parser.add_argument("--entries", default="", help="comma list of entry ids (default all)")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--pause", type=float, default=0.0, help="seconds before each call")
    parser.add_argument("--output", default=None, help="write results JSON here")
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="JSONL file of finished rows; reruns skip rows already in it",
    )
    parser.add_argument("--report", default=None, help="write the markdown report here")
    parser.add_argument("--report-from", default=None, help="render a report from results JSON")
    parser.add_argument("--validate-corpus", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _split(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _check_choice(name: str, chosen: tuple[str, ...], allowed: tuple[str, ...]) -> str | None:
    bad = [item for item in chosen if item not in allowed]
    return f"unknown {name}: {', '.join(bad)}" if bad else None


def render_from_results(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    report: str = stats.render_report(data["table"], data["unions"], data["meta"])
    return report


def select_entries(corpus: core.Corpus, wanted: tuple[str, ...]) -> list[core.Entry]:
    if not wanted:
        return list(corpus.entries)
    known = {e.id: e for e in corpus.entries}
    missing = [w for w in wanted if w not in known]
    if missing:
        raise core.CorpusError(f"unknown entry ids: {', '.join(missing)}")
    return [known[w] for w in wanted]


def prepare(
    args: argparse.Namespace,
) -> tuple[list[core.Materialized], tuple[str, ...], tuple[str, ...]]:
    arms, roles = _split(args.arms), _split(args.roles)
    for problem in (
        _check_choice("arm", arms, core.ARMS),
        _check_choice("role", roles, core.ROLES),
    ):
        if problem:
            raise core.CorpusError(problem)
    corpus = core.load_corpus(REPO_ROOT / args.corpus)
    entries = select_entries(corpus, _split(args.entries))
    return [core.materialize(e, git_show) for e in entries], arms, roles


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.report_from:
        print(render_from_results(Path(args.report_from)))
        return 0
    try:
        items, arms, roles = prepare(args)
        prompts_md = (REPO_ROOT / PROMPTS_PATH).read_text(encoding="utf-8")
        jobs = plan_jobs(items, arms, roles, args.trials, prompts_md, load_role_systems(roles))
    except (core.CorpusError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.validate_corpus or args.dry_run:
        print(json.dumps({"entries": len(items), "planned_calls": len(jobs)}, indent=2))
        return 0
    return execute(args, jobs, len(items))


def execute(args: argparse.Namespace, jobs: list[Job], entry_count: int) -> int:
    try:
        api_key = load_api_key_for_selected_provider()
    except RuntimeError as exc:
        print(f"ERROR loading API key: {exc}", file=sys.stderr)
        return 2
    print(f"  running {len(jobs)} calls on {args.model}", file=sys.stderr)
    checkpoint = Path(args.checkpoint) if args.checkpoint else None
    rows = run_jobs(
        jobs,
        make_caller(api_key, args.model, args.pause),
        args.workers,
        load_checkpoint(checkpoint),
        checkpoint,
    )
    meta = {"model": args.model, "trials": args.trials, "entries": entry_count}
    result = summarize(rows, meta)
    report = stats.render_report(result["table"], result["unions"], meta)
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.report:
        Path(args.report).write_text(report + "\n", encoding="utf-8")
    print(report)
    return 3 if rows and all(row.get("error") for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
