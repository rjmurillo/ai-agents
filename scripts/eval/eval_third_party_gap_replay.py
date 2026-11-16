#!/usr/bin/env python3
"""Replay third-party-caught defects against this repository's own reviewer.

For each corpus revision the reviewer sees the pull request diff at the head a
third-party bot reviewed (merge base to reviewed commit) and nothing else. A
defect counts as caught when a top-10 finding names its file and a line within
10 of the bot's line. The reviewer prompt is the `code-reviewer` agent template
plus the `technical-review.md` contract, read at `--prompt-ref` (a git ref) or
from the working tree. Two runs that differ only in `--prompt-ref` measure a
prompt change; two runs at the same ref measure noise.

Corpus: evals/third-party-review-gap/replay-corpus.json. Method and limits:
evals/third-party-review-gap/README.md.

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
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _adr_catch_rate_core as adr_core
import _code_review_catch_rate_core as cr_core
import _third_party_gap_core as core
from _anthropic_api import DEFAULT_MODEL, call_api, load_api_key_for_selected_provider
from _eval_api_adapter_constants import http_timeout_seconds
from _third_party_gap_checkpoint import (
    STAMP_KEYS,
    input_mismatch,
    input_sha256,
    load_checkpoint,
    repair_tail,
    stamp_mismatch,
)
from _third_party_gap_report import aggregate, compare

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = "evals/third-party-review-gap/replay-corpus.json"
AGENT_TEMPLATE = "templates/agents/code-reviewer.shared.md"
CONTRACT_PATH = "src/claude/skills/review/resources/technical-review.md"
# Not a budget. The transport requires a value, so this is the model's output
# ceiling: answers are never cut to save tokens, because a cut answer costs a
# rerun. Each row records its output tokens and finish reason instead.
MAX_TOKENS = 64000

# (system, user) -> (answer text, {"output_tokens": int, "finish_reason": str | None})
Caller = Callable[[str, str], tuple[str, dict[str, Any]]]


def git_run(args: tuple[str, ...]) -> str | None:
    """Git stdout, or None on a non-zero exit, a timeout, or a missing git binary."""
    try:
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
    except (subprocess.SubprocessError, OSError):
        return None
    return result.stdout if result.returncode == 0 else None


def read_prompt_file(rel: str, ref: str | None, git: core.GitRun) -> str:
    if ref is None:
        return (REPO_ROOT / rel).read_text(encoding="utf-8")
    text: str | None = git(("show", f"{ref}:{rel}"))
    if text is None:
        raise core.CorpusError(f"cannot read {rel} at {ref}")
    return text


def load_system_prompt(ref: str | None, git: core.GitRun) -> str:
    agent = adr_core.strip_frontmatter(read_prompt_file(AGENT_TEMPLATE, ref, git))
    contract = read_prompt_file(CONTRACT_PATH, ref, git)
    prompt: str = cr_core.build_system_prompt(agent, contract)
    return prompt


def select(revisions: tuple[core.Revision, ...], split: str, ids: str) -> list[core.Revision]:
    chosen = [r for r in revisions if split == "all" or r.split == split]
    wanted = {i.strip() for i in ids.split(",") if i.strip()}
    if wanted:
        unknown = wanted - {r.id for r in revisions}
        if unknown:
            raise core.CorpusError(f"unknown revision id: {', '.join(sorted(unknown))}")
        chosen = [r for r in chosen if r.id in wanted]
    if not chosen:
        raise core.CorpusError("no revision selected")
    return chosen


def rescore(rows: list[dict[str, Any]], revisions: list[core.Revision]) -> list[dict[str, Any]]:
    by_id = {r.id: r for r in revisions}
    return [
        {**row, **core.score_revision(row["raw"], by_id[row["revision"]])}
        for row in rows
        if row["revision"] in by_id
    ]


def output_tokens(metadata: dict[str, object]) -> int:
    """Output tokens from either transport's metadata shape, 0 when absent."""
    direct = metadata.get("output_tokens")
    if isinstance(direct, int):
        return direct
    usage = metadata.get("usage")
    nested = usage.get("completion_tokens") if isinstance(usage, dict) else None
    return nested if isinstance(nested, int) else 0


