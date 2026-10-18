"""Tests for scripts/eval/_run_changes.py (issue #5768)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import _run_changes as rc  # noqa: E402


def _tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def test_a_modified_file_diffs_old_to_new(tmp_path: Path) -> None:
    before = _tree(tmp_path / "a", {"m.py": "x = 1\n"})
    after = _tree(tmp_path / "b", {"m.py": "x = 2\n"})

    patch = rc.change_patch(before, after, ["m.py"])

    assert "--- a/m.py\n+++ b/m.py\n" in patch
    assert "-x = 1\n+x = 2\n" in patch


def test_an_added_file_diffs_from_dev_null(tmp_path: Path) -> None:
    before = _tree(tmp_path / "a", {})
    after = _tree(tmp_path / "b", {"new.py": "y = 1\n"})

    patch = rc.change_patch(before, after, ["new.py"])

    assert "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+y = 1\n" in patch


def test_a_deleted_file_diffs_to_dev_null(tmp_path: Path) -> None:
    before = _tree(tmp_path / "a", {"gone.py": "z = 1\n"})
    after = _tree(tmp_path / "b", {})

    patch = rc.change_patch(before, after, ["gone.py"])

    assert "--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-z = 1\n" in patch


def test_a_missing_final_newline_does_not_run_into_the_next_file(tmp_path: Path) -> None:
    before = _tree(tmp_path / "a", {"a.py": "1\n", "b.py": "1\n"})
    after = _tree(tmp_path / "b", {"a.py": "2", "b.py": "2\n"})

    patch = rc.change_patch(before, after, ["a.py", "b.py"])

    assert "+2\n\\ No newline at end of file\n--- a/b.py" in patch


def test_only_the_named_paths_are_diffed_and_in_sorted_order(tmp_path: Path) -> None:
    before = _tree(tmp_path / "a", {"a.py": "1\n", "z.py": "1\n", "skip.py": "1\n"})
    after = _tree(tmp_path / "b", {"a.py": "2\n", "z.py": "2\n", "skip.py": "2\n"})

    patch = rc.change_patch(before, after, ["z.py", "a.py"])

    assert "skip.py" not in patch
    assert patch.index("a/a.py") < patch.index("a/z.py")


def test_no_changed_paths_gives_an_empty_patch(tmp_path: Path) -> None:
    assert rc.change_patch(tmp_path, tmp_path, []) == ""


def test_a_symlink_is_named_but_its_target_is_never_read(tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret-value\n", encoding="utf-8")
    before = _tree(tmp_path / "a", {})
    after = _tree(tmp_path / "b", {})
    (after / "link.txt").symlink_to(secret)

    patch = rc.change_patch(before, after, ["link.txt"])

    assert "symbolic link not followed" in patch and "top-secret-value" not in patch


def test_a_binary_file_is_named_but_not_diffed(tmp_path: Path) -> None:
    before = _tree(tmp_path / "a", {})
    after = _tree(tmp_path / "b", {})
    (after / "blob.bin").write_bytes(b"\x00\x01\x02")

    assert "# not diffed: binary file" in rc.change_patch(before, after, ["blob.bin"])


def test_an_oversized_file_is_named_but_not_diffed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rc, "MAX_FILE_BYTES", 4)
    before = _tree(tmp_path / "a", {})
    after = _tree(tmp_path / "b", {"big.txt": "123456789\n"})

    patch = rc.change_patch(before, after, ["big.txt"])

    assert "# not diffed: larger than 4 bytes" in patch and "123456789" not in patch


def test_patch_relpath_replaces_unsafe_characters() -> None:
    assert rc.patch_relpath("reduced", "RB-01", 2) == "changes/reduced/RB-01-r2.patch"
    assert rc.patch_relpath("../x", "a/b\\c", 0) == "changes/.._x/a_b_c-r0.patch"
    assert rc.patch_relpath("", "", 0) == "changes/_/_-r0.patch"


def test_a_task_id_cannot_escape_the_output_directory(tmp_path: Path) -> None:
    out = tmp_path / "out"

    relative = rc.write_patch(out, "reduced", "../../evil", 0, "patch text")

    written = (out / relative).resolve()
    assert written.is_relative_to(out.resolve())
    assert written.read_text(encoding="utf-8") == "patch text"
