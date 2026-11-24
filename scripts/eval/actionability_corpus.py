#!/usr/bin/env python3
"""Build the labeled corpus for the comment actionability eval.

Plan tasks M1-T7 to M1-T10 of
``.project-toolkit/plans/active/harness-agnostic-llm-fallback.md``. The eval
method is in ``.project-toolkit/specs/SPEC-harness-agnostic-llm-fallback.md``.

Subcommands:
    sample       Draw a seeded, stratified corpus from saved PR nodes.
    fetch-hunks  Fill ``diff_hunk`` for each row from GitHub.
    sheet        Write the blinded labeling sheet.
    merge-labels Copy labels from the filled sheet back into the corpus.

Each row stores the heuristic score, reasons, and band flag computed once at
sampling time. Nothing downstream rescores: the heuristic reads the clock
(``update_reviewer_signal_stats.py``), so a later rescore could move a row in
or out of the band.

Usage:
    uv run python scripts/eval/actionability_corpus.py sample \\
        --prs .project-toolkit/scratch/band-prs.json --output corpus.jsonl

Exit codes (ADR-035):
    0 - Done
    1 - Secret scan (sample or fetch-hunks) found a blocking hit; nothing written
    2 - Bad argument or unreadable input
    3 - GitHub fetch failed
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval.actionability_io import (  # noqa: E402
    head_sha,
    load_jsonl,
    utc_now_iso,
    write_jsonl,
)
from scripts.eval.actionability_labels import (  # noqa: E402
    DEFAULT_SEED,
    HUNK_FETCHED,
    HUNK_NO_HUNK,
    LABEL_UNSURE,
    SPLIT_DEV,
    SPLIT_HELDOUT,
    SPLIT_OUTSIDE,
    VALID_LABELS,
)
from scripts.eval.actionability_scan import (  # noqa: E402
    add_allow_hex_argument,
    report_scan,
    scan_secrets,
)
from scripts.eval.measure_actionability_band import (  # noqa: E402
    UNKNOWN_POSITION,
    is_in_band,
    thread_position,
)
from scripts.github_core.api import gh_graphql  # noqa: E402
from scripts.update_reviewer_signal_stats import (  # noqa: E402
    CommentData,
    get_actionability_score,
    get_comments_by_reviewer,
)

logger = logging.getLogger(__name__)


MAX_NAMED_ROWS = 10

# The only keys a labeler may see (rubric: body, path, hunk). Premortem R3: the sheet is
# built from this list, never by copying a corpus row, so a new corpus field cannot leak.
SHEET_FIELDS = ("id", "path", "diff_hunk", "body")

# The id travels as a variable, never in the query text (ADR-015).
_HUNK_QUERY = "query($id: ID!) { node(id: $id) { ... on PullRequestReviewComment { diffHunk } } }"


@dataclass
class Skipped:
    """Comments left out of the candidate pool, by reason."""

    unknown_position: int = 0
    duplicate_id: int = 0
    missing_id: int = 0


def _load_json_list(path: Path) -> list[Any] | None:
    """Return the JSON array at ``path``, or None after logging why it cannot be read."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return None
    if not isinstance(data, list):
        logger.error("%s must hold a JSON array", path)
        return None
    return data


def _make_row(
    reviewer: str,
    comment: CommentData,
    position: int,
    sampled_at: str,
) -> dict[str, Any]:
    result = get_actionability_score(comment, llm_classifier=None)
    thread = comment.thread_comments
    return {
        "id": thread[position]["id"],
        "pr_number": comment.pr_number,
        "reviewer": reviewer,
        "thread_position": position,
        "path": comment.path,
        "body": comment.body,
        "created_at": comment.created_at,
        "thread_replies": [n.get("body", "") for i, n in enumerate(thread) if i != position],
        "heuristic_score": result.score,
        "heuristic_reasons": list(result.reasons),
        "in_band": is_in_band(result.score),
        "split": None,
        "diff_hunk": None,
        "hunk_status": None,
        "label": None,
        "sampled_at": sampled_at,
    }


