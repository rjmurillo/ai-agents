"""Execute the optional ai-review post-analysis script."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int


def run_command(argv: Sequence[str]) -> CommandResult:
    completed = subprocess.run(list(argv), check=False)
    return CommandResult(returncode=completed.returncode)


def build_command(script_path: Path, env: Mapping[str, str]) -> list[str]:
    if script_path.suffix == ".py":
        return [
            "python3",
            str(script_path),
            "--pr-number",
            env.get("PR_NUMBER", ""),
            "--verdict",
            env.get("AI_VERDICT", ""),
            "--findings-json",
            env.get("AI_FINDINGS", ""),
        ]
    if script_path.suffix == ".ps1":
        return [
            "pwsh",
            "-NoProfile",
            "-File",
            str(script_path),
            "-PRNumber",
            env.get("PR_NUMBER", ""),
            "-Verdict",
            env.get("AI_VERDICT", ""),
            "-FindingsJson",
            env.get("AI_FINDINGS", ""),
        ]
    raise ValueError(f"Unsupported script type: {script_path} (expected .py or .ps1)")


def execute_post_script(
    *,
    env: Mapping[str, str],
    runner: Callable[[Sequence[str]], CommandResult] = run_command,
) -> int:
    execute_script = env.get("EXECUTE_SCRIPT", "")
    pr_number = env.get("PR_NUMBER", "")
    ai_verdict = env.get("AI_VERDICT", "")

    print(f"Executing post-analysis script: {execute_script}")
    print(f"PR Number: {pr_number}")
    print(f"AI Verdict: {ai_verdict}")

    script_path = Path(execute_script)
    if not script_path.is_file():
        print(f"::error::Execute script not found: {execute_script}")
        return EXIT_LOGIC

    try:
        command = build_command(script_path, env)
    except ValueError as exc:
        print(f"::error::{exc}")
        return EXIT_LOGIC

    result = runner(command)
    if result.returncode != 0:
        print(f"::error::Execute script failed with exit code {result.returncode}")
        return result.returncode

    print("Post-analysis script completed successfully")
    return EXIT_OK


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    if argv:
        print("error: no arguments are supported", file=sys.stderr)
        return EXIT_CONFIG
    return execute_post_script(env=os.environ if env is None else env)


if __name__ == "__main__":
    raise SystemExit(main())
