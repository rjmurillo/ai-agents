"""The ADR-121 resolver `src/claude/lib/ptk_run.py` validates a target and runs it.

The module lives outside any importable package, so each test loads a copy from a
temporary plugin tree. `plugin_root()` then answers for that tree, which is how the
shipped file answers for the tree it sits in.

Four things are pinned:

1. The target check: the pattern, the `..` rule, and the regular-file rule.
2. The root is lexical: a symlinked `lib/ptk_run.py` keeps the link's own root.
3. Every resolver failure writes a `ptk_run:` line to stderr and exits 2.
4. The run semantics: `os.execv` on POSIX (exit code and `sys.path[0]` match a
   direct `python3 <file>`), a child process elsewhere.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RESOLVER_SOURCE = REPO_ROOT / "src" / "claude" / "lib" / "ptk_run.py"

STUB = """\
import json, os, sys
print(json.dumps({"argv": sys.argv[1:], "path0": sys.path[0]}))
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
"""


def _plugin_tree(root: Path) -> Path:
    """Lay out `root/lib/ptk_run.py` (a real copy) and `root/skills/x/scripts/y.py`."""
    (root / "lib").mkdir(parents=True)
    shutil.copy(RESOLVER_SOURCE, root / "lib" / "ptk_run.py")
    script = root / "skills" / "x" / "scripts" / "y.py"
    script.parent.mkdir(parents=True)
    script.write_text(STUB, encoding="utf-8")
    return root


def _load(resolver_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("ptk_run_under_test", resolver_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    return _plugin_tree(tmp_path / "plugin")


@pytest.fixture
def resolver(tree: Path) -> ModuleType:
    return _load(tree / "lib" / "ptk_run.py")


def _run_file(resolver_path: Path, *args: str, stub_exit: int = 0) -> subprocess.CompletedProcess:
    env = {**os.environ, "STUB_EXIT": str(stub_exit)}
    return subprocess.run(
        [sys.executable, str(resolver_path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
        check=False,
    )


@pytest.mark.parametrize(
    "target",
    [
        "skills/x/scripts/y.py",
        "skills/metrics/collect_metrics.py",
        "skills/a-b/scripts/c_d.v2.py",
        "skills/x/./y.py",
    ],
)
def test_validate_target_accepts_shipped_script_paths(resolver: ModuleType, target: str) -> None:
    resolver.validate_target(target)


@pytest.mark.parametrize(
    "target",
    [
        "",
        "y.py",
        "skills/",
        "skills/x/scripts/y.sh",
        "skills/x/scripts/y.py ",
        " skills/x/scripts/y.py",
        "skills/x/scripts/y.py\n",
        "skills/x/scripts/y.py\x00",
        "skills/x/scripts/y.py;ls",
        "skills/x y/y.py",
        "skills/$X/y.py",
        "skills/`id`/y.py",
        'skills/"x"/y.py',
        "skills\\x\\y.py",
        "/skills/x/scripts/y.py",
        "/etc/passwd.py",
        "../skills/x/scripts/y.py",
        "skills/../x/y.py",
        "skills/x/../../../etc/y.py",
        "skills/x/scripts/../y.py",
        "other/x/y.py",
        "--help",
        "-m",
    ],
)
def test_validate_target_rejects_what_the_pattern_or_the_dotdot_rule_forbids(
    resolver: ModuleType, target: str
) -> None:
    with pytest.raises(resolver.ResolverError):
        resolver.validate_target(target)


def test_resolve_target_returns_the_joined_path_for_a_regular_file(
    resolver: ModuleType, tree: Path
) -> None:
    assert resolver.resolve_target(str(tree), "skills/x/scripts/y.py") == os.path.join(
        str(tree), "skills/x/scripts/y.py"
    )


def test_resolve_target_rejects_a_missing_file(resolver: ModuleType, tree: Path) -> None:
    with pytest.raises(resolver.ResolverError, match="not a file"):
        resolver.resolve_target(str(tree), "skills/x/scripts/missing.py")


def test_resolve_target_rejects_a_directory_named_like_a_script(
    resolver: ModuleType, tree: Path
) -> None:
    (tree / "skills" / "x" / "scripts" / "dir.py").mkdir()
    with pytest.raises(resolver.ResolverError, match="not a file"):
        resolver.resolve_target(str(tree), "skills/x/scripts/dir.py")


def test_resolve_target_runs_validation_before_touching_the_disk(
    resolver: ModuleType, tree: Path
) -> None:
    with pytest.raises(resolver.ResolverError, match="not skills/"):
        resolver.resolve_target(str(tree), "lib/ptk_run.py")


@pytest.mark.skipif(os.name != "posix", reason="symlinks")
def test_resolve_target_follows_a_link_to_a_file_but_not_a_link_to_a_directory(
    resolver: ModuleType, tree: Path
) -> None:
    """ADR-119 links `.claude/skills/*` into `src/claude`, so a file link must pass."""
    scripts = tree / "skills" / "x" / "scripts"
    (scripts / "link.py").symlink_to(scripts / "y.py")
    (scripts / "dirlink.py").symlink_to(scripts, target_is_directory=True)
    (scripts / "broken.py").symlink_to(scripts / "nowhere.py")
    assert resolver.resolve_target(str(tree), "skills/x/scripts/link.py").endswith("link.py")
    for name in ("dirlink.py", "broken.py"):
        with pytest.raises(resolver.ResolverError):
            resolver.resolve_target(str(tree), f"skills/x/scripts/{name}")


def test_plugin_root_is_the_parent_of_the_lib_directory(resolver: ModuleType, tree: Path) -> None:
    assert resolver.plugin_root() == str(tree)


@pytest.mark.skipif(os.name != "posix", reason="symlinks")
def test_plugin_root_is_lexical_so_a_linked_resolver_keeps_its_own_root(tmp_path: Path) -> None:
    """`.claude/lib/ptk_run.py` links to `src/claude/lib/ptk_run.py`; the root stays `.claude`."""
    real = _plugin_tree(tmp_path / "real")
    (tmp_path / "linked" / "lib").mkdir(parents=True)
    (tmp_path / "linked" / "lib" / "ptk_run.py").symlink_to(real / "lib" / "ptk_run.py")
    (tmp_path / "linked" / "skills" / "x" / "scripts").mkdir(parents=True)
    (tmp_path / "linked" / "skills" / "x" / "scripts" / "y.py").write_text(
        "print('linked')\n", encoding="utf-8"
    )
    result = _run_file(tmp_path / "linked" / "lib" / "ptk_run.py", "skills/x/scripts/y.py")
    assert (result.returncode, result.stdout) == (0, "linked\n")


def test_main_without_a_target_prints_usage_and_exits_2(
    resolver: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert resolver.main(["ptk_run.py"]) == 2
    assert capsys.readouterr().err.startswith("ptk_run: usage:")


def test_main_reports_a_rejected_target_with_the_prefix_and_exit_2(
    resolver: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert resolver.main(["ptk_run.py", "skills/../y.py"]) == 2
    captured = capsys.readouterr()
    assert captured.err.startswith("ptk_run: target has a '..' part")
    assert captured.out == ""


def test_main_reports_an_unlaunchable_interpreter_as_a_resolver_failure(
    resolver: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "executable", str(tmp_path / "no-such-python"))
    assert resolver.main(["ptk_run.py", "skills/x/scripts/y.py"]) == 2
    assert capsys.readouterr().err.startswith("ptk_run: ")


class _ProcessReplacedError(Exception):
    """Stands in for `os.execv`, which never returns on success."""


def test_posix_launch_replaces_the_process_with_the_interpreter_and_target(
    resolver: ModuleType, monkeypatch: pytest.MonkeyPatch, tree: Path
) -> None:
    calls: list[tuple[str, list[str]]] = []

    def fake_execv(exe: str, argv: list[str]) -> None:
        calls.append((exe, list(argv)))
        raise _ProcessReplacedError

    monkeypatch.setattr(resolver, "IS_POSIX", True)
    monkeypatch.setattr(os, "execv", fake_execv)
    with pytest.raises(_ProcessReplacedError):
        resolver.main(["ptk_run.py", "skills/x/scripts/y.py", "-x", "a b"])
    target = os.path.join(str(tree), "skills/x/scripts/y.py")
    assert calls == [(sys.executable, [sys.executable, target, "-x", "a b"])]


@pytest.mark.parametrize("code", [0, 1, 2, 3, 4])
def test_off_posix_launch_runs_a_child_and_returns_its_exit_code(
    resolver: ModuleType, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    monkeypatch.setattr(resolver, "IS_POSIX", False)
    monkeypatch.setenv("STUB_EXIT", str(code))
    assert resolver.main(["ptk_run.py", "skills/x/scripts/y.py"]) == code


@pytest.mark.skipif(os.name != "posix", reason="os.execv")
def test_posix_run_matches_a_direct_python_run_for_exit_code_and_sys_path0(
    tree: Path,
) -> None:
    script = tree / "skills" / "x" / "scripts" / "y.py"
    direct = subprocess.run(
        [sys.executable, str(script), "a"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    via = _run_file(tree / "lib" / "ptk_run.py", "skills/x/scripts/y.py", "a", stub_exit=0)
    assert via.returncode == direct.returncode == 0
    assert via.stdout == direct.stdout


@pytest.mark.skipif(os.name != "posix", reason="os.execv")
@pytest.mark.parametrize("code", [1, 2, 3, 4])
def test_posix_run_passes_the_target_exit_code_through(tree: Path, code: int) -> None:
    result = _run_file(tree / "lib" / "ptk_run.py", "skills/x/scripts/y.py", stub_exit=code)
    assert result.returncode == code
    assert "ptk_run:" not in result.stderr


def test_a_target_exit_2_carries_no_resolver_prefix(tree: Path) -> None:
    """Callers tell a target's exit 2 from the resolver's by the `ptk_run:` prefix."""
    target_fail = _run_file(tree / "lib" / "ptk_run.py", "skills/x/scripts/y.py", stub_exit=2)
    resolver_fail = _run_file(tree / "lib" / "ptk_run.py", "skills/x/scripts/none.py")
    assert target_fail.returncode == resolver_fail.returncode == 2
    assert "ptk_run:" not in target_fail.stderr
    assert resolver_fail.stderr.startswith("ptk_run:")


def test_resolver_imports_only_the_standard_library() -> None:
    """It runs under a bare `python3`, so nothing outside the stdlib may load at import."""
    probe = (
        "import runpy, sys\n"
        f"runpy.run_path({str(RESOLVER_SOURCE)!r}, run_name='probe')\n"
        "loaded = {m.split('.')[0] for m in sys.modules}\n"
        "extra = sorted(m for m in loaded if m not in sys.stdlib_module_names "
        "and not m.startswith('_') and m not in ('probe', 'runpy'))\n"
        "print(extra)\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", probe],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert (result.returncode, result.stdout.strip()) == (0, "[]"), result.stderr
