#!/usr/bin/env python3
"""Assert the vendored tree contains the expected paths and its scripts start.

Replaces the PowerShell 'Assert vendored tree' block in cli-smoke.yml (ADR-006).

Skill scripts resolve their helpers from <root>/lib (ADR-047). A tree with the
right paths but no lib/ still crashes at import, so after the path check the
script runs `--help` on one script per lib package from the installed tree.

ENV:
  DEMO - absolute path to the demo directory

EXIT CODES (ADR-035):
  0 - all expected paths present and every probe script exits 0
  1 - a path is missing or a probe script fails
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# One script per lib package a shipped skill imports: hook_utilities, paths,
# github_core. `--help` reaches the import bootstrap before argparse exits.
PROBE_SCRIPTS: tuple[str, ...] = (
    "skills/chestertons-fence/scripts/investigate.py",
    "skills/context-optimizer/scripts/distill_artifact.py",
    "skills/merge-resolver/scripts/resolve_pr_conflicts.py",
)

# Each of these makes a script look for lib/ somewhere other than the installed
# tree, which would mask a missing lib/. GITHUB_WORKSPACE matters on Actions:
# it names the source checkout, whose .claude/lib is complete.
_PLUGIN_ROOT_VARS = ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT", "GITHUB_WORKSPACE")
_PROBE_TIMEOUT_SECONDS = 60


def _probe_script(demo_path: Path, relative: str) -> bool:
    """Run `--help` on one vendored script; True when it exits 0.

    The script path stays relative to the install directory, which is passed
    only as ``cwd``. No value read from the environment reaches the argument
    list, so the interpreter always runs a path built from PROBE_SCRIPTS.
    """
    env = {k: v for k, v in os.environ.items() if k not in _PLUGIN_ROOT_VARS}
    script = Path(".claude") / relative
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=demo_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        print(
            f"::error::vendored script timed out after {_PROBE_TIMEOUT_SECONDS}s: "
            f"{demo_path / script}"
        )
        return False
    if result.returncode != 0:
        detail = (result.stderr.strip().splitlines() or ["no stderr"])[-1]
        print(
            f"::error::vendored script failed --help (exit {result.returncode}): "
            f"{demo_path / script}: {detail}"
        )
        return False
    return True


def run(_argv: list[str] | None = None) -> int:
    """Assert expected paths exist in the vendored tree."""
    demo = os.environ.get("DEMO", "")
    if not demo:
        print("::error::DEMO env var is required")
        return 1

    demo_path = Path(demo)
    claude_dir = demo_path / ".claude"

    # (path, is_dir) tuples; is_dir=True checks for directory, False for file.
    #
    # No `commands` entry. ADR-064 (issue #5632) made skills the single
    # user-invocable surface and deleted `.claude/commands/`, so a vendored tree
    # that still carried one would be the defect rather than the expectation.
    expected: list[tuple[Path, bool]] = [
        (claude_dir / "agents", True),
        (claude_dir / "skills", True),
        (claude_dir / "lib", True),
        (claude_dir / "lib" / "paths.py", False),
        (demo_path / "CLAUDE.md", False),
        (demo_path / "AGENTS.md", False),
        (claude_dir / ".ai-agents-version.json", False),
    ]

    missing: list[str] = []
    for path, is_dir in expected:
        kind = "container" if is_dir else "leaf"
        if is_dir and not path.is_dir():
            print(f"::error::missing {kind} {path}")
            missing.append(str(path))
        elif not is_dir and not path.is_file():
            print(f"::error::missing {kind} {path}")
            missing.append(str(path))

    if missing:
        return 1

    failed = [rel for rel in PROBE_SCRIPTS if not _probe_script(demo_path, rel)]
    if failed:
        return 1

    print(
        f"Vendored tree OK ({len(expected)} paths present, {len(PROBE_SCRIPTS)} scripts ran --help)"
    )
    return 0


def main() -> int:
    """Entry point."""
    return run()


if __name__ == "__main__":
    sys.exit(main())
