#!/usr/bin/env python3
"""Bug catch rate of the code-reviewer on a historical-bug corpus (issue #7149).

Replays defects already fixed in this repository's history. For each corpus
entry the reviewer sees the diff that introduced the bug and nothing else, and
the run counts how often a top-5 finding names the defect's file and class.
The method mirrors the ADR harness (scripts/eval/eval_adr_review_catch_rate.py):
deterministic match rule, Wilson intervals, resumable checkpoint, no model
judging another model.

Corpus: evals/code-review-catch-rate/corpus.json. Method and limits:
evals/code-review-catch-rate/README.md.

Cost: one model call per (entry, trial). `--dry-run` prints the count.

Exit codes:
    0 - ok
    2 - config, corpus, or credential invalid, or a leak check failed
    3 - external failure (every call failed)
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
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

import _adr_catch_rate_core as adr_core
import _code_review_catch_rate_core as core
import _code_review_catch_rate_report as report
import _code_review_catch_rate_score as score
from _anthropic_api import DEFAULT_MODEL, call_api, load_api_key_for_selected_provider

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = "evals/code-review-catch-rate/corpus.json"
AGENT_TEMPLATE = "templates/agents/code-reviewer.shared.md"
CONTRACT_PATH = "src/claude/skills/review/resources/technical-review.md"
MAX_TOKENS = 4000

Caller = Callable[[str, str], str]


@dataclass(frozen=True)
class Job:
    entry: str
    trial: int
    system: str
    user: str
    defect_files: tuple[str, ...]
    defect_class: str


def git_run(args: tuple[str, ...]) -> str | None:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
        cwd=str(REPO_ROOT),
    )
    return result.stdout if result.returncode == 0 else None


def load_system_prompt() -> str:
    agent = adr_core.strip_frontmatter((REPO_ROOT / AGENT_TEMPLATE).read_text(encoding="utf-8"))
    contract = (REPO_ROOT / CONTRACT_PATH).read_text(encoding="utf-8")
    prompt: str = core.build_system_prompt(agent, contract)
    return prompt


def select_entries(corpus: core.Corpus, wanted: tuple[str, ...]) -> list[core.Entry]:
    if not wanted:
        return list(corpus.entries)
    known = {e.id for e in corpus.entries}
    unknown = [w for w in wanted if w not in known]
    if unknown:
        raise core.CorpusError(f"unknown entry id: {', '.join(unknown)}")
    return [e for e in corpus.entries if e.id in wanted]


def plan_jobs(
    entries: list[core.Entry], reviews: dict[str, core.ReviewInput], trials: int
) -> list[Job]:
    return [
        Job(e.id, t, reviews[e.id].system, reviews[e.id].user, e.defect_files, e.defect_class)
        for e in entries
        for t in range(trials)
    ]


def run_job(job: Job, caller: Caller) -> dict[str, Any]:
    row: dict[str, Any] = {"entry": job.entry, "trial": job.trial}
    try:
        raw = caller(job.system, job.user)
    except RuntimeError as exc:
        row.update(error=str(exc)[:300], caught=False, near_miss=False)
        return row
    return {**row, **_scored_fields(raw, job.defect_files, job.defect_class), "raw": raw}


def _scored_fields(raw: str, files: tuple[str, ...], klass: str) -> dict[str, Any]:
    outcome = score.score_response(raw, files, klass)
    return {
        "caught": outcome.caught,
        "near_miss": outcome.near_miss,
        "matched": outcome.matched,
        "findings": [
            {"path": f.path, "class": f.klass, "text": f.text[:240]} for f in outcome.findings
        ],
        "extra_findings": outcome.extra,
        "raw_chars": len(raw),
        "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    }


def job_key(row: dict[str, Any]) -> tuple[str, int]:
    return (row["entry"], int(row["trial"]))


def load_checkpoint(path: Path | None) -> list[dict[str, Any]]:
    """Rows already finished. Errored or truncated rows are retried."""
    if path is None or not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    rows = []
    for index, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                break  # a killed run can leave a half-written last line; its job reruns
            raise
    for row in rows:
        if not isinstance(row, dict) or "entry" not in row or "trial" not in row:
            raise ValueError(f"checkpoint {path} holds a line that is not a result row")
    return [
        r for r in rows if not r.get("error") and len(r.get("raw", "")) == r.get("raw_chars", -1)
    ]


def rescore_rows(rows: list[dict[str, Any]], corpus: core.Corpus) -> list[dict[str, Any]]:
    """Score stored responses again with the corpus as it stands now. No model call."""
    entries = {e.id: e for e in corpus.entries}
    out = []
    for row in rows:
        entry = entries.get(row["entry"])
        if entry is None:
            raise core.CorpusError(f"checkpoint row names unknown entry {row['entry']}")
        out.append({**row, **_scored_fields(row["raw"], entry.defect_files, entry.defect_class)})
    return out


def run_jobs(
    jobs: list[Job],
    caller: Caller,
    workers: int,
    done: list[dict[str, Any]] | None = None,
    checkpoint: Path | None = None,
) -> list[dict[str, Any]]:
    """Run jobs not already in `done`; append each finished row to `checkpoint`.

    Rows in `done` that match no requested job (another `--entries` subset, a larger
    `--trials` from an earlier run) are left out, so the aggregate describes only the
    run that was asked for.
    """
    wanted = {(j.entry, j.trial) for j in jobs}
    finished = [r for r in (done or []) if job_key(r) in wanted]
    seen = {job_key(r) for r in finished}
    pending = [j for j in jobs if (j.entry, j.trial) not in seen]
    lock = threading.Lock()

    def work(job: Job) -> dict[str, Any]:
        row = run_job(job, caller)
        if checkpoint is not None:
            with lock, checkpoint.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
        return row

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return finished + list(pool.map(work, pending))


class Usage:
    """Call and output-token totals across worker threads."""

    def __init__(self) -> None:
        self.calls = 0
        self.output_tokens = 0
        self._lock = threading.Lock()

    def add(self, metadata: dict[str, object]) -> None:
        tokens = metadata.get("output_tokens")
        with self._lock:
            self.calls += 1
            if isinstance(tokens, int):
                self.output_tokens += tokens


def make_caller(api_key: str, model: str, pause: float, usage: Usage) -> Caller:
    def call(system: str, user: str) -> str:
        if pause:
            time.sleep(pause)
        metadata: dict[str, object] = {}
        text: str = call_api(
            api_key,
            [{"role": "user", "content": user}],
            system=system,
            model=model,
            max_tokens=MAX_TOKENS,
            metadata=metadata,
        )
        usage.add(metadata)
        return text

    return call


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--corpus", default=DEFAULT_CORPUS)
    parser.add_argument("--entries", default="", help="comma list of entry ids (default all)")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--pause", type=float, default=0.0, help="seconds before each call")
    parser.add_argument("--output", default=None, help="write results JSON here")
    parser.add_argument(
        "--checkpoint", default=None, help="JSONL of finished rows; reruns skip them"
    )
    parser.add_argument("--report", default=None, help="write the markdown report here")
    parser.add_argument("--report-from", default=None, help="render a report from results JSON")
    parser.add_argument(
        "--rescore", action="store_true", help="re-score --checkpoint rows; no model call"
    )
    parser.add_argument(
        "--validate-corpus", action="store_true", help="load, build prompts, run leak checks"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.trials < 1:
        parser.error("--trials must be at least 1")
    return args


def _split(raw: str) -> tuple[str, ...]:
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def prepare(
    args: argparse.Namespace, git: core.GitRun = git_run
) -> tuple[core.Corpus, list[core.Entry], dict[str, core.ReviewInput]]:
    corpus = core.load_corpus(REPO_ROOT / args.corpus)
    entries = select_entries(corpus, _split(args.entries))
    system = load_system_prompt()
    reviews = {e.id: core.build_review_input(e, system, git) for e in entries}
    return corpus, entries, reviews


def validate(
    entries: list[core.Entry],
    reviews: dict[str, core.ReviewInput],
    jobs: list[Job],
    git: core.GitRun,
) -> dict[str, Any]:
    leaks = {e.id: r for e in entries if (r := core.check_no_leak(e, reviews[e.id], git))}
    return {
        "entries": len(entries),
        "planned_calls": len(jobs),
        "max_diff_chars": max(r.diff_chars for r in reviews.values()),
        "total_diff_chars": sum(r.diff_chars for r in reviews.values()),
        "leaks": leaks,
    }


SUBSCRIPTION_PROVIDERS = ("claude-cli", "codex-cli", "copilot-cli")


def _cost_note(provider: str) -> str:
    """Subscription CLIs report no dollar cost; the metered API path is not priced here."""
    if provider in SUBSCRIPTION_PROVIDERS:
        return "subscription CLI, no metered spend; dollars not reported"
    return "metered API; dollars not computed by this harness, see output_tokens"


def build_meta(
    args: argparse.Namespace,
    corpus_path: Path,
    entry_count: int,
    usage: Usage | None,
    resumed_rows: int = 0,
) -> dict[str, Any]:
    """`calls` and `output_tokens` count this invocation only; `resumed_rows` were reused."""
    provider = os.environ.get("EVAL_PROVIDER") or "anthropic"
    return {
        "model": args.model,
        "provider": provider,
        "date": datetime.date.today().isoformat(),
        "trials": args.trials,
        "entries": entry_count,
        "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "calls": usage.calls if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
        "resumed_rows": resumed_rows,
        "cost": _cost_note(provider),
    }


def write_outputs(
    args: argparse.Namespace, rows: list[dict[str, Any]], meta: dict[str, Any], corpus: core.Corpus
) -> str:
    result = report.summarize(rows, meta, corpus)
    text: str = report.render_report(result)
    if args.output:
        Path(args.output).write_text(report.dump_results(result), encoding="utf-8")
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    return text


def rescore(args: argparse.Namespace) -> int:
    if not args.checkpoint:
        print("ERROR: --rescore needs --checkpoint", file=sys.stderr)
        return 2
    try:
        corpus = core.load_corpus(REPO_ROOT / args.corpus)
        wanted = tuple(e.id for e in select_entries(corpus, _split(args.entries)))
        rows = rescore_rows(load_checkpoint(Path(args.checkpoint)), corpus)
    except (core.CorpusError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    rows = [r for r in rows if r["entry"] in wanted]
    meta = build_meta(args, REPO_ROOT / args.corpus, len({r["entry"] for r in rows}), None)
    meta["trials"] = max((int(r["trial"]) for r in rows), default=-1) + 1
    meta["rescored"] = True
    print(write_outputs(args, rows, meta, corpus))
    return 0


def execute(
    args: argparse.Namespace,
    jobs: list[Job],
    corpus: core.Corpus,
    caller: Caller | None,
    usage: Usage,
) -> int:
    if caller is None:
        try:
            api_key = load_api_key_for_selected_provider()
        except RuntimeError as exc:
            print(f"ERROR loading API key: {exc}", file=sys.stderr)
            return 2
        caller = make_caller(api_key, args.model, args.pause, usage)
    print(f"  running {len(jobs)} calls on {args.model}", file=sys.stderr)
    checkpoint = Path(args.checkpoint) if args.checkpoint else None
    try:
        done = load_checkpoint(checkpoint)
    except (OSError, ValueError) as exc:
        print(f"ERROR: cannot read checkpoint {checkpoint}: {exc}", file=sys.stderr)
        return 2
    rows = run_jobs(jobs, caller, args.workers, done, checkpoint)
    resumed = len({job_key(r) for r in done} & {(j.entry, j.trial) for j in jobs})
    meta = build_meta(args, REPO_ROOT / args.corpus, len({j.entry for j in jobs}), usage, resumed)
    print(write_outputs(args, rows, meta, corpus))
    return 3 if rows and all(r.get("error") for r in rows) else 0


def main(
    argv: list[str] | None = None, caller: Caller | None = None, git: core.GitRun = git_run
) -> int:
    """`caller` and `git` are test seams. Production leaves both at their defaults."""
    args = parse_args(argv)
    if args.report_from:
        try:
            print(report.render_from_results(Path(args.report_from)))
        except (OSError, ValueError, KeyError) as exc:
            print(f"ERROR: cannot render {args.report_from}: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.rescore:
        return rescore(args)
    try:
        corpus, entries, reviews = prepare(args, git)
        jobs = plan_jobs(entries, reviews, args.trials)
        if args.validate_corpus:
            summary = validate(entries, reviews, jobs, git)
            print(json.dumps(summary, indent=2))
            return 2 if summary["leaks"] else 0
    except (core.CorpusError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps({"entries": len(entries), "planned_calls": len(jobs)}, indent=2))
        return 0
    return execute(args, jobs, corpus, caller, Usage())


if __name__ == "__main__":
    sys.exit(main())
