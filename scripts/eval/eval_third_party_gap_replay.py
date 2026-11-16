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
import math
import os
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
from _adr_catch_rate_stats import wilson_interval
from _anthropic_api import DEFAULT_MODEL, call_api, load_api_key_for_selected_provider

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


def load_checkpoint(path: Path | None) -> list[dict[str, Any]]:
    """Finished rows, one per (revision, trial). Errored rows are dropped so they rerun.

    Two runs that overlapped on one checkpoint can each write the same job. The
    first finished row is kept, so a duplicate never counts a defect twice.
    """
    if path is None or not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln]
    for index, line in enumerate(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                break  # a killed run can leave a half-written last line
            raise
        if not isinstance(row, dict) or "revision" not in row or "trial" not in row:
            raise ValueError(f"checkpoint {path} holds a line that is not a result row")
        key = (str(row["revision"]), int(row["trial"]))
        if not row.get("error") and key not in seen:
            seen.add(key)
            rows.append(row)
    return rows


def rescore(rows: list[dict[str, Any]], revisions: list[core.Revision]) -> list[dict[str, Any]]:
    by_id = {r.id: r for r in revisions}
    return [
        {**row, **core.score_revision(row["raw"], by_id[row["revision"]])}
        for row in rows
        if row["revision"] in by_id
    ]


def _rate(hits: int, total: int) -> dict[str, Any]:
    low, high = wilson_interval(hits, total) if total else (0.0, 0.0)
    return {"hits": hits, "n": total, "rate": hits / total if total else 0.0, "ci": [low, high]}


def aggregate(rows: list[dict[str, Any]], revisions: list[core.Revision]) -> dict[str, Any]:
    """Per-defect rates overall and by context, theme, and bot; per-review finding counts."""
    by_id = {r.id: r for r in revisions}
    cells: dict[str, dict[str, list[int]]] = {}

    def bump(group: str, key: str, caught: bool, same: bool) -> None:
        cell = cells.setdefault(group, {}).setdefault(key, [0, 0, 0])
        cell[0] += int(caught)
        cell[1] += int(same)
        cell[2] += 1

    for row in rows:
        rev = by_id[row["revision"]]
        for defect in rev.defects:
            got = row["defects"][defect.thread]
            for group, key in (
                ("all", "all"),
                ("context", defect.context),
                ("theme", defect.theme),
                ("bot", defect.bot),
            ):
                bump(group, key, got["caught"], got["same_file"])
    out: dict[str, Any] = {}
    for group, keyed in cells.items():
        out[group] = {
            key: {"caught": _rate(c, n), "same_file": _rate(s, n)}
            for key, (c, s, n) in sorted(keyed.items())
        }
    findings = [row["findings"] for row in rows]
    out["reviews"] = {
        "n": len(rows),
        "no_findings": sum(1 for row in rows if row["no_findings"]),
        "mean_findings": sum(findings) / len(findings) if findings else 0.0,
        "cut_at_ceiling": sum(1 for row in rows if row.get("finish_reason") == "length"),
        "output_tokens": sum(int(row.get("output_tokens") or 0) for row in rows),
    }
    return out


def output_tokens(metadata: dict[str, object]) -> int:
    """Output tokens from either transport's metadata shape, 0 when absent."""
    direct = metadata.get("output_tokens")
    if isinstance(direct, int):
        return direct
    usage = metadata.get("usage")
    nested = usage.get("completion_tokens") if isinstance(usage, dict) else None
    return nested if isinstance(nested, int) else 0


def mcnemar_exact_p(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p: a binomial test on the discordant pairs at p = 0.5."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail: float = sum(math.comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2**n
    return min(1.0, 2 * tail)


def compare(
    baseline: list[dict[str, Any]],
    treatment: list[dict[str, Any]],
    revisions: list[core.Revision],
) -> dict[str, Any]:
    """Pair the two arms by (revision, trial, defect) and test the caught difference.

    Only jobs both arms finished are paired, so an arm that ran further never
    gets credit for the extra jobs. ``context`` splits the same counts by the
    defect's ``context`` label.
    """
    contexts = {d.thread: d.context for r in revisions for d in r.defects}
    by_key = {(r["revision"], int(r["trial"])): r for r in treatment}
    cells: dict[str, dict[str, int]] = {}
    outcome = ("both", "baseline_only", "treatment_only", "neither")
    for row in baseline:
        other = by_key.get((row["revision"], int(row["trial"])))
        if other is None:
            continue
        for thread, got in row["defects"].items():
            mine, theirs = got["caught"], other["defects"][thread]["caught"]
            key = (
                "both"
                if mine and theirs
                else "baseline_only"
                if mine
                else ("treatment_only" if theirs else "neither")
            )
            for group in ("all", f"context:{contexts.get(thread, 'unknown')}"):
                cell = cells.setdefault(
                    group, dict.fromkeys((*outcome, "same_file_baseline", "same_file_treatment"), 0)
                )
                cell[key] += 1
                cell["same_file_baseline"] += int(got["same_file"])
                cell["same_file_treatment"] += int(other["defects"][thread]["same_file"])
    paired: dict[str, dict[str, Any]] = {}
    for group, cell in sorted(cells.items()):
        paired[group] = {
            **cell,
            "n": sum(cell[k] for k in outcome),
            "mcnemar_p": mcnemar_exact_p(cell["baseline_only"], cell["treatment_only"]),
        }
    return {"paired": paired}


RATE_LIMIT_WAITS_SECONDS = (60, 120, 300, 600, 900, 900, 900, 900)


def call_with_rate_limit_backoff(
    send: Callable[[], str], sleep: Callable[[float], None] = time.sleep
) -> str:
    """Retry only an HTTP 429, which the provider rejects before generating anything.

    A 429 costs no output tokens, so waiting it out is cheap. A timeout or any
    other failure may have been billed, so it is never retried here: it becomes
    an error row that a later run with the same checkpoint reruns on purpose.
    """
    for wait in RATE_LIMIT_WAITS_SECONDS:
        try:
            return send()
        except RuntimeError as exc:
            if "429" not in str(exc):
                raise
            sleep(wait)
    return send()


def make_caller(model: str, usage: dict[str, int]) -> Caller:
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
        return text, {"output_tokens": tokens, "finish_reason": metadata.get("finish_reason")}

    return call


def run(
    jobs: list[tuple[core.Revision, int, core.ReviewInput]],
    caller: Caller,
    workers: int,
    checkpoint: Path | None,
    done: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    finished = {(r["revision"], int(r["trial"])) for r in done}
    pending = [j for j in jobs if (j[0].id, j[1]) not in finished]
    lock = threading.Lock()

    def work(job: tuple[core.Revision, int, core.ReviewInput]) -> dict[str, Any]:
        rev, trial, review = job
        row: dict[str, Any] = {"revision": rev.id, "trial": trial}
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


def _meta(args: argparse.Namespace, corpus_path: Path, usage: dict[str, int]) -> dict[str, Any]:
    return {
        "model": args.model,
        "provider": os.environ.get("EVAL_PROVIDER") or "anthropic",
        "prompt_ref": args.prompt_ref or "worktree",
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
    if args.compare:
        if checkpoint is None:
            print("ERROR: --compare needs --checkpoint (the treatment arm)", file=sys.stderr)
            return 2
        try:
            baseline_rows = rescore(load_checkpoint(Path(args.compare)), revisions)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        result = compare(baseline_rows, rescore(done, revisions), revisions)
        return _emit(args, result, corpus_path, usage)
    if args.rescore:
        if checkpoint is None:
            print("ERROR: --rescore needs --checkpoint", file=sys.stderr)
            return 2
        result = aggregate(rescore(done, revisions), revisions)
        return _emit(args, result, corpus_path, usage)
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
    if args.dry_run:
        print(json.dumps({"revisions": len(revisions), "planned_calls": len(jobs)}))
        return 0
    if caller is None:
        try:
            caller = make_caller(args.model, usage)
        except RuntimeError as exc:
            print(f"ERROR loading credentials: {exc}", file=sys.stderr)
            return 2
    rows = run(jobs, caller, args.workers, checkpoint, done)
    scored = [r for r in rows if not r.get("error")]
    if rows and not scored:
        print("ERROR: every call failed", file=sys.stderr)
        return 3
    return _emit(args, aggregate(scored, revisions), corpus_path, usage)


def _emit(
    args: argparse.Namespace, result: dict[str, Any], corpus_path: Path, usage: dict[str, int]
) -> int:
    payload = {"meta": _meta(args, corpus_path, usage), "result": result}
    text = json.dumps(payload, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
