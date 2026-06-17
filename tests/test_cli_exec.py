#!/usr/bin/env python3
"""Unit guard for platform-safe CLI executable resolution (issue #2629).

The Nightly CLI Smoke e2e launches the real ``copilot`` / ``claude`` CLIs with
``subprocess.run([name, ...])``. On Windows those CLIs are npm shims named
``copilot.cmd`` / ``claude.cmd``; ``CreateProcess`` does not consult ``PATH`` or
apply ``PATHEXT`` the way a shell does, so a bare name raises
``FileNotFoundError: [WinError 2]``. ``scripts.cli_exec.resolve_executable``
resolves the name to a concrete on-disk path before launch.

These tests simulate a Windows PATH layout on a Linux runner (the e2e itself
cannot run under ``act``, which is Linux-only), so a launcher that regresses to
a Linux-only bare-name spawn fails here in bare CI before it reaches the Windows
nightly job again. The Windows codepath is forced via ``windows=True`` and fed a
synthetic ``PATH`` / ``PATHEXT`` env, so the real PATHEXT resolution runs on any
host (``shutil.which`` cannot: it gates PATHEXT on ``sys.platform == 'win32'``
and reaches into ``_winapi``, absent on Linux).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.cli_exec import resolve_executable


def _windows_env(bin_dir: Path) -> dict[str, str]:
    return {
        "PATH": str(bin_dir),
        "PATHEXT": ".COM;.EXE;.BAT;.CMD",
    }


def test_windows_resolves_bare_name_to_cmd_shim(tmp_path: Path) -> None:
    """On Windows a bare CLI name resolves to its ``.cmd`` shim full path.

    This is the exact failure from #2629: subprocess on Windows cannot find
    ``copilot`` because the real file is ``copilot.cmd`` and CreateProcess does
    not apply PATHEXT. The resolver must hand subprocess the resolved path.
    """
    bin_dir = tmp_path / "npm"
    bin_dir.mkdir()
    (bin_dir / "copilot.cmd").write_text("@echo off\n", encoding="utf-8")

    resolved = resolve_executable("copilot", windows=True, env=_windows_env(bin_dir))

    assert Path(resolved).name == "copilot.cmd"
    assert Path(resolved).parent == bin_dir


def test_windows_prefers_pathext_order(tmp_path: Path) -> None:
    """PATHEXT precedence is honored: ``.EXE`` wins over a later ``.CMD``.

    A name with two candidate shims must resolve to the earlier PATHEXT entry,
    matching Windows launch semantics; a wrong order would launch the wrong file.
    """
    bin_dir = tmp_path / "npm"
    bin_dir.mkdir()
    (bin_dir / "claude.cmd").write_text("@echo off\n", encoding="utf-8")
    (bin_dir / "claude.exe").write_text("MZ", encoding="utf-8")

    resolved = resolve_executable(
        "claude",
        windows=True,
        env={"PATH": str(bin_dir), "PATHEXT": ".EXE;.CMD"},
    )

    assert Path(resolved).name == "claude.exe"


def test_windows_name_with_explicit_extension_matches_directly(tmp_path: Path) -> None:
    """A name already carrying a known extension resolves without re-appending.

    Guards against double-appending (``copilot.cmd.cmd``) when a caller passes a
    fully-qualified shim name.
    """
    bin_dir = tmp_path / "npm"
    bin_dir.mkdir()
    (bin_dir / "copilot.cmd").write_text("@echo off\n", encoding="utf-8")

    resolved = resolve_executable("copilot.cmd", windows=True, env=_windows_env(bin_dir))

    assert Path(resolved).name == "copilot.cmd"


def test_windows_unresolved_name_raises_clear_error(tmp_path: Path) -> None:
    """A name absent from PATH raises FileNotFoundError naming the executable.

    Fail loud at resolution time with the executable name, not later with an
    opaque WinError 2 from deep inside subprocess.
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError) as excinfo:
        resolve_executable("copilot", windows=True, env=_windows_env(empty))
    assert "copilot" in str(excinfo.value)