def build_rows(prs: list[dict[str, Any]], sampled_at: str) -> tuple[list[dict[str, Any]], Skipped]:
    """Score every reviewer comment once and return rows plus what was skipped."""
    rows: list[dict[str, Any]] = []
    skipped = Skipped()
    seen_ids: set[str] = set()
    by_reviewer = get_comments_by_reviewer(prs)
    for reviewer in sorted(by_reviewer):
        for comment in by_reviewer[reviewer].comments:
            position = thread_position(comment)
            if position == UNKNOWN_POSITION:
                skipped.unknown_position += 1
                continue
            node_id = comment.thread_comments[position].get("id")
            if not node_id:
                skipped.missing_id += 1
                continue
            if node_id in seen_ids:
                skipped.duplicate_id += 1
                continue
            seen_ids.add(node_id)
            rows.append(_make_row(reviewer, comment, position, sampled_at))
    return rows, skipped


def _one_per_reviewer(
    rows: list[dict[str, Any]], count: int, rng: random.Random
) -> list[dict[str, Any]]:
    by_reviewer: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_reviewer.setdefault(row["reviewer"], []).append(row)
    reviewers = sorted(by_reviewer)
    if count < len(reviewers):
        reviewers = rng.sample(reviewers, count)
    picks = []
    for reviewer in reviewers:
        candidates = by_reviewer[reviewer]
        rng.shuffle(candidates)
        picks.append(candidates[0])
    return picks


def stratified_sample(
    rows: list[dict[str, Any]], count: int, rng: random.Random
) -> list[dict[str, Any]]:
    """Take one row per reviewer first, then fill the rest uniformly.

    A stratum with fewer rows than ``count`` returns every row.
    """
    if count >= len(rows):
        return list(rows)
    picks = _one_per_reviewer(rows, count, rng)
    picked_ids = {row["id"] for row in picks}
    pool = [row for row in rows if row["id"] not in picked_ids]
    return picks + rng.sample(pool, count - len(picks))


def assign_splits(
    band: list[dict[str, Any]],
    outside: list[dict[str, Any]],
    dev_count: int,
    rng: random.Random,
) -> None:
    """Mark ``dev_count`` band rows dev and the rest heldout. Outside rows are outside."""
    dev_indexes = set(rng.sample(range(len(band)), min(dev_count, len(band))))
    for index, row in enumerate(band):
        row["split"] = SPLIT_DEV if index in dev_indexes else SPLIT_HELDOUT
    for row in outside:
        row["split"] = SPLIT_OUTSIDE


def _warn_shortfall(name: str, available: int, requested: int) -> None:
    if available < requested:
        print(
            f"warning: {name} stratum has {available} rows, {requested} requested; taking all",
            file=sys.stderr,
        )


def _sample_args_valid(args: argparse.Namespace) -> bool:
    counts = (args.band_count, args.outside_count, args.dev_count)
    if any(count < 0 for count in counts):
        logger.error("--band-count, --outside-count, and --dev-count must be 0 or more")
        return False
    return True


def cmd_sample(args: argparse.Namespace) -> int:
    """Draw the corpus and write it unless the secret scan fails."""
    if not _sample_args_valid(args):
        return 2
    prs = _load_json_list(args.prs)
    if prs is None:
        return 2

    rows, skipped = build_rows(prs, utc_now_iso())
    rng = random.Random(args.seed)
    band_pool = [r for r in rows if r["in_band"]]
    outside_pool = [r for r in rows if not r["in_band"]]
    _warn_shortfall("band", len(band_pool), args.band_count)
    _warn_shortfall(SPLIT_OUTSIDE, len(outside_pool), args.outside_count)
    band = stratified_sample(band_pool, args.band_count, rng)
    outside = stratified_sample(outside_pool, args.outside_count, rng)
    assign_splits(band, outside, args.dev_count, rng)
    corpus = band + outside
    head = head_sha()
    for row in corpus:
        row["corpus_seed"] = args.seed
        row["corpus_head_sha"] = head

    if not report_scan(scan_secrets(corpus, allow_hex_rows=args.allow_hex_rows)):
        return 1
    write_jsonl(args.output, corpus)
    print(
        f"sampled {len(band)} band, {len(outside)} outside of {len(rows)} candidates; "
        f"skipped unknown_position {skipped.unknown_position}, "
        f"duplicate_id {skipped.duplicate_id}, missing_id {skipped.missing_id}; "
        f"seed {args.seed}, head {head}"
    )
    return 0


