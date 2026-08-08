from __future__ import annotations

import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(VALIDATION_DIR))

import check_duplicate_test_helpers as checker
import pre_pr_sequence


@pytest.fixture
def repo_workspace() -> Iterator[Path]:
    scratch_root = REPO_ROOT / ".pytest_tmp"
    scratch_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="duplicate-test-helpers-", dir=scratch_root) as raw:
        repo = Path(raw)
        (repo / "tests").mkdir()
        yield repo


def _write(repo: Path, relative_path: str, content: str) -> Path:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestDuplicateTestHelpers:
    def test_repository_tests_have_no_duplicate_module_level_helpers(self) -> None:
        assert checker.find_duplicate_module_level_helpers(REPO_ROOT) == []

    def test_accepts_unique_module_level_helpers(self, repo_workspace: Path) -> None:
        _write(
            repo_workspace,
            "tests/test_ok.py",
            "def _first():\n"
            "    return 1\n\n"
            "def _second():\n"
            "    return 2\n",
        )

        assert checker.find_duplicate_module_level_helpers(repo_workspace) == []
        assert checker.validate_duplicate_test_helpers(repo_workspace)

    def test_reports_duplicate_private_helper_with_both_lines(
        self, repo_workspace: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(
            repo_workspace,
            "tests/test_duplicate.py",
            "def _helper():\n"
            "    return 1\n\n"
            "def _helper(value):\n"
            "    return value\n",
        )

        findings = checker.find_duplicate_module_level_helpers(repo_workspace)
        valid = checker.validate_duplicate_test_helpers(repo_workspace)
        captured = capsys.readouterr()

        assert not valid
        assert findings == [(repo_workspace / "tests/test_duplicate.py", "_helper", 1, 4)]
        assert "tests/test_duplicate.py:1 and 4 duplicate _helper()" in captured.err

    def test_reports_duplicate_async_helpers(self, repo_workspace: Path) -> None:
        _write(
            repo_workspace,
            "tests/test_async_duplicate.py",
            "async def _load():\n"
            "    return 1\n\n"
            "async def _load(value):\n"
            "    return value\n",
        )

        assert checker.find_duplicate_module_level_helpers(repo_workspace) == [
            (repo_workspace / "tests/test_async_duplicate.py", "_load", 1, 4)
        ]

    def test_ignores_nested_functions_and_class_methods(self, repo_workspace: Path) -> None:
        _write(
            repo_workspace,
            "tests/test_scopes.py",
            "def _outer():\n"
            "    def _helper():\n"
            "        return 1\n"
            "    def _helper(value):\n"
            "        return value\n"
            "    return _helper(2)\n\n"
            "class TestThing:\n"
            "    def _helper(self):\n"
            "        return 1\n"
            "    def _helper(self, value):\n"
            "        return value\n",
        )

        assert checker.find_duplicate_module_level_helpers(repo_workspace) == []

    def test_syntax_error_fails_closed(self, repo_workspace: Path) -> None:
        _write(repo_workspace, "tests/test_bad.py", "def broken(\n")

        with pytest.raises(checker.ScanError, match="could not analyze test source"):
            checker.find_duplicate_module_level_helpers(repo_workspace)

    def test_invalid_utf8_fails_closed(self, repo_workspace: Path) -> None:
        path = repo_workspace / "tests/test_bad.py"
        path.write_bytes(b"\xff\xfe")

        with pytest.raises(checker.ScanError, match="could not analyze test source"):
            checker.find_duplicate_module_level_helpers(repo_workspace)

    def test_git_scope_excludes_ignored_test_artifacts(
        self, repo_workspace: Path
    ) -> None:
        subprocess.run(["git", "init", "-q"], cwd=repo_workspace, check=True)
        _write(repo_workspace, ".gitignore", "tests/tmp/\n")
        _write(repo_workspace, "tests/test_clean.py", "def clean():\n    pass\n")
        ignored = repo_workspace / "tests/tmp/bin.py"
        ignored.parent.mkdir()
        ignored.write_bytes(b"\xff\xfe")
        subprocess.run(
            ["git", "add", ".gitignore", "tests/test_clean.py"],
            cwd=repo_workspace,
            check=True,
        )

        assert checker.find_duplicate_module_level_helpers(repo_workspace) == []

    def test_cli_exit_codes(self, repo_workspace: Path) -> None:
        script = REPO_ROOT / "scripts/validation/check_duplicate_test_helpers.py"
        clean_repo = repo_workspace / "clean"
        dirty_repo = repo_workspace / "dirty"
        clean_repo.mkdir()
        dirty_repo.mkdir()
        (clean_repo / "tests").mkdir()
        (dirty_repo / "tests").mkdir()
        _write(clean_repo, "tests/test_clean.py", "def _one():\n    return 1\n")
        _write(
            dirty_repo,
            "tests/test_dirty.py",
            "def _same():\n    return 1\n\ndef _same():\n    return 2\n",
        )

        clean = subprocess.run(
            [sys.executable, str(script), str(clean_repo)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        dirty = subprocess.run(
            [sys.executable, str(script), str(dirty_repo)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        config = subprocess.run(
            [sys.executable, str(script), str(repo_workspace / "missing")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        assert clean.returncode == 0
        assert dirty.returncode == 1
        assert config.returncode == 2
        assert "duplicate _same()" in dirty.stderr
        assert "Invalid repository root" in config.stderr

    def test_cli_returns_two_for_invalid_tracked_source(
        self, repo_workspace: Path
    ) -> None:
        script = REPO_ROOT / "scripts/validation/check_duplicate_test_helpers.py"
        bad_repo = repo_workspace / "bad"
        (bad_repo / "tests").mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=bad_repo, check=True)
        (bad_repo / "tests/test_bad.py").write_bytes(b"\xff\xfe")
        subprocess.run(["git", "add", "tests/test_bad.py"], cwd=bad_repo, check=True)

        result = subprocess.run(
            [sys.executable, str(script), str(bad_repo)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        assert result.returncode == 2
        assert "Duplicate-helper scan did not run" in result.stderr

    def test_pre_pr_sequence_runs_duplicate_helper_detection_after_nested_tests(self) -> None:
        recorded: list[str] = []

        def fake_run_validation(
            name: str, _state: object, _callback: object, skip: bool = False
        ) -> bool:
            recorded.append(name)
            return True

        state = SimpleNamespace(total=0, passed=0, failed=0, skipped=0)
        args = SimpleNamespace(quick=True, skip_tests=False, verbose=False)
        pre_pr_sequence.run_all_validations(REPO_ROOT, args, state, fake_run_validation)

        idx = recorded.index("Nested Test Detection")
        assert recorded[idx + 1] == "Duplicate Test Helper Detection"
