"""ADR-121 decisions 11 and 12 in the resolver `src/claude/lib/ptk_run.py`.

Decision 11: when the target is not under the resolver's own root, the later
locator candidates are tried in order, with realpath dedupe and a `ptk_run: note:`
line. Decision 12: under `python3 -I` the target runs with `-I` on both launch paths.
Fixtures and helpers come from `test_ptk_run.py`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests.build_scripts.test_ptk_run import (
    RESOLVER_SOURCE,
    STUB,
    _load,
    _plugin_tree,
    _ProcessReplacedError,
    _run_file,
)
from tests.build_scripts.test_ptk_run import _no_ambient_roots as _no_ambient_roots
from tests.build_scripts.test_ptk_run import resolver as resolver
from tests.build_scripts.test_ptk_run import tree as tree

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
