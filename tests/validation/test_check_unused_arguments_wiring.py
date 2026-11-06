"""Tests for how check_unused_arguments.py is wired: the real baseline, hooks, and workflow."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "validation"))

import check_unused_arguments
import pytest
import tomllib
import yaml
from check_unused_arguments import (
    BASELINE_RELPATH,
    REPO_ROOT,
    Comparison,
    compare,
    load_baseline,
    main,
    scan,
    validate_unused_arguments,
)

from tests.validation.unused_arguments_helpers import (
    BASELINE,
    BASELINE_LINE,
    SCRIPT,
    UNUSED_KEY,
    fake_run,
    make_repo,
)


def test_repository_findings_equal_the_committed_baseline() -> None:
    # Findings against the baseline only. Growth against a base ref is covered
    # by the growth tests, and a checkout may have no remote refs.
    assert compare(scan(REPO_ROOT).keys, load_baseline(BASELINE)) == Comparison([], [])


def test_repository_scan_reads_a_nonzero_number_of_files() -> None:
    result = scan(REPO_ROOT)

    assert result.scanned_files > 0
    assert result.keys


def test_main_defaults_baseline_to_the_repo_root(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(f"{UNUSED_KEY}\n", encoding="utf-8")

    assert main(["--repo-root", str(repo)]) == 0


def test_validate_unused_arguments_returns_true_when_baseline_matches(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(f"{UNUSED_KEY}\n", encoding="utf-8")

    assert validate_unused_arguments(repo) is True


def test_validate_unused_arguments_fails_closed_without_baseline(tmp_path: Path) -> None:
    assert validate_unused_arguments(make_repo(tmp_path)) is False


def test_validate_unused_arguments_fails_closed_without_ruff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(f"{UNUSED_KEY}\n", encoding="utf-8")
    hidden = SimpleNamespace(util=SimpleNamespace(find_spec=lambda _name: None))
    monkeypatch.setattr(check_unused_arguments, "importlib", hidden)
    monkeypatch.setattr(check_unused_arguments.shutil, "which", lambda _name: None)

    assert validate_unused_arguments(repo) is False


def test_validate_unused_arguments_fails_closed_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = make_repo(tmp_path)
    baseline = repo / BASELINE_RELPATH
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(f"{UNUSED_KEY}\n", encoding="utf-8")
    expired = subprocess.TimeoutExpired(cmd="ruff", timeout=1)
    monkeypatch.setattr(
        check_unused_arguments.subprocess, "run", fake_run(subprocess.run, ruff=expired)
    )

    assert validate_unused_arguments(repo) is False


def test_pre_pr_sequence_runs_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    import pre_pr_sequence

    calls: list[Path] = []

    def fake(root: Path) -> bool:
        calls.append(root)
        return False

    monkeypatch.setattr(pre_pr_sequence, "validate_unused_arguments", fake)
    gates = [g for g in pre_pr_sequence._SEQUENCE if g.name == "Unused Argument Detection"]

    assert len(gates) == 1
    assert gates[0].run(REPO_ROOT, argparse.Namespace()) is False
    assert calls == [REPO_ROOT]


def test_baseline_is_sorted_so_removals_diff_cleanly() -> None:
    keys = load_baseline(BASELINE)

    assert keys == sorted(keys)


def test_baseline_has_one_line_per_key_so_parallel_deletions_cannot_leave_a_stale_line() -> None:
    # Two pull requests that each fix one of two findings under a repeated line
    # each delete one copy of it. git merges that cleanly into a single stale
    # line that fails the gate on the base branch. Owner-qualified keys keep
    # every line distinct, so each pull request deletes a different line.
    keys = load_baseline(BASELINE)

    assert len(set(keys)) == len(keys)


def test_baseline_entries_are_path_code_argument_and_owner_with_no_line_number() -> None:
    bad = [key for key in load_baseline(BASELINE) if not BASELINE_LINE.match(key)]

    assert bad == []


def test_repo_wide_ruff_select_does_not_include_arg() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert not [rule for rule in config["tool"]["ruff"]["lint"]["select"] if "ARG".startswith(rule)]


def test_vulture_is_not_a_dependency_or_config() -> None:
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    extras = config["project"]["optional-dependencies"]["dev"]

    assert "vulture" not in config["tool"]
    assert not [dep for dep in extras if dep.lower().startswith("vulture")]
    assert "vulture" not in (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")


def _run_commands(node: object) -> list[str]:
    if isinstance(node, dict):
        found = [node["run"]] if isinstance(node.get("run"), str) else []
        return found + [cmd for value in node.values() for cmd in _run_commands(value)]
    if isinstance(node, list):
        return [cmd for item in node for cmd in _run_commands(item)]
    return []


def test_pre_push_hook_runs_the_gate() -> None:
    lefthook = yaml.safe_load((REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    assert any(SCRIPT in cmd for cmd in _run_commands(lefthook["pre-push"]))


def test_pytest_workflow_runs_the_gate_in_the_ratchet_guard_against_the_fetched_base() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pytest.yml").read_text(encoding="utf-8")
    )
    commands = [
        cmd for cmd in _run_commands(workflow["jobs"]["count-ratchet-guard"]) if SCRIPT in cmd
    ]

    assert len(commands) == 1
    assert "--base-ref FETCH_HEAD" in commands[0]
    assert not [
        job
        for name, job in workflow["jobs"].items()
        if name != "count-ratchet-guard" and any(SCRIPT in cmd for cmd in _run_commands(job))
    ]


def test_the_ratchet_guard_has_no_condition_that_could_skip_the_gate() -> None:
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pytest.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["count-ratchet-guard"]

    assert "if" not in job
    assert "needs" not in job
    assert "count-ratchet-guard" in workflow["jobs"]["test-result"]["needs"]


def test_baseline_sits_next_to_the_script() -> None:
    assert (
        BASELINE
        == Path(check_unused_arguments.__file__).resolve().parent / "unused_arguments_baseline.txt"
    )


def test_total_deadline_is_below_the_lefthook_job_cap() -> None:
    lefthook = yaml.safe_load((REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    jobs = [
        job
        for job in _walk_jobs(lefthook["pre-push"])
        if job.get("name") == "python-unused-arguments"
    ]

    assert len(jobs) == 1
    cap = float(str(jobs[0]["timeout"]).removesuffix("s"))
    assert check_unused_arguments.Deadline().seconds < cap


def _walk_jobs(node: object) -> list[dict[str, object]]:
    if isinstance(node, dict):
        found = [node] if "name" in node and "run" in node else []
        return found + [job for value in node.values() for job in _walk_jobs(value)]
    if isinstance(node, list):
        return [job for item in node for job in _walk_jobs(item)]
    return []
