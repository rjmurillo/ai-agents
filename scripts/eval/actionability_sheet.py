"""The blinded labeling sheet and the merge of labels back into the corpus.

Plan tasks M1-T10 and M1-T11. Subcommands ``sheet`` and ``merge-labels`` of
``actionability_corpus.py``. The sheet carries only the fields a labeler may see
(``evals/comment-actionability/RUBRIC.md``), so no score, reviewer, reply, split, or
provenance reaches the person labeling.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval.actionability_io import load_jsonl, write_jsonl  # noqa: E402
from scripts.eval.actionability_labels import (  # noqa: E402
    DEFAULT_SEED,
    LABEL_UNSURE,
    VALID_LABELS,
)

MAX_NAMED_ROWS = 10

# The only keys a labeler may see (rubric: body, path, hunk). Premortem R3: the sheet is
# built from this list, never by copying a corpus row, so a new corpus field cannot leak.
SHEET_FIELDS = ("id", "path", "diff_hunk", "body")


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


def register_sheet_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Add the ``sheet`` and ``merge-labels`` subcommands to the corpus CLI."""
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
