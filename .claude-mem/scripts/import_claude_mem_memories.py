#!/usr/bin/env python3
"""Import Claude-Mem memory snapshots from .claude-mem/memories/.

Idempotent import of all JSON memory files from the memories directory.
Automatically prevents duplicates using composite keys.

The Claude-Mem plugin is an optional dependency. It ships as a Claude Code
plugin and has no Copilot CLI equivalent, so the importer path is resolved in
this order:

  1. ``--importer PATH`` on the command line
  2. the ``CLAUDE_MEM_IMPORTER`` environment variable
  3. the Claude Code plugin default under ``~/.claude/plugins/``

When none of the three resolves, the plugin is not installed and the import is
skipped with exit 0. When a path IS configured (1 or 2) but is missing or the
importer fails, that is a real failure and exits 1.

EXIT CODES:
  0  - Success, or the optional plugin is not installed (skipped)
  1  - A configured importer is missing, or one or more imports failed

See: ADR-035 Exit Code Standardization
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_MEMORIES_DIR = _SCRIPT_DIR.parent / "memories"

IMPORTER_ENV_VAR = "CLAUDE_MEM_IMPORTER"

_SOURCE_ARGUMENT = "--importer argument"
_SOURCE_ENVIRONMENT = f"{IMPORTER_ENV_VAR} environment variable"
_SOURCE_DEFAULT = "Claude Code plugin default"
_SOURCE_UNSET = "unset"


@dataclass(frozen=True)
class ImporterResolution:
    """Where the importer path came from, and what it is.

    ``path`` is None only when nothing was configured and no default exists on
    disk. ``source`` names the origin for both error messages and the
    configured/not-configured decision that drives the exit code.
    """

    path: Path | None
    source: str

    @property
    def is_configured(self) -> bool:
        """True when the caller named a path, so a miss is a real failure."""
        return self.source in (_SOURCE_ARGUMENT, _SOURCE_ENVIRONMENT)


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
    """
    if explicit:
        return ImporterResolution(Path(explicit).expanduser(), _SOURCE_ARGUMENT)

    env_value = env.get(IMPORTER_ENV_VAR, "").strip()
    if env_value:
        return ImporterResolution(Path(env_value).expanduser(), _SOURCE_ENVIRONMENT)

    default = claude_default_importer(home)
    if default.exists():
        return ImporterResolution(default, _SOURCE_DEFAULT)

    return ImporterResolution(None, _SOURCE_UNSET)


def _run_imports(importer: Path, files: list[Path]) -> tuple[int, list[tuple[str, str]]]:
    """Run the importer once per file. Returns (success count, failures)."""
    import_count = 0
    failed_files: list[tuple[str, str]] = []

    for file_path in files:
        print(f"  {file_path.name}")
        try:
            result = subprocess.run(
                ["npx", "tsx", str(importer), str(file_path)],
                capture_output=True,
                text=True,
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

    if resolution.path is None:
        print(
            "SKIP: Claude-Mem plugin not installed. Set "
            f"${IMPORTER_ENV_VAR} or pass --importer to enable importing."
        )
        return 0

    if not resolution.path.exists():
        print(
            f"ERROR: Claude-Mem importer from {resolution.source} not found at: {resolution.path}",
            file=sys.stderr,
        )
        return 1

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
    import_count, failed_files = _run_imports(resolution.path, files)
    return _report(import_count, failed_files)


if __name__ == "__main__":
    sys.exit(main())
