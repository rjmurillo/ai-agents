#!/usr/bin/env python3
"""Compare shared agent behavior through real Claude and Copilot CLIs.

The evaluator installs one Claude agent and one Copilot agent into separate
isolated git repositories. Each CLI receives the same fixture request through
its non-interactive prompt flag. Reports keep runtime events, resolved model
ids, agent hashes, tool traces, and assertion results.

Exit codes follow AGENTS.md: 0 ok, 1 logic, 2 config, 3 external, 4 auth.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from _runtime_output import RuntimeOutputError, parse_events, runtime_failure_record
from _runtime_parity import (
    SENTINEL,
    Fixture,
    ParityConfigError,
    hash_file,
    live_files,
    load_fixtures,
    prepare_workspace,
    runtime_env,
    score_assertions,
)

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = Path(__file__).parent / "examples" / "runtime-parity-fixtures.json"
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_TIMEOUT = 900.0
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
AUTH_HINTS = (
    "authentication",
    "not logged in",
    "please run /login",
    "sign in",
    "unauthorized",
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
    return [
        executable,
        "--agent",
        "parity",
        "--no-custom-instructions",
        *(["--no-ask-user"] if "question" not in fixture.tools else []),
        "--disable-builtin-mcps",
        "--no-remote",
        "--no-remote-export",
        "--allow-all-tools",
        "--output-format",
        "json",
        "--model",
        model,
        "--prompt",
        fixture.prompt,
        *_tool_args(fixture.tools, harness),
    ]


def _claude_result(events: Sequence[Mapping[str, object]]) -> tuple[str, str | None]:
    model: str | None = None
    response = ""
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            value = event.get("model")
            model = value if isinstance(value, str) else model
        if event.get("type") == "result" and isinstance(event.get("result"), str):
            response = str(event["result"]).strip()
    return response, model


def _copilot_result(events: Sequence[Mapping[str, object]]) -> tuple[str, str | None]:
    """Return the final answer and the model that produced every part of it.

    The model is attributed per content-bearing message, not per event. An
    empty or tool-only event that names a model says nothing about who wrote
    the answer, so a sequence with an unattributed or mixed content-bearing
    message reports no model and the fail-closed model gate rejects it.
    """
    chunks: list[str] = []
    models: list[str | None] = []
    for event in events:
        if event.get("type") != "assistant.message":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        content = data.get("content")
        model = data.get("model")
        if isinstance(content, str) and content.strip():
            chunks.append(content.strip())
            models.append(model if isinstance(model, str) else None)
    if not chunks:
        return "", None
    attributed = set(models)
    if len(attributed) == 1 and None not in attributed:
        return chunks[-1], models[-1]
    return chunks[-1], None


QUESTION_TOOLS = frozenset({"askuserquestion", "ask_user", "askuser", "ask-user"})


def _tool_name(event: object) -> str:
    if not isinstance(event, Mapping):
        return ""
    data = event.get("data")
    if isinstance(data, Mapping):
        for key in ("toolName", "name", "tool"):
            value = data.get(key)
            if isinstance(value, str):
                return value
    name = event.get("name")
    return name if isinstance(name, str) else ""


def question_mechanism(tools: Sequence[object], response: str) -> str:
    """Name the branch the harness actually took to pose its question.

    Recording this keeps a capability difference visible. Both CLIs answer in
    prose today because neither exposes a question tool in non-interactive
    mode, so a fixture that scores only the text cannot tell "asked in prose
    because that is all this CLI can do" from "asked in prose because the
    runner disabled the tool". The day one harness ships a callable question
    tool, this field diverges and the parity check fails instead of collapsing
    both sides into a shared fallback.
    """
    for tool in tools:
        if _tool_name(tool).lower() in QUESTION_TOOLS:
            return "structured_event"
    return "text_fallback" if response.strip() else "no_answer"


def _traces(events: Sequence[Mapping[str, object]]) -> tuple[list[object], list[object]]:
    tools: list[object] = []
    subagents: list[object] = []
    for event in events:
        event_type = event.get("type")
        if event_type in {"tool.execution_start", "tool.execution_complete"}:
            tools.append(event)
        if isinstance(event_type, str) and "subagent" in event_type.lower():
            subagents.append(event)
        message = event.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tools.append(block)
                    if block.get("name") in {"Agent", "Task"}:
                        subagents.append(block)
    return tools, subagents


def _failure_code(run: subprocess.CompletedProcess[str]) -> int:
    text = f"{run.stdout}\n{run.stderr}".lower()
    return EXIT_AUTH if any(hint in text for hint in AUTH_HINTS) else EXIT_EXTERNAL


def _redacted_argv(argv: Sequence[str], harness: str) -> list[str]:
    redacted = list(argv)
    prompt_flag = "--print" if harness == "claude" else "--prompt"
    redacted[redacted.index(prompt_flag) + 1] = "<fixture-prompt>"
    return redacted


def _control_report(fixture: Fixture) -> dict[str, object]:
    return {
        "provenance": "prompt-only",
        "positive": score_assertions(
            fixture, fixture.positive.response, fixture.positive.files
        ),
        "negative": score_assertions(
            fixture, fixture.negative.response, fixture.negative.files
        ),
    }


def _version(executable: str, runner: Runner, timeout: float) -> str:
    run = runner(
        [executable, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if run.returncode != 0:
        raise RuntimeError(f"{executable} --version failed")
    return (run.stdout or run.stderr).strip()


def _run_fixture(
    fixture: Fixture,
    harness: str,
    executable: str,
    model: str,
    workspace: Path,
    runner: Runner,
    timeout: float,
) -> tuple[dict[str, object], int]:
    prepare_workspace(fixture, harness, workspace)
    argv = build_argv(harness, executable, model, fixture)
    try:
        run = runner(
            argv,
            cwd=workspace,
            env=runtime_env(workspace, harness),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return (
            runtime_failure_record(
                harness,
                _redacted_argv(argv, harness),
                exit_code=None,
                error="runtime timed out",
            ),
            EXIT_EXTERNAL,
        )
    try:
        events = parse_events(run.stdout)
    except RuntimeOutputError as exc:
        return (
            runtime_failure_record(
                harness,
                _redacted_argv(argv, harness),
                exit_code=run.returncode,
                error=str(exc),
                raw_output=run.stdout,
            ),
            EXIT_EXTERNAL,
        )
    response, resolved_model = (
        _claude_result(events)
        if harness == "claude"
        else _copilot_result(events)
    )
    files = live_files(fixture, workspace)
    assertions = score_assertions(fixture, response, files)
    tools, subagents = _traces(events)
    code = EXIT_OK if run.returncode == 0 else _failure_code(run)
    if run.returncode == 0 and (not response or not resolved_model):
        code = EXIT_EXTERNAL
    assertions.append(
        {
            "kind": "profile_isolation",
            "path": None,
            "expected": "sentinel absent",
            "passed": SENTINEL not in run.stdout and SENTINEL not in response,
        }
    )
    return (
        {
            "provenance": "Claude runtime" if harness == "claude" else "Copilot runtime",
            "command": _redacted_argv(argv, harness),
            "exit_code": run.returncode,
            "resolved_model": resolved_model,
            "raw_output": run.stdout,
            "response": response,
            "question_mechanism": question_mechanism(tools, response),
            "tool_events": tools,
            "subagent_events": subagents,
            "assertions": assertions,
            "error": None,
            "passed": code == EXIT_OK and all(item["passed"] for item in assertions),
        },
        code,
    )


def _default_output() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
    return REPO_ROOT / "artifacts" / "runtime-parity" / run_id / "report.json"


def run_evaluation(
    *,
    fixtures_path: Path,
    model: str,
    output: Path,
    claude_bin: str,
    copilot_bin: str,
    timeout: float,
    dry_run: bool,
    runner: Runner = subprocess.run,
) -> tuple[dict[str, object], int]:
    """Run all fixtures, stopping immediately on a resolved-model mismatch."""
    fixtures = load_fixtures(fixtures_path)
    versions = {
        "claude": _version(claude_bin, runner, timeout),
        "copilot": _version(copilot_bin, runner, timeout),
    }
    report: dict[str, object] = {
        "schema_version": 1,
        "requested_model": model,
        "cli_versions": versions,
        "fixture_count": len(fixtures),
        "fixtures": [],
        "verdict": "DRY_RUN" if dry_run else "PASS",
    }
    if dry_run:
        report["fixtures"] = [
            {
                "id": fixture.fixture_id,
                "claude_agent_sha256": hash_file(fixture.claude_agent),
                "copilot_agent_sha256": hash_file(fixture.copilot_agent),
                "fixture_sha256": hashlib.sha256(
                    fixture.prompt.encode("utf-8")
                ).hexdigest(),
                "controls": _control_report(fixture),
            }
            for fixture in fixtures
        ]
        return report, EXIT_OK
    if output.exists() or (output.parent / "workspaces").exists():
        raise ParityConfigError(
            "output path already contains a runtime parity run"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    workspaces = output.parent / "workspaces"
    final_code = EXIT_OK
    records: list[dict[str, object]] = []
    for fixture in fixtures:
        fixture_record: dict[str, object] = {
            "id": fixture.fixture_id,
            "claude_agent_sha256": hash_file(fixture.claude_agent),
            "copilot_agent_sha256": hash_file(fixture.copilot_agent),
            "fixture_sha256": hashlib.sha256(
                fixture.prompt.encode("utf-8")
            ).hexdigest(),
            "controls": _control_report(fixture),
        }
        claude, claude_code = _run_fixture(
            fixture,
            "claude",
            claude_bin,
            model,
            workspaces / fixture.fixture_id / "claude",
            runner,
            timeout,
        )
        fixture_record["claude"] = claude
        final_code = max(final_code, claude_code)
        if claude_code != EXIT_OK:
            records.append(fixture_record)
            report["verdict"] = "ERROR"
            break
        copilot, copilot_code = _run_fixture(
            fixture,
            "copilot",
            copilot_bin,
            model,
            workspaces / fixture.fixture_id / "copilot",
            runner,
            timeout,
        )
        fixture_record["copilot"] = copilot
        final_code = max(final_code, copilot_code)
        records.append(fixture_record)
        if copilot_code != EXIT_OK:
            report["verdict"] = "ERROR"
            break
        if (
            claude["resolved_model"] != model
            or copilot["resolved_model"] != model
            or claude["resolved_model"] != copilot["resolved_model"]
        ):
            report["verdict"] = "FAIL_MODEL_MISMATCH"
            final_code = EXIT_LOGIC
            break
        if claude["question_mechanism"] != copilot["question_mechanism"]:
            report["verdict"] = "FAIL_QUESTION_MECHANISM_MISMATCH"
            final_code = EXIT_LOGIC
            break
        if not claude["passed"] or not copilot["passed"]:
            report["verdict"] = "FAIL"
            final_code = EXIT_LOGIC
    report["fixtures"] = records
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report, final_code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--copilot-bin", default="copilot")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    args = _parser().parse_args(argv)
    if MODEL_ID_RE.fullmatch(args.model) is None:
        print("Error: --model has an invalid format.", file=sys.stderr)
        return EXIT_CONFIG
    if (
        isinstance(args.timeout, bool)
        or not math.isfinite(args.timeout)
        or args.timeout <= 0
    ):
        print("Error: --timeout must be finite and greater than zero.", file=sys.stderr)
        return EXIT_CONFIG
    output = (args.output or _default_output()).resolve()
    try:
        report, code = run_evaluation(
            fixtures_path=args.fixtures.resolve(),
            model=args.model,
            output=output,
            claude_bin=args.claude_bin,
            copilot_bin=args.copilot_bin,
            timeout=args.timeout,
            dry_run=args.dry_run,
            runner=runner,
        )
    except ParityConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_CONFIG
    except (FileNotFoundError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(json.dumps(report, indent=2))
    if not args.dry_run:
        print(f"Report: {output}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
