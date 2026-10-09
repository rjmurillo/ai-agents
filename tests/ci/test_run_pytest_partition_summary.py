"""Each CI leg prints a one-line summary naming what it ran.

Issue #6239: a split leg names its group and the restored durations map it used,
so a failing or slow group can be rerun locally from the log alone. The restored
map is copied to a per-leg file, which is the only file pytest-split writes.
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


def _restored(root: Path, payload: bytes) -> Path:
    restored = root / mod.DURATIONS_RESTORE_PATH
    restored.parent.mkdir(parents=True, exist_ok=True)
    restored.write_bytes(payload)
    return restored


def test_summary_line_for_a_split_leg_names_the_split_and_durations_hash(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    capture_runner(monkeypatch)
    _restored(tmp_path, b'{"a::t": 1.0}')
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    digest = hashlib.sha256(b'{"a::t": 1.0}').hexdigest()[:12]
    mod.main(["--partition", "split-3"])
    assert capsys.readouterr().err.strip() == (
        "partition=split-3 mode=full splits=4 group=3 "
        f"durations={mod.DURATIONS_RESTORE_PATH} durations_sha256={digest}"
    )


def test_summary_line_reports_a_missing_durations_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    capture_runner(monkeypatch)
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    mod.main(["--partition", "split-1"])
    assert capsys.readouterr().err.strip().endswith("durations_sha256=missing")


def test_a_directory_at_the_restored_path_reports_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / mod.DURATIONS_RESTORE_PATH).mkdir(parents=True)
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    assert mod._durations_digest() == "missing"


def test_relative_paths_resolve_because_the_runner_sets_cwd_to_the_root() -> None:
    """pytest receives relative paths; run_pytest_non_tmp runs it from the root.

    tests/ci/test_pytest_non_tmp_policy.py pins cwd == PROJECT_ROOT for the
    subprocess call. This pins the other half: both modules agree on the root.
    """
    assert run_pytest_non_tmp.PROJECT_ROOT == mod._PROJECT_ROOT
    assert not Path(mod.DURATIONS_RESTORE_PATH).is_absolute()
    assert not Path(mod._leg_durations_path("split-1")).is_absolute()


def test_a_missing_durations_file_raises_a_ci_warning_annotation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """A degraded split shows in the Actions UI, not only in the leg log."""
    capture_runner(monkeypatch)
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    mod.main(["--partition", "split-2"])
    assert capsys.readouterr().out.startswith("::warning title=pytest-split::")


def test_a_restored_durations_file_raises_no_annotation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    capture_runner(monkeypatch)
    _restored(tmp_path, b"{}")
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    mod.main(["--partition", "split-2"])
    assert "::warning" not in capsys.readouterr().out


def test_a_dedicated_leg_raises_no_annotation_and_seeds_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    capture_runner(monkeypatch)
    monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
    mod.main(["--partition", "pr-autofix"])
    assert "::warning" not in capsys.readouterr().out
    assert not (tmp_path / mod.LEG_DURATIONS_DIR).exists()


class TestSeedLegDurations:
    def test_copies_the_restored_map_to_the_leg_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        capture_runner(monkeypatch)
        restored = _restored(tmp_path, b'{"a::t": 1.0}')
        monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
        mod.main(["--partition", "split-4"])
        leg_file = tmp_path / "artifacts" / "durations-split-4.json"
        assert leg_file.read_bytes() == b'{"a::t": 1.0}'
        assert restored.read_bytes() == b'{"a::t": 1.0}'

    def test_seeds_before_pytest_starts(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _restored(tmp_path, b"{}")
        monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
        seen: list[bool] = []

        def fake_main(_argv: list[str]) -> int:
            seen.append((tmp_path / "artifacts" / "durations-split-1.json").is_file())
            return 0

        monkeypatch.setattr(mod.run_pytest_non_tmp, "main", fake_main)
        mod.main(["--partition", "split-1"])
        assert seen == [True]

    def test_removes_a_stale_leg_file_when_nothing_restored(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        capture_runner(monkeypatch)
        stale = tmp_path / "artifacts" / "durations-split-2.json"
        stale.parent.mkdir()
        stale.write_text('{"old::t": 9.0}', encoding="utf-8")
        monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
        mod.main(["--partition", "split-2"])
        assert not stale.exists()

    def test_each_leg_gets_its_own_copy(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        capture_runner(monkeypatch)
        _restored(tmp_path, b"{}")
        monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
        mod.main(["--partition", "split-1"])
        assert not (tmp_path / "artifacts" / "durations-split-2.json").exists()
