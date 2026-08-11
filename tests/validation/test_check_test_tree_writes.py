"""Tests for check_test_tree_writes.py (issue #3772).

Covers the gate that detects test files writing to the repository working
tree instead of using ``tmp_path``.

Positive tests: clean patterns that must NOT be flagged.
Negative controls: patterns that MUST be flagged.
Edge cases: sanctioned scratch roots, read-only shutil operations.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

# Import the module under test.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "validation"))
import check_test_tree_writes as cttw

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_test_file(tmp_path: Path, source: str, name: str = "test_example.py") -> Path:
    """Write *source* to a ``test_*.py`` file inside *tmp_path* and return it."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(source), encoding="utf-8")
    return p


def _findings(source: str, tmp_path: Path) -> list[tuple[int, str]]:
    """Parse *source* and return (lineno, desc) findings."""
    p = _make_test_file(tmp_path, source)
    return cttw._scan_file(p)


# ---------------------------------------------------------------------------
# positive tests: patterns that must NOT be flagged
# ---------------------------------------------------------------------------


class TestCleanPatterns:
    def test_write_to_tmp_path_is_not_flagged(self, tmp_path: Path) -> None:
        source = """\
            _PROJECT_ROOT = Path("/repo")
            def test_something(tmp_path):
                (tmp_path / "output.txt").write_text("hello")
        """
        assert _findings(source, tmp_path) == []

    def test_open_read_only_is_not_flagged(self, tmp_path: Path) -> None:
        source = """\
            _PROJECT_ROOT = Path("/repo")
            def test_something():
                with open(_PROJECT_ROOT / "README.md", "r") as f:
                    _ = f.read()
        """
        assert _findings(source, tmp_path) == []

    def test_sanctioned_pytest_tmp_is_not_flagged(self, tmp_path: Path) -> None:
        source = """\
            _PROJECT_ROOT = Path("/repo")
            def test_something():
                (_PROJECT_ROOT / ".pytest_tmp" / "sub").mkdir(parents=True)
        """
        assert _findings(source, tmp_path) == []

    def test_shutil_copytree_source_from_root_is_not_flagged(self, tmp_path: Path) -> None:
        """Reading FROM the repo root is not a write to the repo root."""
        source = """\
            import shutil
            REPO_ROOT = Path("/repo")
            def test_staging(tmp_path):
                dest = tmp_path / "stage"
                shutil.copytree(REPO_ROOT / "templates", dest / "templates")
        """
        assert _findings(source, tmp_path) == []

    def test_tempfile_usage_not_flagged(self, tmp_path: Path) -> None:
        source = """\
            import tempfile
            _PROJECT_ROOT = Path("/repo")
            def test_something():
                with tempfile.TemporaryDirectory() as d:
                    p = Path(d) / "out.txt"
                    p.write_text("x")
        """
        assert _findings(source, tmp_path) == []

    def test_project_root_joined_to_tempfile_factory_is_not_flagged(
        self, tmp_path: Path
    ) -> None:
        source = """\
            import tempfile
            _PROJECT_ROOT = Path("/repo")
            def test_something():
                (_PROJECT_ROOT / tempfile.mkdtemp() / "out.txt").write_text("hello")
        """
        assert _findings(source, tmp_path) == []

    def test_no_root_binding_not_flagged(self, tmp_path: Path) -> None:
        source = """\
            def test_something(tmp_path):
                (tmp_path / "file.txt").write_text("data")
        """
        assert _findings(source, tmp_path) == []

    def test_open_without_mode_not_flagged(self, tmp_path: Path) -> None:
        """open() with no mode defaults to 'r'; should not flag."""
        source = """\
            _PROJECT_ROOT = Path("/repo")
            def test_something():
                with open(_PROJECT_ROOT / "config.txt") as f:
                    _ = f.read()
        """
        assert _findings(source, tmp_path) == []

    def test_shutil_copy_to_tmp_path_not_flagged(self, tmp_path: Path) -> None:
        source = """\
            import shutil
            REPO_ROOT = Path("/repo")
            def test_copy(tmp_path):
                shutil.copy(REPO_ROOT / "src.py", tmp_path / "dst.py")
        """
        assert _findings(source, tmp_path) == []


# ---------------------------------------------------------------------------
# negative controls: patterns that MUST be flagged
# ---------------------------------------------------------------------------


