"""Secret scan for corpus rows, shared by sample, fetch-hunks, and predict.

Plan task M1-T9, premortem R4. Scans comment bodies, thread replies, and diff
hunks. Only row ids and reason names ever leave this module, never matched text.

A row is blocked when any of these fire:

* ``redact_ci_sink`` with assignment redaction on (``scripts/redact_secrets.py``):
  environment secrets, authorization headers, URL credentials, the base token
  shapes, emails, and ``credential-assignment``.
* A pattern in ``BLOCKING_PATTERNS``: vendor token shapes the base redactor lacks,
  and GitHub token families that follow an underscore, where the base rule's
  ``\\b`` does not match.
* A 32+ hex run whose length is not 40 or 64, unless the row id is named in
  ``--allow-hex-rows``.

Hex runs of exactly 40 or 64 characters are git object ids. They never block and
are reported by row id for review. A 32-hex run right after a known reviewer-bot
prefix is a public identifier and is counted, not reported (``_PUBLIC_HEX_ID_PREFIXES``).

Stricter than ``redact_secrets.redact``: that function flags every 32+ hex run, so
it fires on each quoted commit SHA. This scan allows the two git lengths.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from typing import Any

from scripts.redact_secrets import redact_ci_sink

HEX_SECRET_REASON = "hex-secret"
HEX_ALLOWED_LENGTHS = frozenset({40, 64})

# Public identifiers that reviewer bots embed in their comments. A hex run counts only
# when it is exactly this long and the text right before it ends with one of these
# prefixes, case and spacing included:
#   Devin review markers: <!-- devin-review-comment {"id": "BUG_pr-review-job-<32hex>"} -->
#   (also the ANALYSIS_ and SEC_ variants, which share the `pr-review-job-` suffix)
#   semgrep findings:     Syntactic id: <32hex>
# Checked against the saved PR comments in .project-toolkit/scratch/band-prs.json:
# 1,062 runs follow `pr-review-job-`, the rest follow `Syntactic id: `.
_PUBLIC_HEX_ID_LENGTH = 32
_PUBLIC_HEX_ID_PREFIXES = ("pr-review-job-", "Syntactic id: ")

# Same shape as the "hex-secret" rule in scripts/redact_secrets.py (`_RULES`).
# tests/eval/test_actionability_scan.py checks the two agree across lengths.
HEX_RUN = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])")

_NOT_ALNUM_BEFORE = r"(?<![A-Za-z0-9])"

# One table, one reason name per row. The lookbehind keeps prose such as "task-ant"
# or "mask-anthropic-keys" from matching inside a longer word.
BLOCKING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("anthropic-api-key", re.compile(_NOT_ALNUM_BEFORE + r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai-project-key", re.compile(_NOT_ALNUM_BEFORE + r"sk-proj-[A-Za-z0-9_-]{20,}")),
    ("openai-api-key", re.compile(_NOT_ALNUM_BEFORE + r"sk-[A-Za-z0-9]{20,}")),
    ("google-api-key", re.compile(_NOT_ALNUM_BEFORE + r"AIza[0-9A-Za-z_-]{35}(?![0-9A-Za-z_-])")),
    ("gitlab-pat", re.compile(_NOT_ALNUM_BEFORE + r"glpat-[A-Za-z0-9_-]{20,}")),
    ("npm-token", re.compile(_NOT_ALNUM_BEFORE + r"npm_[A-Za-z0-9]{36}(?![A-Za-z0-9])")),
    ("slack-token", re.compile(_NOT_ALNUM_BEFORE + r"xox[abpr]-[A-Za-z0-9-]{10,}")),
    (
        "sendgrid-api-key",
        re.compile(_NOT_ALNUM_BEFORE + r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}"),
    ),
    (
        "github-token-embedded",
        re.compile(_NOT_ALNUM_BEFORE + r"(?:ghp|ghs|gho|ghu|ghr)_[A-Za-z0-9]{36,}"),
    ),
    ("github-pat-embedded", re.compile(_NOT_ALNUM_BEFORE + r"github_pat_[A-Za-z0-9_]{22,}")),
)


@dataclass(frozen=True, slots=True)
class ScanResult:
    """What a scan found and how much it examined."""

    blocking: dict[str, list[str]]
    hex_reported: list[str]
    rows_scanned: int
    hunks_scanned: int
    public_ids: int = 0


def parse_allow_hex_rows(text: str) -> frozenset[str]:
    """Parse ``ID[,ID...]`` into a set of row ids. Blank items are dropped."""
    return frozenset(item.strip() for item in text.split(",") if item.strip())


def add_allow_hex_argument(parser: argparse.ArgumentParser) -> None:
    """Add ``--allow-hex-rows`` to a subcommand parser."""
    parser.add_argument(
        "--allow-hex-rows",
        type=parse_allow_hex_rows,
        default=frozenset(),
        metavar="ID[,ID...]",
        help="Rows whose non-git-length hex strings were reviewed. Excuses hex only.",
    )


def _row_texts(row: dict[str, Any], include_hunk: bool) -> list[str]:
    hunk = row.get("diff_hunk") if include_hunk else None
    return [row["body"], *row["thread_replies"], *([hunk] if hunk is not None else [])]


def _is_public_hex_id(text: str, run: re.Match[str]) -> bool:
    """True for a 32-hex run that directly follows a known reviewer-bot prefix."""
    return run.end() - run.start() == _PUBLIC_HEX_ID_LENGTH and text[: run.start()].endswith(
        _PUBLIC_HEX_ID_PREFIXES
    )


def _hex_runs(text: str) -> tuple[list[int], int]:
    """Return the lengths of the hex runs that need a verdict, and the public-id count."""
    lengths: list[int] = []
    public = 0
    for run in HEX_RUN.finditer(text):
        if _is_public_hex_id(text, run):
            public += 1
        else:
            lengths.append(run.end() - run.start())
    return lengths, public


def _text_reasons(text: str) -> set[str]:
    reasons = set(redact_ci_sink(text, redact_assignments=True).reasons)
    reasons.update(name for name, pattern in BLOCKING_PATTERNS if pattern.search(text))
    return reasons


def scan_secrets(
    rows: list[dict[str, Any]],
    *,
    allow_hex_rows: frozenset[str] = frozenset(),
    include_hunk: bool = True,
) -> ScanResult:
    """Scan every row. A null ``diff_hunk`` is skipped, as is any hunk when not requested."""
    blocking: dict[str, list[str]] = {}
    hex_reported: list[str] = []
    hunks = public_ids = 0
    for row in rows:
        texts = _row_texts(row, include_hunk)
        hunks += int(include_hunk and row.get("diff_hunk") is not None)
        reasons: set[str] = set()
        hex_lengths: list[int] = []
        for text in texts:
            reasons |= _text_reasons(text)
            lengths, public = _hex_runs(text)
            hex_lengths += lengths
            public_ids += public
        odd_hex = any(length not in HEX_ALLOWED_LENGTHS for length in hex_lengths)
        if odd_hex and row["id"] not in allow_hex_rows:
            reasons.add(HEX_SECRET_REASON)
        if reasons:
            blocking[row["id"]] = sorted(reasons)
        elif hex_lengths:
            hex_reported.append(row["id"])
    return ScanResult(blocking, hex_reported, len(rows), hunks, public_ids)


def report_scan(result: ScanResult) -> bool:
    """Print the scan outcome to stderr. Return True when nothing blocks.

    Names row ids and reason names only. Always prints the examined counts, so a
    clean scan of nothing reads differently from a clean scan of everything.
    """
    for row_id, reasons in sorted(result.blocking.items()):
        print(f"secret scan: row {row_id}: {', '.join(reasons)}", file=sys.stderr)
    if result.hex_reported:
        print(
            f"review: hex-like strings in rows {', '.join(result.hex_reported)}",
            file=sys.stderr,
        )
    print(
        f"scanned {result.rows_scanned} rows (+{result.hunks_scanned} hunks): "
        f"blocking {len(result.blocking)}, hex-reported {len(result.hex_reported)}, "
        f"public-id {result.public_ids}",
        file=sys.stderr,
    )
    return not result.blocking
