"""Materialize and test the installed plugin hooks as a consumer would see them.

This script simulates what happens after `/plugin install project-toolkit@ai-agents`:
it copies the plugin tree into the standard install layout, creates a scratch consumer
repo that is NOT the ai-agents checkout, sets the environment the host would set, and
asserts the hooks allow a Bash tool call.

Exit codes follow the repo convention:
  0 = all assertions passed
  1 = a hook assertion failed (the bug this gate catches)
  2 = configuration error (bad arguments, missing paths)

Usage:
  python scripts/ci/test_installed_plugin_hooks.py --plugin-source src/copilot-cli \
      --install-root <tmp>/installed-plugins/ai-agents/project-toolkit \
      --consumer-cwd <tmp>/consumer-repo

Optional flags:
  --negative-env    Run in degraded mode: unset plugin root vars and hide the
                    interpreter. Asserts the hook still ALLOWS (fail-open).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _materialize_plugin(source: Path, install_root: Path) -> None:
    """Copy the plugin source tree into the install layout."""
    if install_root.exists():
        shutil.rmtree(install_root)
    shutil.copytree(source, install_root)


def _create_consumer_repo(cwd: Path) -> None:
    """Create a minimal git repo that is NOT the ai-agents checkout."""
    cwd.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=str(cwd),
        capture_output=True,
        check=True,
    )
    readme = cwd / "README.md"
    readme.write_text("# Consumer project\n", encoding="utf-8")
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=t@t", "add", "."],
        cwd=str(cwd),
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "-c", "user.name=test", "-c", "user.email=t@t", "commit", "-m", "init"],
        cwd=str(cwd),
        capture_output=True,
        check=True,
    )


def _bash_payload() -> bytes:
    return json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
    }).encode()


def _run_hook(
    dispatch_py: Path,
    payload: bytes,
    *,
    consumer_cwd: Path,
    plugin_root: Path | None,
    hide_interpreter: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    env = dict(os.environ)
    # Remove any existing plugin root vars
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PLUGIN_ROOT", None)

    if plugin_root is not None:
        env["COPILOT_PLUGIN_ROOT"] = str(plugin_root)
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)

    if hide_interpreter:
        # Simulate interpreter absence by mangling PATH
        env["PATH"] = ""

    return subprocess.run(
        [sys.executable, "-u", str(dispatch_py)],
        input=payload,
        capture_output=True,
        cwd=str(consumer_cwd),
        env=env,
        timeout=30,
    )


def _find_dispatcher(install_root: Path, event: str) -> Path | None:
    """Find the _dispatch.py for an event, refusing anything outside the root.

    ``install_root`` arrives from the command line, so the resolved candidate is
    checked for containment before it is ever handed to ``subprocess``. Only the
    root is caller-supplied; the rest of the path is fixed. Containment is what
    makes that guarantee hold anyway, since a symlink under ``hooks`` could
    otherwise point the interpreter at a script outside the install tree.

    The interpreter is invoked as an argument list with no shell, so a shell
    metacharacter in the path is passed through as a literal argument and cannot
    start a second command. Validating here is a boundary check on which file
    gets executed, not an escaping fix. Refs #4672.
    """
    root = install_root.resolve()
    for variant in (event, event[0].lower() + event[1:]):
        candidate = (root / "hooks" / variant / "_dispatch.py").resolve()
        if not candidate.is_file():
            continue
        if not candidate.is_relative_to(root):
            raise ValueError(
                f"refusing to run {candidate}: resolves outside {root}"
            )
        return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-source", required=True, type=Path)
    parser.add_argument("--install-root", required=True, type=Path)
    parser.add_argument("--consumer-cwd", required=True, type=Path)
    # Takes a value rather than being a flag so the caller can forward a
    # workflow input directly. Assembling the flag conditionally in YAML was
    # an ADR-006 violation and put a branch where it could not be tested.
    parser.add_argument(
        "--negative-env",
        choices=("true", "false"),
        default="false",
        help="Test fail-open: unset plugin root and hide interpreter",
    )
    args = parser.parse_args()
    negative_env = args.negative_env == "true"

    # Resolve all paths to absolute before any cwd change
    args.plugin_source = args.plugin_source.resolve()
    args.install_root = args.install_root.resolve()
    args.consumer_cwd = args.consumer_cwd.resolve()

    if not args.plugin_source.is_dir():
        print(f"ERROR: plugin source not found: {args.plugin_source}", file=sys.stderr)
        return 2

    # Materialize
    _materialize_plugin(args.plugin_source, args.install_root)
    _create_consumer_repo(args.consumer_cwd)

    payload = _bash_payload()
    events_to_test = ["PreToolUse", "PostToolUse"]
    failures = 0

    for event in events_to_test:
        dispatch_py = _find_dispatcher(args.install_root, event)
        if dispatch_py is None:
            print(f"SKIP: no dispatcher for {event}")
            continue

        if negative_env:
            # Test fail-open: plugin root set to nonexistent path
            # (simulates Failure A: variable set but path invalid)
            proc = _run_hook(
                dispatch_py,
                payload,
                consumer_cwd=args.consumer_cwd,
                plugin_root=Path("/nonexistent/plugin/root"),
            )
            if proc.returncode != 0:
                print(
                    f"FAIL: {event} denied (exit {proc.returncode}) with unset "
                    f"plugin root. Expected allow (exit 0).\n"
                    f"  stderr: {proc.stderr.decode(errors='replace')}"
                )
                failures += 1
            else:
                warning_present = b"hooks DISABLED" in proc.stderr
                if not warning_present:
                    print(
                        f"FAIL: {event} allowed but no warning on stderr.\n"
                        f"  stderr: {proc.stderr.decode(errors='replace')}"
                    )
                    failures += 1
                else:
                    print(f"PASS: {event} fail-open with warning (negative-env)")
        else:
            # Normal positive test
            proc = _run_hook(
                dispatch_py,
                payload,
                consumer_cwd=args.consumer_cwd,
                plugin_root=args.install_root,
            )
            if proc.returncode != 0:
                print(
                    f"FAIL: {event} denied (exit {proc.returncode}). "
                    f"Expected allow (exit 0).\n"
                    f"  stderr: {proc.stderr.decode(errors='replace')}"
                )
                failures += 1
            else:
                print(f"PASS: {event} allowed (positive)")

    if failures > 0:
        print(f"\n{failures} assertion(s) failed.")
        return 1
    print("\nAll assertions passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
