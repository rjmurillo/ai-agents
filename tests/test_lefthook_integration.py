from __future__ import annotations

import io
import json
import os
import runpy
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import NoReturn, Self

import pytest
import yaml

from scripts.validation import git_hook_policy as policy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEFTHOOK = shutil.which("lefthook")
SEMGREP = shutil.which("semgrep")
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
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", "--", relative_path)
    _git(repo, "commit", "-qm", f"test: add {Path(relative_path).name}")
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


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
    (repo / "lefthook.yml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
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
    content = path.read_text(encoding="utf-8")
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
    session.write_text(content, encoding="utf-8")
    return session


def test_adr_review_policy_blocks_stale_debate_reference(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_today_session(tmp_path, '{"notes": "/adr-review was run"}')
    analysis = tmp_path / ".agents" / "analysis"
    analysis.mkdir(parents=True)
    (analysis / "old-debate.md").write_text("ADR-042 review", encoding="utf-8")

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
    (analysis / "adr-062-debate.md").write_text("ADR-062 review", encoding="utf-8")

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
    (analysis / "adr-0620-debate.md").write_text("ADR-0620 review", encoding="utf-8")

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
    evidence.write_text("ADR-062 review", encoding="utf-8")
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
    retro.write_text("# Retrospective\nreal work\n", encoding="utf-8")

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
    (sessions / "2026-03-14-session-1.json").write_text(
        '{"notes": "Learnings captured"}', encoding="utf-8"
    )

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
    retro.write_text("# Retrospective\nstale\n", encoding="utf-8")
    sessions = tmp_path / ".agents" / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "2026-03-13-session-1.json").write_text(
        '{"notes": "Learnings captured"}', encoding="utf-8"
    )

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
        "update-causal-graph",
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
        "update-causal-graph",
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
        "memory-size",
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
        "update-causal-graph",
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
    marker.write_text(
        "from pathlib import Path\nimport sys\n"
        "p=Path('jobs.log'); old=p.read_text() if p.exists() else ''\n"
        "p.write_text(old + sys.argv[1] + '\\n')\n",
        encoding="utf-8",
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
    (repo / "lefthook.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
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
    (repo / "hang.py").write_text("import time\n\ntime.sleep(5)\n", encoding="utf-8")
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
    (repo / "lefthook.yml").write_text(yaml.safe_dump(config), encoding="utf-8")

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
    detector.write_text(
        "from pathlib import Path\nimport sys\n"
        "Path('root-job-ran.txt').write_text(','.join(sys.argv[1:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    (repo / "root-only.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "test: base")
    base_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", base_sha)
    (repo / "root-only.txt").write_text("head\n", encoding="utf-8")
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
    marker.write_text(
        "from pathlib import Path\nimport sys\n"
        "p = Path('jobs.log')\n"
        "old = p.read_text() if p.exists() else ''\n"
        "entry = sys.argv[1] + ':' + ','.join(sys.argv[2:]) + '\\n'\n"
        "p.write_text(old + entry)\n",
        encoding="utf-8",
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
    (repo / "lefthook.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    _commit_file(repo, "base.txt", "base\n")
    for path in ("root.md", "nested/doc.md", "root.py", "nested/source.py"):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("content\n", encoding="utf-8")
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
    marker.write_text(
        "from pathlib import Path\nimport sys\n"
        "p = Path('jobs.log')\n"
        "old = p.read_text() if p.exists() else ''\n"
        "p.write_text(old + sys.argv[1] + '\\n')\n",
        encoding="utf-8",
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
    (repo / "lefthook.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
    _git(repo, "add", "lefthook.yml", "marker.py")
    _git(repo, "commit", "-qm", "test: base")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    for path in ("root.py", "nested/source.py", "nested/config.yml"):
        target = repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("value = 1\n", encoding="utf-8")
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
    marker.write_text(
        "from pathlib import Path\nimport sys\n"
        "p = Path('stdin.log')\n"
        "old = p.read_text() if p.exists() else ''\n"
        "p.write_text(old + sys.argv[1] + ':' + sys.stdin.read())\n",
        encoding="utf-8",
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
    (repo / "lefthook.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
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
    marker.write_text(
        "from pathlib import Path\nimport sys\n"
        "Path('push-files.log').write_text('\\n'.join(sys.argv[1:]))\n",
        encoding="utf-8",
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
    (repo / "lefthook.yml").write_text(yaml.safe_dump(config), encoding="utf-8")
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
        path.write_text(f"value: int = {value}\n", encoding="utf-8")
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
    message.write_text("fix: clean message\n", encoding="utf-8")

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
    message.write_text(f"fix: bad {chr(0x2014)} message\n", encoding="utf-8")
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
    fixer.write_text(
        "from pathlib import Path\nimport sys\n"
        "Path(sys.argv[1]).write_text('fixed\\n', encoding='utf-8')\n"
        "Path('generated.txt').write_text('generated\\n', encoding='utf-8')\n",
        encoding="utf-8",
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
    (repo / "lefthook.yml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    _commit_file(repo, "source.py", "before\n")
    _git(repo, "add", "lefthook.yml", "fixer.py")
    _git(repo, "commit", "-qm", "test: add formatter")
    (repo / "source.py").write_text("changed\n", encoding="utf-8")
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
        path.write_text(raw, encoding="utf-8")
    else:
        payload: dict[str, object] = {}
        if branch is not None:
            payload = {"branch": branch} if legacy else {"session": {"branch": branch}}
        path.write_text(json.dumps(payload), encoding="utf-8")
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
    merge_head.write_text(f"{head}\n", encoding="utf-8")

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
    message.write_text("fix: clean\n", encoding="utf-8")
    assert policy.check_commit_message(message) == 0

    message.write_text(f"fix: bad {chr(0x2013)} range\n", encoding="utf-8")
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
    (repo / "doc.md").write_text(f"bad {chr(0x2014)} text\n", encoding="utf-8")
    _git(repo, "add", "doc.md")
    (repo / "doc.md").write_text("working tree clean\n", encoding="utf-8")

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
    clean.write_text("clean\n", encoding="utf-8")
    bad.write_text("bad \N{EN DASH} text\n", encoding="utf-8")
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
    (repo / "doc.md").write_text(f"bad {chr(0x2014)} text\n", encoding="utf-8")
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
    recorder.write_text(
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "Path('observed.txt').write_text(\n"
        "    os.environ.get('GIT_INDEX_FILE', '') + '\\n' + '\\n'.join(sys.argv[1:]),\n"
        "    encoding='utf-8',\n"
        ")\n",
        encoding="utf-8",
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
    (repo / "lefthook.yml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    (repo / "default.md").write_text("base\n", encoding="utf-8")
    (repo / "alternate.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "lefthook.yml", "record_staged.py", "default.md", "alternate.md")
    _git(repo, "commit", "-qm", "test: add active-index probe")

    alternate_index = repo / ".git/alternate-index"
    shutil.copy2(repo / ".git/index", alternate_index)
    (repo / "default.md").write_text("default change\n", encoding="utf-8")
    _git(repo, "add", "default.md")

    _run_lefthook(
        repo,
        "run",
        "pre-commit",
        env={"GIT_INDEX_FILE": str(alternate_index)},
    )
    observed = repo / "observed.txt"
    assert not observed.exists()

    (repo / "alternate.md").write_text("alternate change\n", encoding="utf-8")
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
    path.write_text(f"vendor {chr(0x2014)} text\n", encoding="utf-8")
    _git(repo, "add", "-f", "node_modules/pkg/README.md")

    assert policy.check_staged_dashes(["node_modules/pkg/README.md"], repo) == 0


def test_action_pin_policy_checks_staged_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    workflow = repo / ".github/workflows/test.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text("steps:\n  - uses: actions/checkout@v4\n", encoding="utf-8")
    _git(repo, "add", ".github/workflows/test.yml")

    assert policy.check_staged_action_pins([".github/workflows/test.yml"], repo) == 1
    workflow.write_text(
        "steps:\n  - uses: actions/checkout@1234567890123456789012345678901234567890\n",
        encoding="utf-8",
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
    workflow.write_text("steps:\n  - uses: ./local-action\n", encoding="utf-8")
    _git(repo, "add", ".github/workflows/test.yml")

    assert policy.check_staged_action_pins([".github/workflows/test.yml"], repo) == 0
    assert policy.check_staged_action_pins(["../outside.yml"], repo) == 2


def test_security_suppression_policy_blocks_only_active_code(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    source = repo / "source.py"
    suppression_a = "# no" + "sec"
    suppression_b = "# no" + "sem" + "grep"
    source.write_text(f"value = 1  {suppression_a}\n", encoding="utf-8")

    assert policy.check_security_suppressions(["source.py"], repo) == 1
    source.write_text(f"value = 1  {suppression_b}\n", encoding="utf-8")
    assert policy.check_security_suppressions(["source.py"], repo) == 1
    source.write_text("value = 1\n", encoding="utf-8")
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
    (repo / ".vscode/mcp.json").write_text('{"version": 2}\n', encoding="utf-8")
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
    generated.write_text("generated\n", encoding="utf-8")
    (repo / unrelated_path).write_text("unrelated\n", encoding="utf-8")
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
    generated.write_text("{}\n", encoding="utf-8")
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
    (repo / session).write_text("{}\n", encoding="utf-8")
    episode = repo / ".agents/memory/episodes/episode-2026-07-19-session-1-test.json"
    episode.parent.mkdir(parents=True)
    episode.write_text("{}\n", encoding="utf-8")
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


def _copy_causal_updater(repo: Path) -> None:
    for relative in (
        ".claude/skills/memory/scripts/extract_session_episode.py",
        ".claude/skills/memory/scripts/update_causal_graph.py",
    ):
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT_ROOT / relative, destination)


def test_causal_graph_uses_staged_episode_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _copy_causal_updater(repo)
    episode = repo / ".agents/memory/episodes/episode-test.json"
    episode.parent.mkdir(parents=True)
    episode.write_text(json.dumps(_episode_payload("episode-staged", "staged")), encoding="utf-8")
    _git(repo, "add", ".agents/memory/episodes/episode-test.json")
    episode.write_text(json.dumps(_episode_payload("episode-working", "working")), encoding="utf-8")

    assert policy.update_causal_graph(repo) == 0

    graph = json.loads(
        (repo / ".agents/memory/causality/causal-graph.json").read_text(encoding="utf-8")
    )
    serialized = json.dumps(graph)
    assert "staged" in serialized
    assert "working" not in serialized
    assert (
        ".agents/memory/causality/causal-graph.json"
        in _git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    )


def test_causal_graph_restores_snapshot_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    graph = repo / ".agents/memory/causality/causal-graph.json"
    graph.parent.mkdir(parents=True)
    graph.write_text('{"original": true}\n', encoding="utf-8")
    episode = repo / ".agents/memory/episodes/episode-test.json"
    episode.parent.mkdir(parents=True)
    episode.write_text(
        json.dumps(_episode_payload("episode-test", "content")),
        encoding="utf-8",
    )
    _git(repo, "add", ".agents/memory/episodes/episode-test.json")
    monkeypatch.setattr(policy, "_run_causal_updater", lambda *_args: 1)

    assert policy.update_causal_graph(repo) == 0
    assert graph.read_text(encoding="utf-8") == '{"original": true}\n'


def test_causal_graph_aborts_when_snapshot_cannot_be_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    graph = repo / ".agents/memory/causality/causal-graph.json"
    graph.parent.mkdir(parents=True)
    graph.write_bytes(b'{"original": true}\n')
    episode = repo / ".agents/memory/episodes/episode-test.json"
    episode.parent.mkdir(parents=True)
    episode.write_text(
        json.dumps(_episode_payload("episode-test", "content")),
        encoding="utf-8",
    )
    _git(repo, "add", ".agents/memory/episodes/episode-test.json")
    original_read_bytes = Path.read_bytes

    def fail_graph_read(path: Path) -> bytes:
        if path == graph:
            raise OSError("snapshot read failed")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_graph_read)
    monkeypatch.setattr(
        policy,
        "_apply_causal_graph_updates",
        lambda *_args: pytest.fail("update must not run without a snapshot"),
    )

    assert policy.update_causal_graph(repo) == 2
    assert original_read_bytes(graph) == b'{"original": true}\n'


def test_causal_graph_noops_without_staged_episodes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    assert policy.update_causal_graph(repo) == 0


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
    source.write_text(f"value = 1  {'# no' + 'sec'}\n", encoding="utf-8")
    _git(repo, "add", "nested/source.py")
    _git(repo, "commit", "-qm", "test: pushed suppression")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    source.write_text("value = 1\n", encoding="utf-8")
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
    source.write_text("value = 2\n", encoding="utf-8")
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
    source.write_text("dangerous = True\n", encoding="utf-8")
    _git(repo, "add", "nested/source.py")
    _git(repo, "commit", "-qm", "test: pushed finding")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    source.write_text("dangerous = False\n", encoding="utf-8")

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
    (repo / "nested/source.py").write_text("dangerous = True\n", encoding="utf-8")
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
    (repo / "source.js").write_text(
        "const value = '$Format:a%eval(userInput);$';\n",
        encoding="utf-8",
    )
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
    (repo / "source.py").write_text("dangerous = True\n", encoding="utf-8")
    _git(repo, "add", "source.py")
    _git(repo, "commit", "-qm", "test: pushed finding")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    dangerous_blob = _git(repo, "rev-parse", f"{head}:source.py").stdout.strip()
    benign = repo / "benign.py"
    benign.write_text("dangerous = False\n", encoding="utf-8")
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
        target.write_text("payload.txt", encoding="utf-8")
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
    target.write_text("value = 1\n" + "# padding\n" * 110_000, encoding="utf-8")
    (tmp_path / ".semgrepignore").write_text(f"{target.name}\n", encoding="utf-8")
    config = tmp_path / "semgrep.yml"
    config.write_text(
        """
rules:
  - id: impossible-equality
    languages: [python]
    message: impossible
    severity: ERROR
    pattern: $X == $X
""".lstrip(),
        encoding="utf-8",
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
    target.write_text(
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
        encoding="utf-8",
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
    target.write_text(
        'runs:\n  using: composite\n  steps:\n    - shell: pwsh\n      run: Write-Host "safe"\n',
        encoding="utf-8",
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
    target.write_text(
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: |\n"
        "        Write-Host 'safe'\n"
        "    - shell: bash\n"
        "      run: echo safe\n",
        encoding="utf-8",
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


def test_semgrep_rejects_code_two_error_at_bash_step_in_mixed_shell_file(
    tmp_path: Path,
) -> None:
    target = tmp_path / "action.yml"
    bash_script = 'DATA=$(curl -fsSL https://example.com/install.sh)\neval "$DATA"'
    target.write_text(
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: Write-Host 'safe'\n"
        "    - shell: bash\n"
        "      run: |\n"
        "        DATA=$(curl -fsSL https://example.com/install.sh)\n"
        '        eval "$DATA"\n',
        encoding="utf-8",
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
    target.write_text(
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        f"      run: {script}\n"
        "    - shell: bash\n"
        f"      run: {script}\n",
        encoding="utf-8",
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
    target.write_text(
        "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n",
        encoding="utf-8",
    )
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
    target.write_text(
        'runs:\n  steps: [\n    - shell: pwsh\n      run: Write-Host "safe"\n',
        encoding="utf-8",
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

    assert result.returncode == 2


def test_semgrep_rejects_code_two_error_when_yaml_is_empty(tmp_path: Path) -> None:
    target = tmp_path / "action.yml"
    target.write_text("", encoding="utf-8")
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
    target.write_text(
        "shared: &shared\n"
        "  shell: pwsh\n"
        '  run: Write-Host "safe"\n'
        "runs:\n"
        "  steps:\n"
        "    - *shared\n",
        encoding="utf-8",
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
    target.write_text(
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: |\n"
        "        Write-Host 'first'\n"
        "        Write-Host 'second'\n",
        encoding="utf-8",
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
    target.write_text(
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: |\n" + "".join(f"        {line}\n" for line in lines),
        encoding="utf-8",
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
    target.write_text(
        "runs:\n"
        "  steps:\n"
        "    - shell: pwsh\n"
        "      run: Write-Host 'safe'\n"
        "    - shell: bash\n"
        "      run: echo safe\n",
        encoding="utf-8",
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
    target.write_text(
        "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n",
        encoding="utf-8",
    )
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
    target.write_text(
        "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n",
        encoding="utf-8",
    )
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
    target.write_text(content, encoding="utf-8")
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
    target.write_text(content, encoding="utf-8")
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
    target.write_text(content, encoding="utf-8")
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
    target.write_text(
        f"runs:\n  using: composite\n  steps:\n    - shell: {shell}\n      run: echo safe\n",
        encoding="utf-8",
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
    target.write_text(
        "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n",
        encoding="utf-8",
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


def test_semgrep_rejects_error_outside_requested_targets(tmp_path: Path) -> None:
    target = tmp_path / "action.yml"
    outside = tmp_path / "outside.yml"
    target.write_text("name: safe\n", encoding="utf-8")
    outside.write_text(
        "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n",
        encoding="utf-8",
    )
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
    target.write_text("name: safe\n", encoding="utf-8")
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
    target.write_text(
        "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n    - run: echo safe\n",
        encoding="utf-8",
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
    target.write_text(
        "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n",
        encoding="utf-8",
    )
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
    target.write_text(
        "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n",
        encoding="utf-8",
    )
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
    target.write_text(
        "runs:\n  steps:\n    - shell: pwsh\n      run: Write-Host 'safe'\n",
        encoding="utf-8",
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
    source.write_text("value: int = 1\n", encoding="utf-8")
    monkeypatch.setattr(policy, "_invoke_mypy", lambda *_args: _completed(1))

    assert policy.run_mypy(["deleted.py"], tmp_path) == 0
    assert policy.run_mypy(["source.py", "deleted.py"], tmp_path) == 1


def test_mypy_policy_rejects_unsafe_paths_and_symlinks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert policy.run_mypy(["../outside.py"], tmp_path) == 2

    source = tmp_path / "source.py"
    source.write_text("value: int = 1\n", encoding="utf-8")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == source or original_is_symlink(path),
    )
    assert policy.run_mypy(["source.py"], tmp_path) == 2


def _write_source(tmp_path: Path, name: str = "source.py") -> None:
    (tmp_path / name).write_text("value: int = 1\n", encoding="utf-8")


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
    (tmp_path / "pkg" / "mod.py").write_text("value: int = 1\n", encoding="utf-8")
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
    (repo / "mod.py").write_text(
        "line one\nline TWO changed\nline three\nline four\nline five\n",
        encoding="utf-8",
    )
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
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1))

    assert policy._read_index_blob(tmp_path, "missing") is None
    assert policy._read_head_blob(tmp_path, "missing") is None


def test_head_blob_reader_returns_content(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _commit_file(repo, "tracked", "content\n")

    assert policy._read_head_blob(repo, "tracked") == b"content\n"


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
    merge_head.write_text(f"{head}\n", encoding="utf-8")

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
    workflow.write_text("uses: ./local-action\n", encoding="utf-8")
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
    shell_script.write_text("echo blocked\n", encoding="utf-8")
    disguised_script.write_text("#!/usr/bin/env bash\necho blocked\n", encoding="utf-8")
    python_script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
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
    generated.write_text("agent\n", encoding="utf-8")

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
    outside.write_text("content\n", encoding="utf-8")
    monkeypatch.setattr(policy, "_generated_candidates", lambda *_args: [outside])
    assert policy.stage_generated("mcp", repo) == 2

    inside = repo / "inside"
    inside.write_text("content\n", encoding="utf-8")
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
    episode.write_text("{}\n", encoding="utf-8")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == episode or original_is_symlink(path),
    )
    assert policy._stage_episode("episode-link", tmp_path) == 2


def test_causal_graph_handles_git_and_symlink_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_staged_episode_paths", lambda *_args: None)
    assert policy.update_causal_graph(tmp_path) == 2

    monkeypatch.setattr(policy, "_staged_episode_paths", lambda *_args: ["episode"])
    graph = tmp_path / ".agents/memory/causality/causal-graph.json"
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == graph or original_is_symlink(path),
    )
    assert policy.update_causal_graph(tmp_path) == 2


def test_causal_graph_apply_propagates_prune_and_blob_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = tmp_path / "graph.json"
    monkeypatch.setattr(policy, "_prune_deleted_episodes", lambda *_args: 1)
    assert policy._apply_causal_graph_updates([], ["deleted"], graph, tmp_path) == 1

    monkeypatch.setattr(policy, "_prune_deleted_episodes", lambda *_args: 0)
    monkeypatch.setattr(policy, "_read_index_blob", lambda *_args: None)
    assert policy._apply_causal_graph_updates(["episode.json"], [], graph, tmp_path) == 1


def test_deleted_episode_pruning_uses_head_id_and_reports_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "_read_head_blob",
        lambda *_args: b'{"id": "episode-from-head"}',
    )
    assert policy._deleted_episode_id("episode-file.json", tmp_path) == "episode-from-head"

    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(1))
    assert (
        policy._prune_deleted_episodes(
            [".agents/memory/episodes/episode-file.json"],
            tmp_path / "graph.json",
            tmp_path,
        )
        == 1
    )


def test_deleted_episode_id_falls_back_to_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy, "_read_head_blob", lambda *_args: b"not json")
    assert policy._deleted_episode_id("episode-file.json", tmp_path) == "episode-file"
    monkeypatch.setattr(policy, "_read_head_blob", lambda *_args: None)
    assert policy._deleted_episode_id("episode-file.json", tmp_path) == "episode-file"


def test_causal_updater_reports_failure_and_restore_removes_new_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        policy,
        "_run_command",
        lambda *_args, **_kwargs: _completed(1, "out\n", "err\n"),
    )
    assert (
        policy._run_causal_updater(
            tmp_path / "episode.json",
            tmp_path / "graph.json",
            tmp_path,
        )
        == 1
    )

    graph = tmp_path / "graph.json"
    graph.write_text("new\n", encoding="utf-8")
    policy._restore_file(graph, None)
    assert not graph.exists()
    assert policy._stage_causal_graph(graph, tmp_path) == 0


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
        if args[:3] == ["show", "-s", "--format=%P"]:
            return _completed(0, "first-parent main-parent\n")
        return _completed(0)

    monkeypatch.setattr(policy, "_run_git", fake_git)

    assert policy._check_commit_limit(update, tmp_path) == 0


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
    assert captured["timeout"] == policy.TEST_SUITE_TIMEOUT_SECONDS
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
    assert policy.run_taste_advisory(["source.py"], tmp_path) == 0
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
    validator.write_text("pass\n", encoding="utf-8")
    memory = tmp_path / ".serena/memories/large.md"
    memory.parent.mkdir(parents=True)
    memory.write_text("large\n", encoding="utf-8")

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
    candidate.write_text("{}\n", encoding="utf-8")
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

    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(0, "clean\n"))
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
    destination.write_text("not a directory\n", encoding="utf-8")
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

    grafts.write_text("\n  # ignored comment\n", encoding="utf-8")
    assert policy._check_no_grafts(linked) == 0

    grafts.write_text(f"{head} {'0' * 40}\n", encoding="utf-8")
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
    absolute_merge_head.write_text("head\n", encoding="utf-8")
    monkeypatch.setattr(
        policy,
        "_run_git",
        lambda *_args: _completed(0, f"{absolute_merge_head}\n"),
    )
    assert policy._merge_in_progress(tmp_path)

    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: _completed(0))
    assert (
        policy._prune_deleted_episodes(
            [".agents/memory/episodes/episode-one.json"],
            tmp_path / "graph.json",
            tmp_path,
        )
        == 0
    )

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
    root_update = _push_update(range_spec="head")
    monkeypatch.setattr(policy, "_commit_paths", lambda *_args: ["root.py"])
    assert policy._changed_commit_paths(root_update, tmp_path) == ["root.py"]

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
    validator.write_text("pass\n", encoding="utf-8")
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
    good.write_text("good\n", encoding="utf-8")
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
        ("update-causal-graph", [], "update_causal_graph"),
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
    assert policy._staged_episode_paths(tmp_path, "D") is None


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
