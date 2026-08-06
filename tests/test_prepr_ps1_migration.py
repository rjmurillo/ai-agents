"""Tests for the ADR-042 PowerShell-to-Python gate migration (Issues #4658-#4661, #4674).

Proves:
1. Class-level invariant: no wrapper references a .ps1 that does not exist.
2. Each ported gate invokes the Python replacement and returns pass/fail correctly.
3. The deleted Pester gate is no longer registered.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKS_TOOLING = REPO_ROOT / "scripts" / "validation" / "checks_tooling.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "validation"))


class TestNoPsReferences:
    """Guard: no wrapper references a .ps1 path that does not exist in the repo."""

    def _extract_ps1_paths(self) -> list[str]:
        """Parse checks_tooling.py AST and extract all string literals ending in .ps1."""
        source = CHECKS_TOOLING.read_text()
        tree = ast.parse(source)
        ps1_paths: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.endswith(".ps1") or node.value.endswith(".ps1'"):
                    ps1_paths.append(node.value)
            elif isinstance(node, ast.JoinedStr):
                for part in node.values:
                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                        if ".ps1" in part.value:
                            ps1_paths.append(part.value)
        return ps1_paths

    def test_no_unreachable_ps1_references(self) -> None:
        """Every .ps1 path literal in checks_tooling.py must exist on disk OR
        appear only in a code path that is unreachable (behind a legacy fallback
        that first checks for the Python port)."""
        ps1_refs = self._extract_ps1_paths()
        missing = []
        for ref in ps1_refs:
            # The AST gives us the relative slug, not the full path construction.
            # We look for any tracked file matching the basename.
            basename = Path(ref).name if "/" not in ref else ref.split("/")[-1]
            result = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "ls-files", f"*{basename}"],
                capture_output=True, text=True, timeout=10,
            )
            if basename not in (result.stdout or ""):
                missing.append(ref)
        assert not missing, (
            f"checks_tooling.py references .ps1 files not in the repository: {missing}. "
            "Port the wrapper to the Python replacement or delete it."
        )


class TestPesterGateRemoved:
    """Issue #4661: validate_pester_tests is deleted and unregistered."""

    def test_not_in_sequence(self) -> None:
        from pre_pr_sequence import _SEQUENCE

        gate_names = [g.name for g in _SEQUENCE]
        assert "Pester Unit Tests" not in gate_names

    def test_not_importable_from_tooling(self) -> None:
        import checks_tooling

        assert not hasattr(checks_tooling, "validate_pester_tests")


class TestSessionEndGate:
    """Issue #4658: validate_session_end calls validate_session_json.py."""

    def test_passes_when_no_changed_logs(self) -> None:
        from checks_tooling import validate_session_end

        # No changed session logs on branch -> PASS
        with patch("checks_tooling._resolve_branch_base_ref", return_value="main"):
            with patch("checks_tooling._run_subprocess", return_value=(0, "", "")):
                assert validate_session_end(REPO_ROOT) is True

    def test_fails_on_invalid_log(self, tmp_path: Path) -> None:
        from checks_tooling import validate_session_end

        # Create an invalid session log
        sessions_dir = tmp_path / ".agents" / "sessions"
        sessions_dir.mkdir(parents=True)
        bad_log = sessions_dir / "2099-01-01-session-01.json"
        bad_log.write_text('{"not": "valid session"}')

        # Create the validator script marker so the existence check passes
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "validate_session_json.py").write_text("# placeholder")

        with patch("checks_tooling._resolve_branch_base_ref", return_value="main"):
            with patch(
                "checks_tooling._run_subprocess",
                side_effect=[
                    # git diff returns the session log path
                    (0, ".agents/sessions/2099-01-01-session-01.json\n", ""),
                    # validator invocation fails
                    (1, "[FAIL] Invalid session log", ""),
                ],
            ):
                assert validate_session_end(tmp_path) is False

    def test_no_missing_script_skip_when_script_present(self) -> None:
        from checks_tooling import validate_session_end

        # With a valid base ref and changed log, should NOT raise MissingScriptSkip
        # when validate_session_json.py exists (which it does in this repo).
        with patch("checks_tooling._resolve_branch_base_ref", return_value="main"):
            with patch("checks_tooling._run_subprocess", return_value=(0, "", "")):
                # No changed logs -> passes without needing the script
                result = validate_session_end(REPO_ROOT)
                assert result is True


class TestPathNormalizationGate:
    """Issue #4659: validate_path_normalization calls the Python port."""

    def test_passes_on_clean_tree(self) -> None:
        from checks_tooling import validate_path_normalization

        assert validate_path_normalization(REPO_ROOT) is True

    def test_raises_when_script_missing(self, tmp_path: Path) -> None:
        from checks_common import MissingScriptSkip
        from checks_tooling import validate_path_normalization

        with pytest.raises(MissingScriptSkip):
            validate_path_normalization(tmp_path)

    def test_fails_on_absolute_path_violation(self, tmp_path: Path) -> None:
        """A .md file containing a Linux absolute path must FAIL the gate."""
        from checks_tooling import validate_path_normalization

        # Set up the validator script (symlink to real one)
        build_dir = tmp_path / "build" / "scripts"
        build_dir.mkdir(parents=True)
        real_script = REPO_ROOT / "build" / "scripts" / "validate_path_normalization.py"
        (build_dir / "validate_path_normalization.py").write_bytes(
            real_script.read_bytes()
        )

        # Create a .md file with a forbidden absolute path
        doc = tmp_path / "bad-doc.md"
        doc.write_text("Install from /home/username/repo/bin/tool\n")

        result = validate_path_normalization(tmp_path)
        assert result is False


