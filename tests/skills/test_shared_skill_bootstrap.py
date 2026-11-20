"""Exercise both skill entry points with the shipped plugin layout."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/claude"


@pytest.fixture(params=["llm-council/scripts/council.py", "sol-loop/scripts/sol_loop.py"])
def entry(request: pytest.FixtureRequest) -> Path:
    return Path("skills") / request.param


def _help(
    script: Path,
    cwd: Path,
    *,
    copilot: Path | None = None,
    claude: Path | None = None,
    pythonpath: str | None = None,
    isolated: bool = False,
    resolver: Path | None = None,
    preload_paths: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "PYTHONPATH", "PYTHONSAFEPATH"}
    }
    for name, root in (("COPILOT_PLUGIN_ROOT", copilot), ("CLAUDE_PLUGIN_ROOT", claude)):
        if root is not None:
            env[name] = str(root)
    if pythonpath is not None:
        env["PYTHONPATH"] = pythonpath
    target = [str(script)]
    if resolver is not None:
        target = [str(resolver), script.relative_to(resolver.parent.parent).as_posix()]
    if preload_paths:
        target = [
            "-c",
            "import runpy, sys, types\n"
            "sys.modules['paths'] = types.ModuleType('paths')\n"
            "runpy.run_path(sys.argv.pop(1), run_name='__main__')",
            str(script),
        ]
    return subprocess.run(
        [sys.executable, *(["-I"] if isolated else []), *target, "--help"],
        cwd=cwd,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


@pytest.fixture
def installed(tmp_path: Path, entry: Path) -> Path:
    plugin = tmp_path / "installed plugin"
    shutil.copytree(
        SOURCE / entry.parent, plugin / entry.parent, ignore=shutil.ignore_patterns("__pycache__")
    )
    (plugin / "lib").mkdir()
    shutil.copyfile(SOURCE / "lib/bootstrap.py", plugin / "lib/bootstrap.py")
    shutil.copyfile(SOURCE / "lib/paths.py", plugin / "lib/paths.py")
    shutil.copyfile(SOURCE / "lib/ptk_run.py", plugin / "lib/ptk_run.py")
    return plugin


@pytest.mark.parametrize(
    "tree",
    [
        ".claude",
        "src/claude",
        "src/codex",
        "src/copilot-cli",
        "src/cursor",
        "src/hermes/project-toolkit-quality",
        "src/muse",
    ],
)
@pytest.mark.parametrize("use_resolver", [False, True])
def test_shipped_help_from_consumer_cwd(
    tmp_path: Path,
    entry: Path,
    tree: str,
    use_resolver: bool,
) -> None:
    plugin = ROOT / tree
    resolver = plugin / "lib/ptk_run.py" if use_resolver else None
    result = _help(plugin / entry, tmp_path, isolated=True, resolver=resolver)
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


@pytest.mark.parametrize("link_file", [False, True])
@pytest.mark.parametrize("use_resolver", [False, True])
def test_symlinked_installed_script_uses_real_plugin(
    tmp_path: Path,
    entry: Path,
    installed: Path,
    link_file: bool,
    use_resolver: bool,
) -> None:
    link = tmp_path / "linked" / entry
    try:
        if link_file:
            link.parent.mkdir(parents=True)
            link.symlink_to(installed / entry)
        else:
            link.parent.parent.parent.mkdir(parents=True)
            link.parent.parent.symlink_to(installed / entry.parent.parent, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlinks unavailable: {exc}")

    resolver = None
    if use_resolver:
        resolver = tmp_path / "linked/lib/ptk_run.py"
        resolver.parent.mkdir()
        shutil.copyfile(installed / "lib/ptk_run.py", resolver)
    result = _help(link, tmp_path, isolated=True, resolver=resolver)

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def _mark_paths(plugin: Path, marker: str) -> Path:
    lib = plugin / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    source = (SOURCE / "lib/paths.py").read_text(encoding="utf-8")
    (lib / "paths.py").write_text(f"{source}\nprint({marker!r})\n", encoding="utf-8")
    return lib


@pytest.mark.parametrize(
    ("copilot_valid", "claude_valid", "selected"),
    [
        (True, True, "copilot"),
        (False, True, "claude"),
        (False, False, "own"),
    ],
)
def test_root_precedence_and_validation(
    tmp_path: Path,
    entry: Path,
    installed: Path,
    copilot_valid: bool,
    claude_valid: bool,
    selected: str,
) -> None:
    copilot = tmp_path / "copilot"
    claude = tmp_path / "claude"
    _mark_paths(installed, "own")
    for root, valid in ((copilot, copilot_valid), (claude, claude_valid)):
        if valid:
            lib = _mark_paths(root, root.name)
            (lib / "bootstrap.py").write_text(
                "raise RuntimeError('foreign bootstrap')\n", encoding="utf-8"
            )
        else:
            (root / "lib/paths.py").mkdir(parents=True)

    result = _help(installed / entry, tmp_path, copilot=copilot, claude=claude)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == selected


def test_selected_paths_beats_pythonpath_even_if_already_listed(
    tmp_path: Path,
    entry: Path,
    installed: Path,
) -> None:
    lib = _mark_paths(installed, "own")
    for filename in ("paths.py", "bootstrap.py"):
        (tmp_path / filename).write_text("raise RuntimeError('ambient shadow')\n", encoding="utf-8")
    for filename in ("council_backends.py", "sol_cli.py"):
        (lib / filename).write_text("raise RuntimeError('lib shadow')\n", encoding="utf-8")

    result = _help(
        installed / entry, tmp_path, pythonpath=os.pathsep.join((str(tmp_path), str(lib)))
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "own"


@pytest.mark.parametrize("preload_paths", [False, True])
def test_selected_paths_file_beats_package_and_cached_module(
    tmp_path: Path,
    entry: Path,
    installed: Path,
    preload_paths: bool,
) -> None:
    lib = _mark_paths(installed, "own")
    package = lib / "paths"
    package.mkdir()
    (package / "__init__.py").write_text("raise RuntimeError('package shadow')\n", encoding="utf-8")

    result = _help(installed / entry, tmp_path, isolated=True, preload_paths=preload_paths)

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "own"


def test_no_paths_file_preserves_candidate_diagnostic(
    tmp_path: Path,
    entry: Path,
    installed: Path,
) -> None:
    (installed / "lib").rename(installed / "original lib")
    (installed / "lib").mkdir()
    shutil.copyfile(SOURCE / "lib/bootstrap.py", installed / "lib/bootstrap.py")
    copilot = tmp_path / "absent copilot"
    claude = tmp_path / "absent claude"

    result = _help(installed / entry, tmp_path, copilot=copilot, claude=claude)

    assert result.returncode == 1
    candidates = ", ".join(str(root / "lib") for root in (copilot, claude, installed))
    assert f"RuntimeError: paths.py not found in any of: {candidates}" in result.stderr
    assert result.stdout == ""


def test_bootstrap_requires_a_file(tmp_path: Path, entry: Path, installed: Path) -> None:
    bootstrap = installed / "lib/bootstrap.py"
    bootstrap.rename(installed / "original bootstrap.py")
    bootstrap.mkdir()
    (bootstrap / "__main__.py").write_text(
        "raise RuntimeError('directory launch')\n", encoding="utf-8"
    )

    result = _help(installed / entry, tmp_path)

    assert result.returncode == 1
    assert f"ImportError: Cannot load skill bootstrap from {bootstrap}" in result.stderr
    assert "directory launch" not in result.stderr
