"""A plugin root that names a different plugin must not break the shared parser import.

Skill scripts that read frontmatter add their plugin ``lib`` to ``sys.path`` and
import ``hook_utilities.frontmatter_block``. Repo gates such as
``check_skill_artifact_flow.py`` load some of those scripts by path. The
bootstrap prefers the script's own plugin ``lib`` when it holds the parser, so
a root from ``CLAUDE_PLUGIN_ROOT`` that lacks the parser, or ships an older
one, cannot shadow it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_push_pr_interpreter_floor import PYTHON310, requires_python310

REPO_ROOT = Path(__file__).resolve().parents[1]
_PROBES = (
    "from hook_utilities.frontmatter_block import",
    "from hook_utilities import frontmatter_block",
    "from hook_utilities.scan_rules import",
)
_BOOTSTRAP = "_LIB_DIR = Path(__file__).resolve().parents[3]"


def _env(plugin_root: Path | None) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT")
    }
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    return env


def _run(argv: list[str], plugin_root: Path | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *argv],
        cwd=REPO_ROOT,
        env=_env(plugin_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )


def _bootstrapped_scripts() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--", "src/claude/skills/*.py", ".claude/skills/*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.split("\0")
    found = []
    for rel in filter(None, listed):
        path = REPO_ROOT / rel
        if path.is_symlink() or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if _BOOTSTRAP in text and any(probe in text for probe in _PROBES):
            found.append(rel)
    return sorted(found)


_SCRIPTS = _bootstrapped_scripts()

_LOAD = (
    "import importlib.util, sys; p = sys.argv[1]; "
    "sys.path.insert(0, __import__('os').path.dirname(p)); "
    "s = importlib.util.spec_from_file_location('probe_target', p); "
    "m = importlib.util.module_from_spec(s); sys.modules['probe_target'] = m; "
    "s.loader.exec_module(m); "
    "import hook_utilities.frontmatter_block as fb; print(fb.__file__)"
)


def _stale_root(tmp_path: Path) -> Path:
    root = tmp_path / "stale-plugin"
    pkg = root / "lib" / "hook_utilities"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "frontmatter_block.py").write_text(
        'raise ImportError("stale parser from a foreign plugin root")\n', encoding="utf-8"
    )
    return root


def test_every_bootstrap_copy_is_found() -> None:
    assert len(_SCRIPTS) >= 18, _SCRIPTS


@pytest.mark.parametrize(
    "script",
    ["scripts/validation/check_skill_artifact_flow.py", "scripts/validation/skill_size.py"],
)
def test_gate_passes_when_plugin_root_names_a_foreign_plugin(tmp_path: Path, script: str) -> None:
    foreign = tmp_path / "foreign-plugin"
    (foreign / "lib").mkdir(parents=True)

    baseline = _run([script], None)
    result = _run([script], foreign)

    assert "hook_utilities" not in result.stderr, result.stderr
    assert result.returncode == baseline.returncode, result.stderr


@pytest.mark.parametrize("script", _SCRIPTS)
def test_own_plugin_lib_wins_over_a_stale_plugin_root(tmp_path: Path, script: str) -> None:
    stale = _stale_root(tmp_path)

    result = _run(["-c", _LOAD, script], stale)

    assert result.returncode == 0, result.stderr
    loaded = Path(result.stdout.strip().splitlines()[-1]).resolve()
    own = (REPO_ROOT / script).resolve().parents[3] / "lib" / "hook_utilities"
    assert loaded == (own / "frontmatter_block.py").resolve(), loaded


@pytest.mark.parametrize("script", _SCRIPTS)
def test_script_imports_with_a_plugin_root_lacking_the_parser(tmp_path: Path, script: str) -> None:
    foreign = tmp_path / "foreign-plugin"
    (foreign / "lib").mkdir(parents=True)

    result = _run(["-c", _LOAD, script], foreign)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", _SCRIPTS)
def test_script_outside_its_plugin_falls_back_to_the_plugin_root(
    tmp_path: Path, script: str
) -> None:
    """A copied script whose own lib lacks the parser uses the environment root."""
    source = (REPO_ROOT / script).resolve()
    copied_dir = tmp_path / "loose" / "skills" / source.parent.parent.name / "scripts"
    shutil.copytree(source.parent, copied_dir, ignore=shutil.ignore_patterns("__pycache__"))
    copied = copied_dir / source.name
    (tmp_path / "loose" / "lib").mkdir()
    assert not (tmp_path / "loose" / "lib" / "hook_utilities").exists()
    plugin_root = REPO_ROOT / "src" / "claude"

    without_root = _run(["-c", _LOAD, str(copied)], None)
    with_root = _run(["-c", _LOAD, str(copied)], plugin_root)

    assert without_root.returncode != 0, without_root.stdout
    assert "hook_utilities" in without_root.stderr, without_root.stderr
    assert with_root.returncode == 0, with_root.stderr
    loaded = Path(with_root.stdout.strip().splitlines()[-1]).resolve()
    expected = plugin_root / "lib" / "hook_utilities" / "frontmatter_block.py"
    assert loaded == expected.resolve(), loaded


@requires_python310
@pytest.mark.parametrize("script", _SCRIPTS)
def test_script_imports_on_the_python310_floor(script: str) -> None:
    """Skill scripts run on the host interpreter, which can be 3.10.

    The shared parser's package must not import a 3.11+ name such as
    ``datetime.UTC`` (PR #7531 review). Executing the module body catches it.
    """
    assert PYTHON310 is not None
    result = subprocess.run(
        [PYTHON310, "-I", "-c", _LOAD, str(REPO_ROOT / script)],
        cwd=REPO_ROOT,
        env=_env(None),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
