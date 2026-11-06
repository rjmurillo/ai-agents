"""Spec refs named in a pull request body must stay under .project-toolkit.

Issue #6506: ``spec_load_content`` used to open any ``.md`` path a PR body named.
A ``..`` segment, an absolute path, or a symlink reached runner files and put
them into the model prompt. The loader now resolves each ref and refuses one
that leaves ``./.project-toolkit``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci.spec_load_content import EXIT_CONFIG, EXIT_OK, run


def _spec_tree(root: Path) -> Path:
    """Create ./.project-toolkit/specs under ``root`` and return it."""
    tree = root / ".project-toolkit" / "specs"
    tree.mkdir(parents=True, exist_ok=True)
    return tree


class TestSpecRefConfinement:
    """Issue #6506: a spec ref named in a PR body must stay under .project-toolkit."""

    def _env(self, tmp_path: Path, refs: str) -> dict[str, str]:
        return {
            "SPEC_REFS": refs,
            "ISSUE_REFS": "",
            "GITHUB_REPOSITORY": "owner/repo",
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_OUTPUT": str(tmp_path / "out.txt"),
            "GITHUB_RUN_ID": "0",
        }

    def test_a_ref_inside_the_spec_tree_loads(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        (_spec_tree(tmp_path) / "ok.md").write_text("# ok body")

        with patch.dict(os.environ, self._env(tmp_path, ".project-toolkit/specs/ok.md")):
            assert run() == EXIT_OK

        assert "ok body" in (tmp_path / "spec-content-0.md").read_text()

    def test_dot_dot_out_of_the_tree_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _spec_tree(tmp_path)
        (tmp_path / "outside.md").write_text("RUNNER FILE CONTENT")

        refs = ".project-toolkit/specs/../../outside.md"
        with patch.dict(os.environ, self._env(tmp_path, refs)):
            assert run() == EXIT_CONFIG

        assert "escapes .project-toolkit" in capsys.readouterr().err
        assert not (tmp_path / "spec-content-0.md").exists()

    def test_an_absolute_path_outside_the_tree_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        _spec_tree(tmp_path)
        outside = tmp_path / "outside.md"
        outside.write_text("RUNNER FILE CONTENT")

        with patch.dict(os.environ, self._env(tmp_path, str(outside))):
            assert run() == EXIT_CONFIG

    def test_a_symlink_that_leaves_the_tree_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        outside = tmp_path / "outside.md"
        outside.write_text("RUNNER FILE CONTENT")
        (_spec_tree(tmp_path) / "link.md").symlink_to(outside)

        with patch.dict(os.environ, self._env(tmp_path, ".project-toolkit/specs/link.md")):
            assert run() == EXIT_CONFIG

        assert not (tmp_path / "spec-content-0.md").exists()

    def test_a_dot_dot_that_stays_inside_the_tree_resolves(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge: the check is containment, not a ban on the characters."""
        monkeypatch.chdir(tmp_path)
        tree = _spec_tree(tmp_path)
        (tree / "sub").mkdir()
        (tree / "ok.md").write_text("# inside body")

        refs = ".project-toolkit/specs/sub/../ok.md"
        with patch.dict(os.environ, self._env(tmp_path, refs)):
            assert run() == EXIT_OK

    def test_a_spec_id_whose_match_is_a_symlink_out_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        outside = tmp_path / "outside.txt"
        outside.write_text("RUNNER FILE CONTENT")
        (_spec_tree(tmp_path) / "REQ-777-x.txt").symlink_to(outside)

        with patch.dict(os.environ, self._env(tmp_path, "REQ-777")):
            assert run() == EXIT_CONFIG
