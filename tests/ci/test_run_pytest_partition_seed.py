"""The runner seeds each split leg's file from the restored map."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci import run_pytest_partition as mod
from tests.ci.run_pytest_partition_helpers import capture_runner


def _restore(root: Path, payload: bytes) -> Path:
    restored = root / mod.DURATIONS_RESTORE_PATH
    restored.parent.mkdir(parents=True, exist_ok=True)
    restored.write_bytes(payload)
    return restored


class TestSeedLegDurations:
    def test_copies_the_restored_map_and_leaves_it_untouched(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        capture_runner(monkeypatch)
        restored = _restore(tmp_path, b'{"a::t": 1.0}')
        monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
        mod.main(["--partition", "split-4"])
        assert (tmp_path / "artifacts" / "durations-split-4.json").read_bytes() == b'{"a::t": 1.0}'
        assert restored.read_bytes() == b'{"a::t": 1.0}'

    def test_seeds_before_pytest_starts(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _restore(tmp_path, b"{}")
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

    def test_a_leg_writes_only_its_own_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        capture_runner(monkeypatch)
        _restore(tmp_path, b"{}")
        monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
        mod.main(["--partition", "split-1"])
        assert not (tmp_path / "artifacts" / "durations-split-2.json").exists()

    def test_a_dedicated_leg_seeds_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        capture_runner(monkeypatch)
        monkeypatch.setattr(mod, "_PROJECT_ROOT", tmp_path)
        mod.main(["--partition", "pr-autofix"])
        assert not (tmp_path / mod.LEG_DURATIONS_DIR).exists()