def test_posix_returns_bare_name_unchanged(tmp_path: Path) -> None:
    """On POSIX the bare name is returned; subprocess resolves it via PATH.

    No behavior change for the Linux/macOS jobs that already pass; the bug was
    Windows-only and the fix must not perturb the platforms that work. The env
    is irrelevant on POSIX, so a missing shim must not raise.
    """
    resolved = resolve_executable("copilot", windows=False, env={"PATH": str(tmp_path)})
    assert resolved == "copilot"


def test_default_platform_detection_uses_os_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ``windows`` is unset, the resolver derives it from ``os.name``.

    Guards the default path the e2e actually calls: the e2e passes only the
    name, so the platform branch must come from the runtime, not a caller flag.
    """
    bin_dir = tmp_path / "npm"
    bin_dir.mkdir()
    (bin_dir / "claude.cmd").write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("PATHEXT", ".CMD")

    monkeypatch.setattr("os.name", "nt")
    resolved = resolve_executable("claude")
    assert Path(resolved).name == "claude.cmd"

    monkeypatch.setattr("os.name", "posix")
    assert resolve_executable("claude") == "claude"


def test_windows_mixed_case_env_keys_normalized(tmp_path: Path) -> None:
    """Mixed-case env keys such as ``Path`` / ``Pathext`` resolve correctly.

    On Windows, ``dict(os.environ)`` is a plain case-sensitive Python dict
    whose path variable may be stored as ``Path`` (mixed-case) rather than
    ``PATH``. Without key normalization, the lookup ``env.get("PATH")``
    returns ``None`` and the resolver finds nothing.  The fix upper-cases all
    keys before passing the dict to ``_resolve_windows``, so the resolver is
    robust regardless of how the caller obtained the environment mapping.
    """
    bin_dir = tmp_path / "npm"
    bin_dir.mkdir()
    (bin_dir / "copilot.cmd").write_text("@echo off\n", encoding="utf-8")

    mixed_env = {
        "Path": str(bin_dir),
        "Pathext": ".COM;.EXE;.BAT;.CMD",
    }
    resolved = resolve_executable("copilot", windows=True, env=mixed_env)

    assert Path(resolved).name == "copilot.cmd"
    assert Path(resolved).parent == bin_dir


def test_e2e_launchers_route_through_resolver() -> None:
    """The CLI hook e2e must launch the CLIs through ``resolve_executable``.

    Regression guard for #2629. The Windows failure came from
    ``subprocess.run(["copilot", ...])`` with a bare name. The e2e cannot run
    under ``act`` (Linux-only), so this source-level check bites in bare CI if a
    future edit reverts any CLI launch to a bare-name list. Every ``copilot`` /
    ``claude`` argv[0] in the e2e module must be a ``resolve_executable(...)``
    call, never a bare string literal.
    """
    e2e_source = (
        Path(__file__).resolve().parents[1] / "tests" / "e2e" / "test_cli_hook_e2e.py"
    ).read_text(encoding="utf-8")

    # A bare-name launch is the bug shape: an argv list opening with the literal
    # CLI name followed by arguments, e.g. ``["copilot", "plugin", ...]``. The
    # fixed form opens with ``resolve_executable("copilot")``. A bare
    # ``["copilot"]`` with no trailing args (used to build a CompletedProcess in
    # a diagnostics test) is not a launch and is intentionally not matched.
    for cli in ("copilot", "claude"):
        assert f'[resolve_executable("{cli}")' in e2e_source, (
            f"e2e must launch {cli!r} via resolve_executable, not a bare name"
        )
        # Regex catches bare-name launches regardless of quote style
        # (single/double), whitespace/newlines, or list vs. tuple argv form.
        # The trailing comma inside the brackets is the discriminator: it marks
        # "at least one more argument" and distinguishes a real launch from the
        # intentional single-element ``CompletedProcess(["copilot"], ...)``
        # diagnostic stub that has no comma inside the list brackets.
        # ``subprocess\.(?:run|Popen)`` is anchored so CompletedProcess
        # constructions are never matched.
        bare_launch = re.compile(
            r"""subprocess\.(?:run|Popen)\s*\(\s*[\[(]\s*['"]""" + re.escape(cli) + r"""['"]\s*,""",
            re.DOTALL,
        )
        assert not bare_launch.search(e2e_source), (
            f"e2e has a bare-name {cli!r} launch; route it through resolve_executable (#2629)"
        )
