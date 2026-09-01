#!/usr/bin/env python3
"""Bind the codeql-scan wrappers to the delegates that actually exist (Issue #4921).

The wrappers resolved `Test-CodeQLConfig.ps1`, `Invoke-CodeQLScan.ps1`, and
`Install-CodeQL.ps1` long after those files were deleted, so every operation
failed with exit 3. The existing suites did not catch it because each one
fabricates the delegate under `tmp_path` using whatever name the wrapper asks
for. A fixture cannot disagree with the code that names it, so the tests stayed
green while the skill was broken.

The tests here resolve delegates against the real repository and against the
real delegate argument parsers, so no fixture can satisfy them:

    - `test_delegate_scripts_exist_in_real_repo` fails if a declared delegate
      name has no matching file in `.codeql/scripts/`.
    - `test_scan_flags_accepted_by_real_delegate_parser` feeds the flags the
      wrapper emits to the delegate's own `build_parser()`, so a flag renamed on
      either side fails here.
    - `test_validate_operation_succeeds_in_this_repository` runs the wrapper as
      a subprocess in this checkout and asserts the exit code from the issue
      report is gone.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import PROJECT_ROOT, import_skill_script

WRAPPER_RELATIVE_PATHS = (
    ".claude/skills/codeql-scan/scripts/invoke_codeql_scan.py",
    ".claude/skills/codeql-scan/scripts/invoke_codeql_scan_skill.py",
)

CODEQL_SCRIPTS_DIR = PROJECT_ROOT / ".codeql" / "scripts"

# The documented entry point. SKILL.md, line 19:
#   python3 .claude/skills/codeql-scan/scripts/invoke_codeql_scan.py --operation full
wrapper = import_skill_script(WRAPPER_RELATIVE_PATHS[0], module_name="codeql_wrapper")
skill_wrapper = import_skill_script(
    WRAPPER_RELATIVE_PATHS[1], module_name="codeql_wrapper_skill"
)

# The delegate is imported under an alias: its file name (invoke_codeql_scan.py)
# collides with the wrapper's, and a shared sys.modules key would let one shadow
# the other and silently weaken every assertion below.
scan_delegate = import_skill_script(
    ".codeql/scripts/invoke_codeql_scan.py", module_name="codeql_scan_delegate"
)
config_delegate = import_skill_script(
    ".codeql/scripts/test_codeql_config.py", module_name="codeql_config_delegate"
)


def _namespace(operation: str, languages: list[str] | None, ci: bool) -> Any:
    """Build the argparse namespace the documented wrapper passes internally."""
    return wrapper.build_parser().parse_args(
        [
            "--operation",
            operation,
            *(["--languages", *languages] if languages else []),
            *(["--ci"] if ci else []),
        ]
    )


class TestDelegatesExistInRealRepository:
    """Anti-fabrication: assert against the repository, never against tmp_path."""

    def test_delegate_scripts_exist_in_real_repo(self) -> None:
        missing = [
            name
            for name in wrapper.DELEGATE_SCRIPT_NAMES
            if not (CODEQL_SCRIPTS_DIR / name).is_file()
        ]
        assert not missing, (
            f"Wrapper names delegates that do not exist in {CODEQL_SCRIPTS_DIR}: "
            f"{missing}. This is the Issue #4921 failure: the wrapper resolves a "
            f"script the repository does not ship."
        )

    def test_skill_wrapper_delegates_exist_in_real_repo(self) -> None:
        missing = [
            name
            for name in skill_wrapper.DELEGATE_SCRIPT_NAMES
            if not (CODEQL_SCRIPTS_DIR / name).is_file()
        ]
        assert not missing, f"Sibling wrapper names missing delegates: {missing}"

    def test_both_wrappers_agree_on_delegate_names(self) -> None:
        """One skill, one set of delegates. Divergence means one wrapper is stale."""
        assert wrapper.DELEGATE_SCRIPT_NAMES == skill_wrapper.DELEGATE_SCRIPT_NAMES

    def test_delegates_are_python_not_powershell(self) -> None:
        for name in wrapper.DELEGATE_SCRIPT_NAMES:
            assert name.endswith(".py"), f"{name} is not a Python delegate"

    @pytest.mark.parametrize("relative_path", WRAPPER_RELATIVE_PATHS)
    def test_no_powershell_references_remain(self, relative_path: str) -> None:
        """Regression guard naming the exact removed files from the issue."""
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        for removed in (
            "Test-CodeQLConfig.ps1",
            "Invoke-CodeQLScan.ps1",
            "Install-CodeQL.ps1",
        ):
            assert removed not in source, f"{relative_path} still references {removed}"
        assert '"pwsh"' not in source, f"{relative_path} still shells out to pwsh"


class TestFlagsMatchRealDelegateContracts:
    """Bind emitted flags to the delegate parsers, not to a remembered contract."""

    @pytest.mark.parametrize(
        ("operation", "languages", "ci"),
        [
            ("full", None, False),
            ("quick", None, False),
            ("full", ["python"], False),
            ("full", ["python", "actions"], True),
            ("quick", ["actions"], True),
        ],
    )
    def test_scan_flags_accepted_by_real_delegate_parser(
        self, operation: str, languages: list[str] | None, ci: bool
    ) -> None:
        command = wrapper._build_scan_command(
            Path("/repo/.codeql/scripts/invoke_codeql_scan.py"),
            _namespace(operation, languages, ci),
        )
        # Drop the interpreter and the script path; keep the delegate's own flags.
        delegate_args = command[2:]
        parsed = scan_delegate.build_parser().parse_args(delegate_args)

        assert parsed.use_cache is (operation == "quick")
        assert parsed.ci is ci
        assert parsed.languages == languages

    def test_config_delegate_accepts_wrapper_invocation(self) -> None:
        """The wrapper passes no flags; the delegate must accept an empty argv."""
        parsed = config_delegate.build_parser().parse_args([])
        assert parsed.config_path.endswith("codeql-config.yml")

    def test_quick_uses_cache_and_full_does_not(self) -> None:
        quick = wrapper._build_scan_command(Path("s.py"), _namespace("quick", None, False))
        full = wrapper._build_scan_command(Path("s.py"), _namespace("full", None, False))
        assert "--use-cache" in quick
        assert "--use-cache" not in full

    def test_install_hint_names_the_python_installer(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / ".codeql").mkdir()
        with patch.object(wrapper, "_get_repo_root", return_value=tmp_path):
            exit_code = wrapper.main(["--operation", "full"])

        assert exit_code == 3
        err = capsys.readouterr().err
        assert "install_codeql.py --add-to-path" in err
        assert "pwsh" not in err


class TestWrapperRunsInThisRepository:
    """End-to-end against the real checkout, the reproduction from the issue."""

    def test_validate_operation_succeeds_in_this_repository(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / WRAPPER_RELATIVE_PATHS[0]),
             "--operation", "validate"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT),
            check=False,
        )
        assert result.returncode == 0, (
            f"Issue #4921 reproduction: expected exit 0, got {result.returncode}.\n"
            f"stderr: {result.stderr}"
        )
        assert "Configuration script not found" not in result.stderr

    def test_validate_succeeds_from_a_subdirectory(self) -> None:
        """Delegates run with cwd=repo root, so the caller's cwd cannot break them."""
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / WRAPPER_RELATIVE_PATHS[0]),
             "--operation", "validate"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT / "tests"),
            check=False,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"


