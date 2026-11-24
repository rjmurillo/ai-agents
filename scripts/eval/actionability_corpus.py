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
    1 - Secret scan (sample or fetch-hunks) found a non-hex hit; nothing written
    2 - Bad argument or unreadable input
    3 - GitHub fetch failed
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval.actionability_io import atomic_write_text  # noqa: E402
from scripts.eval.actionability_labels import (  # noqa: E402
    LABEL_UNSURE,
    SPLIT_DEV,
    SPLIT_HELDOUT,
    SPLIT_OUTSIDE,
    VALID_LABELS,
)
from scripts.eval.measure_actionability_band import (  # noqa: E402
    UNKNOWN_POSITION,
    is_in_band,
    thread_position,
)
from scripts.github_core.api import gh_graphql  # noqa: E402
from scripts.redact_secrets import redact  # noqa: E402
from scripts.update_reviewer_signal_stats import (  # noqa: E402
    CommentData,
    get_actionability_score,
    get_comments_by_reviewer,
)

logger = logging.getLogger(__name__)

DEFAULT_SEED = 20261124
HEX_SECRET_REASON = "hex-secret"


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


def utc_now_iso() -> str:
    """Return the current UTC time. Patched in tests so output stays byte-stable."""
    return datetime.now(UTC).isoformat(timespec="seconds")


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


def load_jsonl(path: Path) -> list[dict[str, Any]] | None:
    """Return the JSON objects in ``path``, one per line, or None after logging why not."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Cannot read %s: %s", path, exc)
        return None
    if not all(isinstance(row, dict) for row in rows):
        logger.error("%s must hold one JSON object per line", path)
        return None
    return rows


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


def _scannable_texts(row: dict[str, Any]) -> list[str]:
    hunk = row.get("diff_hunk")
    return [row["body"], *row["thread_replies"], *([hunk] if hunk is not None else [])]


def scan_secrets(rows: list[dict[str, Any]]) -> tuple[dict[str, list[str]], list[str]]:
    """Scan bodies, replies, and diff hunks. Return (non-hex hits by row id, hex-only ids).

    Only reason names are returned, never the matched text. A null ``diff_hunk``
    is skipped, so the same scan serves ``sample`` and ``fetch-hunks``.
    """
    failures: dict[str, list[str]] = {}
    hex_only: list[str] = []
    for row in rows:
        reasons: set[str] = set()
        for text in _scannable_texts(row):
            reasons.update(redact(text).reasons)
        non_hex = sorted(reasons - {HEX_SECRET_REASON})
        if non_hex:
            failures[row["id"]] = non_hex
        elif reasons:
            hex_only.append(row["id"])
    return failures, hex_only


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    atomic_write_text(path, text)


def _warn_shortfall(name: str, available: int, requested: int) -> None:
    if available < requested:
        print(
            f"warning: {name} stratum has {available} rows, {requested} requested; taking all",
            file=sys.stderr,
        )


def _report_secret_scan(rows: list[dict[str, Any]]) -> bool:
    """Print scan results to stderr. Return True when the corpus may be written."""
    failures, hex_only = scan_secrets(rows)
    for row_id, reasons in sorted(failures.items()):
        print(f"secret scan: row {row_id}: {', '.join(reasons)}", file=sys.stderr)
    if hex_only:
        print(f"review: hex-like strings in rows {', '.join(hex_only)}", file=sys.stderr)
    return not failures


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

    if not _report_secret_scan(corpus):
        return 1
    write_jsonl(args.output, corpus)
    print(
        f"sampled {len(band)} band, {len(outside)} outside of {len(rows)} candidates; "
        f"skipped unknown_position {skipped.unknown_position}, "
        f"duplicate_id {skipped.duplicate_id}, missing_id {skipped.missing_id}"
    )
    return 0


def _fetch_hunk(node_id: str) -> str | None:
    """Return the diff hunk for one review comment node, or None when it has none."""
    data = gh_graphql(_HUNK_QUERY, {"id": node_id})
    node = data.get("node")
    hunk = node.get("diffHunk") if isinstance(node, dict) else None
    return hunk if isinstance(hunk, str) and hunk else None


def cmd_fetch_hunks(args: argparse.Namespace) -> int:
    """Fill ``diff_hunk`` for rows that lack one, then secret-scan every row.

    Writes only when every call succeeds and the scan finds no non-hex hit.
    """
    rows = load_jsonl(args.corpus)
    if rows is None:
        return 2
    fetched = 0
    no_hunk = 0
    for row in rows:
        if row.get("diff_hunk") is not None:
            continue
        try:
            hunk = _fetch_hunk(row["id"])
        except RuntimeError as exc:
            print(f"fetch failed at row {row['id']}: {exc}", file=sys.stderr)
            return 3
        row["diff_hunk"] = hunk
        if hunk is None:
            no_hunk += 1
        else:
            fetched += 1
    if not _report_secret_scan(rows):
        return 1
    write_jsonl(args.output, rows)
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
    sample.set_defaults(handler=cmd_sample)

    hunks = sub.add_parser("fetch-hunks", help="Fetch the diff hunk for each row")
    hunks.add_argument("--corpus", type=Path, required=True, help="Corpus JSONL from sample")
    hunks.add_argument("--output", type=Path, required=True, help="Corpus JSONL to write")
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
