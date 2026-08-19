"""Materialize and test the installed plugin hooks as a consumer would see them.

This script simulates what happens after `/plugin install project-toolkit@ai-agents`:
it copies the plugin tree into the standard install layout, creates a scratch consumer
repo that is NOT the ai-agents checkout, sets the environment the host would set, and
asserts the shipped hook surface is internally consistent and non-wedging.

ADR-096 retired every tool-call hook, so the plugin now ships zero registered
hook events. This script previously treated an empty manifest as an
unconditional failure ("an empty run is a failure, never a skip", issue #4672).
That assumption is exactly what ADR-096 reverses, so the assertion is inverted
rather than deleted: what the script asserts now is AGREEMENT between what the
manifest registers and what the tree ships.

  - zero registered events and zero shipped dispatchers -> PASS, the ADR-096
    state. Reported with explicit counts, never as a silent skip.
  - zero registered events but a dispatcher still on disk -> FAIL. That is
    orphaned machinery a consumer would install and never run, and it is the
    shape a half-finished regeneration leaves behind.
  - one or more registered events -> the original #4672 coverage applies
    unchanged: every registered event MUST have a dispatcher that resolves and
    allows an unmatched call, and MUST fail open under a broken plugin root.

Keeping the non-empty path fully armed is the point. It means re-adding a
tool-use hook re-arms this gate automatically instead of landing against a
guard that has quietly become a no-op.

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
    event is a failure and never a skip.

    Returns an empty list for two different situations, which the caller must
    separate rather than collapse: a manifest that legitimately registers
    nothing (the ADR-096 state) and one that could not be read at all. Use
    :func:`_manifest_is_readable` to tell them apart. Before ADR-096 both were
    treated as failure, which is why this docstring used to claim the function
    "never certifies an empty run"; that claim no longer holds and the caller
    now owns the distinction.
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


def _manifest_is_readable(install_root: Path) -> bool:
    """True when hooks.json parses and carries a well-formed ``hooks`` mapping.

    Separates "registers nothing" from "could not be read", which
    :func:`_registered_events` reports identically as an empty list. Without
    this split, permitting the empty case would also permit a manifest that
    failed to generate, and those are opposite verdicts.
    """
    manifest = install_root / "hooks" / "hooks.json"
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and isinstance(data.get("hooks"), dict)


def _shipped_dispatchers(install_root: Path) -> list[Path]:
    """Every ``_dispatch.py`` present under the installed plugin's hooks tree.

    With zero events registered, any dispatcher still on disk is orphaned
    machinery: a consumer installs it and nothing ever runs it. That is the
    residue a half-finished regeneration leaves, so it is a failure rather
    than a curiosity.
    """
    hooks_dir = install_root / "hooks"
    if not hooks_dir.is_dir():
        return []
    return sorted(hooks_dir.glob("*/_dispatch.py"))


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

    if not _manifest_is_readable(args.install_root):
        # Unreadable or structurally wrong manifest. Still a hard failure: this
        # is the generation-broke case, not the deliberately-empty one.
        print(
            f"FAIL: hooks.json missing, unparseable, or has no 'hooks' mapping "
            f"in {args.install_root}",
            file=sys.stderr,
        )
        return 1

    events_to_test = _registered_events(args.install_root)
    orphans = _shipped_dispatchers(args.install_root)
    # Report the examined counts unconditionally, so a run that checked nothing
    # is distinguishable from one that checked something and passed
    # (.claude/rules/ci-scripts.md MUST 12).
    print(
        f"installed plugin registers {len(events_to_test)} hook event(s): "
        f"{events_to_test or '[]'}; {len(orphans)} dispatcher(s) on disk"
    )

    if not events_to_test:
        # ADR-096: zero registered tool-call hooks is the deliberately shipped
        # state. Assert the tree AGREES with the manifest rather than passing
        # on an empty loop.
        if orphans:
            print(
                f"FAIL: {len(orphans)} dispatcher(s) shipped with zero registered "
                f"events. A consumer installs machinery nothing can run; this is "
                f"the residue of an incomplete regeneration.\n"
                + "\n".join(f"  orphan: {p}" for p in orphans)
            )
            print("\n1 assertion(s) failed.")
            return 1
        print(
            "PASS: zero registered hook events and zero shipped dispatchers "
            "(ADR-096 zero-tool-use-hooks state)"
        )
        print("\nAll assertions passed.")
        return 0

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
            # ADR-096 retired the last registered gate, so there is no longer a
            # guard to drive both ways here. This branch now proves only that a
            # registered event's dispatcher resolves and allows an unmatched
            # call, which is the #2205 customer-wedge property. A future hook
            # that re-populates this loop MUST add its own deny-side assertion:
            # an allow alone cannot separate "the gate ran and allowed" from
            # "nothing matched", and that ambiguity is what hid the coverage
            # loss when the Bash groups were retired under #5154.
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