class TestFlaggedPatterns:
    def test_write_text_to_project_root_flagged(self, tmp_path: Path) -> None:
        source = """\
            _PROJECT_ROOT = Path("/repo")
            def test_something():
                (_PROJECT_ROOT / "output.txt").write_text("hello")
        """
        findings = _findings(source, tmp_path)
        assert len(findings) == 1
        assert "write_text" in findings[0][1]

    def test_mkdir_to_project_root_flagged(self, tmp_path: Path) -> None:
        source = """\
            REPO_ROOT = Path("/repo")
            def test_something():
                (REPO_ROOT / "newdir").mkdir(parents=True)
        """
        findings = _findings(source, tmp_path)
        assert len(findings) == 1
        assert "mkdir" in findings[0][1]

    def test_touch_to_project_root_flagged(self, tmp_path: Path) -> None:
        source = """\
            PROJECT_ROOT = Path("/repo")
            def test_something():
                (PROJECT_ROOT / "marker.txt").touch()
        """
        findings = _findings(source, tmp_path)
        assert len(findings) == 1
        assert "touch" in findings[0][1]

    def test_open_write_to_project_root_flagged(self, tmp_path: Path) -> None:
        source = """\
            _PROJECT_ROOT = Path("/repo")
            def test_something():
                with open(_PROJECT_ROOT / "out.txt", "w") as f:
                    f.write("data")
        """
        findings = _findings(source, tmp_path)
        assert len(findings) == 1
        assert "open()" in findings[0][1]

    def test_open_append_to_project_root_flagged(self, tmp_path: Path) -> None:
        source = """\
            _PROJECT_ROOT = Path("/repo")
            def test_something():
                with open(_PROJECT_ROOT / "log.txt", "a") as f:
                    f.write("entry")
        """
        findings = _findings(source, tmp_path)
        assert len(findings) == 1

    def test_shutil_copytree_dest_to_project_root_flagged(self, tmp_path: Path) -> None:
        source = """\
            import shutil
            _PROJECT_ROOT = Path("/repo")
            def test_something(tmp_path):
                shutil.copytree(tmp_path / "src", _PROJECT_ROOT / "dst")
        """
        findings = _findings(source, tmp_path)
        assert len(findings) == 1
        assert "copytree" in findings[0][1]

    def test_write_bytes_to_project_root_flagged(self, tmp_path: Path) -> None:
        source = """\
            _PROJECT_ROOT = Path("/repo")
            def test_something():
                (_PROJECT_ROOT / "data.bin").write_bytes(b"\\x00")
        """
        findings = _findings(source, tmp_path)
        assert len(findings) == 1
        assert "write_bytes" in findings[0][1]

    def test_lineno_is_correct(self, tmp_path: Path) -> None:
        source = """\
            _PROJECT_ROOT = Path("/repo")

            def test_something():
                pass
                (_PROJECT_ROOT / "out.txt").write_text("x")
        """
        findings = _findings(source, tmp_path)
        assert findings, "expected at least one finding"
        assert findings[0][0] == 5  # line 5 is the write_text call


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_syntax_error_file_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "test_bad.py"
        p.write_text("def test(:\n", encoding="utf-8")
        assert cttw._scan_file(p) == []

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "test_empty.py"
        p.write_text("", encoding="utf-8")
        assert cttw._scan_file(p) == []

    def test_shutil_rmtree_on_root_flagged(self, tmp_path: Path) -> None:
        source = """\
            import shutil
            _PROJECT_ROOT = Path("/repo")
            def test_cleanup():
                shutil.rmtree(_PROJECT_ROOT / "generated")
        """
        findings = _findings(source, tmp_path)
        assert len(findings) == 1
        assert "rmtree" in findings[0][1]

    def test_multiple_findings_all_reported(self, tmp_path: Path) -> None:
        source = """\
            _PROJECT_ROOT = Path("/repo")
            def test_multi():
                (_PROJECT_ROOT / "a.txt").write_text("a")
                (_PROJECT_ROOT / "b.txt").write_text("b")
        """
        findings = _findings(source, tmp_path)
        assert len(findings) == 2

    def test_nested_function_write_flagged(self, tmp_path: Path) -> None:
        """Writes inside helper functions within the test file are also detected."""
        source = """\
            _PROJECT_ROOT = Path("/repo")
            def _helper():
                (_PROJECT_ROOT / "helper.txt").write_text("x")
            def test_something():
                _helper()
        """
        findings = _findings(source, tmp_path)
        assert len(findings) == 1


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_exit_0_on_clean_repo(self, tmp_path: Path) -> None:
        """main() exits 0 when no writes are found."""
        # Use a minimal fake git repo structure.
        (tmp_path / ".git").mkdir()
        subprocess.run(
            ["git", "init", str(tmp_path)],
            capture_output=True,
            check=False,
        )
        # No test files in the repo -> zero findings.
        result = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[2]
                    / "scripts"
                    / "validation"
                    / "check_test_tree_writes.py"
                ),
                "--repo-root",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0
        assert "OK" in result.stdout

    def test_exit_2_on_non_repo(self, tmp_path: Path) -> None:
        """main() exits 2 when the path is not a git repository."""
        result = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[2]
                    / "scripts"
                    / "validation"
                    / "check_test_tree_writes.py"
                ),
                "--repo-root",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 2

    def test_exit_1_when_flagged_file_in_repo(self, tmp_path: Path) -> None:
        """main() exits 1 when a flagged test file is tracked in the repo."""
        # Set up a minimal git repo with one offending test file.
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "t@t.com"],
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "T"],
            capture_output=True,
            check=False,
        )
        offending = tmp_path / "test_bad.py"
        offending.write_text(
            "_PROJECT_ROOT = Path('.')\n"
            "def test_bad():\n"
            "    (_PROJECT_ROOT / 'out.txt').write_text('x')\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "test_bad.py"],
            capture_output=True,
            check=True,
        )
        result = subprocess.run(
            [
                sys.executable,
                str(
                    Path(__file__).resolve().parents[2]
                    / "scripts"
                    / "validation"
                    / "check_test_tree_writes.py"
                ),
                "--repo-root",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 1
        assert "FAIL" in result.stderr
