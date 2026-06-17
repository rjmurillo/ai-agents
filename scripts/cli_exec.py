#!/usr/bin/env python3
"""Platform-safe resolution of a CLI executable for ``subprocess`` launch.

Issue #2629. On Windows, npm-installed CLIs (``copilot``, ``claude``) are shims
named ``copilot.cmd`` / ``claude.cmd``. ``subprocess.run([name, ...])`` calls
``CreateProcess``, which does NOT search ``PATH`` or apply ``PATHEXT`` the way a
shell does, so a bare name raises ``FileNotFoundError: [WinError 2]``. The Linux
and macOS spawns search ``PATH`` and never hit this, which is why only the
``windows-latest`` nightly job failed.

``resolve_executable`` returns a value safe to pass as ``argv[0]``:

  * Windows: the full resolved path to the executable, found by scanning ``PATH``
    and applying ``PATHEXT`` (``copilot`` -> ``...\\copilot.cmd``), so
    ``CreateProcess`` receives a concrete file. Raises ``FileNotFoundError``
    naming the executable when it is absent, instead of an opaque WinError 2
    surfacing later from inside subprocess.
  * POSIX: the bare name unchanged. ``CreateProcess`` is not involved; the
    POSIX exec path searches ``PATH`` itself, and the Linux/macOS jobs already
    pass. Returning the name avoids perturbing the working platforms.

The Windows resolution is implemented here rather than delegated to
``shutil.which`` so the PATHEXT logic is exercisable in unit tests on a Linux
runner. ``shutil.which`` gates its PATHEXT branch on ``sys.platform == 'win32'``
and reaches into ``_winapi``, which is absent on Linux, so it cannot stand in
for the Windows codepath in bare CI. The e2e that hit #2629 cannot run under
``act`` (Linux-only), so a Linux-exercisable resolver is what guards the
regression.

This is deliberately ``shell=False``-safe: it resolves a path and keeps the list
argv form, so no shell-quoting or command-injection surface is introduced.
"""

from __future__ import annotations

import os

# Default Windows executable extensions, used when PATHEXT is unset. Mirrors the
# canonical Windows default; resolution is case-insensitive per Windows rules.
_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"

# Windows uses ';' to separate both PATH and PATHEXT entries, regardless of the
# host running this code. The resolver must use the Windows separator (not the
# host's ``os.pathsep``, which is ':' on POSIX) so the Windows codepath is
# correct when simulated on a Linux/macOS runner for tests (issue #2629).
_WIN_LIST_SEP = ";"


def _windows_pathext(env: dict[str, str]) -> list[str]:
    raw = env.get("PATHEXT") or _DEFAULT_PATHEXT
    return [ext for ext in raw.split(_WIN_LIST_SEP) if ext]


def _match_in_dir(directory: str, target: str) -> str | None:
    """Return the path of a file in ``directory`` whose name equals ``target``.

    Comparison is case-insensitive to mirror Windows filesystem semantics, so
    a ``.CMD`` PATHEXT entry matches an on-disk ``copilot.cmd``. Listing the
    directory (rather than probing an exact-case candidate) keeps the match
    correct when the Windows codepath is exercised on a case-sensitive
    filesystem in tests. Uses ``os.path`` string ops, not ``pathlib``, so the
    Windows codepath does not instantiate a ``WindowsPath`` (which raises on a
    POSIX host) when simulated in unit tests.
    """
    try:
        entries = os.listdir(directory)
    except OSError:
        return None
    lowered = target.lower()
    for entry in entries:
        if entry.lower() != lowered:
            continue
        full = os.path.join(directory, entry)
        if os.path.isfile(full):
            return full
    return None


def _resolve_windows(name: str, env: dict[str, str]) -> str | None:
    """Scan PATH applying PATHEXT, mimicking the shell resolution CreateProcess skips.

    Returns the first matching path, or ``None`` when no candidate exists. A name
    that already carries a known extension is matched directly; otherwise each
    PATHEXT extension is appended in order. Matching is case-insensitive, as on
    Windows. Directories are scanned in PATH order, extensions in PATHEXT order.
    """
    pathext = _windows_pathext(env)
    has_ext = any(name.lower().endswith(ext.lower()) for ext in pathext)
    targets = [name] if has_ext else [name + ext for ext in pathext]
    directories = [d for d in env.get("PATH", "").split(_WIN_LIST_SEP) if d]
    for directory in directories:
        for target in targets:
            match = _match_in_dir(directory, target)
            if match is not None:
                return match
    return None


def resolve_executable(
    name: str,
    *,
    windows: bool | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Return a ``subprocess``-safe ``argv[0]`` for ``name`` on this platform.

    Args:
        name: Bare executable name (for example ``copilot``).
        windows: Force the Windows codepath when ``True``, the POSIX codepath
            when ``False``. Defaults to runtime detection via ``os.name == 'nt'``.
        env: Environment mapping to read ``PATH`` / ``PATHEXT`` from on the
            Windows codepath. Defaults to ``os.environ``. Injectable so the
            Windows resolution is testable against a simulated layout on Linux.

    Returns:
        On Windows, the full resolved path to the executable. On POSIX, ``name``.

    Raises:
        FileNotFoundError: On Windows when ``name`` cannot be resolved on PATH.
    """
    is_windows = os.name == "nt" if windows is None else windows
    if not is_windows:
        return name
    resolved = _resolve_windows(name, dict(os.environ) if env is None else env)
    if resolved is None:
        raise FileNotFoundError(
            f"Executable {name!r} not found on PATH "
            f"(PATHEXT-aware Windows resolution found no match)."
        )
    return resolved
