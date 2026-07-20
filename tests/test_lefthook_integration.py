from __future__ import annotations

import io
import json
import os
import runpy
import shutil
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from scripts.validation import git_hook_policy as policy

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEFTHOOK = shutil.which("lefthook")
SEMGREP = shutil.which("semgrep")
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
                    f'"{sys.executable}"',
                ).replace(
                    "uv run --frozen python",
                    f'"{sys.executable}"',
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
        "adr-change-advisory",
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
    pre_commit_names = [str(job["name"]) for job in _flatten_jobs(config["pre-commit"]["jobs"])]
    assert pre_commit_names.index("memory-token-update") < pre_commit_names.index("memory-size")
    assert pre_commit_names.index("memory-size") < pre_commit_names.index("memory-cross-reference")
    assert pre_commit_names.index("memory-cross-reference") < pre_commit_names.index(
        "memory-skill-format"
    )
    assert pre_commit_names.index("memory-skill-format") < pre_commit_names.index(
        "memory-sync-advisory"
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
        "adr-change-advisory",
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
            "run": f'"{sys.executable}" marker.py autofix',
            "skip": [{"run": 'test "$SKIP_AUTOFIX" = "1"'}],
        },
        {"name": "check", "run": f'"{sys.executable}" marker.py check'},
        {
            "name": "actionlint",
            "run": f'"{sys.executable}" marker.py actionlint',
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
    policy_text = (
        PROJECT_ROOT / "scripts/validation/git_hook_policy.py"
    ).read_text(encoding="utf-8")
    auto_retro_text = (
        PROJECT_ROOT / ".claude/hooks/Stop/invoke_auto_retrospective.py"
    ).read_text(encoding="utf-8")

    assert "scripts/hooks/pre-commit" not in config_text
    assert "scripts/hooks/pre-push" not in config_text
    assert "scripts/hooks/commit-msg" not in config_text
    assert "auto-retro-suppress" not in config_text
    assert "auto-retrospective.suppress" not in policy_text
    assert "auto-retrospective.suppress" not in auto_retro_text
    assert all(not path.exists() for path in HOOK_PAYLOADS)


def test_runtime_configuration_validates_with_pinned_lefthook() -> None:
    assert LEFTHOOK is not None

    version = subprocess.run(
        [LEFTHOOK, "version"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    validated = subprocess.run(
        [LEFTHOOK, "validate"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert version.stdout.splitlines()[0] == "2.1.10"
    assert validated.returncode == 0
    assert "All good" in validated.stdout


def test_install_resets_legacy_hooks_path(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _copy_runtime_config(repo)
    _git(repo, "config", "core.hooksPath", ".githooks")

    _run_lefthook(repo, "install", "--reset-hooks-path")

    _run_lefthook(repo, "check-install")
    hooks_path = _git(repo, "config", "--get", "core.hooksPath", check=False)
    assert hooks_path.returncode == 1
    assert os.access(repo / ".git/hooks/pre-push", os.X_OK)


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
                    "run": f'"{sys.executable}" marker.py markdown {{staged_files}}',
                    "glob": "**/*.md",
                },
                {
                    "name": "python-check",
                    "run": f'"{sys.executable}" marker.py python {{staged_files}}',
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
        {"name": "mypy", "run": f'"{sys.executable}" marker.py mypy', "glob": "**/*.py"},
        {
            "name": "suppression",
            "run": f'"{sys.executable}" marker.py suppression',
            "glob": "**/*.{py,ps1,psm1}",
            "use_stdin": True,
        },
        {
            "name": "security",
            "run": f'"{sys.executable}" marker.py security',
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


def test_piped_pre_push_jobs_each_receive_stdin(tmp_path: Path) -> None:
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
            "run": f'"{sys.executable}" marker.py {name}',
            "use_stdin": True,
        }
        for name in ("security", "suppressions", "identity")
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
    assert output.count(push_input) == 3
    assert output.startswith("security:")
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
                    "run": f'"{sys.executable}" marker.py {{push_files}}',
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
    assert "commit message contains" in blocked_message.stdout
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
                    "run": f'"{sys.executable}" fixer.py {{staged_files}}',
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


def test_commit_message_policy_handles_clean_dirty_and_missing(tmp_path: Path) -> None:
    message = tmp_path / "message"
    message.write_text("fix: clean\n", encoding="utf-8")
    assert policy.check_commit_message(message) == 0

    message.write_text(f"fix: bad {chr(0x2013)} range\n", encoding="utf-8")
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
    alternate_index = repo / ".git/alternate-index"
    shutil.copy2(repo / ".git/index", alternate_index)
    monkeypatch.setenv("GIT_INDEX_FILE", str(alternate_index))
    (repo / "doc.md").write_text(f"bad {chr(0x2014)} text\n", encoding="utf-8")
    _git(repo, "add", "doc.md")
    generated = repo / ".vscode/mcp.json"
    generated.parent.mkdir(parents=True)
    generated.write_text("{}\n", encoding="utf-8")

    assert policy.check_staged_dashes(["doc.md"], repo) == 1
    assert policy.stage_generated("mcp", repo) == 0
    staged = _git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    assert staged == [".vscode/mcp.json", "doc.md"]

    monkeypatch.delenv("GIT_INDEX_FILE")
    default_staged = _git(repo, "diff", "--cached", "--name-only").stdout
    assert default_staged == ""


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

    assert result == 0
    assert len(calls) == 1
    assert calls[0][-1] == ".claude/skills/real-skill"


def test_generated_staging_uses_the_named_allowlist(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / ".vscode").mkdir()
    (repo / ".factory").mkdir()
    (repo / ".vscode/mcp.json").write_text("{}\n", encoding="utf-8")
    (repo / ".factory/mcp.json").write_text("{}\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text("do not stage\n", encoding="utf-8")

    assert policy.stage_generated("mcp", repo) == 0

    staged = _git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    assert staged == [".factory/mcp.json", ".vscode/mcp.json"]
    assert _git(repo, "status", "--short", "unrelated.txt").stdout.startswith("??")


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
    relative = ".claude/skills/memory/scripts/update_causal_graph.py"
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
    missing = tmp_path / "missing"
    monkeypatch.setattr(policy, "_generated_candidates", lambda *_args: [missing])
    assert policy.stage_generated("mcp", tmp_path) == 0

    outside = tmp_path.parent / f"{tmp_path.name}-outside-file"
    outside.write_text("content\n", encoding="utf-8")
    monkeypatch.setattr(policy, "_generated_candidates", lambda *_args: [outside])
    assert policy.stage_generated("mcp", tmp_path) == 2

    inside = tmp_path / "inside"
    inside.write_text("content\n", encoding="utf-8")
    monkeypatch.setattr(policy, "_generated_candidates", lambda *_args: [inside])
    monkeypatch.setattr(policy, "_run_git", lambda *_args: _completed(1, stderr="failed\n"))
    assert policy.stage_generated("mcp", tmp_path) == 1


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
    for key in (
        "CLAUDE_PROJECT_DIR",
        "COPILOT_PLUGIN_ROOT",
        "GIT_INDEX_FILE",
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
    assert policy.run_adr_reminder(tmp_path) == 0
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
    results = iter([_completed(0), _completed(1)])
    monkeypatch.setattr(policy, "_run_command", lambda *_args, **_kwargs: next(results))
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
    monkeypatch.setattr(policy, "_read_commit_blob", lambda *_args: None)
    assert policy.check_pushed_suppressions(io.StringIO(ref_line), tmp_path) == 2

    monkeypatch.setattr(policy, "_read_commit_blob", lambda *_args: "clean\n")
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
        ("adr-reminder", [], "run_adr_reminder"),
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
