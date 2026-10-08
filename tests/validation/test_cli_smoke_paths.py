"""Tests for the shared CLI smoke path list (REQ-047 AC10, issue #6069).

One module feeds the lefthook pre-push gates and the CI path filter. These
tests cover the matcher, the git diff wrapper, the CLI contract, and the drift
guard that fails when ``lefthook.yml`` globs differ from the module tuples.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.validation import cli_smoke_paths as paths

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHA_A = "a" * 40
_SHA_B = "b" * 40


def _should_run(changed: list[str]) -> bool:
    return bool(paths.matched_paths(changed))


def test_union_contains_every_hook_and_plugin_glob() -> None:
    assert set(paths.HOOK_E2E_GLOBS) <= set(paths.SMOKE_PATH_GLOBS)
    assert set(paths.PLUGIN_E2E_GLOBS) <= set(paths.SMOKE_PATH_GLOBS)


def test_union_has_no_duplicates() -> None:
    assert len(paths.SMOKE_PATH_GLOBS) == len(set(paths.SMOKE_PATH_GLOBS))


@pytest.mark.parametrize(
    "changed",
    [
        ".claude-plugin/marketplace.json",
        "src/claude/.claude-plugin/plugin.json",
        "src/claude/skills/build/SKILL.md",
        "src/copilot-cli/hooks/hooks.json",
        "src/copilot-cli/agents/analyst.agent.md",
        ".claude/skills/build/SKILL.md",
        ".claude/hooks/pre_tool_use.py",
        "tests/e2e/test_plugin_load_smoke.py",
        "tests/e2e/test_cli_hook_e2e.py",
        ".github/workflows/plugin-cli-smoke.yml",
        "scripts/validation/cli_smoke_paths.py",
        ".github/plugin/marketplace.json",
        "scripts/validation/assert_smoke_ran.py",
        "scripts/validation/assert_trusted_smoke_context.py",
        "scripts/ci/require_job_results.py",
        "tests/integration/test_e2e_install.py",
        "tests/e2e/copilot_hook_probe.py",
        "tests/e2e/smoke_skip_policy.py",
        "pyproject.toml",
        "uv.lock",
    ],
)
def test_smoke_paths_trigger_a_run(changed: str) -> None:
    assert _should_run([changed]) is True


@pytest.mark.parametrize(
    "changed",
    [
        "README.md",
        "docs/COST-GOVERNANCE.md",
        "scripts/ci/invoke_claude_review.py",
        ".github/workflows/pytest.yml",
        ".github/workflows/claude.yml",
        "tests/test_something.py",
    ],
)
def test_non_smoke_paths_do_not_trigger_a_run(changed: str) -> None:
    assert _should_run([changed]) is False


def test_empty_change_list_does_not_run() -> None:
    assert _should_run([]) is False


def test_one_matching_path_among_many_triggers_a_run() -> None:
    assert _should_run(["README.md", "src/claude/skills/x.md", "docs/a.md"]) is True


def test_changed_files_lists_the_three_dot_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="a.md\n\nsrc/claude/x.md\n", stderr="")

    monkeypatch.setattr(paths.subprocess, "run", fake_run)

    assert paths.changed_files(_SHA_A, _SHA_B, _REPO_ROOT) == ["a.md", "src/claude/x.md"]
    assert f"{_SHA_A}...{_SHA_B}" in seen[0]


def test_changed_files_raises_when_git_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="bad object")

    monkeypatch.setattr(paths.subprocess, "run", fake_run)

    with pytest.raises(paths.DiffError, match="bad object"):
        paths.changed_files(_SHA_A, _SHA_B, _REPO_ROOT)


@pytest.mark.parametrize("bad", ["", "main", "--output=x", "abc", "g" * 40, "A" * 40, "a" * 39])
def test_changed_files_rejects_a_non_sha_revision(bad: str) -> None:
    with pytest.raises(paths.DiffError, match="40-character"):
        paths.changed_files(bad, _SHA_B, _REPO_ROOT)
    with pytest.raises(paths.DiffError, match="40-character"):
        paths.changed_files(_SHA_A, bad, _REPO_ROOT)


def test_main_dispatch_writes_true_without_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(paths, "changed_files", lambda *_a: pytest.fail("git must not run"))

    assert paths.main(["--event-name", "workflow_dispatch"]) == paths.EXIT_OK
    assert out.read_text(encoding="utf-8") == "run=true\n"
    assert "run=true" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("changed", "expected"),
    [(["src/claude/skills/x.md"], "true"), (["README.md"], "false"), ([], "false")],
)
def test_main_writes_the_decision(
    changed: list[str],
    expected: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(paths, "changed_files", lambda *_a: changed)

    code = paths.main(["--event-name", "pull_request", "--base", _SHA_A, "--head", _SHA_B])

    assert code == paths.EXIT_OK
    assert out.read_text(encoding="utf-8") == f"run={expected}\n"


def test_main_fails_closed_when_the_diff_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))

    def boom(*_a: object) -> list[str]:
        raise paths.DiffError("bad object")

    monkeypatch.setattr(paths, "changed_files", boom)

    code = paths.main(["--event-name", "pull_request", "--base", _SHA_A, "--head", _SHA_B])

    assert code == paths.EXIT_LOGIC
    assert not out.exists()
    assert "bad object" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--event-name", "pull_request", "--base", _SHA_A],
        ["--event-name", "pull_request", "--head", _SHA_B],
        ["--event-name", "pull_request"],
        ["--event-name", "pull_request", "--base", "", "--head", ""],
        ["--event-name", "push", "--base", _SHA_A, "--head", _SHA_B],
        ["--event-name", "schedule"],
        [],
    ],
)
def test_main_rejects_missing_arguments_and_unknown_events(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        paths.main(argv)
    assert exc.value.code == paths.EXIT_USAGE


def test_main_prints_without_github_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(paths, "changed_files", lambda *_a: [])

    code = paths.main(["--event-name", "pull_request", "--base", _SHA_A, "--head", _SHA_B])

    assert code == paths.EXIT_OK
    assert "run=false" in capsys.readouterr().out


@pytest.mark.parametrize(
    "error",
    [OSError("git missing"), subprocess.TimeoutExpired(cmd="git", timeout=1)],
    ids=["oserror", "timeout"],
)
def test_changed_files_raises_when_git_does_not_run(
    error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(*_a: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        raise error

    monkeypatch.setattr(paths.subprocess, "run", fake_run)

    with pytest.raises(paths.DiffError, match=f"git diff did not run: {type(error).__name__}"):
        paths.changed_files(_SHA_A, _SHA_B, _REPO_ROOT)


def test_matched_paths_keeps_only_matches_in_order() -> None:
    changed = ["README.md", "src/claude/b.md", "docs/x.md", "src/claude/a.md"]
    assert paths.matched_paths(changed) == ["src/claude/b.md", "src/claude/a.md"]
    assert paths.matched_paths(["README.md"]) == []


def test_describe_matches_lists_all_at_the_cap() -> None:
    matched = [f"src/claude/{i}.md" for i in range(paths.MAX_LISTED_PATHS)]
    text = paths.describe_matches(matched)
    assert len(text.splitlines()) == paths.MAX_LISTED_PATHS
    assert "more" not in text


def test_describe_matches_caps_and_counts_the_rest() -> None:
    matched = [f"src/claude/{i}.md" for i in range(paths.MAX_LISTED_PATHS + 5)]
    lines = paths.describe_matches(matched).splitlines()
    assert len(lines) == paths.MAX_LISTED_PATHS + 1
    assert lines[-1] == "  and 5 more"


def test_main_prints_matched_paths_before_run_true(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(paths, "changed_files", lambda *_a: ["README.md", "src/claude/x.md"])

    code = paths.main(["--event-name", "pull_request", "--base", _SHA_A, "--head", _SHA_B])

    out = capsys.readouterr().out
    assert code == paths.EXIT_OK
    assert out.index("src/claude/x.md") < out.index("run=true")
    assert "README.md" not in out
    assert "1 changed path(s) match" in out


def test_main_prints_no_path_list_when_nothing_matches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(paths, "changed_files", lambda *_a: ["README.md"])

    paths.main(["--event-name", "pull_request", "--base", _SHA_A, "--head", _SHA_B])

    out = capsys.readouterr().out
    assert "match the smoke path filter" not in out
    assert "run=false" in out


def _find_named_jobs(node: object, job_name: str) -> list[dict]:
    """Collect every mapping named ``job_name`` anywhere in the lefthook tree."""
    found: list[dict] = []
    if isinstance(node, dict):
        if node.get("name") == job_name:
            found.append(node)
        for value in node.values():
            found.extend(_find_named_jobs(value, job_name))
    elif isinstance(node, list):
        for item in node:
            found.extend(_find_named_jobs(item, job_name))
    return found


def _lefthook_globs(job_name: str) -> tuple[str, ...]:
    config = yaml.safe_load((_REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))
    jobs = _find_named_jobs(config, job_name)
    assert len(jobs) == 1, f"expected one lefthook job named {job_name}, found {len(jobs)}"
    return tuple(jobs[0]["glob"])


def test_lefthook_hook_globs_equal_the_module_tuple() -> None:
    assert _lefthook_globs("hook-anchoring-e2e") == paths.HOOK_E2E_GLOBS


def test_lefthook_plugin_globs_equal_the_module_tuple() -> None:
    assert _lefthook_globs("plugin-load-e2e") == paths.PLUGIN_E2E_GLOBS


def test_drift_guard_fails_when_a_glob_is_removed() -> None:
    drifted = paths.PLUGIN_E2E_GLOBS[:-1]
    assert drifted != paths.PLUGIN_E2E_GLOBS
    assert _lefthook_globs("plugin-load-e2e") != drifted


_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "plugin-cli-smoke.yml"
_REPO_PATH_RE = re.compile(r"(?<![\w.-])((?:scripts|tests)/[\w./-]+\.py)")


def _workflow_invoked_repo_paths() -> set[str]:
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return {
        match
        for job in doc["jobs"].values()
        for step in job["steps"]
        for match in _REPO_PATH_RE.findall(str(step.get("run", "")))
    }


def test_workflow_invokes_repo_scripts_and_tests() -> None:
    """Guard: the extraction below finds the paths it is meant to check."""
    invoked = _workflow_invoked_repo_paths()

    assert "scripts/validation/assert_smoke_ran.py" in invoked
    assert "tests/e2e/test_plugin_load_smoke.py" in invoked
    assert "tests/integration/test_e2e_install.py" in invoked


def test_every_repo_path_the_workflow_runs_matches_the_smoke_globs() -> None:
    """A change to a script or test the smoke runs must trigger the smoke."""
    unmatched = sorted(p for p in _workflow_invoked_repo_paths() if not _should_run([p]))

    assert unmatched == []
