#!/usr/bin/env python3
"""Drive the installed plugin hook on a machine with no Python interpreter.

Why this exists as a Python script rather than inline workflow shell:

ADR-006 keeps logic out of workflow YAML. The vanilla rows previously carried
40 line shell and PowerShell blocks with loops and conditionals, which is the
exact shape that rule forbids, and the two copies had already drifted apart in
what they asserted.

Why a script can orchestrate a no-Python test:

The interpreter must be absent for the CODE UNDER TEST, not for the harness.
On Linux the hook runs inside a container that genuinely has no Python, driven
from the runner which has one. On Windows the hook runs with an environment
whose PATH has every interpreter-bearing directory removed, while this harness
runs from the interpreter's absolute path. In both cases the hook command
resolves no interpreter, which is the customer's condition (issue #4672).

The precondition is asserted before the hook runs, and a row that stops being
vanilla fails loudly rather than quietly passing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_INTERPRETERS = ("python3", "python", "py")

# Emitted by every degraded path in the generated hook command.
_REQUIRED_WARNING_FRAGMENTS = (
    "project-toolkit@ai-agents",
    "hooks DISABLED",
    "session is unaffected",
)

_PAYLOAD = json.dumps(
    {
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
        "session_id": "vanilla-guard",
        "hook_event_name": "PreToolUse",
    }
)


class GuardError(RuntimeError):
    """A vanilla row did not behave as the contract requires."""


class EnvironmentUnavailableError(RuntimeError):
    """The row could not run at all, which is not the same as failing.

    Distinguishing these two is the whole point. A missing container
    runtime is an infrastructure gap; reporting it as "the plugin denied"
    or as "the image is not vanilla" sends the reader to the wrong place.
    Local act has no Docker, so this fires there and not in CI.
    """


def scrub_path(raw_path: str) -> str:
    """Drop every PATH entry that contains an interpreter.

    Filtering by directory NAME is not sufficient. On a GitHub Windows runner
    the App Execution Alias directory holds python.exe and python3.exe while
    its own name says nothing about Python, so a name based filter leaves the
    row non-vanilla. Measured: the precondition failed with "python3 found"
    and "python found" while py was correctly gone.
    """
    kept = []
    for entry in raw_path.split(os.pathsep):
        if not entry.strip():
            continue
        directory = Path(entry)
        has_interpreter = any(
            (directory / f"{name}{suffix}").exists()
            for name in _INTERPRETERS
            for suffix in ("", ".exe")
        )
        if not has_interpreter:
            kept.append(entry)
    return os.pathsep.join(kept)


def assert_no_interpreter(env: dict[str, str]) -> None:
    """Fail loudly when the row is not actually vanilla."""
    found = [
        name for name in _INTERPRETERS if shutil.which(name, path=env.get("PATH", ""))
    ]
    if found:
        raise GuardError(
            "row is not vanilla: these interpreters still resolve: " + ", ".join(found)
        )


def extract_hook_command(hooks_json: Path, event: str, key: str) -> str:
    """Read one hook command with a real JSON parser.

    grep and sed cannot do this. The command contains escaped quotes, so a
    "[^"]*" pattern truncates at the first one and yields an empty string, and
    an empty command makes the shell exit 0, satisfying a did-not-deny
    assertion while testing nothing. Measured: grep produced 0 characters
    where the real command is 1234.
    """
    data = json.loads(hooks_json.read_text(encoding="utf-8"))
    entries = data.get("hooks", {}).get(event, [])
    for entry in entries:
        command = entry.get(key)
        if command:
            return str(command)
    raise GuardError(f"no {key} command for event {event} in {hooks_json}")


def event_is_registered(hooks_json: Path, event: str) -> bool:
    """Return whether the manifest registers any hook on *event*.

    Zero tool-use hooks is a valid, deliberately-shipped state (ADR-097): a
    row with no ``PreToolUse`` entry has no hook command to prove
    vanilla-safe, and driving Docker or a PATH-scrubbed PowerShell anyway
    would test the harness, not the plugin's contract. A missing or
    malformed manifest is a different failure and must not be read as
    "nothing registered"; this function lets those propagate as a raised
    exception rather than swallowing them into an empty result.

    A *present* event whose value is not a list (``{"PreToolUse": {}}``) is
    the same kind of malformed manifest, not an absent registration: reading
    it as "not registered" would let a broken manifest pass this guard
    vacuously instead of failing closed, which contradicts the fail-closed
    contract this docstring already claims for a malformed ``hooks``
    mapping.
    """
    data = json.loads(hooks_json.read_text(encoding="utf-8"))
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        raise GuardError(f"malformed 'hooks' mapping in {hooks_json}")
    if event not in hooks:
        return False
    entries = hooks[event]
    if not isinstance(entries, list):
        raise GuardError(
            f"malformed '{event}' entry in {hooks_json}: expected a list, "
            f"got {type(entries).__name__}"
        )
    return len(entries) > 0


def assert_degraded(returncode: int, output: str) -> None:
    """The contract: degraded and warning, never denied."""
    if returncode != 0:
        raise GuardError(
            f"hook DENIED with exit {returncode}; it must degrade, not block.\n"
            f"Output:\n{output}"
        )
    missing = [f for f in _REQUIRED_WARNING_FRAGMENTS if f not in output]
    if missing:
        raise GuardError(
            "hook allowed but did not warn. Missing from output: "
            + ", ".join(repr(m) for m in missing)
            + f"\nOutput:\n{output}"
        )


def run_windows(install_root: Path, consumer_cwd: Path) -> tuple[int, str]:
    env = dict(os.environ)
    env["PATH"] = scrub_path(env.get("PATH", ""))
    assert_no_interpreter(env)
    env["COPILOT_PLUGIN_ROOT"] = str(install_root)
    env["CLAUDE_PLUGIN_ROOT"] = str(install_root)
    command = extract_hook_command(
        install_root / "hooks" / "hooks.json", "PreToolUse", "powershell"
    )
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        input=_PAYLOAD,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=str(consumer_cwd),
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def run_linux_container(image: str, install_root: Path, consumer_cwd: Path) -> tuple[int, str]:
    """Run the hook inside a container that genuinely has no interpreter.

    The container is the code under test's environment. This harness stays on
    the runner, so the container never needs Python for the test to be driven.
    """
    if shutil.which("docker") is None:
        raise EnvironmentUnavailableError(
            "docker is not available, so the Python-free container cannot be started. "
            "This row requires a runner with Docker."
        )
    probe = subprocess.run(
        ["docker", "run", "--rm", image, "sh", "-c",
         "command -v python3 || command -v python || echo NONE"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    # An empty result and a failed invocation are different things. Treating a
    # failed docker call as "an interpreter resolved" reports a confusing
    # not-vanilla error for what is actually a missing container runtime.
    if probe.returncode != 0:
        raise EnvironmentUnavailableError(
            f"could not probe image {image}: docker exited {probe.returncode}. "
            f"stderr: {probe.stderr.strip() or '(empty)'}"
        )
    if "NONE" not in probe.stdout:
        raise GuardError(
            f"image {image} is not vanilla; an interpreter resolved: {probe.stdout.strip()}"
        )
    command = extract_hook_command(
        install_root / "hooks" / "hooks.json", "PreToolUse", "bash"
    )
    script = f"cd /consumer && {command}"
    proc = subprocess.run(
        [
            "docker", "run", "--rm", "-i",
            "-v", f"{install_root}:/plugin:ro",
            "-v", f"{consumer_cwd}:/consumer",
            "-e", "COPILOT_PLUGIN_ROOT=/plugin",
            "-e", "CLAUDE_PLUGIN_ROOT=/plugin",
            image, "bash", "-c", script,
        ],
        input=_PAYLOAD, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("linux-container", "windows-path"))
    parser.add_argument("--install-root", required=True, type=Path)
    parser.add_argument("--consumer-cwd", required=True, type=Path)
    parser.add_argument("--image", default="", help="Container image for linux-container mode")
    args = parser.parse_args(argv)

    if args.mode == "linux-container" and not args.image:
        print("--image is required for linux-container mode", file=sys.stderr)
        return 2

    install_root = args.install_root.resolve()
    hooks_json = install_root / "hooks" / "hooks.json"
    try:
        if not event_is_registered(hooks_json, "PreToolUse"):
            print(
                "VANILLA GUARD PASSED (vacuous): no PreToolUse hooks registered "
                f"in {hooks_json}; nothing to prove vanilla-safe (ADR-097)."
            )
            return 0
    except (OSError, json.JSONDecodeError) as exc:
        print(f"VANILLA GUARD FAILED: could not read {hooks_json}: {exc}", file=sys.stderr)
        return 1
    except GuardError as exc:
        print(f"VANILLA GUARD FAILED: {exc}", file=sys.stderr)
        return 1

    try:
        if args.mode == "linux-container":
            returncode, output = run_linux_container(
                args.image, install_root, args.consumer_cwd.resolve()
            )
        else:
            returncode, output = run_windows(
                install_root, args.consumer_cwd.resolve()
            )
        print(f"hook exit code: {returncode}")
        print(f"hook output:\n{output}")
        assert_degraded(returncode, output)
    except EnvironmentUnavailableError as exc:
        print(f"VANILLA GUARD CANNOT RUN: {exc}", file=sys.stderr)
        return 3
    except GuardError as exc:
        print(f"VANILLA GUARD FAILED: {exc}", file=sys.stderr)
        return 1

    print("VANILLA GUARD PASSED: hook degraded with a warning and did not deny.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
