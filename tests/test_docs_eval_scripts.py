from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_SCRIPTS = REPO_ROOT / "docs" / "eval" / "scripts"


def test_parse_scores_requires_overall() -> None:
    original_path = sys.path.copy()
    sys.path.insert(0, str(EVAL_SCRIPTS))
    try:
        import evalkit  # noqa: PLC0415
    finally:
        sys.path[:] = original_path

    text = """
    {
      "cohesion": 7,
      "coupling": 7,
      "encapsulation": 7,
      "testability": 7,
      "non_redundancy": 7
    }
    """

    assert evalkit.parse_scores(text) is None


def test_parse_scores_requires_integer_values() -> None:
    original_path = sys.path.copy()
    sys.path.insert(0, str(EVAL_SCRIPTS))
    try:
        import evalkit  # noqa: PLC0415
    finally:
        sys.path[:] = original_path

    text = """
    {
      "cohesion": 7,
      "coupling": 7,
      "encapsulation": 7,
      "testability": 7,
      "non_redundancy": 7,
      "overall": null
    }
    """

    assert evalkit.parse_scores(text) is None