def _fetch_hunk(node_id: str) -> str | None:
    """Return the diff hunk for one review comment node, or None when it has none."""
    data = gh_graphql(_HUNK_QUERY, {"id": node_id})
    node = data.get("node")
    hunk = node.get("diffHunk") if isinstance(node, dict) else None
    return hunk if isinstance(hunk, str) and hunk else None


# What a failed gh call can raise: a GraphQL error, a timeout, or a missing or blocked binary.
_FETCH_ERRORS = (RuntimeError, subprocess.TimeoutExpired, OSError)


def _hunk_status(row: dict[str, Any]) -> str | None:
    """Return the row's hunk outcome. A hunk with no recorded status counts as fetched."""
    status = row.get("hunk_status")
    if status is None and row.get("diff_hunk") is not None:
        return HUNK_FETCHED
    return status if status in (HUNK_FETCHED, HUNK_NO_HUNK) else None


def _fetch_pending(rows: list[dict[str, Any]]) -> tuple[int, int, tuple[str, str] | None]:
    """Fetch the hunk for each unresolved row, stopping at the first transport failure.

    Returns (fetched, no_hunk, failure) where failure is (row id, exception class name).
    The exception text is dropped: GraphQL errors can embed response bodies.
    """
    fetched = no_hunk = 0
    for row in rows:
        row["hunk_status"] = _hunk_status(row)
    for row in rows:
        if row["hunk_status"] is not None:
            continue
        try:
            hunk = _fetch_hunk(row["id"])
        except _FETCH_ERRORS as exc:
            return fetched, no_hunk, (row["id"], type(exc).__name__)
        row["diff_hunk"] = hunk
        row["hunk_status"] = HUNK_FETCHED if hunk is not None else HUNK_NO_HUNK
        fetched += hunk is not None
        no_hunk += hunk is None
    return fetched, no_hunk, None


def cmd_fetch_hunks(args: argparse.Namespace) -> int:
    """Fill ``diff_hunk`` for unresolved rows, secret-scan every row, then write.

    The scan runs first and blocks the write: a row that fails it is never written, on
    success or on abort. When a call fails, the rows resolved so far are written (after the
    scan passes) so a rerun on the output resumes. ``fetched k of N`` counts rows whose hunk
    status is resolved, whether fetched or confirmed to have none.
    """
    rows = load_jsonl(args.corpus)
    if rows is None:
        return 2
    fetched, no_hunk, failure = _fetch_pending(rows)
    resolved = sum(1 for row in rows if row["hunk_status"] is not None)
    if failure is not None:
        print(f"fetch failed at row {failure[0]}: {failure[1]}", file=sys.stderr)
    if not report_scan(scan_secrets(rows, allow_hex_rows=args.allow_hex_rows)):
        print(f"fetched {resolved} of {len(rows)} rows; nothing written", file=sys.stderr)
        return 1
    write_jsonl(args.output, rows)
    if failure is not None:
        print(f"fetched {resolved} of {len(rows)} rows; partial output written", file=sys.stderr)
        return 3
    print(f"fetched {fetched}, no_hunk {no_hunk}, of {len(rows)} rows")
    return 0


def cmd_sheet(args: argparse.Namespace) -> int:
    """Write the blinded labeling sheet: allowlisted fields, seeded shuffle, blank labels."""
    rows = load_jsonl(args.corpus)
    if rows is None:
        return 2
    sheet = [{**{key: row.get(key) for key in SHEET_FIELDS}, "label": None} for row in rows]
    random.Random(args.seed).shuffle(sheet)
    write_jsonl(args.output, sheet)
    print(f"wrote {len(sheet)} rows with fields {', '.join([*SHEET_FIELDS, 'label'])}")
    return 0


