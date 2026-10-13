"""``build_all.py --check`` says which drifted paths are merely uncommitted (issue #6427).

``--check`` diffs the regenerated tree against HEAD, so a correct regeneration
that was never committed reads as drift. The fix compares each drifted path with
the snapshot taken before generation and prints one remedy line.

Coverage:

- positive: a path whose bytes the generators left unchanged is reported.
- negative: a path the generators rewrote, a path absent from the snapshot, and
  a deleted path are not reported.
- edge: all, some, and none unchanged print three different outputs; ``run``
  hands the pre-generation snapshot to ``_run_generators``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import build_all  # noqa: E402


def _tree(tmp_path: Path) -> dict[Path, bytes]:
    """Four paths: unchanged, rewritten, absent from the snapshot, deleted."""
    (tmp_path / "same.md").write_text("same", encoding="utf-8")
    (tmp_path / "rewritten.md").write_text("after", encoding="utf-8")
    (tmp_path / "fresh.md").write_text("new", encoding="utf-8")
    return {
        tmp_path / "same.md": b"same",
        tmp_path / "rewritten.md": b"before",
        tmp_path / "deleted.md": b"gone",
    }


class TestPathsUnchangedByRegeneration:
    def test_only_the_byte_identical_path_is_reported(self, tmp_path: Path) -> None:
        snapshot = _tree(tmp_path)

        got = build_all._paths_unchanged_by_regeneration(
            tmp_path, ["same.md", "rewritten.md", "fresh.md", "deleted.md"], snapshot
        )

        assert got == ["same.md"]

    def test_an_empty_drift_list_reports_nothing(self, tmp_path: Path) -> None:
        assert build_all._paths_unchanged_by_regeneration(tmp_path, [], {}) == []

    def test_a_directory_is_not_a_file_and_is_skipped(self, tmp_path: Path) -> None:
        (tmp_path / "d").mkdir()

        got = build_all._paths_unchanged_by_regeneration(tmp_path, ["d"], {tmp_path / "d": b""})

        assert got == []


class TestRemedyMessage:
    def test_all_unchanged_says_commit_and_rerun(self) -> None:
        msg = build_all._unchanged_regeneration_message(4, 4)

        assert msg.startswith(f"{build_all.UNCOMMITTED_UNCHANGED_PREFIX} 4 of 4")
        assert "Commit the regenerated files, then rerun --check." in msg

    def test_some_unchanged_names_the_stale_remainder(self) -> None:
        msg = build_all._unchanged_regeneration_message(1, 4)

        assert "1 of 4" in msg
        assert "The other 3 are stale" in msg
        assert "build/scripts/build_all.py" in msg


class TestPrintStalePaths:
    def test_no_snapshot_prints_the_list_and_no_marker(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        build_all._print_stale_paths(tmp_path, ["a.md"], None)

        err = capsys.readouterr().err
        assert "STALENESS DETECTED: uncommitted regen drift:\n  a.md\n" in err
        assert build_all.UNCOMMITTED_UNCHANGED_PREFIX not in err

    def test_nothing_unchanged_prints_no_marker(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        snapshot = _tree(tmp_path)

        build_all._print_stale_paths(tmp_path, ["rewritten.md", "fresh.md"], snapshot)

        assert build_all.UNCOMMITTED_UNCHANGED_PREFIX not in capsys.readouterr().err

    def test_everything_unchanged_prints_the_commit_marker(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        snapshot = _tree(tmp_path)

        build_all._print_stale_paths(tmp_path, ["same.md"], snapshot)

        assert f"{build_all.UNCOMMITTED_UNCHANGED_PREFIX} 1 of 1" in capsys.readouterr().err


class TestRunWiring:
    def test_check_mode_passes_the_pre_generation_snapshot_to_the_generators(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sentinel = build_all.OwnedSnapshot()
        seen: dict[str, Any] = {}

        def fake_generators(*_args: Any, **kwargs: Any) -> int:
            seen.update(kwargs)
            return 0

        monkeypatch.setattr(
            build_all, "_select_platform_configs", lambda *_a: [tmp_path / "x.yaml"]
        )
        monkeypatch.setattr(build_all, "_snapshot_owned_prefixes", lambda *_a, **_k: sentinel)
        monkeypatch.setattr(build_all, "_git_boundaries_under", lambda *_a: set())
        monkeypatch.setattr(build_all.binplace_manifest, "claude_allowlist", lambda _r: set())
        monkeypatch.setattr(build_all, "_run_generators", fake_generators)
        monkeypatch.setattr(build_all, "_restore_owned_prefixes", lambda *_a, **_k: True)
        monkeypatch.setattr(build_all, "_effective_owned_prefixes", lambda _r: ())

        code = build_all.run(tmp_path, platform=None, check=True, clean=False, audit_format="md")

        assert code == 0
        assert seen["owned_snapshot"] is sentinel