class TestNegativePaths:
    """Failures must report exit 3 or 2, never a silent success."""

    def test_missing_config_delegate_returns_3(self, tmp_path: Path) -> None:
        (tmp_path / ".codeql").mkdir()
        with patch.object(wrapper, "_get_repo_root", return_value=tmp_path):
            assert wrapper.main(["--operation", "validate"]) == 3

    def test_missing_scan_delegate_returns_3(self, tmp_path: Path) -> None:
        cli = tmp_path / ".codeql" / "cli" / "codeql"
        cli.parent.mkdir(parents=True)
        cli.write_text("")
        with patch.object(wrapper, "_get_repo_root", return_value=tmp_path):
            assert wrapper.main(["--operation", "full"]) == 3

    def test_outside_git_repository_returns_3(self) -> None:
        with patch.object(wrapper, "_get_repo_root", return_value=None):
            assert wrapper.main(["--operation", "validate"]) == 3

    def test_invalid_config_maps_delegate_1_to_wrapper_2(self, tmp_path: Path) -> None:
        """Delegate exit 1 (invalid) becomes the wrapper's documented 2."""
        self._write_delegate(tmp_path, "test_codeql_config.py")
        with (
            patch.object(wrapper, "_get_repo_root", return_value=tmp_path),
            patch("subprocess.run", return_value=MagicMock(returncode=1)),
        ):
            assert wrapper.main(["--operation", "validate"]) == 2

    def test_missing_config_file_maps_delegate_2_to_wrapper_2(
        self, tmp_path: Path
    ) -> None:
        """Delegate exit 2 (config file absent) also becomes the wrapper's 2."""
        self._write_delegate(tmp_path, "test_codeql_config.py")
        with (
            patch.object(wrapper, "_get_repo_root", return_value=tmp_path),
            patch("subprocess.run", return_value=MagicMock(returncode=2)),
        ):
            assert wrapper.main(["--operation", "validate"]) == 2

    def test_findings_in_ci_mode_pass_through_as_1(self, tmp_path: Path) -> None:
        self._write_delegate(tmp_path, "invoke_codeql_scan.py")
        cli = tmp_path / ".codeql" / "cli" / "codeql"
        cli.parent.mkdir(parents=True)
        cli.write_text("")
        with (
            patch.object(wrapper, "_get_repo_root", return_value=tmp_path),
            patch("subprocess.run", return_value=MagicMock(returncode=1)),
        ):
            assert wrapper.main(["--operation", "full", "--ci"]) == 1

    @staticmethod
    def _write_delegate(root: Path, name: str) -> Path:
        scripts = root / ".codeql" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        delegate = scripts / name
        delegate.write_text("# delegate")
        return delegate


