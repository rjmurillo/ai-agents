"""Tests for council_review.py, the scored review loop's PR table."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "llm_council_support", Path(__file__).with_name("_support.py")
)
if _SUPPORT_SPEC is None or _SUPPORT_SPEC.loader is None:
    raise ImportError("llm-council _support.py is missing")
support = importlib.util.module_from_spec(_SUPPORT_SPEC)
_SUPPORT_SPEC.loader.exec_module(support)

review = support.load_script("council_review.py", "council_review_t")

MEMBERS = ["claude-opus-5.5", "gpt-6-sol", "claude-sonnet-5"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Findings...\nSCORE: 7/10\n", "7/10"),
        ("**SCORE:** 9 / 10", "9/10"),
        ("score: 8.5/10", "8.5/10"),
        ("SCORE: 6/10\nafter fixes\nSCORE: 9/10", "9/10"),
        ("SCORE: 11/10", ""),
        ("I would give it a 7", ""),
        ("", ""),
        # whole-line score, normalized value
        ("SCORE: 007/10", "7/10"),
        ("SCORE: 8.0000/10", "8/10"),
        ("SCORE: 8.50/10", "8.5/10"),
        ("SCORE: 10/10", "10/10"),
        ("SCORE: 0/10", "0/10"),
        ("**SCORE: 9/10**", "9/10"),
        ("__SCORE: 9/10__", "9/10"),
        ("  *SCORE:* 6/10  \r\n", "6/10"),
        ("SCORE: 6/10 **", "6/10"),
        # not a whole-line score
        ("SCORE: 8/10.5", ""),
        ("SCORE: 8/100", ""),
        ("SCORE: 8/10 (strong)", ""),
        ("SCORE: 8/10.", ""),
        ("Overall SCORE: 8/10", ""),
        ("SCORE: 8/10 and SCORE: 7/10", ""),
        ("SCORE: -1/10", ""),
        ("SCORE: 10.5/10", ""),
        # the last valid line wins, an invalid later line does not replace it
        ("SCORE: 4/10\nSCORE: 8/10.5", "4/10"),
    ],
)
def test_parse_score(text, expected):
    assert review.parse_score(text) == expected


def _write(review_dir, round_no, member, text):
    path = review_dir / f"round-{round_no}" / f"{review.member_slug(member)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_table_matches_the_upstream_shape_and_never_invents_a_score(tmp_path, capsys):
    _write(tmp_path, 1, "claude-opus-5.5", "SCORE: 7/10")
    _write(tmp_path, 1, "gpt-6-sol", "SCORE: 8/10")
    _write(tmp_path, 1, "claude-sonnet-5", "no number here")
    _write(tmp_path, 2, "claude-opus-5.5", "SCORE: 9/10")
    _write(tmp_path, 2, "gpt-6-sol", "SCORE: 10/10")

    code = review.main(["table", "--review-dir", str(tmp_path), "--members", ",".join(MEMBERS)])

    assert code == 0
    assert capsys.readouterr().out == (
        "## Council review\n\nRounds: 2\n\n"
        "| Delegate | Round 1 | Round 2 |\n"
        "| --- | --- | --- |\n"
        "| claude-opus-5.5 | 7/10 | 9/10 |\n"
        "| gpt-6-sol | 8/10 | 10/10 |\n"
        "| claude-sonnet-5 | no score | no score |\n"
    )


def test_rounds_sort_numerically(tmp_path):
    for n in (10, 2, 1):
        (tmp_path / f"round-{n}").mkdir()
    (tmp_path / "notes").mkdir()

    assert [p.name for p in review.round_dirs(tmp_path)] == ["round-1", "round-2", "round-10"]


def test_no_rounds_is_config_error(tmp_path, capsys):
    assert review.main(["table", "--review-dir", str(tmp_path), "--members", "a"]) == 2
    assert "no round-<n>" in capsys.readouterr().err


def test_missing_review_dir_is_config_error(tmp_path):
    assert review.main(["table", "--review-dir", str(tmp_path / "nope"), "--members", "a"]) == 2


def test_table_keeps_round_numbers_from_directory_names(tmp_path, capsys):
    _write(tmp_path, 1, "gpt-6-sol", "SCORE: 6/10")
    _write(tmp_path, 3, "gpt-6-sol", "SCORE: 9/10")

    review.main(["table", "--review-dir", str(tmp_path), "--members", "gpt-6-sol"])

    out = capsys.readouterr().out
    assert "| Delegate | Round 1 | Round 3 |" in out
    assert "| gpt-6-sol | 6/10 | 9/10 |" in out


def test_no_members_is_config_error(tmp_path, capsys):
    (tmp_path / "round-1").mkdir()

    assert review.main(["table", "--review-dir", str(tmp_path), "--members", ","]) == 2
    assert "no members" in capsys.readouterr().err


def test_member_file_name_replaces_slashes(tmp_path, capsys):
    _write(tmp_path, 1, "openai/gpt-4.1", "SCORE: 7/10")

    review.main(["table", "--review-dir", str(tmp_path), "--members", "openai/gpt-4.1"])

    assert (tmp_path / "round-1" / "openai_gpt-4.1.md").is_file()
    assert "| openai/gpt-4.1 | 7/10 |" in capsys.readouterr().out
