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
import os
import re
import signal
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from _runtime_output import (
    RuntimeOutputError,
    parse_events,
    question_mechanism,
    question_payload,
    runtime_failure_record,
    structured_tool_model,
)
from _runtime_output import (
    accumulate_verdict as _accumulate_verdict,
)
from _runtime_output import (
    claude_result as _claude_result,
)
from _runtime_output import (
    comparison_verdict as _comparison_verdict,
)
from _runtime_output import (
    copilot_result as _copilot_result,
)
from _runtime_output import (
    failure_code as _failure_code,
)
from _runtime_output import (
    redacted_argv as _redacted_argv,
)
from _runtime_output import (
    runtime_error as _runtime_error,
)
from _runtime_output import (
    traces as _traces,
)
from _runtime_parity import (
    SENTINEL,
    Fixture,
    ParityConfigError,
    hash_installed_agent,
    live_files,
    load_fixtures,
    prepare_workspace,
    probe_version,
    runtime_env,
    score_assertions,
    verify_worktree_identity,
)

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = Path(__file__).parent / "examples" / "runtime-parity-fixtures.json"
DEFAULT_MODEL = "claude-opus-4.6"
DEFAULT_TIMEOUT = 900.0
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run_in_process_group(
    argv: list[str] | tuple[str, ...],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    capture_output: bool = False,
    timeout: float | None = None,
    **_extra: object,
) -> subprocess.CompletedProcess[str]:
    """Drop-in replacement for subprocess.run that kills the full process tree on timeout.

    subprocess.run(timeout=...) only terminates the direct child.  CLI launchers
    can leave descendants running, consuming model quota and modifying the
    workspace after the report says it stopped.  This function starts the child
    in its own session (Unix) and kills the entire process group on timeout.
    See _copilot_cli_acp.py:164-179 for the same pattern.
    """
    stdout_arg: int | None = subprocess.PIPE if capture_output else None
    stderr_arg: int | None = subprocess.PIPE if capture_output else None

    use_session = os.name != "nt"
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=stdout_arg,
        stderr=stderr_arg,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=use_session,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if use_session:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
        else:
            proc.kill()
        proc.wait()
        raise
    return subprocess.CompletedProcess(list(argv), proc.returncode, stdout, stderr)


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


def _control_report(fixture: Fixture) -> dict[str, object]:
    return {
        "provenance": "prompt-only",
        "positive": score_assertions(fixture, fixture.positive.response, fixture.positive.files),
        "negative": score_assertions(fixture, fixture.negative.response, fixture.negative.files),
    }


def _invoke_runtime(
    fixture: Fixture,
    harness: str,
    executable: str,
    model: str,
    workspace: Path,
    runner: Runner,
    timeout: float,
) -> tuple[
    subprocess.CompletedProcess[str] | None,
    list[str],
    dict[str, object] | None,
]:
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
            None,
            argv,
            runtime_failure_record(
                harness,
                _redacted_argv(argv, harness),
                exit_code=None,
                error="runtime timed out",
            ),
        )
    return run, argv, None


def _parse_runtime_events(
    run: subprocess.CompletedProcess[str],
    harness: str,
    argv: Sequence[str],
) -> tuple[list[dict[str, object]] | None, dict[str, object] | None]:
    try:
        return parse_events(run.stdout), None
    except RuntimeOutputError as exc:
        return None, runtime_failure_record(
            harness,
            _redacted_argv(argv, harness),
            exit_code=run.returncode,
            error=str(exc),
            raw_output=run.stdout,
            stderr=run.stderr,
        )


def _score_runtime_result(
    fixture: Fixture,
    harness: str,
    argv: Sequence[str],
    run: subprocess.CompletedProcess[str],
    events: Sequence[Mapping[str, object]],
    workspace: Path,
) -> tuple[dict[str, object], int]:
    response, resolved_model = (
        _claude_result(events) if harness == "claude" else _copilot_result(events)
    )
    tools, subagents = _traces(events)
    mechanism = question_mechanism(tools, response)
    if harness == "copilot" and mechanism == "structured_event" and not resolved_model:
        resolved_model = structured_tool_model(events)
    files = live_files(fixture, workspace)
    assertion_text = question_payload(tools) if mechanism == "structured_event" else response
    assertions = score_assertions(fixture, assertion_text, files)
    code = EXIT_OK if run.returncode == 0 else _failure_code(run)
    if run.returncode == 0 and (mechanism == "no_answer" or not resolved_model):
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
            "stderr": run.stderr,
            "response": response,
            "question_mechanism": mechanism,
            "tool_events": tools,
            "subagent_events": subagents,
            "assertions": assertions,
            "error": _runtime_error(run, mechanism, resolved_model),
            "passed": code == EXIT_OK and all(item["passed"] for item in assertions),
        },
        code,
    )


