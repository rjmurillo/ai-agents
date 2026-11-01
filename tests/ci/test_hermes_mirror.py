"""Tests for the content-checked Hermes mirror skip used by the count ratchets."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import hermes_mirror, subprocess_encoding_count_ratchet, type_ignore_count_ratchet

_PACK = "src/hermes/project-toolkit-delivery"
_LIB_SRC = "src/claude/lib/github_core/api.py"
_LIB_COPY = f"{_PACK}/lib/github_core/api.py"
_SKILL_SRC = "src/claude/skills/review/scripts/run.py"
_SKILL_COPY = f"{_PACK}/skills/review/scripts/run.py"
_IGNORE = "x = 1  # type" + ": ignore\n"
_BAD_CALL = "import subprocess\nsubprocess.run(['x'], capture_output=True, encoding='utf-8')\n"


def test_lib_mirror_packages_match_the_lib_mirror_registry() -> None:
    """Every package lib_mirror renders is one the ratchets skip as a mirror."""
    from build.scripts import lib_mirror

    assert set(hermes_mirror.LIB_MIRROR_PACKAGES) == set(lib_mirror.PACKAGES)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    _git(tmp_path, "init")
    for rel, text in files.items():
        _write(tmp_path, rel, text)
    _git(tmp_path, "add", *files)
    return tmp_path


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        (_LIB_COPY, _LIB_SRC),
        (_SKILL_COPY, _SKILL_SRC),
        (f"{_PACK}/lib/paths.py", None),
        (f"{_PACK}/lib/other_pkg/x.py", None),
        (f"{_PACK}/plugin.json", None),
        ("src/hermes/not-a-pack/skills/review/scripts/run.py", None),
        (_SKILL_SRC, None),
    ],
)
def test_hermes_canonical_source_mapping(rel: str, expected: str | None) -> None:
    assert hermes_mirror.hermes_canonical_source(rel) == expected


class TestIsVerbatimHermesMirror:
    def test_identical_bytes_are_a_mirror(self, tmp_path: Path) -> None:
        _repo(tmp_path, {_LIB_SRC: "a = 1\n", _LIB_COPY: "a = 1\n"})
        tracked = frozenset({_LIB_SRC, _LIB_COPY})
        assert hermes_mirror.is_verbatim_hermes_mirror(tmp_path, _LIB_COPY, tracked) is True

    def test_planted_line_breaks_the_mirror(self, tmp_path: Path) -> None:
        _repo(tmp_path, {_LIB_SRC: "a = 1\n", _LIB_COPY: "a = 1\n" + _IGNORE})
        tracked = frozenset({_LIB_SRC, _LIB_COPY})
        assert hermes_mirror.is_verbatim_hermes_mirror(tmp_path, _LIB_COPY, tracked) is False

    def test_untracked_source_is_not_a_mirror(self, tmp_path: Path) -> None:
        _repo(tmp_path, {_LIB_SRC: "a = 1\n", _LIB_COPY: "a = 1\n"})
        assert hermes_mirror.is_verbatim_hermes_mirror(tmp_path, _LIB_COPY, frozenset()) is False

    def test_missing_source_file_is_not_a_mirror(self, tmp_path: Path) -> None:
        _write(tmp_path, _LIB_COPY, "a = 1\n")
        tracked = frozenset({_LIB_SRC, _LIB_COPY})
        assert hermes_mirror.is_verbatim_hermes_mirror(tmp_path, _LIB_COPY, tracked) is False

    def test_non_hermes_path_is_not_a_mirror(self, tmp_path: Path) -> None:
        assert (
            hermes_mirror.is_verbatim_hermes_mirror(tmp_path, "scripts/a.py", frozenset()) is False
        )


class TestTypeIgnoreRatchetContentCheck:
    @pytest.mark.parametrize(
        ("copy", "src", "source_count"), [(_LIB_COPY, _LIB_SRC, 0), (_SKILL_COPY, _SKILL_SRC, 1)]
    )
    def test_verbatim_copy_is_skipped(
        self, tmp_path: Path, copy: str, src: str, source_count: int
    ) -> None:
        """Only the src/claude source counts (the lib source is itself a skipped mirror)."""
        root = _repo(tmp_path, {src: _IGNORE, copy: _IGNORE})
        assert type_ignore_count_ratchet.current_count(root) == source_count

    @pytest.mark.parametrize(("copy", "src"), [(_LIB_COPY, _LIB_SRC), (_SKILL_COPY, _SKILL_SRC)])
    def test_planted_ignore_in_copy_is_counted(self, tmp_path: Path, copy: str, src: str) -> None:
        root = _repo(tmp_path, {src: "x = 1\n", copy: "x = 1\n" + _IGNORE})
        assert type_ignore_count_ratchet.current_count(root) == 1


class TestSubprocessRatchetContentCheck:
    @pytest.mark.parametrize(("copy", "src"), [(_LIB_COPY, _LIB_SRC), (_SKILL_COPY, _SKILL_SRC)])
    def test_verbatim_copy_is_skipped(self, tmp_path: Path, copy: str, src: str) -> None:
        root = _repo(tmp_path, {src: _BAD_CALL, copy: _BAD_CALL})
        assert subprocess_encoding_count_ratchet.current_count(root) == 1

    @pytest.mark.parametrize(("copy", "src"), [(_LIB_COPY, _LIB_SRC), (_SKILL_COPY, _SKILL_SRC)])
    def test_planted_violation_in_copy_is_counted(
        self, tmp_path: Path, copy: str, src: str
    ) -> None:
        root = _repo(tmp_path, {src: "import subprocess\n", copy: _BAD_CALL})
        assert subprocess_encoding_count_ratchet.current_count(root) == 1
