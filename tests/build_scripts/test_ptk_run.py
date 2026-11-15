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


@pytest.fixture(autouse=True)
def _no_ambient_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Fallthrough reads the root variables and `.claude` under cwd; isolate both."""
    for name in ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"):
        monkeypatch.delenv(name, raising=False)
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)


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
        "skills/.../y.py",
        "skills/x/..../y.py",
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
    with pytest.raises(resolver.ResolverError, match="not a file under any plugin root"):
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
    assert captured.err.startswith("ptk_run: target has a part made only of dots")
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


@pytest.mark.parametrize("empty", ["", None])
def test_main_reports_an_empty_interpreter_path_as_a_resolver_failure(
    resolver: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tree: Path,
    empty: str | None,
) -> None:
    """`sys.executable` can be empty or None; that must exit 2 with the prefix, not a traceback."""
    (tree / "skills" / "x" / "scripts").mkdir(parents=True, exist_ok=True)
    (tree / "skills" / "x" / "scripts" / "y.py").write_text("print(1)\n", encoding="utf-8")
    monkeypatch.setattr(resolver, "plugin_root", lambda: str(tree))
    monkeypatch.setattr(sys, "executable", empty)
    assert resolver.main(["ptk_run.py", "skills/x/scripts/y.py"]) == 2
    assert capsys.readouterr().err.startswith("ptk_run: sys.executable is empty")


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


# ADR-121 decision 11: fallthrough to a later candidate root.

FOREIGN_STUB = "print('foreign')\n"


def _other_root(path: Path, *, resolver_file: bool = True, target: str | None = STUB) -> Path:
    """Lay out a candidate root with or without its own resolver and target."""
    if resolver_file:
        (path / "lib").mkdir(parents=True)
        shutil.copy(RESOLVER_SOURCE, path / "lib" / "ptk_run.py")
    if target is not None:
        script = path / "skills" / "x" / "scripts" / "z.py"
        script.parent.mkdir(parents=True)
        script.write_text(target, encoding="utf-8")
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_own_root_wins_when_it_holds_the_target(
    resolver: ModuleType,
    tree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    other = _other_root(tmp_path / "other")
    (other / "skills" / "x" / "scripts" / "y.py").write_text(FOREIGN_STUB, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(other))
    path = resolver.resolve_target(str(tree), "skills/x/scripts/y.py")
    assert path == os.path.join(str(tree), "skills/x/scripts/y.py")
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("variable", ["CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"])
def test_falls_through_to_an_env_root_that_holds_resolver_and_target(
    resolver: ModuleType,
    tree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    variable: str,
) -> None:
    other = _other_root(tmp_path / "other")
    monkeypatch.setenv(variable, str(other))
    path = resolver.resolve_target(str(tree), "skills/x/scripts/z.py")
    assert path == os.path.join(str(other), "skills/x/scripts/z.py")
    err = capsys.readouterr().err
    assert err == (
        f"ptk_run: note: 'skills/x/scripts/z.py' is not under {str(tree)!r}; "
        f"running it from {str(other)!r}\n"
    )


def test_falls_through_to_dot_claude_under_the_working_directory(
    resolver: ModuleType,
    tree: Path,
) -> None:
    _other_root(Path.cwd() / ".claude")
    assert resolver.resolve_target(str(tree), "skills/x/scripts/z.py") == os.path.join(
        ".claude", "skills/x/scripts/z.py"
    )


def test_candidates_follow_locator_order(
    resolver: ModuleType,
    tree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _other_root(tmp_path / "first")
    second = _other_root(tmp_path / "second")
    _other_root(Path.cwd() / ".claude")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(first))
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(second))
    assert resolver.candidate_roots(str(tree)) == [str(first), str(second), ".claude"]
    assert resolver.resolve_target(str(tree), "skills/x/scripts/z.py").startswith(str(first))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT")
    assert resolver.resolve_target(str(tree), "skills/x/scripts/z.py").startswith(str(second))


def test_a_root_without_the_resolver_is_skipped_even_with_a_same_named_target(
    resolver: ModuleType,
    tree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #7281: a foreign plugin's exported root holds its own files, not ours."""
    foreign = _other_root(tmp_path / "foreign", resolver_file=False, target=FOREIGN_STUB)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(foreign))
    with pytest.raises(resolver.ResolverError, match="not a file under any plugin root"):
        resolver.resolve_target(str(tree), "skills/x/scripts/z.py")


def test_a_root_with_the_resolver_but_not_the_target_is_skipped(
    resolver: ModuleType,
    tree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lacking = _other_root(tmp_path / "lacking", target=None)
    holding = _other_root(tmp_path / "holding")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(lacking))
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(holding))
    assert resolver.resolve_target(str(tree), "skills/x/scripts/z.py").startswith(str(holding))


