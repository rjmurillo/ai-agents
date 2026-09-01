#!/usr/bin/env python3
"""Import Claude-Mem memory snapshots from .claude-mem/memories/.

Idempotent import of all JSON memory files from the memories directory.
Automatically prevents duplicates using composite keys.

The Claude-Mem plugin is an optional dependency. Upstream ships a Copilot CLI
integration, but it is MCP-only: it installs an MCP server entry and no importer
path. The bulk-importer script itself does exist upstream, and is the very
script this module invokes, so the gap is not a missing script. The gap is that
nothing in the Copilot integration installs it or points at an installed copy,
so this module has a Claude Code default path to fall back on and no Copilot
equivalent of that default.

Verified against github.com/thedotmack/claude-mem at commit
8f085b4f8861122201a5524be71d696a49a812a3 (2026-08-31),
``src/services/integrations/McpIntegrations.ts:242``::

    'copilot-cli': installMcpIntegration(COPILOT_CLI_CONFIG),

whose ``COPILOT_CLI_CONFIG`` (same file, lines 116 to 122) writes
``~/.github/copilot/mcp.json``. At that revision ``scripts/import-memories.ts``
exists but nothing routes Copilot to it. Re-verify before relying on this: a
later upstream release could add a Copilot importer path, and this comment
would not know.

The importer path is resolved in this order:

  1. ``--importer PATH`` on the command line
  2. the ``CLAUDE_MEM_IMPORTER`` environment variable
  3. the Claude Code plugin default under ``~/.claude/plugins/``

The exit code turns on whether anything was CONFIGURED, not on whether a path
resolved. When nothing is configured (no argument, no environment value, and no
default found on disk), the plugin is not installed and the import is skipped
with exit 0. When something IS configured but unusable, that is a real failure
and exits 1. That includes a blank ``--importer``, which resolves to no path yet
still counts as configured, so "no path resolved" alone does not mean skip. See
``ImporterResolution.is_configured``.

EXIT CODES:
  0  - Success, or nothing configured and no plugin installed (skipped).
       Also ``--help``, which argparse exits 0 without reaching ``main``'s body.
  1  - A configured importer is missing or unusable, or an import failed
  2  - Malformed command line: an unknown flag, a bare ``--importer`` with no
       value, an unexpected positional. ``argparse`` raises ``SystemExit(2)``
       from ``parse_args`` and the entrypoint's ``sys.exit(main())`` propagates
       it, so this code bypasses the resolution contract below entirely. It is
       reachable only when the CALLER's command line is wrong, never as an
       outcome of an import, so a caller that invokes this script correctly sees
       only 0 and 1.

Partial deviation from ADR-035. The exit-2 path above CONFORMS: ADR-035's Exit
Code Reference assigns code 2 to "Usage, configuration, or environment error",
covering "Missing params, invalid args, missing dependencies", which is what a
malformed command line is.

Three exit-1 paths deviate, and callers must not assume the standard mapping for
them. Under the ADR they would also be 2: a blank ``--importer`` (invalid arg), a
configured importer path that does not exist (configuration), and a missing
``npx`` (missing dependency). They exit 1 here.

That is deliberate, not an oversight. Issue #4780's acceptance criteria fix the
IMPORT outcome at two codes, 0 for a supported skip and 1 for a real failure, so
that a caller can branch on "did the import work" without a third state. Routing
those three to 2 would put a real failure and a supported skip on either side of
a code that also means "you typed the command wrong", which is the distinction
the issue exists to make clean. Revisit only with that issue, not as a drive-by
conformance fix.

See: ADR-035 Exit Code Standardization (deviation documented above)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORIES_DIR = _SCRIPT_DIR.parent / "memories"

IMPORTER_ENV_VAR = "CLAUDE_MEM_IMPORTER"

_SOURCE_ARGUMENT = "--importer argument"
_SOURCE_ARGUMENT_BLANK = "--importer argument (empty)"
_SOURCE_ENVIRONMENT = f"{IMPORTER_ENV_VAR} environment variable"
_SOURCE_DEFAULT = "Claude Code plugin default"
_SOURCE_UNSET = "unset"

_CONFIGURED_SOURCES = (_SOURCE_ARGUMENT, _SOURCE_ARGUMENT_BLANK, _SOURCE_ENVIRONMENT)


@dataclass(frozen=True)
class ImporterResolution:
    """Where the importer path came from, and what it is.

    ``path`` is None in two distinct states, so it MUST NOT be read as a
    not-configured signal:

    - ``source`` is ``_SOURCE_UNSET``: nothing was configured and no default
      exists on disk. ``is_configured`` is False, and the caller should skip.
    - ``source`` is ``_SOURCE_ARGUMENT_BLANK``: the caller passed ``--importer``
      with a blank value. ``is_configured`` is True, and the caller must fail.

    ``is_configured`` is the only correct test for the configured/not-configured
    decision that drives the exit code. ``source`` additionally names the origin
    for error messages.
    """

    path: Path | None
    source: str

    @property
    def is_configured(self) -> bool:
        """True when configuration was attempted, so a miss is a real failure.

        That is: ``--importer`` was supplied, even blank, or a nonblank
        ``CLAUDE_MEM_IMPORTER`` was set. It does NOT mean a usable path exists.
        A blank ``--importer`` names no path and is still configured, which is
        why ``path`` may be None here.
        """
        return self.source in _CONFIGURED_SOURCES


def is_blank(raw: str) -> bool:
    """True when a configuration value carries no path.

    Detection only. Callers pass the ORIGINAL string on to resolution, never the
    stripped view: a POSIX filename may legitimately begin or end with a space,
    so trimming the value that resolves would execute a different file or report
    a real importer missing.
    """
    return not raw.strip()


class PathModule(Protocol):
    """The slice of ``posixpath``/``ntpath`` the path helpers below depend on.

    Named as a Protocol rather than typed ``ModuleType`` so the dependency is
    visible and checked: ``ModuleType`` attribute access is ``Any``, which would
    let a wrong module through and silently erase the return types.

    The members are read-only properties on purpose. Typeshed declares
    ``ntpath.altsep`` as ``str`` and ``posixpath.altsep`` as ``None``, and a
    mutable Protocol attribute is invariant, so a writable ``altsep: str | None``
    matches neither module. A read-only member is covariant and matches both.

    ``splitdrive`` takes a positional-only parameter named ``p``, matching
    typeshed. Both matter, and neither is cosmetic. The real functions accept no
    keyword at all: ``posixpath.splitdrive(path="x")`` raises ``TypeError:
    splitdrive() got an unexpected keyword argument 'path'``. A Protocol that
    declares a named parameter therefore advertises a call that cannot work, and
    the type checker endorses it: under ``mypy --strict``, assigning ``os.path``
    to such a Protocol passes AND a ``splitdrive(path=...)`` call through it
    passes, so the checker launders a runtime crash instead of catching it.

    Stricter/looser/different than canonical: ``_PathModule`` in
    ``.claude/skills/skillforge/scripts/quick_validate.py`` is the same idea and
    is the source of the positional-only form used here. It declares ``sep`` and
    ``altsep`` as plain attributes, which this deliberately does not copy. That
    version does not accept ``ntpath`` (``altsep: expected "str | None", got
    "str"``); it is sound there only because that module ever assigns ``os.path``.
    This module injects ``ntpath`` by design, so the read-only form is required.
    """

    @property
    def sep(self) -> str: ...

    @property
    def altsep(self) -> str | None: ...

    def splitdrive(self, p: str, /) -> tuple[str, str]: ...


def path_separators(pathmod: PathModule | None = None) -> str:
    """Characters a platform accepts as path separators.

    ``pathmod`` is a standard-library path module and defaults to ``os.path``,
    which IS ``posixpath`` or ``ntpath`` for the running platform. Pass
    ``posixpath`` or ``ntpath`` to ask about the other one.

    ``altsep`` is the standard library's own answer: None on POSIX, and ``"/"``
    on Windows where ``sep`` is a backslash. Deriving the set from it rather than
    testing ``os.name`` keeps this correct for any platform the standard library
    describes, and keeps the backslash out of the set on POSIX, where it is an
    ordinary filename character rather than a separator.
    """
    mod: PathModule = os.path if pathmod is None else pathmod
    return mod.sep + (mod.altsep or "")


def expand_home(raw: str, home: Path, *, pathmod: PathModule | None = None) -> Path:
    """Expand a leading ``~`` against ``home`` instead of the process environment.

    ``pathmod`` defaults to ``os.path`` and exists so both platform behaviors are
    testable from either platform. Pass ``posixpath`` or ``ntpath``. One knob
    rather than two, because the separator question and the drive question below
    must be answered about the SAME platform; splitting them lets a caller pin a
    combination no platform has.

    Stricter/looser/different than canonical: ``Path.expanduser`` reads the real
    ``HOME`` or ``USERPROFILE`` and the password database, which defeats the
    injected ``home`` this module resolves against and forces tests to mutate
    global state. This expands only the current user's ``~``.

    Separator handling is platform-dependent, and deliberately so. On Windows a
    backslash separates path segments, so ``~\\importer.ts`` is a tilde path. On
    POSIX a backslash is a legal filename character, so the same string is a
    single literal relative filename and expanding it would rewrite a real name
    into a different path. Only the separators that platform actually recognizes
    are treated as such, in both the prefix test and the suffix strip.

    A ``~otheruser`` prefix is NOT expanded. It is returned unchanged, which
    makes it a RELATIVE path beginning with a literal ``~otheruser`` segment, so
    it never resolves against a stranger's home. The caller's later existence
    check then runs against whatever that relative path resolves to under the
    process working directory. That normally does not exist and the caller
    reports the literal path, but failure is not guaranteed: a directory
    literally named ``~otheruser`` in the working directory would satisfy the
    check and be executed. Do not rely on this branch as a rejection.

    The suffix is stripped of further leading separators before joining. Without
    that, ``~//importer.ts`` leaves ``/importer.ts``, and ``Path.__truediv__``
    discards its left operand when the right side is rooted, so the expansion
    would silently return ``/importer.ts`` and drop ``home`` entirely.

    A suffix left carrying a DRIVE after that strip is returned literally, the
    same as ``~otheruser``. Stripping separators does not make a suffix relative
    on Windows, where a drive is a second anchoring mechanism: ``~/D:/x`` leaves
    ``D:/x``, and joining that onto ``home`` yields ``D:\\x``, dropping ``home``
    exactly as a rooted suffix would. The drive-relative form is worse still,
    because ``C:x`` anchors to that drive's own working directory, which is
    process-global state no argument to this function can describe. Both are
    malformed input rather than a path under ``home``, so neither is expanded.
    ``splitdrive`` is the same per-platform module's answer, which is why it
    reports no drive on POSIX and leaves ``D:`` an ordinary directory name there.

    Deferring to ``splitdrive`` also inherits its permissiveness: ``ntpath``
    calls any single character before a colon a drive, so on Windows ``1:x`` is
    treated as anchored even though no such drive can exist. That direction is
    the safe one. A wrongly-anchored suffix returned literally fails the
    caller's existence check and reports the literal path, while a wrongly
    expanded one would resolve somewhere the caller never named.
    """
    mod: PathModule = os.path if pathmod is None else pathmod
    seps = path_separators(mod)
    if raw == "~":
        return home
    if not raw.startswith(tuple("~" + sep for sep in seps)):
        return Path(raw)
    suffix = raw[2:].lstrip(seps)
    if mod.splitdrive(suffix)[0]:
        return Path(raw)
    return home / suffix


def claude_default_importer(home: Path) -> Path:
    """Path the Claude-Mem marketplace plugin installs under a Claude Code home."""
    return (
        home
        / ".claude"
        / "plugins"
        / "marketplaces"
        / "thedotmack"
        / "scripts"
        / "import-memories.ts"
    )


def resolve_importer(
    explicit: str | None,
    env: Mapping[str, str],
    home: Path,
) -> ImporterResolution:
    """Resolve the importer path from argument, environment, then harness default.

    An empty or whitespace-only environment value counts as unset: exporting
    ``CLAUDE_MEM_IMPORTER=""`` is how a shell disables an inherited value, and
    treating it as a configured-but-broken path would turn that into exit 1.

    A blank ``--importer`` is the opposite case and is rejected, not ignored.
    ``explicit is None`` means the flag was never passed; ``--importer ""`` means
    the caller passed the highest-priority option and supplied nothing usable,
    so falling through to a lower tier would silently disregard an explicit
    instruction.
    """
    if explicit is not None:
        if is_blank(explicit):
            return ImporterResolution(None, _SOURCE_ARGUMENT_BLANK)
        return ImporterResolution(expand_home(explicit, home), _SOURCE_ARGUMENT)

    env_value = env.get(IMPORTER_ENV_VAR, "")
    if not is_blank(env_value):
        return ImporterResolution(expand_home(env_value, home), _SOURCE_ENVIRONMENT)

    default = claude_default_importer(home)
    if default.exists():
        return ImporterResolution(default, _SOURCE_DEFAULT)

    return ImporterResolution(None, _SOURCE_UNSET)


def _run_imports(importer: Path, files: list[Path]) -> tuple[int, list[tuple[str, str]]]:
    """Run the importer once per file. Returns (success count, failures)."""
    import_count = 0
    failed_files: list[tuple[str, str]] = []

    # tsx parses a leading dash as a flag, and a configured importer may be a
    # RELATIVE path the caller chose. A file named "--experimental-foo" is legal
    # and passes the existence check, so `str(importer)` would hand tsx a flag
    # instead of a script and the configured importer would silently never run.
    # An absolute path cannot start with a dash, which removes the ambiguity for
    # every name rather than blacklisting the ones seen so far.
    #
    # Stricter/looser/different than canonical: os.path.abspath, NOT
    # Path.resolve(). Both defeat the dash, but resolve() also collapses
    # symlinks, and the importer is a script that may locate its own imports
    # relative to itself. Measured: for "linked/importer.ts" where "linked" is a
    # symlink to "real", abspath keeps the directory the caller named while
    # resolve() reports ".../real", which changes the script's own base
    # directory. Package managers install plugin trees behind symlinks, so that
    # is a live difference and not a hypothetical one.
    importer_arg = os.path.abspath(importer)

    for file_path in files:
        print(f"  {file_path.name}")
        try:
            result = subprocess.run(
                ["npx", "tsx", importer_arg, str(file_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as e:
            failed_files.append((file_path.name, str(e)))
            print(f"    WARNING: Failed to import: {e}")
            continue

        if result.returncode != 0:
            msg = f"Plugin exited with code {result.returncode}"
            failed_files.append((file_path.name, msg))
            print(f"    WARNING: Import failed: exit code {result.returncode}")
        else:
            import_count += 1

    return import_count, failed_files


def _report(import_count: int, failed_files: list[tuple[str, str]]) -> int:
    print()
    if not failed_files:
        print(f"Import complete: {import_count} file(s) processed successfully")
        print("   Duplicates automatically skipped via composite key matching")
        return 0

    print(f"Import completed with failures: {import_count} succeeded, {len(failed_files)} failed")
    print("\nFailed files:")
    for name, reason in failed_files:
        print(f"  FAIL {name}: {reason}")
    return 1


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Import Claude-Mem memory snapshots")
    parser.add_argument(
        "--importer",
        default=None,
        help=(
            "Path to the Claude-Mem import-memories.ts script. Overrides "
            f"${IMPORTER_ENV_VAR} and the Claude Code plugin default."
        ),
    )
    args = parser.parse_args(argv)

    resolution = resolve_importer(
        args.importer,
        os.environ if env is None else env,
        Path.home() if home is None else home,
    )

    if resolution.source == _SOURCE_ARGUMENT_BLANK:
        print(
            "ERROR: --importer was passed an empty path. Omit the flag to fall "
            f"back to ${IMPORTER_ENV_VAR} and the Claude Code plugin default.",
            file=sys.stderr,
        )
        return 1

    importer = resolution.path
    if importer is None or not importer.is_file():
        # is_file() rather than exists(): a directory can occupy the path (a
        # misconfigured --importer, or a marketplace layout change), and
        # exists() alone would let that pass the guard and then fail
        # unhelpfully once tsx runs against a directory. is_configured, not
        # the absence itself, decides the exit code: a path the caller named
        # is a real failure, an uninstalled optional plugin is a supported
        # state.
        if resolution.is_configured:
            print(
                f"ERROR: Claude-Mem importer from {resolution.source} not found at: {importer}",
                file=sys.stderr,
            )
            return 1
        print(
            "SKIP: Claude-Mem plugin not installed. Set "
            f"${IMPORTER_ENV_VAR} or pass --importer to enable importing."
        )
        return 0

    if not _MEMORIES_DIR.exists():
        _MEMORIES_DIR.mkdir(parents=True, exist_ok=True)
        print("No memory files to import")
        return 0

    # Only top-level .json files
    files = sorted(_MEMORIES_DIR.glob("*.json"))
    if not files:
        print(f"No memory files to import from: {_MEMORIES_DIR}")
        return 0

    print(f"Importing {len(files)} memory file(s) from .claude-mem/memories/")
    import_count, failed_files = _run_imports(importer, files)
    return _report(import_count, failed_files)


if __name__ == "__main__":
    sys.exit(main())
