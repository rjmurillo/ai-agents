"""Regression tests for issue #3085: read-only PR scripts run offline.

Running ``uv run .claude/skills/github/scripts/pr/*.py`` in a network-restricted
sandbox resolves the whole project environment, which downloads
``anthropic==0.116.0`` (a core dependency in ``pyproject.toml``) from PyPI and
times out. The read-only PR status scripts never call the anthropic SDK, so the
documented offline path is bare ``python3`` (see the github skill's "Offline
Invocation" section).

These tests pin the invariant that keeps the offline path working: the read-only
PR scripts and ``github_core`` must import without the anthropic SDK, at both
import time and run time.

The runtime checks block ``anthropic`` in a subprocess via
``sys.modules["anthropic"] = None`` (CPython makes ``import anthropic`` raise
``ImportError`` when the entry is ``None``). The blocker matters because
``anthropic`` is not installed in the eval/test environment, so a plain "import
succeeds" check would pass vacuously; ``test_anthropic_blocker_actually_blocks``
proves the blocker is real.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LIB_DIR = _REPO_ROOT / ".claude" / "lib"
_PR_DIR = _REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr"
_CORE_DIR = _LIB_DIR / "github_core"

# A representative read-only PR status script. ``--help`` forces argparse to
# print usage and ``sys.exit(0)`` after all module-level imports have run, so it
# exercises the full import path without any network call.
_READONLY_SCRIPT = _PR_DIR / "get_pull_requests.py"


def _imports_anthropic(source: str) -> bool:
    """Return True if the module source imports the ``anthropic`` package.

    Uses the AST so ``anthropic`` appearing in a comment or string does not
    count. Matches ``import anthropic``, ``import anthropic.types``, and
    ``from anthropic import ...``.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "anthropic" or alias.name.startswith("anthropic."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "anthropic" or module.startswith("anthropic."):
                return True
    return False


def _python_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*.py") if "__pycache__" not in p.parts)


def _run_blocked(program: str, env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run ``program`` in a subprocess with the anthropic SDK blocked."""
    env = os.environ.copy()
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True, encoding="utf-8",
        env=env,
        timeout=60,
        check=False,
    )


_BLOCK_ANTHROPIC = 'import sys\nsys.modules["anthropic"] = None\n'


# ---------------------------------------------------------------------------
# Static guard: the read-only PR closure must not import anthropic.
# ---------------------------------------------------------------------------


def test_readonly_pr_and_core_sources_do_not_import_anthropic() -> None:
    # Arrange
    sources = _python_files(_PR_DIR) + _python_files(_CORE_DIR)
    assert sources, "expected PR and github_core source files to exist"

    # Act
    offenders = [p for p in sources if _imports_anthropic(p.read_text(encoding="utf-8"))]

    # Assert
    rel = [str(p.relative_to(_REPO_ROOT)) for p in offenders]
    assert not offenders, f"read-only PR closure imports anthropic (breaks offline path): {rel}"


def test_import_detector_flags_real_anthropic_import() -> None:
    # A negative control: the detector must catch a real import, else the
    # static guard above would pass vacuously.
    assert _imports_anthropic("import anthropic\n")
    assert _imports_anthropic("from anthropic import Anthropic\n")
    assert _imports_anthropic("import anthropic.types\n")
    # The bare word in a comment or string must not count.
    assert not _imports_anthropic("# uses the anthropic sdk elsewhere\nx = 'anthropic'\n")


# ---------------------------------------------------------------------------
# Runtime guard: importing / running with anthropic blocked must succeed.
# ---------------------------------------------------------------------------


def test_anthropic_blocker_actually_blocks_import() -> None:
    # Proves the sys.modules[...] = None blocker raises ImportError, so the
    # runtime checks below are meaningful even though anthropic is not installed.
    program = _BLOCK_ANTHROPIC + (
        "try:\n"
        "    import anthropic\n"
        "    print('NOT_BLOCKED')\n"
        "except ImportError:\n"
        "    print('BLOCKED')\n"
    )
    result = _run_blocked(program, {})
    assert result.returncode == 0, result.stderr
    assert "BLOCKED" in result.stdout
    assert "NOT_BLOCKED" not in result.stdout


def test_github_core_imports_with_anthropic_blocked() -> None:
    program = _BLOCK_ANTHROPIC + (
        "import sys\n"
        f"sys.path.insert(0, {str(_LIB_DIR)!r})\n"
        "import github_core\n"
        "print('IMPORT_OK')\n"
    )
    result = _run_blocked(program, {})
    assert result.returncode == 0, f"github_core failed to import offline:\n{result.stderr}"
    assert "IMPORT_OK" in result.stdout


def test_readonly_pr_script_runs_offline_with_anthropic_blocked() -> None:
    assert _READONLY_SCRIPT.is_file(), f"missing script: {_READONLY_SCRIPT}"
    program = _BLOCK_ANTHROPIC + (
        "import runpy\n"
        "import sys\n"
        f"sys.argv = [{str(_READONLY_SCRIPT)!r}, '--help']\n"
        f"runpy.run_path({str(_READONLY_SCRIPT)!r}, run_name='__main__')\n"
    )
    # --help triggers argparse SystemExit(0) after all imports run.
    result = _run_blocked(program, {})
    assert result.returncode == 0, f"read-only PR script failed offline:\n{result.stderr}"
    assert "usage:" in result.stdout.lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
