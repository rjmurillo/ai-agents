"""Script entry points must import when run as a plain script.

CI and documentation invoke scripts through file paths. In that mode
``sys.path[0]`` is the script's directory, not the repository root, so an
absolute ``scripts.*`` import fails unless the entry point puts the root on
``sys.path`` itself.

Local runs never reproduce this. ``uv`` installs the project in editable mode,
and modern setuptools implements that with an ``_EditableFinder`` on
``sys.meta_path`` rather than a path entry. Removing the repository root from
``sys.path`` therefore leaves ``scripts`` fully importable, which is why a
reproduction that only edits ``sys.path`` reports success against a genuinely
broken file. The harness below drops the finder as well.

The defect is also invisible to a static scan of module-level imports. The
entry point that turned ``Validate Vendor Portability`` red imported no
``scripts.*`` name at all: it imported a sibling flat, and that sibling did the
absolute import. Executing the module is what catches the transitive edge.

Refs #4210 (recurrence catalogue), #3073 (the first fix of this shape).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
MAIN_GUARD = '__name__ == "__main__"'
MODULE_ONLY_ENTRY_POINTS = frozenset(
    {
        SCRIPTS_DIR / "memory_enhancement" / "__main__.py",
        SCRIPTS_DIR / "memory_enhancement" / "hooks" / "session_end_memory.py",
    }
)

# Reproduce a bare `python3 <script>` interpreter: repository root absent from
# `sys.path`, editable-install finders removed, script directory present.
# `run_name` is deliberately not `__main__` so module-level imports run without
# the CLI.
_RUNNER = (
    "import os, runpy, sys\n"
    "repo_root = os.path.realpath(sys.argv[1])\n"
    "script = os.path.realpath(sys.argv[2])\n"
    "sys.path[:] = [p for p in sys.path if os.path.realpath(p) != repo_root]\n"
    "sys.meta_path[:] = [f for f in sys.meta_path"
    " if 'editable' not in getattr(f, '__module__', '').lower()]\n"
    "sys.path.insert(0, os.path.dirname(script))\n"
    "runpy.run_path(script, run_name='__not_main__')\n"
)


def _import_as_script(script: Path, repo_root: Path) -> subprocess.CompletedProcess[str]:
    """Import ``script`` with the repository root off the import path."""
    env = os.environ.copy()
    plugin_root = str(repo_root / ".claude")
    env["COPILOT_PLUGIN_ROOT"] = plugin_root
    env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    return subprocess.run(
        [sys.executable, "-c", _RUNNER, str(repo_root), str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(repo_root),
        check=False,
        env=env,
    )


def _entry_points() -> list[Path]:
    return sorted(
        path
        for path in SCRIPTS_DIR.rglob("*.py")
        if path not in MODULE_ONLY_ENTRY_POINTS
        and MAIN_GUARD in path.read_text(encoding="utf-8")
    )


def _entry_point_ids() -> list[str]:
    return [path.name for path in _entry_points()]


def test_the_scan_finds_entry_points() -> None:
    """Guard the population: an empty scan would make every case vacuous."""
    entry_points = _entry_points()

    assert len(entry_points) >= 250
    assert SCRIPTS_DIR / "issue_triage.py" in entry_points


@pytest.mark.parametrize("script", _entry_points(), ids=_entry_point_ids())
def test_entry_point_imports_without_the_repo_root_on_sys_path(script: Path) -> None:
    """Every entry point imports in script mode."""
    result = _import_as_script(script, REPO_ROOT)

    assert result.returncode == 0, (
        f"{script.name} fails when run as a plain script, the way CI invokes it.\n"
        "Add the repository root to sys.path before the import, as "
        "scripts/validation/check_model_pins.py does.\n"
        f"stderr:\n{result.stderr}"
    )


def test_the_harness_detects_a_broken_entry_point(tmp_path: Path) -> None:
    """Negative control: a detector that cannot fail has not been run.

    Reproduces the exact shape that turned the workflow red, a flat sibling
    import whose target performs the absolute import. A harness that only
    edited ``sys.path`` would pass this.
    """
    package = tmp_path / "scripts" / "validation"
    package.mkdir(parents=True)
    (tmp_path / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaf.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "sibling.py").write_text(
        "from scripts.validation.leaf import VALUE\n", encoding="utf-8"
    )
    broken = package / "entry.py"
    broken.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
        "from sibling import VALUE  # noqa: E402\n"
        'if __name__ == "__main__":\n'
        "    print(VALUE)\n",
        encoding="utf-8",
    )

    result = _import_as_script(broken, tmp_path)

    assert result.returncode != 0, "harness passed a file with the known defect"
    assert "No module named 'scripts'" in result.stderr


def test_the_harness_accepts_a_bootstrapped_entry_point(tmp_path: Path) -> None:
    """The same fixture passes once it adds the repository root itself."""
    package = tmp_path / "scripts" / "validation"
    package.mkdir(parents=True)
    (tmp_path / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "leaf.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "sibling.py").write_text(
        "from scripts.validation.leaf import VALUE\n", encoding="utf-8"
    )
    fixed = package / "entry.py"
    fixed.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        "_SCRIPT_DIR = Path(__file__).resolve().parent\n"
        "_REPO_ROOT = _SCRIPT_DIR.parent.parent\n"
        "if str(_REPO_ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(_REPO_ROOT))\n"
        "sys.path.insert(0, str(_SCRIPT_DIR))\n"
        "from sibling import VALUE  # noqa: E402\n"
        'if __name__ == "__main__":\n'
        "    print(VALUE)\n",
        encoding="utf-8",
    )

    result = _import_as_script(fixed, tmp_path)

    assert result.returncode == 0, result.stderr