class TestEdgeCases:
    def test_python_executable_falls_back_when_unset(self) -> None:
        """sys.executable is documented to be empty in frozen builds."""
        with patch.object(sys, "executable", ""):
            assert wrapper._python_executable() == "python3"
            assert skill_wrapper._python_executable() == "python3"

    def test_python_executable_prefers_current_interpreter(self) -> None:
        with patch.object(sys, "executable", "/venv/bin/python"):
            assert wrapper._python_executable() == "/venv/bin/python"

    def test_delegate_launch_failure_returns_3(self, tmp_path: Path) -> None:
        TestNegativePaths._write_delegate(tmp_path, "test_codeql_config.py")
        with (
            patch.object(wrapper, "_get_repo_root", return_value=tmp_path),
            patch("subprocess.run", side_effect=OSError("Exec format error")),
        ):
            assert wrapper.main(["--operation", "validate"]) == 3

    def test_unexpected_delegate_exit_code_passes_through(self, tmp_path: Path) -> None:
        TestNegativePaths._write_delegate(tmp_path, "invoke_codeql_scan.py")
        cli = tmp_path / ".codeql" / "cli" / "codeql"
        cli.parent.mkdir(parents=True)
        cli.write_text("")
        with (
            patch.object(wrapper, "_get_repo_root", return_value=tmp_path),
            patch("subprocess.run", return_value=MagicMock(returncode=42)),
        ):
            assert wrapper.main(["--operation", "full"]) == 42

    def test_delegate_runs_from_repository_root(self, tmp_path: Path) -> None:
        """cwd anchors the delegate's relative defaults to the repository."""
        TestNegativePaths._write_delegate(tmp_path, "test_codeql_config.py")
        with (
            patch.object(wrapper, "_get_repo_root", return_value=tmp_path),
            patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
        ):
            wrapper.main(["--operation", "validate"])

        assert mock_run.call_args.kwargs["cwd"] == str(tmp_path)

    def test_delegate_launched_with_current_interpreter(self, tmp_path: Path) -> None:
        TestNegativePaths._write_delegate(tmp_path, "test_codeql_config.py")
        with (
            patch.object(wrapper, "_get_repo_root", return_value=tmp_path),
            patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_run,
        ):
            wrapper.main(["--operation", "validate"])

        command = mock_run.call_args.args[0]
        assert command[0] == sys.executable
        assert command[1].endswith("test_codeql_config.py")

    def test_missing_codeql_directory_skips_without_error(self, tmp_path: Path) -> None:
        """Consumer repos without .codeql/ are skipped, not failed."""
        with patch.object(wrapper, "_get_repo_root", return_value=tmp_path):
            assert wrapper.main(["--operation", "full"]) == 0
