"""Each CI leg prints a one-line summary naming what it ran.

Issue #6239: a split leg names its group and the durations file it used, so a
failing or slow group can be rerun locally from the log alone.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.ci import run_pytest_non_tmp
from scripts.ci import run_pytest_partition as mod
from tests.ci.run_pytest_partition_helpers import capture_runner


def test_summary_line_for_a_dedicated_leg_is_partition_and_mode_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    capture_runner(monkeypatch)
    mod.main(["--partition", "safe-push"])
    assert capsys.readouterr().err.strip() == "partition=safe-push mode=full"


def test_summary_line_for_a_split_leg_names_the_split_and_durations_hash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    capture_runner(monkeypatch)
    durations = tmp_path / "durations"
    durations.write_bytes(b'{"a::t": 1.0}')
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(mod, "DURATIONS_PATH", "durations")
    digest = hashlib.sha256(b'{"a::t": 1.0}').hexdigest()[:12]
    mod.main(["--partition", "split-3"])
    assert capsys.readouterr().err.strip() == (
        "partition=split-3 mode=full splits=4 group=3 "
        f"durations=durations durations_sha256={digest}"
    )


def test_summary_line_reports_a_missing_durations_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    capture_runner(monkeypatch)
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    mod.main(["--partition", "split-1"])
    assert capsys.readouterr().err.strip().endswith("durations_sha256=missing")


def test_a_directory_at_the_durations_path_reports_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / mod.DURATIONS_PATH).mkdir()
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    assert mod._durations_digest() == "missing"


def test_relative_durations_path_resolves_because_the_runner_sets_cwd_to_the_root() -> None:
    """pytest receives the relative path; run_pytest_non_tmp runs it from the root.

    tests/ci/test_pytest_non_tmp_policy.py pins cwd == PROJECT_ROOT for the
    subprocess call. This pins the other half: both modules agree on the root
    and the committed file exists beneath it.
    """
    assert run_pytest_non_tmp.PROJECT_ROOT == mod._PROJECT_ROOT
    assert (run_pytest_non_tmp.PROJECT_ROOT / mod.DURATIONS_PATH).is_file()
