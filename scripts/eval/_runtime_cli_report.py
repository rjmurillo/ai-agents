"""CLI argument and report helpers for runtime parity evaluation."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from _runtime_parity import (
    Fixture,
    hash_file,
    hash_installed_agent,
    probe_version,
    score_assertions,
)

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _tool_args(tools: Sequence[str], harness: str) -> list[str]:
    if harness == "claude":
        names = {"question": "AskUserQuestion", "write": "Edit"}
        selected = [names[name] for name in tools]
        return ["--tools", ",".join(selected)] if selected else ["--tools", ""]
    names = {"question": "ask_user", "write": "edit"}
    selected = [names[name] for name in tools]
    args = [f"--available-tools={','.join(selected)}"]
    args.extend(f"--allow-tool={tool}" for tool in selected)
    return args


def build_argv(
    harness: str,
    executable: str,
    model: str,
    fixture: Fixture,
) -> list[str]:
    """Build a shell-free real CLI invocation for one fixture."""
    if harness == "claude":
        return [
            executable,
            "--print",
            fixture.prompt,
            "--agent",
            "parity",
            "--setting-sources",
            "project",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--permission-mode",
            "acceptEdits",
            "--output-format",
            "stream-json",
            "--verbose",
            "--no-session-persistence",
            "--model",
            model,
            *_tool_args(fixture.tools, harness),
        ]
    instruction_args = (
        [] if fixture.copilot_instruction is not None else ["--no-custom-instructions"]
    )
    return [
        executable,
        "--agent",
        "parity",
        *instruction_args,
        *(["--no-ask-user"] if "question" not in fixture.tools else []),
        "--disable-builtin-mcps",
        "--no-remote",
        "--no-remote-export",
        "--no-auto-update",
        "--allow-all-tools",
        "--output-format",
        "json",
        "--model",
        model,
        "--prompt",
        fixture.prompt,
        *_tool_args(fixture.tools, harness),
    ]


def fixture_record(fixture: Fixture) -> dict[str, object]:
    """Build immutable fixture and control provenance."""
    record = {
        "id": fixture.fixture_id,
        "claude_agent_sha256": hash_installed_agent(fixture.claude_agent),
        "copilot_agent_sha256": hash_installed_agent(fixture.copilot_agent),
        "fixture_sha256": hashlib.sha256(fixture.prompt.encode("utf-8")).hexdigest(),
        "controls": {
            "provenance": "prompt-only",
            "positive": score_assertions(
                fixture,
                fixture.positive.response,
                fixture.positive.files,
            ),
            "negative": score_assertions(
                fixture,
                fixture.negative.response,
                fixture.negative.files,
            ),
        },
    }
    if fixture.claude_instruction is not None:
        record["claude_instruction_sha256"] = hash_file(fixture.claude_instruction)
    if fixture.copilot_instruction is not None:
        record["copilot_instruction_sha256"] = hash_file(fixture.copilot_instruction)
    return record


def probe_versions(
    output: Path,
    claude_bin: str,
    copilot_bin: str,
    runner: Runner,
    timeout: float,
) -> dict[str, str]:
    """Record both isolated CLI versions."""
    version_workspaces = output.parent / "version-probes"
    return {
        "claude": probe_version(
            claude_bin,
            "claude",
            version_workspaces / "claude",
            runner,
            timeout,
        ),
        "copilot": probe_version(
            copilot_bin,
            "copilot",
            version_workspaces / "copilot",
            runner,
            timeout,
        ),
    }
