"""Tests for scripts/validation/validate_python_syntax.py (issue #2655).

Pins behaviour of the floor-aware parse gate that prevents the PR #2640
regression: PEP 758 ``except A, B:`` syntax is valid on the 3.14 dev target but
a ``SyntaxError`` on the 3.10-3.13 hosts the CLI may run under, so the gate must
parse against the declared support floor, not the host interpreter.

- pos: a tree that parses at the floor returns exit 0
- neg (floor): the exact regression shape (PEP 758 except) is rejected at the
  floor even though the host interpreter (3.14) would accept it
- neg (classic): an always-invalid syntax error is rejected
- edge: an invalid repo root returns exit 2 (config error per ADR-035)
- branch: the git-unavailable filesystem-walk fallback skips vendored dirs
- floor: ``support_floor`` reads ``requires-python`` from pyproject
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "validate_python_syntax.py"
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from validate_python_syntax import (  # noqa: E402
    _walk_python_files,
    find_syntax_errors,
    support_floor,
    validate_python_syntax,
)

# PEP 758: valid on Python 3.14, SyntaxError on 3.13 and earlier.
_PEP758 = "try:\n    x = 1\nexcept OSError, ValueError:\n    pass\n"
# Always invalid on every Python 3.
_CLASSIC = "def broken(:\n    pass\n"
# Floor-clean equivalent.
_CLEAN = "try:\n    x = 1\nexcept (OSError, ValueError):\n    pass\n"

_FLOOR_310 = 'requires-python = ">=3.10"\n'


def _git_repo(root: Path) -> None:
    """Initialise a git repo and stage everything so git ls-files sees it."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)


def _run_cli(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(repo_root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_floor_clean_tree_passes(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    (tmp_path / "ok.py").write_text(_CLEAN, encoding="utf-8")
    _git_repo(tmp_path)

    result = _run_cli(tmp_path)

    assert result.returncode == 0, result.stderr
    assert find_syntax_errors(tmp_path) == []


def test_pep758_rejected_at_floor(tmp_path: Path) -> None:
    # Guards against the exact regression: valid on the 3.14 host running this
    # test, but the gate must reject it because the floor is 3.10.
    (tmp_path / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    (tmp_path / "broken.py").write_text(_PEP758, encoding="utf-8")
    _git_repo(tmp_path)

    result = _run_cli(tmp_path)

    assert result.returncode == 1
    assert "broken.py" in result.stderr
    assert "except expressions without parentheses" in result.stderr


def test_classic_syntax_error_rejected(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    (tmp_path / "classic.py").write_text(_CLASSIC, encoding="utf-8")
    _git_repo(tmp_path)

    failures = find_syntax_errors(tmp_path)

    assert any(p.name == "classic.py" for p, _ in failures)


def test_invalid_repo_root_returns_config_error(tmp_path: Path) -> None:
    result = _run_cli(tmp_path / "does-not-exist")

    assert result.returncode == 2


def test_walk_fallback_skips_vendored_and_finds_broken(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text(_PEP758, encoding="utf-8")
    vendored = tmp_path / ".venv" / "lib"
    vendored.mkdir(parents=True)
    (vendored / "alsobroken.py").write_text(_PEP758, encoding="utf-8")

    found = {p.name for p in _walk_python_files(tmp_path)}

    assert "broken.py" in found
    assert "alsobroken.py" not in found


def test_support_floor_reads_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('requires-python = ">=3.11"\n', encoding="utf-8")

    assert support_floor(tmp_path) == (3, 11)


def test_support_floor_defaults_when_missing(tmp_path: Path) -> None:
    assert support_floor(tmp_path) == (3, 10)


def test_validate_function_returns_false_on_floor_violation(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(_FLOOR_310, encoding="utf-8")
    (tmp_path / "broken.py").write_text(_PEP758, encoding="utf-8")
    _git_repo(tmp_path)

    assert validate_python_syntax(tmp_path) is False


def test_repo_itself_parses_at_floor() -> None:
    # The live repository must pass its own gate.
    assert find_syntax_errors(REPO_ROOT) == []