def _run_fixture(
    fixture: Fixture,
    harness: str,
    executable: str,
    model: str,
    workspace: Path,
    runner: Runner,
    timeout: float,
) -> tuple[dict[str, object], int]:
    run, argv, failure = _invoke_runtime(
        fixture, harness, executable, model, workspace, runner, timeout
    )
    if failure is not None:
        return failure, EXIT_EXTERNAL
    assert run is not None
    events, failure = _parse_runtime_events(run, harness, argv)
    if failure is not None:
        return failure, EXIT_EXTERNAL
    assert events is not None
    return _score_runtime_result(fixture, harness, argv, run, events, workspace)


def _default_output() -> Path:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
    return REPO_ROOT / "artifacts" / "runtime-parity" / run_id / "report.json"


def _probe_versions(
    output: Path,
    claude_bin: str,
    copilot_bin: str,
    runner: Runner,
    timeout: float,
) -> dict[str, str]:
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


def _fixture_record(fixture: Fixture) -> dict[str, object]:
    return {
        "id": fixture.fixture_id,
        "claude_agent_sha256": hash_installed_agent(fixture.claude_agent),
        "copilot_agent_sha256": hash_installed_agent(fixture.copilot_agent),
        "fixture_sha256": hashlib.sha256(fixture.prompt.encode("utf-8")).hexdigest(),
        "controls": _control_report(fixture),
    }


def _run_fixture_pair(
    fixture: Fixture,
    model: str,
    workspaces: Path,
    claude_bin: str,
    copilot_bin: str,
    runner: Runner,
    timeout: float,
) -> tuple[dict[str, object], int, str | None]:
    record = _fixture_record(fixture)
    claude, claude_code = _run_fixture(
        fixture,
        "claude",
        claude_bin,
        model,
        workspaces / fixture.fixture_id / "claude",
        runner,
        timeout,
    )
    record["claude"] = claude
    if claude_code != EXIT_OK:
        return record, claude_code, "ERROR"
    copilot, copilot_code = _run_fixture(
        fixture,
        "copilot",
        copilot_bin,
        model,
        workspaces / fixture.fixture_id / "copilot",
        runner,
        timeout,
    )
    record["copilot"] = copilot
    if copilot_code != EXIT_OK:
        return record, copilot_code, "ERROR"
    verdict = _comparison_verdict(claude, copilot, model)
    return record, EXIT_LOGIC if verdict else EXIT_OK, verdict


def _run_live_fixtures(
    fixtures: Sequence[Fixture],
    model: str,
    workspaces: Path,
    claude_bin: str,
    copilot_bin: str,
    runner: Runner,
    timeout: float,
) -> tuple[list[dict[str, object]], str, int]:
    records: list[dict[str, object]] = []
    final_code = EXIT_OK
    final_verdict = "PASS"
    for fixture in fixtures:
        record, code, verdict = _run_fixture_pair(
            fixture,
            model,
            workspaces,
            claude_bin,
            copilot_bin,
            runner,
            timeout,
        )
        records.append(record)
        final_code = max(final_code, code)
        if verdict in {"ERROR", "FAIL_MODEL_MISMATCH"}:
            return records, verdict, final_code
        if verdict is not None:
            final_verdict = _accumulate_verdict(final_verdict, verdict)
    return records, final_verdict, final_code


def run_evaluation(
    *,
    fixtures_path: Path,
    model: str,
    output: Path,
    claude_bin: str,
    copilot_bin: str,
    timeout: float,
    dry_run: bool,
    runner: Runner = _run_in_process_group,
) -> tuple[dict[str, object], int]:
    """Run all fixtures, stopping immediately on a resolved-model mismatch."""
    fixtures = load_fixtures(fixtures_path)
    workspaces = output.parent / "workspaces"
    if not dry_run and (output.exists() or workspaces.exists()):
        raise ParityConfigError("output path already contains a runtime parity run")
    report: dict[str, object] = {
        "schema_version": 1,
        "requested_model": model,
        "cli_versions": _probe_versions(output, claude_bin, copilot_bin, runner, timeout),
        "fixture_count": len(fixtures),
        "fixtures": [],
        "verdict": "DRY_RUN" if dry_run else "PASS",
    }
    if dry_run:
        report["fixtures"] = [_fixture_record(fixture) for fixture in fixtures]
        return report, EXIT_OK
    output.parent.mkdir(parents=True, exist_ok=True)
    records, verdict, final_code = _run_live_fixtures(
        fixtures,
        model,
        workspaces,
        claude_bin,
        copilot_bin,
        runner,
        timeout,
    )
    report["fixtures"] = records
    report["verdict"] = verdict
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


def main(argv: Sequence[str] | None = None, *, runner: Runner = _run_in_process_group) -> int:
    args = _parser().parse_args(argv)
    if MODEL_ID_RE.fullmatch(args.model) is None:
        print("Error: --model has an invalid format.", file=sys.stderr)
        return EXIT_CONFIG
    if isinstance(args.timeout, bool) or not math.isfinite(args.timeout) or args.timeout <= 0:
        print("Error: --timeout must be finite and greater than zero.", file=sys.stderr)
        return EXIT_CONFIG
    output = (args.output or _default_output()).resolve()
    try:
        verify_worktree_identity()
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
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(json.dumps(report, indent=2))
    if not args.dry_run:
        print(f"Report: {output}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