# The transports report a rate limit as "HTTP 429". A bare "429" can appear in
# other text (a timeout value, a token count), so match the status phrase only.
RATE_LIMITED = re.compile(r"\bHTTP 429\b")
# Set once any job exhausts the wait schedule; later jobs then fail at once
# instead of each sleeping through the whole schedule again.
RATE_LIMIT_EXHAUSTED = threading.Event()
RATE_LIMIT_WAITS_SECONDS = (60, 120, 300, 600, 900, 900, 900, 900)


def call_with_rate_limit_backoff(
    send: Callable[[], str], sleep: Callable[[float], None] = time.sleep
) -> str:
    """Retry only an HTTP 429, which the provider rejects before generating anything.

    A 429 costs no output tokens, so waiting it out is cheap. A timeout or any
    other failure may have been billed, so it is never retried here: it becomes
    an error row that a later run with the same checkpoint reruns on purpose.
    """
    if RATE_LIMIT_EXHAUSTED.is_set():
        raise RuntimeError("rate limit schedule already exhausted by another job; not calling")
    for attempt, wait in enumerate(RATE_LIMIT_WAITS_SECONDS, 1):
        try:
            return send()
        except RuntimeError as exc:
            if not RATE_LIMITED.search(str(exc)):
                raise
            print(f"rate limited (HTTP 429), attempt {attempt}: waiting {wait}s", file=sys.stderr)
            sleep(wait)
    try:
        return send()
    except RuntimeError as exc:
        if RATE_LIMITED.search(str(exc)):
            RATE_LIMIT_EXHAUSTED.set()
        raise


def finish_reason(metadata: dict[str, object]) -> str | None:
    """The provider's finish reason; an Anthropic token-limit stop reads as ``length``.

    The default provider reports ``stop_reason`` and ``termination``, not
    ``finish_reason``, so a truncated answer would otherwise not count as cut at
    the ceiling. ``termination == "token_limit"`` covers every token-limit stop.
    """
    reason = metadata.get("finish_reason")
    token_limit = metadata.get("termination") == "token_limit"
    if reason is None and (token_limit or metadata.get("stop_reason") == "max_tokens"):
        return "length"
    return reason if isinstance(reason, str) else None


def make_caller(model: str, usage: dict[str, int]) -> Caller:
    # Read the timeout setting once, so a bad value is a config error before any call.
    http_timeout_seconds()
    api_key = load_api_key_for_selected_provider()
    lock = threading.Lock()

    def call(system: str, user: str) -> tuple[str, dict[str, Any]]:
        metadata: dict[str, object] = {}
        text: str = call_with_rate_limit_backoff(
            lambda: call_api(
                api_key,
                [{"role": "user", "content": user}],
                system=system,
                model=model,
                max_tokens=MAX_TOKENS,
                metadata=metadata,
            )
        )
        tokens = output_tokens(metadata)
        with lock:
            usage["calls"] += 1
            usage["output_tokens"] += tokens
        return text, {"output_tokens": tokens, "finish_reason": finish_reason(metadata)}

    return call


