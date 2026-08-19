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
  --negative-env    Run in degraded mode: point plugin root to a nonexistent
                    path. Asserts the hook still ALLOWS (fail-open).
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
    """A payload no registered matcher selects.

    Proves the launcher resolves and the dispatcher runs to completion: it
    starts Python, loads the manifest, matches nothing, and allows. That is the
    customer-wedge property (issue #2205), and it is deliberately NOT evidence
    that any guard fired.
    """
    return json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
    }).encode()


def _agent_payload(*, model: str | None) -> bytes:
    """A payload the surviving `^(Agent|Task)$` gate actually selects.

    Issue #5154 retired every command-scoped group, so `Bash` stopped matching
    anything and the Bash payload above silently stopped exercising a guard. It
    kept passing, which is the shape where a test quietly ceases to test what it
    was written for. This payload restores that coverage against the one gate
    still registered.

    Contract, from `invoke_require_subagent_model.py`: exit 0 allows when the
    call names a model, exit 2 blocks when it does not and no model-pinned
    definition exists.
    """
    tool_input: dict[str, str] = {"subagent_type": "no-such-agent-type-5154"}
    if model is not None:
        tool_input["model"] = model
    return json.dumps({"tool_name": "Agent", "tool_input": tool_input}).encode()


def _check_surviving_gate(
    dispatch_py: Path, *, consumer_cwd: Path, install_root: Path
) -> int:
    """Drive the surviving gate both ways. Returns the failure count.

    The deny case is the load-bearing half. Asserting only that a matched
    payload exits 0 cannot separate "the gate ran and allowed" from "nothing
    matched", and that ambiguity is exactly what hid the coverage loss when the
    Bash groups were retired. A deny proves the installed plugin routes to the
    gate. The escape hatch is cleared for that case because it would otherwise
    turn the deny into an allow.
    """
    failures = 0
    hatch = ("CLAUDE_CODE_SUBAGENT_MODEL",)

    allowed = _run_hook(
        dispatch_py,
        _agent_payload(model="claude-haiku-4-5"),
        consumer_cwd=consumer_cwd,
        plugin_root=install_root,
        drop_env=hatch,
    )
    if allowed.returncode != 0:
        print(
            f"FAIL: PreToolUse denied an Agent spawn that named a model "
            f"(exit {allowed.returncode}). Expected allow.\n"
            f"  stderr: {allowed.stderr.decode(errors='replace')}"
        )
        failures += 1
    else:
        print("PASS: PreToolUse allows an Agent spawn that names a model")

    denied = _run_hook(
        dispatch_py,
        _agent_payload(model=None),
        consumer_cwd=consumer_cwd,
        plugin_root=install_root,
        drop_env=hatch,
    )
    if denied.returncode != 2:
        print(
            f"FAIL: PreToolUse did not deny an Agent spawn with no model "
            f"(exit {denied.returncode}, expected 2). Either the dispatcher no "
            f"longer routes to the surviving gate, or the gate stopped firing. "
            f"Without this control the allow case above is vacuous.\n"
            f"  stderr: {denied.stderr.decode(errors='replace')}"
        )
        failures += 1
    else:
        print("PASS: PreToolUse denies an Agent spawn with no model (gate fired)")

    return failures


def _run_hook(
    dispatch_py: Path,
    payload: bytes,
    *,
    consumer_cwd: Path,
    plugin_root: Path | None,
    hide_interpreter: bool = False,
    drop_env: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[bytes]:
    env = dict(os.environ)
    # Remove any existing plugin root vars
    env.pop("COPILOT_PLUGIN_ROOT", None)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    # A caller asserting a deny must be able to clear the guard's escape hatch,
    # which would otherwise turn the expected deny into an allow on any machine
    # that happens to export it.
    for name in drop_env:
        env.pop(name, None)

    if plugin_root is not None:
        env["COPILOT_PLUGIN_ROOT"] = str(plugin_root)
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)

    if hide_interpreter:
        # Simulate interpreter absence by mangling PATH
        env["PATH"] = ""

    # Semgrep traces install_root from argparse to this call and cannot see
    # the containment check in _find_dispatcher, which resolves the candidate
    # and refuses any path outside the install root. That check is real and
    # tested, but it raises rather than returning a sanitized value, so the
    # taint engine keeps following it.
    #
    # Not suppressed: this repository forbids security suppression comments in
    # staged changes, which is a stronger stance than treating them as a last
    # resort, and the gate is right. A suppression records that someone once
    # decided this was fine; the containment check and its tests record why.
    #
    # Command injection is not reachable here regardless. This is an argument
    # list with no shell, so a metacharacter in the path arrives as one literal
    # argument and cannot start a second command, and the interpreter is
    # sys.executable rather than a caller-supplied string.
    return subprocess.run(
        [sys.executable, "-u", str(dispatch_py)],
        input=payload,
        capture_output=True,
        cwd=str(consumer_cwd),
        env=env,
        timeout=30,
    )


def _registered_events(install_root: Path) -> list[str]:
    """Read the events the installed plugin actually registers.

    Hardcoding the list went stale the moment an event lost its last group:
    issue #5154 retired the only PostToolUse group, and a fixed
    ``["PreToolUse", "PostToolUse"]`` then reported a missing dispatcher for an
    event the plugin no longer ships. Reading ``hooks.json`` keeps the #4672
    property that matters, which is that a missing dispatcher for a REGISTERED
    event is a failure and never a skip. An empty or unreadable manifest is
    itself a failure in the caller, so this never certifies an empty run.
    """
    manifest = install_root / "hooks" / "hooks.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return []
    return [event for event, entries in hooks.items() if isinstance(entries, list) and entries]


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
    events_to_test = _registered_events(args.install_root)
    if not events_to_test:
        print(f"ERROR: no hook events registered in {args.install_root}", file=sys.stderr)
        return 1
    failures = 0

    for event in events_to_test:
        dispatch_py = _find_dispatcher(args.install_root, event)
        if dispatch_py is None:
            # A missing dispatcher is a failure, not a skip. Skipping made the
            # guard report success after executing nothing: delete both
            # dispatchers and failures stayed 0. A required check that passes
            # on an empty run is worse than no check, because it certifies the
            # exact breakage it exists to catch. Refs #4672.
            print(f"FAIL: no dispatcher for {event} in {args.install_root}")
            failures += 1
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
            if event == "PreToolUse":
                # The Bash payload below matches no registered group after
                # issue #5154, so on its own it proves only that the launcher
                # resolves. Drive the surviving gate explicitly, both ways.
                failures += _check_surviving_gate(
                    dispatch_py,
                    consumer_cwd=args.consumer_cwd,
                    install_root=args.install_root,
                )
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
