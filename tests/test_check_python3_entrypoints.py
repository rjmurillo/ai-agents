"""Tests for check_python3_entrypoints validator.

Covers:
- Detection of bare python3 invocations that reference scripts importing
  third-party modules (positive case)
- Clean pass when scripts are stdlib-only (negative case)
- Edge cases: missing script file, missing doc file, non-python3 invocation
- Exit-code contract: main() returns 1 on violations, 0 on clean pass

Mutation targets verified:
- _collect_third_party_imports: missing yaml/anthropic yield no violations
- check_docs: bare pattern match, third-party check
- main: exit code under clean pass and violation
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation.check_python3_entrypoints import (
    _THIRD_PARTY_IMPORTS,
    _collect_third_party_imports,
    check_docs,
    main,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).parent.parent
_VALIDATOR = _REPO_ROOT / "scripts/validation/check_python3_entrypoints.py"

# Subprocess captures below pass encoding="utf-8", errors="replace". The
# repo-wide guard tests/test_subprocess_text_encoding.py enforces the encoding
# and states verbatim: "It checks ``encoding`` only. ``errors`` is deliberately
# left to each call site". These sites set it because the child echoes a
# tmp_path that carries whatever bytes the OS gave it, and these assertions
# read the exit code, never the text: a strict decoder could only turn a
# passing run into an unrelated UnicodeDecodeError.


def _write_script(tmp_path: Path, name: str, source: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(source, encoding="utf-8")
    return p


def _write_doc(tmp_path: Path, name: str, lines: list[str]) -> Path:
    p = tmp_path / name
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# _collect_third_party_imports
# ---------------------------------------------------------------------------


class TestCollectThirdPartyImports:
    def test_detects_yaml_import(self, tmp_path: Path) -> None:
        s = _write_script(tmp_path, "a.py", "import yaml\nprint('hi')\n")
        assert "yaml" in _collect_third_party_imports(s)

    def test_detects_yaml_from_import(self, tmp_path: Path) -> None:
        s = _write_script(tmp_path, "a.py", "from yaml import safe_load\n")
        assert "yaml" in _collect_third_party_imports(s)

    def test_detects_anthropic_import(self, tmp_path: Path) -> None:
        s = _write_script(tmp_path, "a.py", "import anthropic\n")
        assert "anthropic" in _collect_third_party_imports(s)

    def test_stdlib_only_returns_empty(self, tmp_path: Path) -> None:
        s = _write_script(tmp_path, "a.py", "import sys\nimport re\nfrom pathlib import Path\n")
        assert _collect_third_party_imports(s) == set()

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert _collect_third_party_imports(tmp_path / "nonexistent.py") == set()

    def test_syntax_error_returns_empty(self, tmp_path: Path) -> None:
        s = _write_script(tmp_path, "a.py", "def broken(\n")
        assert _collect_third_party_imports(s) == set()

    def test_nested_import_detected(self, tmp_path: Path) -> None:
        s = _write_script(tmp_path, "a.py", "def f():\n    import yaml\n")
        assert "yaml" in _collect_third_party_imports(s)

    def test_third_party_imports_set_contains_yaml(self) -> None:
        assert "yaml" in _THIRD_PARTY_IMPORTS

    def test_third_party_imports_set_contains_anthropic(self) -> None:
        assert "anthropic" in _THIRD_PARTY_IMPORTS


# ---------------------------------------------------------------------------
# check_docs
# ---------------------------------------------------------------------------


class TestCheckDocs:
    def test_violation_when_script_imports_yaml(self, tmp_path: Path) -> None:
        _write_script(tmp_path, "scripts/audit.py", "import yaml\n")
        doc = _write_doc(tmp_path, "README.md", ["Run: `python3 scripts/audit.py`"])

        violations = check_docs([doc], tmp_path)

        assert len(violations) == 1
        doc_p, lineno, rel, bad = violations[0]
        assert rel == "scripts/audit.py"
        assert "yaml" in bad
        assert lineno == 1

    def test_no_violation_when_stdlib_only(self, tmp_path: Path) -> None:
        _write_script(tmp_path, "scripts/clean.py", "import sys\n")
        doc = _write_doc(tmp_path, "README.md", ["Run: `python3 scripts/clean.py`"])

        violations = check_docs([doc], tmp_path)

        assert violations == []

    def test_no_violation_when_uv_run(self, tmp_path: Path) -> None:
        _write_script(tmp_path, "scripts/audit.py", "import yaml\n")
        doc = _write_doc(tmp_path, "README.md", ["Run: `uv run python scripts/audit.py`"])

        violations = check_docs([doc], tmp_path)

        assert violations == []

    def test_missing_doc_file_is_skipped(self, tmp_path: Path) -> None:
        violations = check_docs([tmp_path / "missing.md"], tmp_path)
        assert violations == []

    def test_missing_script_file_is_skipped(self, tmp_path: Path) -> None:
        doc = _write_doc(
            tmp_path, "README.md", ["Run: `python3 scripts/nonexistent.py`"]
        )
        violations = check_docs([doc], tmp_path)
        assert violations == []

    def test_multiple_violations_reported(self, tmp_path: Path) -> None:
        _write_script(tmp_path, "scripts/a.py", "import yaml\n")
        _write_script(tmp_path, "scripts/b.py", "import anthropic\n")
        doc = _write_doc(
            tmp_path,
            "README.md",
            [
                "python3 scripts/a.py",
                "python3 scripts/b.py",
            ],
        )

        violations = check_docs([doc], tmp_path)

        assert len(violations) == 2

    def test_line_number_is_accurate(self, tmp_path: Path) -> None:
        _write_script(tmp_path, "scripts/audit.py", "import yaml\n")
        doc = _write_doc(
            tmp_path,
            "README.md",
            ["# Title", "Some prose.", "python3 scripts/audit.py"],
        )

        violations = check_docs([doc], tmp_path)

        assert len(violations) == 1
        assert violations[0][1] == 3


# ---------------------------------------------------------------------------
# main (exit code tests)
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_0_on_clean_pass(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        _write_script(tmp_path, "scripts/clean.py", "import sys\n")
        _write_doc(tmp_path, "README.md", ["python3 scripts/clean.py"])

        result = main(["--docs", "README.md", "--repo-root", str(tmp_path)])

        assert result == 0

    def test_returns_1_on_violation(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        _write_script(tmp_path, "scripts/audit.py", "import yaml\n")
        _write_doc(tmp_path, "README.md", ["python3 scripts/audit.py"])

        result = main(["--docs", "README.md", "--repo-root", str(tmp_path)])

        assert result == 1

    def test_exits_nonzero_as_subprocess(self, tmp_path: Path) -> None:
        """Process exit code must be nonzero, not just the helper return value."""
        _write_script(tmp_path, "scripts/audit.py", "import yaml\n")
        _write_doc(tmp_path, "README.md", ["python3 scripts/audit.py"])

        result = subprocess.run(
            [sys.executable, str(_VALIDATOR), "--docs", "README.md", "--repo-root", str(tmp_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert result.returncode == 1

    def test_exits_zero_on_clean_pass_as_subprocess(self, tmp_path: Path) -> None:
        """Process exit code must be 0 on clean pass."""
        _write_script(tmp_path, "scripts/clean.py", "import sys\n")
        _write_doc(tmp_path, "README.md", ["python3 scripts/clean.py"])

        result = subprocess.run(
            [sys.executable, str(_VALIDATOR), "--docs", "README.md", "--repo-root", str(tmp_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert result.returncode == 0

    def test_returns_0_when_doc_missing(self, tmp_path: Path) -> None:
        result = main(["--docs", "nonexistent.md", "--repo-root", str(tmp_path)])
        assert result == 0

    def test_returns_2_when_doc_is_unreadable(self, tmp_path: Path) -> None:
        """A doc that exists but cannot be read is a file access error (exit 2).

        A directory is the portable unreadable-but-existing path: read_text
        raises IsADirectoryError on POSIX and PermissionError on Windows, both
        OSError. Without the mapping the exception escapes main() and the
        process dies with a traceback and exit 1, which the module contract
        reserves for "mismatches detected".
        """
        (tmp_path / "README.md").mkdir()

        result = main(["--docs", "README.md", "--repo-root", str(tmp_path)])

        assert result == 2

    def test_exits_2_as_subprocess_when_doc_is_unreadable(self, tmp_path: Path) -> None:
        """Process exit code for a file access error is 2, with no traceback."""
        (tmp_path / "README.md").mkdir()

        result = subprocess.run(
            [sys.executable, str(_VALIDATOR), "--docs", "README.md", "--repo-root", str(tmp_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert result.returncode == 2, result.stderr
        assert "Traceback" not in result.stderr
        assert "cannot read documentation file" in result.stderr