def test_a_foreign_root_that_ships_our_resolver_and_target_runs(
    tree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The accepted limit of ADR-121 decisions 10 and 11: whoever ships both files controls them."""
    foreign = _other_root(tmp_path / "foreign", target=FOREIGN_STUB)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(foreign))
    result = _run_file(tree / "lib" / "ptk_run.py", "skills/x/scripts/z.py")
    assert (result.returncode, result.stdout) == (0, "foreign\n")
    assert result.stderr.startswith("ptk_run: note: ")


@pytest.mark.parametrize("variable", ["CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"])
def test_an_empty_root_variable_never_resolves_against_the_working_directory(
    resolver: ModuleType,
    tree: Path,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    _other_root(Path.cwd())  # cwd itself holds both files
    monkeypatch.setenv(variable, "")
    assert str(Path.cwd()) not in resolver.candidate_roots(str(tree))
    assert resolver.candidate_roots(str(tree)) == [".claude"]


@pytest.mark.skipif(os.name != "posix", reason="symlinks")
def test_a_link_to_the_own_root_is_not_probed_twice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-119: `.claude` can be a link to the resolver's own tree."""
    real = _plugin_tree(tmp_path / "real")
    (Path.cwd() / ".claude").symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(real))
    module = _load(real / "lib" / "ptk_run.py")
    assert module.candidate_roots(str(real)) == []


def test_missing_everywhere_exits_2_with_the_pinned_message_and_no_note(tree: Path) -> None:
    result = _run_file(tree / "lib" / "ptk_run.py", "skills/x/scripts/none.py")
    assert result.returncode == 2
    assert result.stderr == (
        "ptk_run: target is not a file under any plugin root: 'skills/x/scripts/none.py'\n"
    )
    assert result.stdout == ""


def test_fallthrough_keeps_stdout_for_the_target_alone(
    tree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-121 decision 14 captures a target's stdout with `$(...)`."""
    other = _other_root(tmp_path / "other", target="print('/only/this')\n")
    monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(other))
    result = _run_file(tree / "lib" / "ptk_run.py", "skills/x/scripts/z.py")
    assert (result.returncode, result.stdout) == (0, "/only/this\n")


def test_note_prints_a_root_with_a_newline_through_repr(
    resolver: ModuleType,
    tree: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    other = _other_root(tmp_path / "odd\nroot")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(other))
    resolver.resolve_target(str(tree), "skills/x/scripts/z.py")
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "\\n" in err


# ADR-121 decision 12: `-I` reaches the target on both launch paths.

ISOLATION_STUB = "import sys\nprint(sys.flags.isolated)\n"


def test_isolated_flag_is_passed_to_the_target_on_posix(
    resolver: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tree: Path,
) -> None:
    calls: list[list[str]] = []

    def fake_execv(exe: str, argv: list[str]) -> None:
        calls.append(list(argv))
        raise _ProcessReplacedError

    monkeypatch.setattr(resolver, "IS_POSIX", True)
    monkeypatch.setattr(resolver, "interpreter_flags", lambda: ["-I"])
    monkeypatch.setattr(os, "execv", fake_execv)
    with pytest.raises(_ProcessReplacedError):
        resolver.main(["ptk_run.py", "skills/x/scripts/y.py"])
    assert calls == [[sys.executable, "-I", os.path.join(str(tree), "skills/x/scripts/y.py")]]


def test_isolated_flag_is_passed_to_the_target_off_posix(
    resolver: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tree: Path,
) -> None:
    seen: list[list[str]] = []

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess:
        seen.append(list(command))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(resolver, "IS_POSIX", False)
    monkeypatch.setattr(resolver, "interpreter_flags", lambda: ["-I"])
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert resolver.main(["ptk_run.py", "skills/x/scripts/y.py"]) == 0
    assert seen == [[sys.executable, "-I", os.path.join(str(tree), "skills/x/scripts/y.py")]]


@pytest.mark.parametrize(("flags", "expected"), [([], "0"), (["-I"], "1")])
def test_a_real_run_matches_the_interpreter_isolation(
    tree: Path,
    flags: list[str],
    expected: str,
) -> None:
    (tree / "skills" / "x" / "scripts" / "iso.py").write_text(ISOLATION_STUB, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, *flags, str(tree / "lib" / "ptk_run.py"), "skills/x/scripts/iso.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert (result.returncode, result.stdout.strip()) == (0, expected), result.stderr
