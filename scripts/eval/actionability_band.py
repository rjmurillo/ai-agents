"""The fallback band policy for the comment actionability eval.

Plan task M1-T2. One home for what counts as "in the band" and where a comment sits in its
thread, so the measurement script and the corpus builder agree. The bounds mirror the
defaults of ``LLMFallbackConfig`` in ``scripts/llm_classification/config.py``
(``low_confidence_min`` 0.4, ``low_confidence_max`` 0.6), and
``tests/eval/test_actionability_band.py`` checks them against that class.

This module reads production types for annotations only, so importing it stays cheap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scripts.update_reviewer_signal_stats import CommentData

BAND_MIN = 0.4
BAND_MAX = 0.6

UNKNOWN_POSITION = -1


def thread_position(comment: CommentData) -> int:
    """Return the comment's index in its thread, or -1 when it cannot be found.

    ``CommentData`` carries no comment id, so the match is on body and
    creation time, the two fields the fetch returns for every node.
    """
    for index, node in enumerate(comment.thread_comments):
        if node.get("body", "") == comment.body and node.get("createdAt", "") == comment.created_at:
            return index
    return UNKNOWN_POSITION


def is_in_band(score: float) -> bool:
    """Return True when the heuristic score falls in the fallback band."""
    return BAND_MIN <= score <= BAND_MAX
