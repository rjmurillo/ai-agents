"""Tests for the baseline artifact lifecycle guard.

Coverage tests ask whether the scan saw the tree. These ask the other half:
whether the artifact about to be replaced can veto its own replacement, and
whether it can be disabled by damaging the artifact itself.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.portability_baseline import (  # noqa: E402
    read_previous_sections,
    refuse_dropped_entries,
    refuse_symlinked_baseline,
    write_baseline_json,
)

UNIT = "skill files"


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scripts" / "validation").mkdir(parents=True)
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "t"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    return root


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _baseline(root: Path, payload: object, *, track: bool = True) -> Path:
    path = _write(root / "scripts" / "validation" / "b.json", payload)
    if track:
        subprocess.run(
            ["git", "-C", str(root), "add", "-A"], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(root), "commit", "-qm", "seed"],
            check=True,
            capture_output=True,
        )
    return path


SECTIONS: dict[str, dict[str, int]] = {
    "files": {"a.md": 2, "b.md": 3},
    "marker_files": {"m.md": 13},
}
NESTED: dict[str, object] = {"_comment": "c", **SECTIONS}


class TestPredecessorLifecycle:
    """An unreadable predecessor must never read as "nothing to protect"."""

    def test_a_never_recorded_baseline_has_nothing_to_protect(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        sections, problem = read_previous_sections(root, root / "scripts/validation/b.json")
        assert (sections, problem) == (None, None)

    def test_a_tracked_baseline_missing_from_disk_is_a_problem(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        path = _baseline(root, NESTED)
        path.unlink()
        sections, problem = read_previous_sections(root, path)
        assert sections is None
        assert problem is not None and "absent from disk" in problem

    def test_a_staged_baseline_deletion_remains_recorded_in_head(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)
        path = _baseline(root, NESTED)
        subprocess.run(
            ["git", "-C", str(root), "rm", "-q", str(path.relative_to(root))],
            check=True,
            capture_output=True,
        )

        sections, problem = read_previous_sections(root, path)

        assert sections is None
        assert problem is not None and "absent from disk" in problem

    def test_a_committed_baseline_deletion_remains_recorded_in_history(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)
        path = _baseline(root, NESTED)
        subprocess.run(
            ["git", "-C", str(root), "rm", "-q", str(path.relative_to(root))],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(root), "commit", "-qm", "delete baseline"],
            check=True,
            capture_output=True,
        )

        sections, problem = read_previous_sections(root, path)

        assert sections is None
        assert problem is not None and "absent from disk" in problem

    def test_corrupt_json_is_a_problem_not_an_absence(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        path = _baseline(root, NESTED)
        path.write_text("<<<<<<< HEAD\n{ ", encoding="utf-8")
        sections, problem = read_previous_sections(root, path)
        assert sections is None
        assert problem is not None and "not valid JSON" in problem

    def test_a_truncated_baseline_is_a_problem(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        path = _baseline(root, NESTED)
        path.write_text("", encoding="utf-8")
        sections, problem = read_previous_sections(root, path)
        assert sections is None and problem is not None

    def test_a_non_object_baseline_is_a_problem(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        path = _baseline(root, ["a.md"])
        sections, problem = read_previous_sections(root, path)
        assert sections is None
        assert problem is not None and "not a JSON object" in problem

    def test_a_non_integer_count_is_a_problem(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        path = _baseline(root, {"files": {"a.md": "many"}})
        sections, problem = read_previous_sections(root, path)
        assert sections is None
        assert problem is not None and "not an integer" in problem

    def test_the_legacy_flat_schema_is_compared_rather_than_refused(
        self, tmp_path: Path
    ) -> None:
        """Refusing it would block a contributor whose checkout predates nesting."""
        root = _repo(tmp_path)
        path = _baseline(root, {"a.md": 2, "b.md": 3})
        sections, problem = read_previous_sections(root, path)
        assert problem is None
        assert sections == {"files": {"a.md": 2, "b.md": 3}}

    def test_both_counted_sections_are_read(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        sections, problem = read_previous_sections(root, _baseline(root, NESTED))
        assert problem is None
        assert sections == {"files": {"a.md": 2, "b.md": 3}, "marker_files": {"m.md": 13}}


class TestReductionsAreRefused:
    """Less debt than the predecessor recorded, in any section, by any route."""

    def test_a_dropped_path_is_refused(self) -> None:
        previous = {"files": {"a.md": 2, "b.md": 3}}
        assert refuse_dropped_entries(previous, {"files": {"a.md": 2}}, UNIT, False)

    def test_a_smaller_count_for_the_same_path_is_refused(self) -> None:
        """A symlink swap keeps the key and empties the count."""
        previous = {"files": {"a.md": 6}}
        assert refuse_dropped_entries(previous, {"files": {"a.md": 1}}, UNIT, False)

    def test_a_marker_only_drop_is_refused(self) -> None:
        """marker_files is an exact-count ratchet, so it needs the same guard."""
        previous = {"files": {"a.md": 2}, "marker_files": {"m.md": 13}}
        current = {"files": {"a.md": 2}, "marker_files": {}}
        assert refuse_dropped_entries(previous, current, UNIT, False)

    def test_a_marker_count_reduction_is_refused(self) -> None:
        previous = {"files": {"a.md": 2}, "marker_files": {"m.md": 13}}
        current = {"files": {"a.md": 2}, "marker_files": {"m.md": 12}}
        assert refuse_dropped_entries(previous, current, UNIT, False)

    def test_an_unreadable_predecessor_is_refused(self) -> None:
        assert refuse_dropped_entries(None, {"files": {}}, UNIT, False, "corrupt")

    def test_an_unreadable_predecessor_is_refused_even_when_shrink_is_allowed(
        self,
    ) -> None:
        """The escape hatch names a known removal; it cannot name an unknown one."""
        assert refuse_dropped_entries(None, {"files": {}}, UNIT, True, "corrupt")

    def test_an_equal_count_rename_fails_closed(self) -> None:
        """The old key is gone, so it is reported. Failing closed is the safe side."""
        previous = {"files": {"old.md": 6}}
        assert refuse_dropped_entries(previous, {"files": {"new.md": 6}}, UNIT, False)

    def test_growth_is_permitted(self) -> None:
        previous = {"files": {"a.md": 2}}
        current = {"files": {"a.md": 3, "b.md": 1}}
        assert not refuse_dropped_entries(previous, current, UNIT, False)

    def test_an_unchanged_baseline_is_permitted(self) -> None:
        same = {"files": {"a.md": 2}}
        assert not refuse_dropped_entries(same, dict(same), UNIT, False)

    def test_a_first_write_is_permitted(self) -> None:
        assert not refuse_dropped_entries(None, {"files": {"a.md": 2}}, UNIT, False)

    def test_a_named_reduction_is_permitted(self) -> None:
        previous = {"files": {"a.md": 2, "b.md": 3}}
        assert not refuse_dropped_entries(previous, {"files": {"a.md": 2}}, UNIT, True)

    def test_the_message_names_the_section_that_regressed(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        previous = {"files": {"a.md": 2}, "marker_files": {"m.md": 13}}
        refuse_dropped_entries(previous, {"files": {"a.md": 2}}, UNIT, False)
        assert "marker_files" in capsys.readouterr().err


class TestTheWriteItself:
    """The write must not follow a symlink, tear, or lose a concurrent update."""

    def test_a_symlinked_baseline_path_is_refused(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        victim = tmp_path / "victim.txt"
        victim.write_text("DO NOT OVERWRITE", encoding="utf-8")
        link = root / "scripts" / "validation" / "b.json"
        link.symlink_to(victim)

        assert refuse_symlinked_baseline(root, link)
        assert write_baseline_json(root, link, NESTED, SECTIONS, UNIT, False) == 2
        assert victim.read_text(encoding="utf-8") == "DO NOT OVERWRITE"

    def test_a_regular_baseline_path_is_written(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        path = root / "scripts" / "validation" / "b.json"
        assert write_baseline_json(root, path, NESTED, SECTIONS, UNIT, False) == 0
        assert json.loads(path.read_text(encoding="utf-8"))["files"] == {"a.md": 2, "b.md": 3}

    def test_a_precreated_temporary_symlink_cannot_redirect_the_write(
        self, tmp_path: Path
    ) -> None:
        root = _repo(tmp_path)
        path = root / "scripts" / "validation" / "b.json"
        victim = tmp_path / "victim.txt"
        victim.write_text("DO NOT OVERWRITE", encoding="utf-8")
        predictable = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        predictable.symlink_to(victim)

        assert write_baseline_json(root, path, NESTED, SECTIONS, UNIT, False) == 0
        assert victim.read_text(encoding="utf-8") == "DO NOT OVERWRITE"
        assert json.loads(path.read_text(encoding="utf-8"))["files"] == {"a.md": 2, "b.md": 3}

    def test_the_predecessor_is_rechecked_at_write_time(self, tmp_path: Path) -> None:
        """The caller's earlier check cannot see a writer that raced it."""
        root = _repo(tmp_path)
        path = _baseline(root, NESTED)
        shrunk: dict[str, dict[str, int]] = {"files": {"a.md": 2}, "marker_files": {"m.md": 13}}
        assert write_baseline_json(root, path, shrunk, shrunk, UNIT, False) == 2
        assert json.loads(path.read_text(encoding="utf-8"))["files"] == {"a.md": 2, "b.md": 3}

    def test_concurrent_writers_serialize_the_read_and_replace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _repo(tmp_path)
        path = _baseline(root, NESTED)
        first_entered_replace = threading.Event()
        release_first = threading.Event()
        second_entered_replace = threading.Event()
        original_replace = os.replace

        def replace(source: Path, destination: Path) -> None:
            if threading.current_thread().name == "stale-writer":
                first_entered_replace.set()
                assert release_first.wait(timeout=2)
            else:
                second_entered_replace.set()
            original_replace(source, destination)

        monkeypatch.setattr(os, "replace", replace)
        reduced = {"files": {"a.md": 1}, "marker_files": {"m.md": 13}}
        results: list[int] = []
        first = threading.Thread(
            target=lambda: results.append(
                write_baseline_json(root, path, NESTED, SECTIONS, UNIT, False)
            ),
            name="stale-writer",
        )
        second = threading.Thread(
            target=lambda: results.append(
                write_baseline_json(root, path, reduced, reduced, UNIT, True)
            ),
            name="tightening-writer",
        )

        first.start()
        assert first_entered_replace.wait(timeout=2)
        second.start()
        second_reached_replace_while_first_held_lock = second_entered_replace.wait(
            timeout=0.2
        )
        release_first.set()
        first.join(timeout=2)
        second.join(timeout=2)

        assert not second_reached_replace_while_first_held_lock
        assert not first.is_alive() and not second.is_alive()
        assert results == [0, 0]
        assert json.loads(path.read_text(encoding="utf-8"))["files"] == {"a.md": 1}

    def test_a_concurrently_truncated_baseline_is_refused(self, tmp_path: Path) -> None:
        """Truncation used to look like "no predecessor", turning a race into a wipe."""
        root = _repo(tmp_path)
        path = _baseline(root, NESTED)
        path.write_text("", encoding="utf-8")
        assert write_baseline_json(root, path, NESTED, SECTIONS, UNIT, False) == 2
        assert path.read_text(encoding="utf-8") == ""

    def test_no_temporary_file_survives_a_refusal(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        path = _baseline(root, NESTED)
        shrunk: dict[str, dict[str, int]] = {"files": {}, "marker_files": {}}
        write_baseline_json(root, path, shrunk, shrunk, UNIT, False)
        assert not list(path.parent.glob("*.tmp"))

    def test_no_temporary_file_survives_a_write(self, tmp_path: Path) -> None:
        root = _repo(tmp_path)
        path = root / "scripts" / "validation" / "b.json"
        write_baseline_json(root, path, NESTED, SECTIONS, UNIT, False)
        assert not list(path.parent.glob("*.tmp"))

    def test_the_replacement_is_atomic(self, tmp_path: Path) -> None:
        """os.replace keeps the artifact whole, so no reader sees a partial file."""
        root = _repo(tmp_path)
        path = _baseline(root, NESTED)
        grown: dict[str, dict[str, int]] = {
            "files": {"a.md": 2, "b.md": 3, "c.md": 9},
            "marker_files": {"m.md": 13},
        }
        inode_before = os.stat(path).st_ino
        assert write_baseline_json(root, path, grown, grown, UNIT, False) == 0
        assert os.stat(path).st_ino != inode_before
        assert json.loads(path.read_text(encoding="utf-8"))["files"]["c.md"] == 9
