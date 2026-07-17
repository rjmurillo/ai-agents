"""Ruff's formatter target must track the syntax support floor (issue #3126).

Root cause: ``[tool.ruff] target-version`` was ``py314`` (the ``requires-python``
dev/install contract) while ``scripts/validation/validate_python_syntax.py``
enforces a 3.10 hook-portability floor. ``ruff format`` then rewrote portable
``except (A, B):`` into PEP 758 ``except A, B:``, which the floor gate rejects,
creating a repeatable edit, format, fail, repair loop.

- pos: the repo ruff config formats an except tuple to floor-parseable output
- neg: a ``py314`` formatter target re-emits the PEP 758 form the floor rejects,
       proving the positive assertion has teeth (a real negative control)
- guard: the configured ruff target equals the support floor, so the two cannot
         silently drift back into opposition
"""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from validate_python_syntax import support_floor  # noqa: E402

# Portable on every Python 3: an exception tuple wrapped in parentheses.
_EXCEPT_TUPLE = "try:\n    x = 1\nexcept (OSError, ValueError):\n    pass\n"
# PEP 758 form ruff emits under a >=3.14 target; a SyntaxError below 3.14.
_PEP758_MARKER = "except OSError, ValueError:"


def _floor_ruff_tag() -> str:
    """Render the support floor as ruff's ``pyXY`` target tag."""
    major, minor = support_floor()
    return f"py{major}{minor}"


def _ruff_format(source: str, *, target: str | None = None) -> str:
    """Format ``source`` via stdin using the repo ruff config.

    Uses the ``ruff`` on PATH (present inside the uv dev venv that runs the
    suite). Passing ``target`` overrides ``target-version`` to exercise the
    negative control. Stdin avoids any per-path exclude in the repo config.
    """
    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff is not on PATH; run under the uv dev environment")
    cmd = [ruff, "format", "--config", str(PYPROJECT)]
    if target is not None:
        cmd += ["--target-version", target]
    cmd.append("-")
    result = subprocess.run(
        cmd,
        input=source,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    )
    return result.stdout


def test_configured_ruff_target_equals_support_floor() -> None:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    target = data["tool"]["ruff"]["target-version"]
    assert target == _floor_ruff_tag(), (
        "ruff target-version must match the validate_python_syntax support "
        "floor so the formatter cannot emit syntax the floor gate rejects"
    )


def test_repo_config_format_preserves_floor_parseable_except() -> None:
    formatted = _ruff_format(_EXCEPT_TUPLE)

    assert _PEP758_MARKER not in formatted
    assert "except (OSError, ValueError):" in formatted
    # Must parse at the declared floor using the gate's own mechanism.
    ast.parse(formatted, feature_version=support_floor())


def test_py314_target_emits_floor_breaking_syntax_negative_control() -> None:
    # A py314 formatter target reintroduces the exact regression; the literal
    # 3.14 here is the PEP 758 boundary, not the (lower) support floor.
    formatted = _ruff_format(_EXCEPT_TUPLE, target="py314")

    assert _PEP758_MARKER in formatted
    with pytest.raises(SyntaxError):
        ast.parse(formatted, feature_version=support_floor())
