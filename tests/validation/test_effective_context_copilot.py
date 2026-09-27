"""Tests for scripts/validation/effective_context_copilot.py (issue #4880).

Split out of ``test_effective_context.py`` (1196 lines, over the taste-lints
500-line ERROR threshold) alongside the module split that motivated it. This
file covers everything specific to Copilot CLI's own loading model: no ``@``
import expansion, raw-byte root/nested reading, and
``.github/instructions/*.instructions.md`` ``applyTo`` scoping (including
the user layer's ``$COPILOT_HOME``). Shared source-reading and CLI/ratchet
tests live in their own split files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.effective_context_resolvers as ecr
from scripts.validation.instruction_budget_globs import UnsupportedApplyToError
from tests.validation._effective_context_helpers import _build_claude_copilot_tree, _write

# --------------------------------------------------------------------------
# REQ-1: list each loaded file, its layer, and its bytes, plus totals.
# --------------------------------------------------------------------------


class TestReq1CopilotResolution:
    """REQ-1, T2: Copilot layer resolution (root, nested/model, scoped)."""

    def test_copilot_reports_every_layer_with_correct_bytes(self, tmp_path: Path) -> None:
        """REQ-1: Copilot root/nested/scoped layers, no import expansion."""
        sizes = _build_claude_copilot_tree(tmp_path)
        result = ecr.resolve_effective_context(tmp_path, "a/b/target.py", "copilot")
        by_path = {f.path: f for f in result.files}

        assert by_path[".github/copilot-instructions.md"].layer == "root"
        assert by_path["AGENTS.md"].layer == "root"
        assert by_path["CLAUDE.md"].layer == "root"
        assert by_path["a/AGENTS.md"].layer == "nested"
        assert by_path["a/CLAUDE.md"].layer == "nested"
        assert by_path[".github/instructions/scoped.instructions.md"].layer == "scoped"
        assert ".github/instructions/other.instructions.md" not in by_path

        # Copilot never expands @ imports: AGENTS.md is read directly (raw
        # bytes), not "because CLAUDE.md imported it".
        assert by_path["AGENTS.md"].reason == "root file"
        assert result.path_local_bytes == sizes["a/CLAUDE.md"] + sizes["a/AGENTS.md"]

    def test_copilot_has_no_import_problems(self, tmp_path: Path) -> None:
        """REQ-1: Copilot resolution never follows imports, so no problems."""
        _build_claude_copilot_tree(tmp_path)
        result = ecr.resolve_effective_context(tmp_path, "a/b/target.py", "copilot")
        assert result.problems == ()


# --------------------------------------------------------------------------
# REQ-5 (Copilot side): the user layer, and boundary races.
# --------------------------------------------------------------------------


class TestCopilotBoundaryBranches:
    """Defensive branches: scoped-dir races, malformed applyTo, user layer."""

    def test_instructions_file_without_applyto_key_scopes_to_nothing(self, tmp_path: Path) -> None:
        """A `.instructions.md` with frontmatter but no `applyTo:` never loads."""
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(
            tmp_path,
            ".github/instructions/no_applyto.instructions.md",
            "---\ndescription: x\n---\nbody\n",
        )
        _write(tmp_path, "target.py", "x = 1\n")
        result = ecr.resolve_effective_context(tmp_path, "target.py", "copilot")
        assert not any(f.path.endswith("no_applyto.instructions.md") for f in result.files)

    def test_non_string_applyto_entry_fails_closed(self, tmp_path: Path) -> None:
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(
            tmp_path,
            ".github/instructions/bad.instructions.md",
            "---\napplyTo:\n  - 5\n---\nbody\n",
        )
        _write(tmp_path, "target.py", "x = 1\n")
        with pytest.raises(UnsupportedApplyToError):
            ecr.resolve_effective_context(tmp_path, "target.py", "copilot")

    def test_copilot_scoped_skips_an_instructions_file_that_disappears(
        self, tmp_path: Path
    ) -> None:
        """The same race as Claude's rules dir, on `resolve_copilot`'s scoped loop."""
        _write(tmp_path, ".github/copilot-instructions.md", "x\n")
        _write(
            tmp_path,
            ".github/instructions/flaky.instructions.md",
            '---\napplyTo: "**"\n---\nbody\n',
        )

        class _FlakyRepo(ecr.Repo):
            def read_bytes(self, rel_path: str) -> bytes | None:
                if rel_path == ".github/instructions/flaky.instructions.md":
                    return None
                return super().read_bytes(rel_path)

        flaky = _FlakyRepo(tmp_path, None)
        files = ecr.resolve_copilot(flaky, "", "target.py", include_user=False)
        assert not any(f.path.endswith("flaky.instructions.md") for f in files)

    def test_copilot_user_layer_reads_copilot_home_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-5: Copilot's user file honors $COPILOT_HOME, default ~/.copilot."""
        copilot_home = tmp_path / "custom-copilot-home"
        copilot_home.mkdir()
        user_bytes = _write(copilot_home, "copilot-instructions.md", "user copilot text\n")
        monkeypatch.setenv(ecr.COPILOT_HOME_ENV, str(copilot_home))

        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo, ".github/copilot-instructions.md", "x\n")
        _write(repo, "target.py", "x = 1\n")

        result = ecr.resolve_effective_context(repo, "target.py", "copilot", include_user=True)
        user_files = [f for f in result.files if f.layer == "user"]
        assert len(user_files) == 1
        assert user_files[0].size_bytes == user_bytes

    def test_copilot_user_layer_absent_when_the_home_file_does_not_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """REQ-5: include_user=True with no user file present adds nothing."""
        copilot_home = tmp_path / "empty-copilot-home"
        copilot_home.mkdir()
        monkeypatch.setenv(ecr.COPILOT_HOME_ENV, str(copilot_home))

        repo = tmp_path / "repo"
        repo.mkdir()
        _write(repo, ".github/copilot-instructions.md", "x\n")
        _write(repo, "target.py", "x = 1\n")

        result = ecr.resolve_effective_context(repo, "target.py", "copilot", include_user=True)
        assert not any(f.layer == "user" for f in result.files)