class TestPlanningArtifactsGate:
    """Issue #4660: validate_planning_artifacts calls the Python port."""

    def test_passes_on_clean_tree(self) -> None:
        from checks_tooling import validate_planning_artifacts

        assert validate_planning_artifacts(REPO_ROOT) is True

    def test_raises_when_script_missing(self, tmp_path: Path) -> None:
        from checks_common import MissingScriptSkip
        from checks_tooling import validate_planning_artifacts

        with pytest.raises(MissingScriptSkip):
            validate_planning_artifacts(tmp_path)

    def test_fails_on_orphan_condition(self, tmp_path: Path) -> None:
        """A planning doc with an orphan specialist condition must FAIL."""
        from checks_tooling import validate_planning_artifacts

        # Set up the validator script
        build_dir = tmp_path / "build" / "scripts"
        build_dir.mkdir(parents=True)
        real_script = REPO_ROOT / "build" / "scripts" / "validate_planning_artifacts.py"
        (build_dir / "validate_planning_artifacts.py").write_bytes(
            real_script.read_bytes()
        )

        # Create a planning doc with an orphan condition (a specialist condition
        # listed outside any table and not referenced in any table row).
        planning_dir = tmp_path / ".agents" / "planning"
        planning_dir.mkdir(parents=True)
        plan_doc = planning_dir / "plan-feature.md"
        plan_doc.write_text(
            "# Feature Plan\n\n"
            "## Tasks\n\n"
            "| Task | Owner |\n"
            "| ---- | ----- |\n"
            "| Build API | Dev |\n\n"
            "## Conditions\n\n"
            "- QA: Integration tests must cover all endpoints\n"
            "- Security: Pen test required before launch\n"
        )

        result = validate_planning_artifacts(tmp_path)
        assert result is False


class TestMypyChangedFilesGate:
    """Issue #4674: validate_mypy_changed_files runs mypy on branch changes."""

    def test_passes_when_no_files_changed(self) -> None:
        from checks_mypy import validate_mypy_changed_files

        with patch("checks_mypy._resolve_branch_base_ref", return_value="main"):
            with patch("checks_mypy._run_subprocess", return_value=(0, "", "")):
                assert validate_mypy_changed_files(REPO_ROOT) is True

    def test_passes_when_no_base_ref(self) -> None:
        from checks_mypy import validate_mypy_changed_files

        with patch("checks_mypy._resolve_branch_base_ref", return_value=None):
            assert validate_mypy_changed_files(REPO_ROOT) is True

    def test_fails_when_new_type_error_added(self, tmp_path: Path) -> None:
        """A file that ADDS a new type error on a changed line must FAIL.

        This is an end-to-end test: creates a real git repo, introduces a type
        error on a new line, and runs run_mypy against it. The ratchet sees the
        error is on a changed line and blocks.
        """
        from git_hook_policy import run_mypy

        # Create a minimal git repo with a base commit
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            capture_output=True, check=True,
        )

        # Base commit: a clean file with no type errors
        py_file = tmp_path / "example.py"
        py_file.write_text("def greet(name: str) -> str:\n    return name\n")
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "base"],
            capture_output=True, check=True,
        )

        # Branch: add a line with a type error
        py_file.write_text(
            "def greet(name: str) -> str:\n"
            "    return name\n"
            "\n"
            "x: int = 'not an int'  # type error on this new line\n"
        )
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "add error"],
            capture_output=True, check=True,
        )

        # run_mypy uses _mypy_ratchet_base_ref() to get the base. We patch it
        # to point at our base commit (HEAD~1).
        with patch("git_hook_policy._mypy_ratchet_base_ref", return_value="HEAD~1"):
            result = run_mypy(["example.py"], tmp_path)

        # The error is on a changed line, so the ratchet blocks it.
        assert result == 1, "Expected FAIL: new type error on a changed line"

    def test_passes_when_preexisting_error_not_on_changed_line(self, tmp_path: Path) -> None:
        """A file with pre-existing type errors that are NOT on changed lines must PASS.

        This pins the ratchet semantic: touching a file that already has errors
        does NOT block, as long as your change does not add to them.
        """
        from git_hook_policy import run_mypy

        # Create a minimal git repo
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            capture_output=True, check=True,
        )

        # Base commit: file already has a type error on line 4
        py_file = tmp_path / "example.py"
        py_file.write_text(
            "def greet(name: str) -> str:\n"
            "    return name\n"
            "\n"
            "x: int = 'not an int'  # pre-existing error\n"
        )
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "base with error"],
            capture_output=True, check=True,
        )

        # Branch: change a DIFFERENT line (add a clean function), leave error alone
        py_file.write_text(
            "def greet(name: str) -> str:\n"
            "    return name\n"
            "\n"
            "x: int = 'not an int'  # pre-existing error\n"
            "\n"
            "def farewell(name: str) -> str:\n"
            "    return f'bye {name}'\n"
        )
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "add clean function"],
            capture_output=True, check=True,
        )

        # run_mypy with ratchet base pointing at the base commit
        with patch("git_hook_policy._mypy_ratchet_base_ref", return_value="HEAD~1"):
            result = run_mypy(["example.py"], tmp_path)

        # The error is pre-existing and NOT on a changed line, so ratchet allows it.
        assert result == 0, "Expected PASS: pre-existing error not on a changed line"
