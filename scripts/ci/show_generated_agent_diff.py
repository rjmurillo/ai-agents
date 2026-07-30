"""Explain a generated-agent validation failure.

The validate job regenerates every agent from its template and fails when a
committed file differs. That failure says only "files differ"; this script runs
after it and says which files, and what to do about it.

Regeneration is repeated here without the validation flag so the working tree
carries the expected content. ``git diff`` then names the manually edited files.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_GENERATOR = ("uv", "run", "python", "build/generate_agents.py")

_REMEDY = """To fix this issue:
  1. Edit the source template in templates/agents/*.shared.md
  2. Run: uv run python build/generate_agents.py
  3. Commit the regenerated files
"""


def _run(argv: tuple[str, ...] | list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def changed_files(cwd: Path) -> list[str]:
    """Return the paths ``git diff`` reports as modified in the working tree."""
    completed = _run(["git", "diff", "--name-only"], cwd)
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            completed.args,
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return [line for line in completed.stdout.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="repository root to run git in")
    args = parser.parse_args(argv)
    root = Path(args.repo_root)

    print("")
    print("=== Files that differ from generated output ===")
    print("")

    regenerated = _run(_GENERATOR, root)
    sys.stdout.write(regenerated.stdout)
    sys.stderr.write(regenerated.stderr)

    try:
        files = changed_files(root)
    except subprocess.CalledProcessError as error:
        print(
            f"git diff --name-only failed with exit code {error.returncode}",
            file=sys.stderr,
        )
        if error.stderr:
            sys.stderr.write(error.stderr)
            if not error.stderr.endswith("\n"):
                sys.stderr.write("\n")
        return 0

    if not files:
        print("No differences detected in git diff (validation may have failed for other reasons)")
        return 0

    print("The following generated files were manually edited:")
    print("")
    for path in files:
        print(f"  - {path}")
    print("")
    print(_REMEDY)
    print("=== Detailed diff ===")
    sys.stdout.write(_run(["git", "diff"], root).stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