def run(
    jobs: list[tuple[core.Revision, int, core.ReviewInput]],
    caller: Caller,
    workers: int,
    checkpoint: Path | None,
    done: list[dict[str, Any]],
    stamp: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Run pending jobs. ``stamp`` (prompt ref, model, provider) is written on every row."""
    finished = {(r["revision"], int(r["trial"])) for r in done}
    pending = [j for j in jobs if (j[0].id, j[1]) not in finished]
    lock = threading.Lock()

    def work(job: tuple[core.Revision, int, core.ReviewInput]) -> dict[str, Any]:
        rev, trial, review = job
        row: dict[str, Any] = {"revision": rev.id, "trial": trial, **(stamp or {})}
        row["input_sha256"] = input_sha256(review.system, review.user)
        try:
            raw, call_meta = caller(review.system, review.user)
            row.update(raw=raw, **call_meta, **core.score_revision(raw, rev))
        except RuntimeError as exc:
            row["error"] = str(exc)[:300]
        if checkpoint is not None:
            with lock, checkpoint.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
        return row

    wanted = {(j[0].id, j[1]) for j in jobs}
    by_id = {j[0].id: j[0] for j in jobs}
    # Score kept rows again from their stored answer, so a corpus edit between
    # runs never mixes old scores with new defects.
    kept = [
        {**r, **core.score_revision(r["raw"], by_id[r["revision"]])}
        for r in done
        if (r["revision"], int(r["trial"])) in wanted
    ]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return kept + list(pool.map(work, pending))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--corpus", default=DEFAULT_CORPUS)
    parser.add_argument("--split", choices=("derive", "heldout", "all"), default="heldout")
    parser.add_argument("--revisions", default="", help="comma list of revision ids")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--prompt-ref", default=None, help="git ref for the reviewer prompt; default worktree"
    )
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--output", default=None, help="write aggregate JSON here")
    parser.add_argument("--rescore", action="store_true", help="score --checkpoint; no call")
    parser.add_argument(
        "--compare",
        default=None,
        help="baseline checkpoint; pair it with --checkpoint (treatment) by job; no call",
    )
    parser.add_argument("--validate-corpus", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.trials < 1:
        parser.error("--trials must be at least 1")
    return args


def _titles(revisions: list[core.Revision], corpus_raw: dict[str, Any]) -> dict[str, str]:
    raw = {r["id"]: r.get("title", "") for r in corpus_raw["revisions"]}
    return {r.id: str(raw.get(r.id, "")) for r in revisions}


def run_stamp(args: argparse.Namespace) -> dict[str, str]:
    return {
        "prompt_ref": args.prompt_ref or "worktree",
        "model": args.model,
        "provider": os.environ.get("EVAL_PROVIDER") or "anthropic",
    }


def rebuilt_meta(
    args: argparse.Namespace, corpus_path: Path, sources: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    """Meta for --rescore and --compare, which make no model call.

    Run parameters come from the rows, never from this invocation's flags, so a
    rebuilt result cannot claim a model, provider, or prompt it did not use.
    """
    arms = {}
    for name, rows in sources.items():
        arms[name] = {
            "rows": len(rows),
            "output_tokens": sum(int(r.get("output_tokens") or 0) for r in rows),
            **{k: sorted({str(r.get(k, "not recorded")) for r in rows}) for k in STAMP_KEYS},
        }
    return {
        "rebuilt_from_checkpoint": True,
        "split": args.split,
        "date": datetime.date.today().isoformat(),
        "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        "arms": arms,
    }


def _meta(args: argparse.Namespace, corpus_path: Path, usage: dict[str, int]) -> dict[str, Any]:
    return {
        **run_stamp(args),
        "split": args.split,
        "trials": args.trials,
        "date": datetime.date.today().isoformat(),
        "corpus_sha256": hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        **usage,
    }


def main(
    argv: list[str] | None = None, caller: Caller | None = None, git: core.GitRun = git_run
) -> int:
    """`caller` and `git` are test seams."""
    args = parse_args(argv)
    corpus_path = REPO_ROOT / args.corpus
    checkpoint = Path(args.checkpoint) if args.checkpoint else None
    try:
        _, revisions_all = core.load_corpus(corpus_path)
        corpus_raw = json.loads(corpus_path.read_text(encoding="utf-8"))
        revisions = select(revisions_all, args.split, args.revisions)
        done = load_checkpoint(checkpoint)
    except (core.CorpusError, OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    usage = {"calls": 0, "output_tokens": 0}
    if args.compare or args.rescore:
        return _offline(args, checkpoint, done, revisions, corpus_path)
    try:
        system = load_system_prompt(args.prompt_ref, git)
        titles = _titles(revisions, corpus_raw)
        reviews = {r.id: core.build_review_input(r, titles[r.id], system, git) for r in revisions}
        if args.validate_corpus:
            leaks = {r.id: x for r in revisions if (x := core.check_no_leak(r, reviews[r.id], git))}
            print(json.dumps({"revisions": len(revisions), "leaks": leaks}, indent=2))
            return 2 if leaks else 0
    except (core.CorpusError, OSError, UnicodeDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    jobs = [(r, t, reviews[r.id]) for r in revisions for t in range(args.trials)]
    stamp = run_stamp(args)
    expected = {(r.id, t): input_sha256(v.system, v.user) for r, t, v in jobs}
    if (mismatch := stamp_mismatch(done, stamp) or input_mismatch(done, expected)) is not None:
        print(f"ERROR: {mismatch}", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps({"revisions": len(revisions), "planned_calls": len(jobs)}))
        return 0
    if caller is None:
        try:
            caller = make_caller(args.model, usage)
        except RuntimeError as exc:
            print(f"ERROR loading credentials: {exc}", file=sys.stderr)
            return 2
    if checkpoint is not None:
        repair_tail(checkpoint)
    rows = run(jobs, caller, args.workers, checkpoint, done, stamp)
    return _finish(args, rows, revisions, corpus_path, usage)


def _offline(
    args: argparse.Namespace,
    checkpoint: Path | None,
    done: list[dict[str, Any]],
    revisions: list[core.Revision],
    corpus_path: Path,
) -> int:
    """--compare and --rescore: score stored answers, call no model.

    A model run may start from no checkpoint; scoring needs every file to exist,
    or a typo would score an empty arm and exit 0.
    """
    inputs = [checkpoint] + ([Path(args.compare)] if args.compare else [])
    absent = [str(p) for p in inputs if p is None or not p.is_file()]
    if absent:
        mode = "--compare" if args.compare else "--rescore"
        print(f"ERROR: {mode} needs existing checkpoint files; missing {absent}", file=sys.stderr)
        return 2
    usage = {"calls": 0, "output_tokens": 0}
    if not args.compare:
        rescored = rescore(done, revisions)
        result = aggregate(rescored, revisions)
        return _emit(args, result, corpus_path, usage, {"checkpoint": rescored})
    try:
        baseline_rows = rescore(load_checkpoint(Path(args.compare)), revisions)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    treatment_rows = rescore(done, revisions)
    result = compare(baseline_rows, treatment_rows, revisions)
    sources = {"baseline": baseline_rows, "treatment": treatment_rows}
    return _emit(args, result, corpus_path, usage, sources)


def _finish(
    args: argparse.Namespace,
    rows: list[dict[str, Any]],
    revisions: list[core.Revision],
    corpus_path: Path,
    usage: dict[str, int],
) -> int:
    """Emit the result of a model run; any failed call makes the exit 3."""
    scored = [r for r in rows if not r.get("error")]
    failed = [r for r in rows if r.get("error")]
    if rows and not scored:
        print("ERROR: every call failed", file=sys.stderr)
        return 3
    result = aggregate(scored, revisions)
    result["errors"] = len(failed)
    _emit(args, result, corpus_path, usage)
    if failed:
        # A partial result must not read as complete: the failed jobs rerun from the checkpoint.
        print(
            f"ERROR: {len(failed)} of {len(rows)} call(s) failed; first: {failed[0]['error']}",
            file=sys.stderr,
        )
        return 3
    return 0


def _emit(
    args: argparse.Namespace,
    result: dict[str, Any],
    corpus_path: Path,
    usage: dict[str, int],
    sources: dict[str, list[dict[str, Any]]] | None = None,
) -> int:
    meta = rebuilt_meta(args, corpus_path, sources) if sources else _meta(args, corpus_path, usage)
    payload = {"meta": meta, "result": result}
    text = json.dumps(payload, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
