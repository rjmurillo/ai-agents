"""Install and verify the pinned GitHub Copilot CLI for ai-review."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
DEFAULT_COPILOT_VERSION = "1.0.63"


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(argv: Sequence[str]) -> CommandResult:
    try:
        completed = subprocess.run(
            list(argv), check=False, capture_output=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        return CommandResult(
            returncode=127,
            stdout="",
            stderr=f"{argv[0]}: command not found",
        )
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{line}\n")


def install_copilot_cli(
    *,
    output_path: Path,
    copilot_version: str = DEFAULT_COPILOT_VERSION,
    runner: Callable[[Sequence[str]], CommandResult] = run_command,
    which: Callable[[str], str | None] = shutil.which,
) -> int:
    print(f"Installing GitHub Copilot CLI@{copilot_version}...")
    install_result = runner(["npm", "install", "-g", f"@github/copilot@{copilot_version}"])
    print(install_result.stdout, end="")
    print(install_result.stderr, end="", file=sys.stderr)
    if install_result.returncode != 0:
        print(f"::error::Failed to install GitHub Copilot CLI@{copilot_version}")
        return EXIT_LOGIC

    print("Verifying installation...")
    if not which("copilot"):
        print("::error::copilot command not found after installation")
        return EXIT_LOGIC

    print("Copilot CLI version:")
    version_result = runner(["copilot", "--no-auto-update", "--version"])
    version_full = (version_result.stdout + version_result.stderr) or "unknown"
    print(version_full, end="" if version_full.endswith("\n") else "\n")
    version = version_full.splitlines()[0] if version_full.splitlines() else "unknown"
    append_line(output_path, f"copilot_version={version}")

    if copilot_version not in version:
        print(
            f"::warning::Expected version {copilot_version} but got {version}. "
            "Binary may have auto-updated."
        )
        print(
            "::warning::Version-drift runbook: "
            ".serena/memories/copilot/copilot-cli-frontmatter-regression-runbook.md "
            "(policy: ADR-094)."
        )
    return EXIT_OK


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    if argv:
        print("error: no arguments are supported", file=sys.stderr)
        return EXIT_CONFIG
    resolved_env = os.environ if env is None else env
    output_file = resolved_env.get("GITHUB_OUTPUT")
    if not output_file:
        print("error: GITHUB_OUTPUT is required", file=sys.stderr)
        return EXIT_CONFIG
    return install_copilot_cli(
        output_path=Path(output_file),
        copilot_version=resolved_env.get("COPILOT_VERSION", DEFAULT_COPILOT_VERSION),
    )


if __name__ == "__main__":
    raise SystemExit(main())
