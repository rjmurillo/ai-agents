"""The pure parts of the collect-only stand-in for a cold pre-push run (issue #6200)."""

from __future__ import annotations

import pytest

from scripts.validation import pytest_deferral

TESTMON_FLAGS = ("--testmon", "--testmon-forceselect")


def test_the_collect_only_command_drops_testmon_and_keeps_everything_else() -> None:
    command = ["python", "-m", "pytest", "--testmon", "--testmon-forceselect", "-m", "x", "tests"]
    assert pytest_deferral.collect_only_command(command, TESTMON_FLAGS) == [
        "python",
        "-m",
        "pytest",
        "-m",
        "x",
        "tests",
        "--collect-only",
        "-qq",
        "-n",
        "0",
    ]


def test_a_command_without_testmon_flags_only_gains_the_collect_options() -> None:
    command = ["python", "-m", "pytest", "tests"]
    result = pytest_deferral.collect_only_command(command, TESTMON_FLAGS)
    assert result[: len(command)] == command
    assert result[len(command) :] == ["--collect-only", "-qq", "-n", "0"]


def test_the_original_command_is_not_mutated() -> None:
    command = ["pytest", "--testmon"]
    pytest_deferral.collect_only_command(command, TESTMON_FLAGS)
    assert command == ["pytest", "--testmon"]


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("100 tests collected in 0.08s\n", 100),
        ("1 test collected in 0.01s\n", 1),
        ("49595/49647 tests collected (52 deselected) in 43.55s\n", 49595),
        ("============ 49595/49647 tests collected (52 deselected) in 43.55s =====\n", 49595),
        ("no tests collected (20 deselected) in 0.06s\n", 0),
        ("no tests collected in 0.01s\n", 0),
        ("tests/a.py::t\ntests/b.py::t\n\n2 tests collected in 0.02s\n", 2),
        ("", None),
        ("Interrupted: 1 error during collection\n", None),
        ("collected 5 items\n", None),
    ],
)
def test_the_count_is_read_from_the_summary_line(output: str, expected: int | None) -> None:
    assert pytest_deferral.collected_count(output) == expected


def test_a_test_id_that_mentions_collection_is_not_a_summary() -> None:
    output = "tests/a.py::test_7_tests_collected_here\n3 tests collected in 1s\n"
    assert pytest_deferral.collected_count(output) == 3


@pytest.mark.parametrize(
    ("counts", "expected"),
    [([1, 2, 3], 6), ([], 0), ([0, 0], 0), ([5, None], None), ([None], None)],
)
def test_the_total_is_unknown_when_any_partition_is_unreadable(
    counts: list[int | None], expected: int | None
) -> None:
    assert pytest_deferral.total_collected(counts) == expected


def test_the_notice_names_the_count_the_ci_run_and_the_opt_in() -> None:
    notice = pytest_deferral.deferral_notice(49595, 180, "THE_OPT_IN")
    assert "all 49,595 tests" in notice
    assert "180s budget" in notice
    assert "CI runs every test" in notice
    assert "pytest.yml" in notice
    assert "pull request" in notice
    assert "every push" not in notice
    assert "THE_OPT_IN=1" in notice


def test_an_unknown_total_still_says_the_whole_suite_was_not_run() -> None:
    notice = pytest_deferral.deferral_notice(None, 150, "OPT_IN")
    assert "Not run locally: the whole suite" in notice
    assert "150s budget" in notice


def test_the_notice_uses_no_em_or_en_dash() -> None:
    notice = pytest_deferral.deferral_notice(10, 180, "OPT_IN")
    assert chr(0x2014) not in notice
    assert chr(0x2013) not in notice
