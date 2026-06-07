"""Deterministic commit-churn classification for PR cohort analysis.

Pure functions with no I/O and no LLM. Classify a commit message headline into
a churn bucket, aggregate a list of headlines into a histogram, and compute a
thrash fraction (non-progress share of commits).

Purpose: measure where the commits go in degenerate (high-commit) PRs versus a
control (low-commit) cohort, so that instruction and rule changes can be
evaluated against historical PR cohorts. A high validation/review/ci share with
a low progress share is the signature of process thrash that tighter context is
meant to reduce; a high merge_rebase share is long-lived-branch churn that
instructions cannot fix.

Classification is priority-ordered: the first bucket whose alternation matches
wins, so the order of ``_BUCKET_TOKENS`` is part of the contract. The buckets
and order were tuned on the rjmurillo/ai-agents degenerate cohort (13 PRs > 60
commits) and reproduce the published 50% validation_protocol share.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# Priority-ordered (first match wins). Each bucket is an alternation of
# case-insensitive regex tokens. Order is part of the contract: merge/revert
# outrank ci/lint, which outrank the generic progress markers.
_BUCKET_TOKENS: list[tuple[str, list[str]]] = [
    ("revert", [r"^revert\b", r"\brevert "]),
    (
        "merge_rebase",
        [
            r"^merge ",
            "merge branch",
            "merge remote",
            "merge main",
            "merge origin",
            r"resolve.*conflict",
            r"\brebase\b",
        ],
    ),
    (
        "ci_fix",
        [
            r"\bci\b",
            r"ci\(",
            r"fix.*workflow",
            r"workflow.*fix",
            r"\bgh[- ]?act\b",
            r"\brunner\b",
            "pipeline",
            r"fix.*action",
            r"unblock.*ci",
            r"fix.*build\b",
        ],
    ),
    (
        "lint_format",
        [
            r"\blint",
            "markdownlint",
            r"\bformat\b",
            "prettier",
            "whitespace",
            r"\bdash\b",
            r"style\(",
            "ruff",
            r"\bblack\b",
            "trailing",
        ],
    ),
    (
        "validation_protocol",
        [
            r"session[- ]?log",
            "protocol",
            r"pre[- ]?pr",
            "validation",
            "validate",
            "compliance",
            "handoff",
            r"\bsession\b",
            r"\bgate\b",
            r"fix.*hook",
        ],
    ),
    (
        "review_response",
        [
            "address",
            "review",
            "feedback",
            "copilot",
            "coderabbit",
            "cursor",
            "gemini",
            r"\bnit\b",
            r"review[- ]?thread",
            r"resolve.*comment",
            r"apply.*suggestion",
        ],
    ),
    ("test_fix", [r"\btest", "pytest", "pester", "flaky", "coverage", "fixture"]),
    ("deps", [r"\bdeps?\b", "dependency", "bump", "renovate"]),
    (
        "progress",
        [
            r"^feat",
            r"feat\(",
            r"^add ",
            "implement",
            r"^create",
            "initial",
            r"^refactor",
            r"refactor\(",
            r"^perf",
            r"perf\(",
            r"^docs",
            r"docs\(",
            "support",
        ],
    ),
]

_RULES: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile("|".join(tokens), re.IGNORECASE)) for name, tokens in _BUCKET_TOKENS
]

# Public list of buckets a headline can land in, in priority order, plus the
# residual "other".
CHURN_BUCKETS: list[str] = [name for name, _ in _BUCKET_TOKENS] + ["other"]


def classify(headline: str) -> str:
    """Classify one commit message headline into a churn bucket.

    Returns the first matching bucket name in priority order, or "other" when no
    rule matches.
    """
    for name, pattern in _RULES:
        if pattern.search(headline):
            return name
    return "other"


def histogram(headlines: Sequence[str]) -> dict[str, int]:
    """Count headlines per bucket. Buckets with zero count are omitted."""
    counts: dict[str, int] = {}
    for headline in headlines:
        bucket = classify(headline)
        counts[bucket] = counts.get(bucket, 0) + 1
    return counts


def thrash_fraction(headlines: Sequence[str]) -> float:
    """Non-progress share of commits, rounded to 3 places.

    0.0 for an empty input. A value near 1.0 means almost every commit was
    process churn (validation, review, ci, merge) rather than feature progress.
    """
    total = len(headlines)
    if total == 0:
        return 0.0
    progress = histogram(headlines).get("progress", 0)
    return round((total - progress) / total, 3)
