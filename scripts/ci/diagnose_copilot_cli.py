"""Copilot CLI diagnostics for the ai-review composite action."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
COPILOT_TEST_TIMEOUT_SECONDS = 10


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(argv: Sequence[str], timeout_seconds: int | None = None) -> CommandResult:
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return CommandResult(
            returncode=124,
            stdout=stdout,
            stderr=stderr,
        )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def append_multiline_output(path: Path, name: str, value: str, delimiter: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{name}<<{delimiter}\n")
        handle.write(value)
        if value and not value.endswith("\n"):
            handle.write("\n")
        handle.write(f"{delimiter}\n")


def _parse_login(auth_response: str) -> str:
    try:
        payload = json.loads(auth_response)
    except json.JSONDecodeError:
        return "unknown"
    login = payload.get("login")
    return login if isinstance(login, str) and login else "unknown"


def _parse_scopes(header_response: str) -> str:
    for line in header_response.splitlines():
        name, separator, value = line.partition(":")
        if separator and name.lower() == "x-oauth-scopes":
            return value.replace(" ", "") or "unknown"
    return "unknown"


def _mask_env_value(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    return f"[SET - {len(value)} chars]" if value else ""


def run_diagnostics(
    *,
    env: Mapping[str, str],
    output_path: Path,
    runner: Callable[[Sequence[str], int | None], CommandResult] = run_command,
    which: Callable[[str], str | None] = shutil.which,
) -> int:
    print("=== COPILOT CLI DIAGNOSTICS ===")
    print()

    health_status = "healthy"
    diagnostic: list[str] = []
    auth_status = ""

    print("1. Checking copilot command availability...")
    copilot_path = which("copilot")
    if not copilot_path:
        print("::error::copilot command not found in PATH")
        health_status = "failed"
        diagnostic.append("ERROR: copilot command not found")
    else:
        print(f"   ✓ copilot command found: {copilot_path}")
        diagnostic.append(f"copilot binary: {copilot_path}")

    print()
    print("2. Checking copilot version...")
    version_result = runner(["copilot", "--version"], None)
    version_output = (version_result.stdout + version_result.stderr).strip()
    print(f"   Version output: {version_output}")
    diagnostic.append(f"version: {version_output}")

    print()
    print("3. Checking copilot --help...")
    help_result = runner(["copilot", "--help"], None)
    if help_result.returncode == 0:
        print("   ✓ copilot --help works")
        diagnostic.append("help: OK")
    else:
        print("   ✗ copilot --help failed")
        health_status = "degraded"
        diagnostic.append("help: FAILED")

    print()
    print("4. Checking GitHub API authentication...")
    auth_result = runner(["gh", "api", "user"], None)
    auth_response = auth_result.stdout + auth_result.stderr
    if '"login"' in auth_response:
        auth_user = _parse_login(auth_response)
        print(f"   ✓ Authenticated as: {auth_user}")
        auth_status = f"authenticated as {auth_user}"

        scopes_result = runner(["gh", "api", "-i", "user"], None)
        scopes = _parse_scopes(scopes_result.stdout + scopes_result.stderr)
        print(f"   Token scopes: {scopes or 'none detected'}")
        auth_status += f", scopes: {scopes or 'unknown'}"
        diagnostic.append(f"auth_user: {auth_user}")
        diagnostic.append(f"auth_scopes: {scopes}")
    else:
        print("   ✗ GitHub API authentication failed")
        print(f"   Response: {auth_response}")
        health_status = "degraded"
        auth_status = "authentication failed"
        diagnostic.append(f"auth_error: {auth_response}")

    print()
    print("5. Checking Copilot API access...")
    print("   Running minimal test prompt (10s timeout)...")
    agent = env.get("COPILOT_AGENT", "")
    model = env.get("COPILOT_MODEL", "")
    print(f"   Agent: {agent}, Model: {model}")
    test_result = runner(
        [
            "copilot",
            "--no-auto-update",
            "--agent",
            agent,
            "--model",
            model,
            "--prompt",
            "Reply with only the word OK",
        ],
        COPILOT_TEST_TIMEOUT_SECONDS,
    )

    print(f"   Test exit code: {test_result.returncode}")
    if test_result.returncode == 0:
        print("   ✓ Copilot CLI test prompt succeeded")
        print(f"   Output: {test_result.stdout}")
        diagnostic.append("test_prompt: PASSED")
    elif test_result.returncode == 124:
        print("   ⚠ Copilot CLI test prompt timed out")
        health_status = "degraded"
        diagnostic.append("test_prompt: TIMEOUT")
    else:
        print(f"   ✗ Copilot CLI test prompt failed (exit code: {test_result.returncode})")
        health_status = "failed"
        diagnostic.append(f"test_prompt: FAILED (exit {test_result.returncode})")
        if test_result.stderr:
            print(f"   Stderr: {test_result.stderr}")
            diagnostic.append(f"test_stderr: {test_result.stderr}")
        if test_result.stdout:
            print(f"   Stdout: {test_result.stdout}")
            diagnostic.append(f"test_stdout: {test_result.stdout}")
        if not test_result.stdout and not test_result.stderr:
            print()
            print("   ⚠ DIAGNOSIS: CLI produced no output at all")
            print("   This typically indicates one of:")
            print("   - The GitHub account does not have Copilot access enabled")
            print("   - The PAT token lacks Copilot permissions")
            print("   - Network connectivity issues to Copilot API")
            diagnostic.append("diagnosis: NO_OUTPUT - likely missing Copilot access")

    print()
    print("6. Environment variables check...")
    print(f"   GH_TOKEN: {_mask_env_value(env, 'GH_TOKEN')}")
    print(f"   GITHUB_TOKEN: {_mask_env_value(env, 'GITHUB_TOKEN')}")
    print(f"   HOME: {env.get('HOME', '')}")
    print(f"   PATH includes npm: {'yes' if 'npm' in env.get('PATH', '') else 'no'}")
    diagnostic.append(f"gh_token_set: {'yes' if env.get('GH_TOKEN') else ''}")
    diagnostic.append(f"github_token_set: {'yes' if env.get('GITHUB_TOKEN') else ''}")

    print()
    print("=== DIAGNOSTIC SUMMARY ===")
    print(f"Health Status: {health_status}")
    print(f"Auth Status: {auth_status}")
    print()

    append_line(output_path, f"health_status={health_status}")
    append_line(output_path, f"auth_status={auth_status}")
    append_multiline_output(output_path, "diagnostic", "\n".join(diagnostic) + "\n", "EOF_DIAG")

    if health_status == "failed":
        print("::warning::Copilot CLI diagnostics indicate problems - main invocation may fail")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("error: no arguments are supported", file=sys.stderr)
        return 2
    output_file = os.environ.get("GITHUB_OUTPUT")
    if not output_file:
        print("error: GITHUB_OUTPUT is required", file=sys.stderr)
        return 2
    return run_diagnostics(env=os.environ, output_path=Path(output_file))


if __name__ == "__main__":
    raise SystemExit(main())
