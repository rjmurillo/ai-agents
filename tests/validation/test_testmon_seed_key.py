"""The testmon seed artifact key and its command line (issue #6239)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import testmon_seed as seed
from tests.validation.testmon_seed_helpers import write_inputs


def test_the_key_is_stable_for_unchanged_inputs(tmp_path: Path) -> None:
    write_inputs(tmp_path)
    assert seed.seed_key(tmp_path) == seed.seed_key(tmp_path)
    assert seed.seed_artifact_name(tmp_path).startswith(seed.SEED_ARTIFACT_PREFIX)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (("lock-v1", "project-v1"), ("lock-v2", "project-v1")),
        (("lock-v1", "project-v1"), ("lock-v1", "project-v2")),
        (("ab", "c"), ("a", "bc")),
    ],
    ids=["lock", "project", "bytes-cannot-move-between-files"],
)
def test_any_input_change_changes_the_key(
    tmp_path: Path, before: tuple[str, str], after: tuple[str, str]
) -> None:
    write_inputs(tmp_path, *before)
    first = seed.seed_key(tmp_path)
    write_inputs(tmp_path, *after)
    assert seed.seed_key(tmp_path) != first


def test_a_missing_input_raises_rather_than_hashing_nothing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        seed.seed_key(tmp_path)


def test_main_prints_the_artifact_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_inputs(tmp_path)
    assert seed.main(["testmon_seed.py", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == seed.seed_artifact_name(tmp_path)


def test_the_default_deadline_is_short() -> None:
    assert seed.SEED_FETCH_TIMEOUT_SECONDS <= 30.0