def _read_sheet_labels(sheet: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    """Return the label per sheet id, plus the problems found while reading the sheet."""
    labels: dict[str, Any] = {}
    invalid: list[str] = []
    no_id = duplicates = 0
    for row in sheet:
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id:
            no_id += 1
        elif row_id in labels:
            duplicates += 1
        else:
            label = row.get("label")
            labels[row_id] = label
            if label is not None and not (isinstance(label, str) and label in VALID_LABELS):
                invalid.append(row_id)
    problems = []
    if no_id:
        problems.append(f"{no_id} sheet rows without an id")
    if duplicates:
        problems.append(f"{duplicates} duplicate sheet ids")
    if invalid:
        named = ", ".join(invalid[:MAX_NAMED_ROWS])
        more = f" and {len(invalid) - MAX_NAMED_ROWS} more" if len(invalid) > MAX_NAMED_ROWS else ""
        problems.append(
            f"invalid label on rows {named}{more}; use {', '.join(VALID_LABELS)} or null"
        )
    return labels, problems


def _join_problems(corpus: list[dict[str, Any]], labels: dict[str, Any]) -> list[str]:
    corpus_ids = [row.get("id") for row in corpus]
    problems = []
    if not all(isinstance(i, str) and i for i in corpus_ids):
        problems.append("corpus rows without an id")
    if len(set(corpus_ids)) != len(corpus_ids):
        problems.append("duplicate corpus ids")
    known = set(corpus_ids)
    unknown = sum(1 for i in labels if i not in known)
    if unknown:
        problems.append(f"{unknown} sheet ids not in the corpus")
    missing = sum(1 for i in corpus_ids if i not in labels)
    if missing:
        problems.append(f"{missing} corpus ids missing from the sheet")
    return problems


def cmd_merge_labels(args: argparse.Namespace) -> int:
    """Copy ``label`` from the sheet into the corpus by id. Take no other sheet field."""
    corpus = load_jsonl(args.corpus)
    sheet = load_jsonl(args.sheet)
    if corpus is None or sheet is None:
        return 2
    labels, problems = _read_sheet_labels(sheet)
    problems += _join_problems(corpus, labels)
    if problems:
        for problem in problems:
            print(f"merge-labels: {problem}", file=sys.stderr)
        return 2
    merged = [{**row, "label": labels[row["id"]]} for row in corpus]
    write_jsonl(args.output, merged)
    kept = [row["label"] for row in merged]
    unsure = kept.count(LABEL_UNSURE)
    unlabeled = kept.count(None)
    print(f"merged {len(kept) - unsure - unlabeled} labels, unlabeled {unlabeled}, unsure {unsure}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("sample", help="Draw a seeded, stratified corpus")
    sample.add_argument("--prs", type=Path, required=True, help="JSON array of PR nodes")
    sample.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sample.add_argument("--band-count", type=int, default=100)
    sample.add_argument("--outside-count", type=int, default=100)
    sample.add_argument("--dev-count", type=int, default=40)
    sample.add_argument("--output", type=Path, required=True, help="Corpus JSONL to write")
    add_allow_hex_argument(sample)
    sample.set_defaults(handler=cmd_sample)

    hunks = sub.add_parser("fetch-hunks", help="Fetch the diff hunk for each row")
    hunks.add_argument("--corpus", type=Path, required=True, help="Corpus JSONL from sample")
    hunks.add_argument("--output", type=Path, required=True, help="Corpus JSONL to write")
    add_allow_hex_argument(hunks)
    hunks.set_defaults(handler=cmd_fetch_hunks)

    sheet = sub.add_parser("sheet", help="Write the blinded labeling sheet")
    sheet.add_argument("--corpus", type=Path, required=True, help="Corpus JSONL")
    sheet.add_argument("--output", type=Path, required=True, help="Sheet JSONL to write")
    sheet.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sheet.set_defaults(handler=cmd_sheet)

    merge = sub.add_parser("merge-labels", help="Copy labels from the sheet into the corpus")
    merge.add_argument("--corpus", type=Path, required=True, help="Corpus JSONL")
    merge.add_argument("--sheet", type=Path, required=True, help="Labeled sheet JSONL")
    merge.add_argument("--output", type=Path, required=True, help="Labeled corpus JSONL to write")
    merge.set_defaults(handler=cmd_merge_labels)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    args = _build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
