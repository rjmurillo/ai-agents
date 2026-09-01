"""Tests for scripts/validation/run_workflow_local_test.py.

Covers the belt-and-suspenders gate: stage ordering and short-circuit,
tool/Docker gaps -> exit 3, bypass env, --no-full, and CLI exit codes. All
external commands (actionlint, gh act, docker) are mocked; no Docker required.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VALIDATION_DIR = str(REPO_ROOT / "scripts" / "validation")
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

import run_workflow_local_test as w

WF = ".github/workflows/x.yml"


@pytest.fixture
def all_tools(monkeypatch):
    """Pretend actionlint, gh, the gh act extension, and Docker are available."""
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_gh_act_available", lambda: True)
    monkeypatch.setattr(w, "_docker_ready", lambda: True)
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)


def _ok(stage):
    return w.StageResult(stage, True)


def _fail(stage):
    return w.StageResult(stage, False, "boom")


# --- bypass / empty ------------------------------------------------------


def test_bypass_env_short_circuits(monkeypatch, tmp_path):
    monkeypatch.setenv(w._BYPASS_ENV, "true")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert r.bypassed is True


def test_bypass_env_accepts_one(monkeypatch, tmp_path):
    # Matches the repo convention: boolean env flags accept "1" and "true".
    monkeypatch.setenv(w._BYPASS_ENV, "1")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert r.bypassed is True


def test_no_files_passes(all_tools, tmp_path):
    r = w.run_local_test([], tmp_path)
    assert r.exit_code == 0
    assert r.stages == []


# --- path containment (CWE-22) + workflow filtering ----------------------


def test_path_traversal_is_exit_2(all_tools, tmp_path):
    # A path that escapes repo_root must be rejected as a config error, not run.
    r = w.run_local_test(["../../etc/passwd"], tmp_path)
    assert r.exit_code == 2
    assert "escapes repository root" in r.note


def test_absolute_path_outside_repo_is_exit_2(all_tools, tmp_path):
    r = w.run_local_test(["/etc/passwd"], tmp_path)
    assert r.exit_code == 2
    assert "escapes repository root" in r.note


def test_missing_repo_root_is_exit_2(all_tools, tmp_path):
    # A direct caller passing a non-existent repo_root is a config error (2),
    # not a stage failure (1). Matches main()'s repo-root check.
    missing = tmp_path / "does" / "not" / "exist"
    r = w.run_local_test([WF], missing)
    assert r.exit_code == 2
    assert "repo root not found" in r.note


def test_non_workflow_paths_are_filtered_out(all_tools, monkeypatch, tmp_path):
    # Custom actions and unrelated YAML never run under gh act; they drop out
    # and, with nothing left to test, the run is a clean no-op.
    r = w.run_local_test([".github/actions/foo/action.yml", "README.md"], tmp_path)
    assert r.exit_code == 0
    assert r.note == "no workflow files to test"


def test_select_workflow_files_keeps_only_workflows(tmp_path):
    selected, err = w._select_workflow_files(
        [
            ".github/workflows/ci.yml",
            ".github/workflows/release.yaml",
            ".github/actions/build/action.yml",
            "docs/x.yml",
            "",
        ],
        tmp_path,
    )
    assert err is None
    assert selected == [
        ".github/workflows/ci.yml",
        ".github/workflows/release.yaml",
    ]


# --- tool / docker gaps --------------------------------------------------


def test_actionlint_missing_is_exit_3(monkeypatch, tmp_path):
    # On a normal (non-container) box a missing actionlint is a real tool gap and
    # blocks at exit 3. The container-downgrade seam is pinned off so the test is
    # deterministic regardless of the host env (Issue #3064).
    monkeypatch.setattr(w, "_have", lambda tool: tool != "actionlint")
    monkeypatch.setattr(w, "_is_remote_container", lambda: False)
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "actionlint" in r.note


def test_actionlint_missing_in_remote_container_downgrades_to_warning(monkeypatch, tmp_path):
    # actionlint unavailable inside a remote container (CLAUDECODE set, no CI)
    # must not block the push: it degrades to a logged warning (exit 0), the same
    # way the gh/gh act gap already does. Issue #3064 extends PR #2548's degrade
    # to the actionlint gap.
    monkeypatch.setattr(w, "_have", lambda tool: tool != "actionlint")
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert r.degraded is True
    assert "actionlint" in r.note


def test_actionlint_missing_in_ci_still_blocks_even_with_container_signal(monkeypatch, tmp_path):
    # CI provisions actionlint, so a missing binary is a real failure. The CI
    # marker overrides the container signal via the real _is_remote_container():
    # hard exit 3, never degraded (Issue #3064).
    monkeypatch.setattr(w, "_have", lambda tool: tool != "actionlint")
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CI", "true")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert r.degraded is False
    assert "actionlint" in r.note


def test_gh_missing_is_exit_3(monkeypatch, tmp_path):
    # On a normal (non-container) box, a missing gh CLI is a real tool gap and
    # blocks at exit 3. The container-downgrade seam is pinned off so the test
    # is deterministic regardless of the host env (Issue #2548, item 3).
    monkeypatch.setattr(w, "_have", lambda tool: tool == "actionlint")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_is_remote_container", lambda: False)
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "gh" in r.note


def test_gh_act_extension_missing_is_exit_3(monkeypatch, tmp_path):
    # gh is present but the act extension is not -> exit 3 before dry-run on a
    # normal box. The container-downgrade seam is pinned off (Issue #2548).
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_gh_act_available", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_is_remote_container", lambda: False)
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "gh act extension" in r.note


def test_gh_act_missing_in_remote_container_downgrades_to_warning(monkeypatch, tmp_path):
    # gh act unavailable inside a remote container (CLAUDECODE set, no CI) must
    # not block the push: it degrades to a logged warning (exit 0). Item 3 of
    # issue #2548.
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_gh_act_available", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert r.degraded is True
    assert "gh act" in r.note


def test_gh_act_missing_in_ci_still_blocks_even_with_container_signal(monkeypatch, tmp_path):
    # In CI, gh act is provisioned, so a missing extension is a real failure.
    # The CI marker overrides the container signal: hard exit 3, never degraded.
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_gh_act_available", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CI", "true")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert r.degraded is False


def test_gh_missing_in_remote_container_downgrades_to_warning(monkeypatch, tmp_path):
    # The downgrade also covers a missing gh CLI: the container cannot install
    # the act extension without an authenticated gh, so a warning is correct.
    monkeypatch.setattr(w, "_have", lambda tool: tool == "actionlint")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert r.degraded is True


def test_gh_act_missing_without_container_signal_still_exit_3(monkeypatch, tmp_path):
    # No container signal and no CI: a local dev box missing the extension is a
    # real tool gap and must keep blocking at exit 3.
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_gh_act_available", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_is_remote_container", lambda: False)
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    monkeypatch.delenv("CI", raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert r.degraded is False


def test_plain_docker_marker_does_not_downgrade(monkeypatch, tmp_path):
    """A local Docker/devcontainer environment should still report a tool gap."""
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_gh_act_available", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w.Path, "exists", lambda self: str(self) == "/.dockerenv")
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CODESPACES", raising=False)

    r = w.run_local_test([WF], tmp_path)

    assert r.exit_code == 3
    assert r.degraded is False


def test_docker_down_is_exit_3_for_full(all_tools, monkeypatch, tmp_path):
    # Dry-run passes (no daemon needed); the full stage needs Docker -> exit 3.
    # docker is installed but the daemon is down -> "not running" note. The
    # container-downgrade seam is pinned off so the exit-3 assertion is
    # deterministic regardless of the host env (Issue #3064).
    monkeypatch.setattr(w, "_docker_ready", lambda: False)
    monkeypatch.setattr(w, "_is_remote_container", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "daemon is not running" in r.note


def test_docker_not_installed_is_exit_3_with_distinct_note(monkeypatch, tmp_path):
    # docker binary absent -> "not installed" note, distinct from daemon-down.
    # The container-downgrade seam is pinned off (Issue #3064).
    monkeypatch.setattr(w, "_have", lambda tool: tool != "docker")
    monkeypatch.setattr(w, "_gh_act_available", lambda: True)
    monkeypatch.setattr(w, "_docker_ready", lambda: False)
    monkeypatch.setattr(w, "_is_remote_container", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "Docker is not installed" in r.note


def test_docker_missing_in_remote_container_downgrades_to_warning(all_tools, monkeypatch, tmp_path):
    # Docker unavailable inside a remote container (CLAUDECODE set, no CI) must
    # not block the push: actionlint and the dry-run pass, and the full stage's
    # Docker gap degrades to a logged warning (exit 0). Issue #3064.
    monkeypatch.setattr(w, "_docker_ready", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert r.degraded is True
    assert "Docker" in r.note


def test_docker_missing_in_ci_still_blocks_even_with_container_signal(
    all_tools, monkeypatch, tmp_path
):
    # CI provisions Docker, so a down daemon is a real failure even with a
    # container env marker present. The CI marker overrides the container signal
    # via the real _is_remote_container(): hard exit 3, never degraded (#3064).
    monkeypatch.setattr(w, "_docker_ready", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CI", "true")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert r.degraded is False
    assert "Docker" in r.note


def test_no_full_does_not_require_docker(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_docker_ready", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    r = w.run_local_test([WF], tmp_path, full=False)
    assert r.exit_code == 0


# --- stage ordering + short-circuit --------------------------------------


def test_actionlint_failure_blocks_and_skips_act(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _fail("actionlint"))
    called = {"act": False}

    def _act(f, r):
        called["act"] = True
        return _ok("gh act -n")

    monkeypatch.setattr(w, "_act_dryrun_stage", _act)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 1
    assert called["act"] is False  # short-circuit before act


def test_dryrun_failure_blocks_and_skips_full(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _fail("gh act -n"))
    called = {"full": False}

    def _full(f, r):
        called["full"] = True
        return _ok("gh act (full)")

    monkeypatch.setattr(w, "_act_full_stage", _full)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 1
    assert called["full"] is False


def test_full_failure_blocks(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _fail("gh act (full)"))
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 1
    assert [s.stage for s in r.stages] == ["actionlint", "gh act -n", "gh act (full)"]


def test_all_stages_pass(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert len(r.stages) == 3


def test_act_true_runs_pytest_matrix_locally(all_tools, monkeypatch, tmp_path):
    workflow_name = ".github/workflows/pytest.yml"
    workflow = tmp_path / workflow_name
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        """jobs:
  test:
    strategy:
      matrix:
        include:
          - partition: bulk
          - partition: safe-push
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ACT", "true")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(
        w,
        "_act_dryrun_stage",
        lambda *_: pytest.fail("ACT fallback must skip gh act dry-run"),
    )
    calls = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        assert env is not None
        assert env["COPILOT_PLUGIN_ROOT"] == str(tmp_path / ".claude")
        assert env["CLAUDE_PLUGIN_ROOT"] == str(tmp_path / ".claude")
        assert env["GITHUB_EVENT_NAME"] == "merge_group"
        assert Path(env["PYTEST_NON_TMP_ROOT"]).parent == Path(env["COVERAGE_FILE"]).parent
        normalized = [*cmd]
        for position, token in enumerate(normalized):
            if token.startswith("--junitxml="):
                relative = token.removeprefix("--junitxml=")
                normalized[position] = f"--junitxml={Path(relative).name}"
                break
        calls.append(
            (
                normalized,
                timeout,
                cwd,
                env["PYTHONDONTWRITEBYTECODE"],
                env.get("ACT"),
                Path(env["COVERAGE_FILE"]).name,
                Path(env["PYTEST_NON_TMP_ROOT"]).name,
            )
        )
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)

    report = w.run_local_test([workflow_name], tmp_path)

    assert report.exit_code == 0
    assert [stage.stage for stage in report.stages] == [
        "actionlint",
        "gh act (local-fallback)",
    ]
    assert calls == [
        (
            [
                "uv",
                "run",
                "--frozen",
                "python",
                "scripts/ci/run_pytest_selected.py",
                "--partition",
                "bulk",
                "--cov",
                "--cov-report=",
                "--junitxml=pytest-0.xml",
            ],
            600,
            tmp_path,
            "1",
            None,
            ".coverage.0",
            "pytest-0",
        ),
        (
            [
                "uv",
                "run",
                "--frozen",
                "python",
                "scripts/ci/run_pytest_selected.py",
                "--partition",
                "safe-push",
                "--cov",
                "--cov-report=",
                "--junitxml=pytest-1.xml",
            ],
            600,
            tmp_path,
            "1",
            None,
            ".coverage.1",
            "pytest-1",
        ),
    ]


def test_act_true_rejects_non_pytest_workflow(all_tools, monkeypatch, tmp_path):
    monkeypatch.setenv("ACT", "true")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(
        w,
        "_local_pytest_stage",
        lambda *_: pytest.fail("non-pytest workflow must not use pytest fallback"),
    )
    _write_wf_secrets(tmp_path, WF)

    report = w.run_local_test([WF], tmp_path)

    assert report.exit_code == 3
    assert "nested act execution supports only the pytest workflow" in report.note


def test_act_true_rejects_mixed_workflow_batch(all_tools, monkeypatch, tmp_path):
    pytest_workflow = ".github/workflows/pytest.yml"
    monkeypatch.setenv("ACT", "true")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(
        w,
        "_local_pytest_stage",
        lambda *_: pytest.fail("mixed workflow batch must not use pytest fallback"),
    )
    _write_wf_secrets(tmp_path, pytest_workflow)
    _write_wf_secrets(tmp_path, WF)

    report = w.run_local_test([pytest_workflow, WF], tmp_path)

    assert report.exit_code == 3
    assert "nested act execution supports only the pytest workflow" in report.note


def test_pytest_workflow_uses_local_fallback_without_act(
    all_tools, monkeypatch, tmp_path
):
    workflow_name = ".github/workflows/pytest.yml"
    workflow = tmp_path / workflow_name
    workflow.parent.mkdir(parents=True)
    workflow.write_text("jobs: {}\n", encoding="utf-8")
    monkeypatch.delenv("ACT", raising=False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(
        w,
        "_act_dryrun_stage",
        lambda *_: pytest.fail("pytest workflow must skip gh act dry-run"),
    )
    monkeypatch.setattr(
        w,
        "_local_pytest_stage",
        lambda f, r: _ok("gh act (local-fallback)"),
    )

    report = w.run_local_test([workflow_name], tmp_path)

    assert report.exit_code == 0
    assert [stage.stage for stage in report.stages] == [
        "actionlint",
        "gh act (local-fallback)",
    ]


def test_no_full_skips_execution_stage(all_tools, monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    called = {"full": False}

    def _full(f, r):
        called["full"] = True
        return _ok("gh act (full)")

    monkeypatch.setattr(w, "_act_full_stage", _full)
    r = w.run_local_test([WF], tmp_path, full=False)
    assert r.exit_code == 0
    assert called["full"] is False
    assert [s.stage for s in r.stages] == ["actionlint", "gh act -n"]


# --- secret-gap detection (#2841) ----------------------------------------


def _write_wf_secrets(tmp_path, rel, *secret_names):
    """Create a workflow file under tmp_path referencing the given secrets."""
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["name: x", "on: push", "jobs:", "  j:", "    runs-on: ubuntu-latest", "    steps:"]
    for name in secret_names:
        lines.append(f"      - run: echo ${{{{ secrets.{name} }}}}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_referenced_secrets_finds_names(tmp_path):
    path = _write_wf_secrets(tmp_path, WF, "BOT_PAT", "COPILOT_TOKEN")
    assert w._referenced_secrets(path) == {"BOT_PAT", "COPILOT_TOKEN"}


def test_referenced_secrets_normalizes_names(tmp_path):
    path = _write_wf_secrets(tmp_path, WF, "bot_pat", "Copilot_Token")
    assert w._referenced_secrets(path) == {"BOT_PAT", "COPILOT_TOKEN"}


def test_referenced_secrets_unreadable_file_is_empty(tmp_path):
    assert w._referenced_secrets(tmp_path / "does-not-exist.yml") == set()


def test_act_secret_file_keys_parses_dotenv(tmp_path):
    (tmp_path / ".secrets").write_text(
        "# comment\n\nBOT_PAT=abc\nOTHER = def\nBAD_LINE\n", encoding="utf-8"
    )
    assert w._act_secret_file_keys(tmp_path) == {"BOT_PAT", "OTHER"}


def test_act_secret_file_keys_ignores_empty_values(tmp_path):
    (tmp_path / ".secrets").write_text(
        "BOT_PAT=\nOTHER =   \nQUOTED=\"\"\nSINGLE=''\nPRESENT = token\n",
        encoding="utf-8",
    )
    assert w._act_secret_file_keys(tmp_path) == {"PRESENT"}


def test_act_secret_file_keys_missing_file_is_empty(tmp_path):
    assert w._act_secret_file_keys(tmp_path) == set()


def test_missing_secrets_respects_available(tmp_path):
    path = _write_wf_secrets(tmp_path, WF, "PRESENT", "ABSENT")
    assert w._missing_secrets(path, {"PRESENT"}) == ["ABSENT"]
    assert w._missing_secrets(path, {"PRESENT", "ABSENT"}) == []


def test_empty_env_secret_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setenv("BOT_PAT_2841", "   ")
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 4
    assert r.secret_skipped is True
    assert "reference secrets absent" in r.note


def test_quoted_empty_env_secret_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setenv("BOT_PAT_2841", '""')
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 4
    assert r.secret_skipped is True


def test_all_workflows_secret_blocked_is_exit_4(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")

    report = w.run_local_test([WF], tmp_path)

    assert report.exit_code == 4
    assert report.secret_skipped is True
    assert "BOT_PAT_2841" not in report.note
    assert WF not in report.note
    assert "reference secrets absent" in report.note
    assert [stage.stage for stage in report.stages] == ["actionlint"]


def test_all_secret_blocked_lints_before_skipping(monkeypatch, tmp_path):
    # actionlint must lint the secret-blocked file, so a syntax error in a
    # workflow that cannot run under act is still caught (exit 1), not skipped.
    monkeypatch.setattr(w, "_have", lambda tool: True)
    seen = {}

    def _capture(f, r):
        seen["f"] = list(f)
        return w.StageResult("actionlint", False, "syntax error")

    monkeypatch.setattr(w, "_actionlint_stage", _capture)
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 1
    assert seen["f"] == [WF]


def test_all_secret_blocked_actionlint_missing_is_exit_3(monkeypatch, tmp_path):
    # actionlint is required for every changed workflow; its absence blocks
    # (exit 3) even when every workflow is secret-blocked. Pin the
    # container-downgrade seam off so the exit-3 assertion holds regardless of
    # the host env (Issue #3064).
    monkeypatch.setattr(w, "_have", lambda tool: tool != "actionlint")
    monkeypatch.setattr(w, "_is_remote_container", lambda: False)
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "actionlint" in r.note


def test_secret_present_in_env_is_runnable(all_tools, monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_PAT_2841", "token-value")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert len(r.stages) == 3


def test_secret_present_in_dotsecrets_is_runnable(all_tools, monkeypatch, tmp_path):
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    (tmp_path / ".secrets").write_text("BOT_PAT_2841=token\n", encoding="utf-8")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert len(r.stages) == 3


def test_secret_present_with_different_case_is_runnable(all_tools, monkeypatch, tmp_path):
    monkeypatch.setenv("bot_pat_2841", "token-value")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert len(r.stages) == 3


def test_github_token_is_runnable_without_local_secret(all_tools, monkeypatch, tmp_path):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))
    _write_wf_secrets(tmp_path, WF, "GITHUB_TOKEN")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert len(r.stages) == 3


def test_secret_in_comment_is_not_blocking(all_tools, monkeypatch, tmp_path):
    # secrets.FOO outside a ${{ }} expression (comment/plain string) is not a
    # real reference and must not mark the workflow secret-blocked (#2841 review).
    monkeypatch.delenv("ABSENT_SECRET", raising=False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))
    path = tmp_path / WF
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "name: x\n# mentions secrets.ABSENT_SECRET in a comment\n"
        "on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n"
        '      - run: echo "the literal text secrets.ABSENT_SECRET is fine"\n',
        encoding="utf-8",
    )
    assert w._referenced_secrets(path) == set()
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert len(r.stages) == 3


def test_mixed_runs_only_runnable_and_notes_skip(all_tools, monkeypatch, tmp_path):
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    clean = ".github/workflows/clean.yml"
    blocked = ".github/workflows/blocked.yml"
    _write_wf_secrets(tmp_path, clean)
    _write_wf_secrets(tmp_path, blocked, "BOT_PAT_2841")
    seen = {}
    monkeypatch.setattr(
        w, "_actionlint_stage", lambda f, r: seen.__setitem__("lint", list(f)) or _ok("actionlint")
    )
    monkeypatch.setattr(
        w, "_act_dryrun_stage", lambda f, r: seen.__setitem__("act", list(f)) or _ok("gh act -n")
    )
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))

    report = w.run_local_test([blocked, clean], tmp_path)

    assert report.exit_code == 0
    assert report.secret_skipped is True
    assert seen["lint"] == [blocked, clean]
    assert seen["act"] == [clean]
    assert "BOT_PAT_2841" not in report.note
    assert blocked not in report.note
    assert "skipped workflows with secrets absent locally" in report.note


def test_mixed_skip_note_visible_in_text_format(all_tools, monkeypatch, tmp_path):
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    clean = ".github/workflows/clean.yml"
    blocked = ".github/workflows/blocked.yml"
    _write_wf_secrets(tmp_path, clean)
    _write_wf_secrets(tmp_path, blocked, "BOT_PAT_2841")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))

    text = w._format_text(w.run_local_test([blocked, clean], tmp_path))

    assert "OK" in text
    assert "skipped workflows with secrets absent locally" in text
    assert "BOT_PAT_2841" not in text
    assert blocked not in text


def test_format_json_exposes_secret_skipped(all_tools, monkeypatch, tmp_path):
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    clean = ".github/workflows/clean.yml"
    blocked = ".github/workflows/blocked.yml"
    _write_wf_secrets(tmp_path, clean)
    _write_wf_secrets(tmp_path, blocked, "BOT_PAT_2841")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))

    payload = json.loads(w._format_json(w.run_local_test([blocked, clean], tmp_path)))

    assert payload["secret_skipped"] is True
    assert "missing_secret_names" not in payload
    assert payload["exit_code"] == 0
    assert "BOT_PAT_2841" not in json.dumps(payload)
    assert blocked not in json.dumps(payload)


def test_format_json_omits_missing_secret_names_for_exit_4(
    all_tools, monkeypatch, tmp_path
):
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))

    payload = json.loads(w._format_json(w.run_local_test([WF], tmp_path)))

    assert payload["secret_skipped"] is True
    assert "missing_secret_names" not in payload
    assert "BOT_PAT_2841" not in json.dumps(payload)
    assert WF not in json.dumps(payload)


def test_exit_4_text_format_omits_secret_name():
    report = w.Report(
        exit_code=4,
        note="unrunnable-locally: changed workflow(s) reference secrets absent.",
    )

    text = w._format_text(report)

    assert "SKIPPED" in text
    assert "reference secrets absent" in text
    assert "BOT_PAT_2841" not in text


def test_cli_returns_4_for_secret_blocked(all_tools, monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    rc = w.main(["--files", WF, "--repo-root", str(tmp_path)])
    assert rc == 4
    assert "SKIPPED" in capsys.readouterr().out


# --- stage internals (subprocess mocked) ---------------------------------


def test_actionlint_stage_passes_files(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        seen["cmd"] = cmd
        seen["env"] = env
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._actionlint_stage([WF, "y.yml"], tmp_path)
    assert res.ok is True
    assert seen["cmd"] == ["actionlint", WF, "y.yml"]


def test_actionlint_stage_applies_shellcheck_severity_floor(monkeypatch, tmp_path):
    """The actionlint stage raises the shellcheck floor to warning (#2374)."""
    seen = {}

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        seen["env"] = env
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    w._actionlint_stage([WF], tmp_path)
    assert seen["env"] is not None
    assert "--severity=warning" in seen["env"]["SHELLCHECK_OPTS"]


def test_shellcheck_env_preserves_existing_opts(monkeypatch):
    monkeypatch.setenv("SHELLCHECK_OPTS", "--exclude=SC1091")
    opts = w._shellcheck_env()["SHELLCHECK_OPTS"]
    assert "--exclude=SC1091" in opts
    assert "--severity=warning" in opts


def test_act_dryrun_stage_runs_each_file_and_stops_on_failure(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(cmd[-1])
        return (1, "", "bad") if cmd[-1] == "a.yml" else (0, "", "")

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_dryrun_stage(["a.yml", "b.yml"], tmp_path)
    assert res.ok is False
    assert calls == ["a.yml"]  # stopped after first failure


def test_act_stage_runs_multi_job_workflow_jobs_serially(monkeypatch, tmp_path):
    wf = tmp_path / WF
    wf.parent.mkdir(parents=True)
    wf.write_text(
        "\n".join(
            [
                "name: x",
                "on: push",
                "jobs:",
                "  first:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - run: echo first",
                "  second:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - run: echo second",
            ]
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(cmd)
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_full_stage([WF], tmp_path)

    assert res.ok is True
    assert calls == [
        ["gh", "act", "-j", "first", "-W", WF],
        ["gh", "act", "-j", "second", "-W", WF],
    ]


def test_act_contention_retry_is_visible(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(cmd)
        if len(calls) == 1:
            return 1, "", "failed to create container"
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_full_stage([WF], tmp_path)

    assert res.ok is True
    assert len(calls) == 2
    assert "retried once after act contention" in res.detail


# --- linked-worktree GIT_DIR handling (#2344) ----------------------------


def test_read_worktree_gitdir_normal_checkout_returns_none(tmp_path):
    (tmp_path / ".git").mkdir()
    assert w._read_worktree_gitdir(tmp_path) is None


def test_read_worktree_gitdir_missing_returns_none(tmp_path):
    assert w._read_worktree_gitdir(tmp_path) is None


def test_read_worktree_gitdir_absolute_pointer(tmp_path):
    gitdir = tmp_path / "main" / ".git" / "worktrees" / "feat"
    gitdir.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    assert w._read_worktree_gitdir(worktree) == str(gitdir.resolve())


def test_read_worktree_gitdir_relative_pointer(tmp_path):
    gitdir = tmp_path / ".git" / "worktrees" / "feat"
    gitdir.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: ../.git/worktrees/feat\n", encoding="utf-8")
    assert w._read_worktree_gitdir(worktree) == str(gitdir.resolve())


def test_read_worktree_gitdir_malformed_returns_none(tmp_path):
    (tmp_path / ".git").write_text("garbage\n", encoding="utf-8")
    assert w._read_worktree_gitdir(tmp_path) is None


def test_malformed_linked_worktree_marker_is_exit_3(all_tools, monkeypatch, tmp_path):
    (tmp_path / ".git").write_text("garbage\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    called = {"act": False}

    def _act(f, r):
        called["act"] = True
        return _ok("gh act -n")

    monkeypatch.setattr(w, "_act_dryrun_stage", _act)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert called["act"] is False
    assert "unsupported linked git worktree marker" in r.note
    assert "SKIP_WORKFLOW_LOCAL_TEST" in r.note


def test_missing_linked_worktree_gitdir_is_exit_3(all_tools, monkeypatch, tmp_path):
    (tmp_path / ".git").write_text("gitdir: /missing/worktree/gitdir\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "linked git worktree gitdir is missing" in r.note


def test_act_env_sets_git_dir_for_linked_worktree(tmp_path):
    gitdir = tmp_path / ".git" / "worktrees" / "feat"
    gitdir.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    env = w._act_env(worktree)
    assert env["GIT_DIR"] == str(gitdir.resolve())
    assert "GIT_WORK_TREE" not in env


def test_act_env_no_git_dir_for_normal_checkout(tmp_path):
    (tmp_path / ".git").mkdir()
    env = w._act_env(tmp_path)
    assert "GIT_DIR" not in env


def test_act_env_strips_inherited_git_hook_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("GIT_DIR", "/wrong/git")
    monkeypatch.setenv("GIT_WORK_TREE", "/wrong/worktree")
    monkeypatch.setenv("GIT_COMMON_DIR", "/wrong/common")
    monkeypatch.setenv("GIT_INDEX_FILE", "/wrong/index")
    env = w._act_env(tmp_path)
    assert "GIT_DIR" not in env
    assert "GIT_WORK_TREE" not in env
    assert "GIT_COMMON_DIR" not in env
    assert "GIT_INDEX_FILE" not in env


def test_act_dryrun_stage_passes_git_dir_env(monkeypatch, tmp_path):
    """A linked worktree's GIT_DIR reaches the gh act subprocess (#2344)."""
    gitdir = tmp_path / ".git" / "worktrees" / "feat"
    gitdir.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    seen: dict[str, dict[str, str] | None] = {}

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        seen["env"] = env
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_dryrun_stage(["a.yml"], worktree)
    assert res.ok is True
    assert seen["env"] is not None
    assert seen["env"]["GIT_DIR"] == str(gitdir.resolve())


# --- CLI -----------------------------------------------------------------


def test_cli_exit_code_propagates(all_tools, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _fail("actionlint"))
    rc = w.main(["--files", WF, "--repo-root", str(tmp_path)])
    assert rc == 1
    assert "FAIL" in capsys.readouterr().out


def test_cli_json(all_tools, monkeypatch, capsys, tmp_path):
    import json

    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    rc = w.main(["--files", WF, "--repo-root", str(tmp_path), "--no-full", "--format", "json"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["exit_code"] == 0


def test_cli_bad_repo_root(capsys):
    rc = w.main(["--files", WF, "--repo-root", "/no/such/xyz"])
    assert rc == 2
    assert "repo root not found" in capsys.readouterr().err


# --- act event selection (Issue #2374) -----------------------------------


def _write_wf(tmp_path: Path, body: str) -> Path:
    wf = tmp_path / "wf.yml"
    wf.write_text(body, encoding="utf-8")
    return wf


def test_workflow_events_scalar_on(tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: push\njobs: {}\n")
    assert w._workflow_events(wf) == ["push"]


def test_workflow_events_list_on(tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: [push, pull_request]\njobs: {}\n")
    assert w._workflow_events(wf) == ["push", "pull_request"]


def test_workflow_events_map_on(tmp_path):
    wf = _write_wf(
        tmp_path,
        "name: x\non:\n  schedule:\n    - cron: '0 9 * * 1'\n  workflow_dispatch:\njobs: {}\n",
    )
    assert set(w._workflow_events(wf)) == {"schedule", "workflow_dispatch"}


def test_workflow_events_missing_file_returns_empty(tmp_path):
    assert w._workflow_events(tmp_path / "absent.yml") == []


def test_workflow_events_returns_empty_when_yaml_missing(monkeypatch, tmp_path):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("No module named yaml")
        return real_import(name, *args, **kwargs)

    wf = _write_wf(tmp_path, "name: x\non: push\njobs: {}\n")
    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert w._workflow_events(wf) == []


def test_select_event_returns_none_when_push_present(tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: [push, schedule]\njobs: {}\n")
    assert w._select_act_event(wf) is None


def test_select_event_returns_none_when_unreadable(tmp_path):
    assert w._select_act_event(tmp_path / "absent.yml") is None


def test_select_event_prefers_workflow_dispatch_for_schedule_only(tmp_path):
    wf = _write_wf(
        tmp_path,
        "name: x\non:\n  schedule:\n    - cron: '0 9 * * 1'\n  workflow_dispatch:\njobs: {}\n",
    )
    assert w._select_act_event(wf) == "workflow_dispatch"


def test_select_event_falls_back_to_only_declared_event(tmp_path):
    wf = _write_wf(tmp_path, "name: x\non:\n  release:\n    types: [published]\njobs: {}\n")
    assert w._select_act_event(wf) == "release"


def test_dryrun_passes_selected_event_to_act(monkeypatch, tmp_path):
    wf = _write_wf(
        tmp_path,
        "name: x\non:\n  workflow_dispatch:\njobs: {}\n",
    )
    seen = {}

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        seen["cmd"] = cmd
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_dryrun_stage([wf.name], tmp_path)
    assert res.ok is True
    assert seen["cmd"] == ["gh", "act", "-n", "workflow_dispatch", "-W", wf.name]


def test_dryrun_omits_event_when_push_declared(monkeypatch, tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: push\njobs: {}\n")
    seen = {}

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        seen["cmd"] = cmd
        return 0, "", ""

    monkeypatch.setattr(w, "_run", fake_run)
    res = w._act_dryrun_stage([wf.name], tmp_path)
    assert res.ok is True
    assert seen["cmd"] == ["gh", "act", "-n", "-W", wf.name]


# --- issue #2719: git-missing in the act container downgrades to a warning ---


def test_act_full_downgrades_git_missing_to_warning(monkeypatch, tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: push\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            "",
            "fatal: not a git repository: (null)",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is True
    assert "[WARN]" in res.detail
    assert "lacks .git" in res.detail


def test_act_full_real_failure_still_blocks(monkeypatch, tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: push\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (1, "", "Error: job 'build' exited 2"),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is False
    assert "job 'build' exited 2" in res.detail


def test_act_dryrun_downgrades_git_missing_to_warning(monkeypatch, tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: push\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            "fatal: not a git repository",
            "",
        ),
    )
    res = w._act_dryrun_stage([wf.name], tmp_path)
    assert res.ok is True
    assert "[WARN]" in res.detail


def test_act_full_keeps_checking_after_git_missing_warning(monkeypatch, tmp_path):
    first = tmp_path / "first.yml"
    second = tmp_path / "second.yml"
    first.write_text("name: first\non: push\njobs: {}\n", encoding="utf-8")
    second.write_text("name: second\non: push\njobs: {}\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(cmd, *, timeout, cwd=None, env=None):
        calls.append(cmd)
        if cmd[-1] == first.name:
            return 1, "", "fatal: not a git repository: (null)"
        return 1, "", "Error: job 'build' exited 2"

    monkeypatch.setattr(w, "_run", fake_run)

    res = w._act_full_stage([first.name, second.name], tmp_path)

    assert res.ok is False
    assert "job 'build' exited 2" in res.detail
    assert [cmd[-1] for cmd in calls] == [first.name, second.name]


def test_act_full_reports_all_git_missing_warnings(monkeypatch, tmp_path):
    first = tmp_path / "first.yml"
    second = tmp_path / "second.yml"
    first.write_text("name: first\non: push\njobs: {}\n", encoding="utf-8")
    second.write_text("name: second\non: push\njobs: {}\n", encoding="utf-8")

    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            "",
            "fatal: not a git repository: (null)",
        ),
    )

    res = w._act_full_stage([first.name, second.name], tmp_path)

    assert res.ok is True
    assert first.name in res.detail
    assert second.name in res.detail


# --- issue #2758: act pull_request-context-undefined downgrades to a warning ---


def test_act_full_downgrades_pr_context_missing_to_warning(monkeypatch, tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: pull_request\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            "",
            "Error: Cannot read properties of undefined (reading 'number')",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is True
    assert "[WARN]" in res.detail
    assert "pull_request event context" in res.detail


def test_act_full_downgrades_other_pr_context_properties(monkeypatch, tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: pull_request\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            "",
            "Error: Cannot read properties of undefined (reading 'head')",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is True
    assert "[WARN]" in res.detail


def test_act_full_workflow_dispatch_pr_context_error_still_blocks(monkeypatch, tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: workflow_dispatch\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            "",
            "Error: Cannot read properties of undefined (reading 'number')",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is False
    assert "reading 'number'" in res.detail


def test_act_dryrun_downgrades_pr_context_missing_to_warning(monkeypatch, tmp_path):
    wf = _write_wf(tmp_path, "name: x\non: pull_request\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            "Cannot read properties of undefined (reading 'number')",
            "",
        ),
    )
    res = w._act_dryrun_stage([wf.name], tmp_path)
    assert res.ok is True
    assert "[WARN]" in res.detail


def test_act_full_pr_context_real_failure_still_blocks(monkeypatch, tmp_path):
    # A nonzero exit with no known act-limitation signature still hard-FAILs:
    # the PR-context downgrade must not mask a real job failure.
    wf = _write_wf(tmp_path, "name: x\non: pull_request\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            "",
            "Cannot read properties of undefined (reading 'sha')",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is False
    assert "reading 'sha'" in res.detail


def test_act_full_downgrades_empty_pr_title_env_to_warning(monkeypatch, tmp_path):
    # PR_TITLE mapped from an empty github.event.pull_request.title under act
    # makes parse_pr_standards.py exit non-zero; downgrade for pull_request. #3265
    wf = _write_wf(tmp_path, "name: x\non: pull_request\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            2,
            "",
            "PR_TITLE environment variable is required",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is True
    assert "[WARN]" in res.detail
    assert "PR_NUMBER, PR_TITLE" in res.detail


def test_act_full_downgrades_empty_pr_number_env_to_warning(monkeypatch, tmp_path):
    # PR_NUMBER mapped from an empty github.event.pull_request.number under act
    # makes pr_description.py's int("") raise; downgrade for pull_request. #3265
    wf = _write_wf(tmp_path, "name: x\non: pull_request\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            "",
            "ValueError: invalid literal for int() with base 10: ''",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is True
    assert "[WARN]" in res.detail


def test_act_full_workflow_dispatch_empty_pr_env_still_blocks(monkeypatch, tmp_path):
    # The empty PR-context env signatures downgrade only for pull_request runs.
    # Under workflow_dispatch the same failure can be a real defect and blocks.
    wf = _write_wf(tmp_path, "name: x\non: workflow_dispatch\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            2,
            "",
            "PR_TITLE environment variable is required",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is False
    assert "PR_TITLE environment variable is required" in res.detail


def test_act_limitation_hint_matches_known_patterns() -> None:
    assert w._act_limitation_hint("fatal: not a git repository") is not None
    assert (
        w._act_limitation_hint(
            "Cannot read properties of undefined (reading 'number')",
            "pull_request",
        )
        is not None
    )
    assert (
        w._act_limitation_hint(
            "Cannot read properties of undefined (reading 'head')",
            "pull_request",
        )
        is not None
    )
    assert (
        w._act_limitation_hint(
            "Cannot read properties of undefined (reading 'requested_reviewers')",
            "pull_request",
        )
        is not None
    )
    assert (
        w._act_limitation_hint(
            "Cannot read properties of undefined (reading 'number')",
            "workflow_dispatch",
        )
        is None
    )
    assert w._act_limitation_hint("Error: job 'build' exited 2") is None


def test_act_limitation_hint_matches_action_cache_copy_failure() -> None:
    """dockerd refusing act's action staging path is transport, not a defect."""
    text = (
        "[Validate Plugin Version Bump/Check Changed Paths] failed to copy content "
        "to container: Error response from daemon: statat "
        "var/run/act/actions/dorny-paths-filter@7b450fff21473bca461d4b92ce414b9d0420d706"
        ": path escapes from parent"
    )
    hint = w._act_limitation_hint(text)
    assert hint is not None
    assert "local transport" in hint


def test_act_limitation_hint_ignores_a_real_copy_failure_elsewhere() -> None:
    """Only the act staging path is excused; other copy failures still block."""
    text = (
        "failed to copy content to container: Error response from daemon: statat "
        "home/runner/work/repo/artifact.tar: path escapes from parent"
    )
    assert w._act_limitation_hint(text) is None


def test_act_limitation_hint_matches_empty_pr_env_patterns() -> None:
    # Empty PR-context env-var manifestations (#3265), event-scoped to
    # pull_request; workflow_dispatch keeps them blocking.
    assert (
        w._act_limitation_hint(
            "PR_TITLE environment variable is required",
            "pull_request",
        )
        is not None
    )
    assert (
        w._act_limitation_hint(
            "ValueError: invalid literal for int() with base 10: ''",
            "pull_request",
        )
        is not None
    )
    assert (
        w._act_limitation_hint(
            "PR_TITLE environment variable is required",
            "workflow_dispatch",
        )
        is None
    )
    # A non-empty int parse error is a real defect, not the empty-env signature.
    assert (
        w._act_limitation_hint(
            "ValueError: invalid literal for int() with base 10: 'abc'",
            "pull_request",
        )
        is None
    )


def test_act_limitation_hint_matches_argparse_empty_pr_number() -> None:
    """argparse's ``type=int`` prints a different message than a bare int().

    post_issue_comment.py takes --issue as an argparse int, so an empty
    PR_NUMBER under act surfaces as "argument --issue: invalid int value: ''"
    rather than the "invalid literal for int()" form. Same act-only cause,
    different surface text.
    """
    assert (
        w._act_limitation_hint(
            "post_issue_comment.py: error: argument --issue: invalid int value: ''",
            "pull_request",
        )
        is not None
    )
    # Event-scoped: workflow_dispatch keeps it blocking.
    assert (
        w._act_limitation_hint(
            "post_issue_comment.py: error: argument --issue: invalid int value: ''",
            "workflow_dispatch",
        )
        is None
    )
    # A non-empty value is a real defect, not the empty-env signature.
    assert (
        w._act_limitation_hint(
            "error: argument --issue: invalid int value: 'abc'",
            "pull_request",
        )
        is None
    )


def test_adr035_wrapper_annotation_is_explained_only_alongside_a_limitation() -> None:
    """run_with_retry.py's ADR-035 annotation is derived, not a cause.

    When the wrapped script failed for an attributed act limitation, the
    wrapper annotation restates that limitation one layer up and must not veto
    the downgrade. On its own it stays unexplained, so a genuine configuration
    error still blocks.
    """
    wrapper = "::error::Configuration error (ADR-035 exit 2). Check command output."
    limitation = "error: argument --issue: invalid int value: ''"

    combined = f"{limitation}\n{wrapper}\n"
    assert w._unexplained_error_annotations(combined, "pull_request") == []
    assert w._act_limitation_hint(combined, "pull_request") is not None

    # Negative: the wrapper alone is a real configuration error.
    assert len(w._unexplained_error_annotations(wrapper, "pull_request")) == 1

    # Negative: event-scoped, so workflow_dispatch keeps both blocking.
    assert len(w._unexplained_error_annotations(combined, "workflow_dispatch")) == 1

    # Negative: a genuine annotation riding along still blocks.
    with_genuine = f"{combined}::error::Genuine action bug\n"
    assert w._act_limitation_hint(with_genuine, "pull_request") is None


def test_format_text_surfaces_warning_detail_on_ok() -> None:
    report = w.Report(
        exit_code=0,
        stages=[
            w.StageResult("actionlint", True),
            w.StageResult("gh act (full)", True, "[WARN] x.yml: act container lacks .git"),
        ],
    )
    out = w._format_text(report)
    assert out.startswith("workflow-local-test: OK")
    assert "[WARN]" in out


def test_act_limitation_hint_matches_paths_filter_missing_base() -> None:
    # act's synthetic event payload omits repository.default_branch, so
    # dorny/paths-filter aborts (#3331). GitHub always populates it, so this
    # signature cannot arise in CI and is safe to downgrade for every event.
    verbatim = (
        "[Python Tests/Check Changed Paths]   ::error::This action requires "
        "'base' input to be configured or 'repository.default_branch' to be "
        "set in the event payload"
    )
    hint = w._act_limitation_hint(verbatim)
    assert hint is not None
    assert "repository.default_branch" in hint
    # Not event-scoped: the payload gap is identical on every act event.
    assert w._act_limitation_hint(verbatim, "pull_request") is not None
    assert w._act_limitation_hint(verbatim, "workflow_dispatch") is not None


def test_act_limitation_hint_matches_local_server_port_collision() -> None:
    text = (
        'time="2026-07-28T02:03:00-07:00" level=fatal '
        'msg="listen tcp 192.168.1.179:34567: bind: address already in use"'
    )
    hint = w._act_limitation_hint(text)
    assert hint is not None
    assert "local reusable-workflow server port" in hint


def test_act_limitation_hint_does_not_match_unrelated_base_error() -> None:
    # A genuine workflow defect that merely mentions 'base' must keep blocking.
    assert w._act_limitation_hint("Error: base branch not found") is None
    assert w._act_limitation_hint("::error::invalid 'base' input value 'xyz'") is None


def test_act_limitation_hint_blocks_when_a_genuine_error_rides_along() -> None:
    # The downgrade used to match anywhere in the combined output, so one act
    # limitation excused every other failure in the same workflow run. An
    # ::error:: annotation no limitation explains must keep the stage blocking.
    combined = (
        "[Python Tests/Check Changed Paths]   ::error::This action requires "
        "'base' input to be configured or 'repository.default_branch' to be "
        "set in the event payload\n"
        "[Python Tests/Run tests]   ::error::pytest exited with 1"
    )
    assert w._act_limitation_hint(combined) is None


def test_act_limitation_hint_downgrades_when_every_annotation_is_explained() -> None:
    # Two limitations in one run is still a limitation, not a defect.
    combined = (
        "[A/Filter]   ::error::This action requires 'base' input to be "
        "configured or 'repository.default_branch' to be set in the event "
        "payload\n"
        "[A/Checkout]   fatal: not a git repository"
    )
    assert w._act_limitation_hint(combined) is not None


def test_act_limitation_hint_explains_paths_filter_git_rev_parse_annotation() -> None:
    combined = (
        "fatal: not a git repository: (null)\n"
        "::error::The process 'git rev-parse --abbrev-ref HEAD' failed with exit code 128"
    )
    assert w._act_limitation_hint(combined, "push") is not None


def test_act_limitation_hint_explains_paths_filter_resolved_git_path_annotation() -> None:
    # dorny/paths-filter at digest 61f87a10 annotates the resolved executable
    # instead of the argv it ran. The stale literal made this read as an
    # unexplained annotation and blocked every push touching a workflow that
    # uses the action, on an unmodified main.
    combined = (
        "[Validate Path Normalization/Check Changed Paths]   | "
        "fatal: not a git repository: (null)\n"
        "[Validate Path Normalization/Check Changed Paths]   "
        "::error::The process '/usr/bin/git' failed with exit code 128"
    )
    assert w._act_limitation_hint(combined, "push") is not None


def test_act_limitation_hint_blocks_non_git_process_annotation() -> None:
    # Same annotation shape, different executable. Nothing about a failing
    # linter is an act limitation, so the run must keep blocking.
    combined = (
        "[A/Lint]   fatal: not a git repository\n"
        "[A/Lint]   ::error::The process '/usr/bin/eslint' failed with exit code 128"
    )
    assert w._act_limitation_hint(combined, "push") is None


def test_act_limitation_hint_blocks_git_process_annotation_with_other_exit_code() -> None:
    # 128 is the no-repository exit. A different code is the action reporting a
    # real git failure, which CI would reproduce.
    combined = (
        "[A/Filter]   fatal: not a git repository\n"
        "[A/Filter]   ::error::The process '/usr/bin/git' failed with exit code 1"
    )
    assert w._act_limitation_hint(combined, "push") is None


def test_act_limitation_hint_blocks_git_exit_128_without_missing_repository() -> None:
    text = "::error::The process '/usr/bin/git' failed with exit code 128"

    assert w._act_limitation_hint(text, "push") is None


def test_act_limitation_hint_attributes_aggregator_cascade_to_limitation() -> None:
    combined = (
        "[CLI Smoke/Check Changed Paths]   fatal: not a git repository: (null)\n"
        "[CLI Smoke/Check Changed Paths]   ::error::The process "
        "'git rev-parse --abbrev-ref HEAD' failed with exit code 128\n"
        "[CLI Smoke/Smoke Result]   ::error::Check changed paths result: failure"
    )
    assert w._act_limitation_hint(combined, "push") is not None


def test_act_limitation_hint_blocks_aggregator_cascade_without_limitation() -> None:
    combined = "[CLI Smoke/Smoke Result]   ::error::Check changed paths result: failure"
    assert w._act_limitation_hint(combined, "push") is None


def test_act_limitation_hint_ignores_non_annotation_noise() -> None:
    # act prints job-level failure lines that carry no attribution. Treating
    # those as unexplained would make every downgrade unreachable.
    combined = (
        "[A/Filter]   ::error::This action requires 'base' input to be "
        "configured or 'repository.default_branch' to be set in the event "
        "payload\n"
        "[A/Filter]   \u274c  Failure - Main dorny/paths-filter@v3\n"
        "Job 'filter' failed"
    )
    assert w._act_limitation_hint(combined) is not None


def test_pr_context_annotation_is_unexplained_outside_pull_request() -> None:
    # The pull_request rules are event-scoped, so under workflow_dispatch their
    # annotation is unexplained and must veto an otherwise-downgradable run.
    combined = (
        "[A/Filter]   ::error::This action requires 'base' input to be "
        "configured or 'repository.default_branch' to be set in the event "
        "payload\n"
        "[A/Validate]   ::error::PR_TITLE environment variable is required"
    )
    assert w._act_limitation_hint(combined, "pull_request") is not None
    assert w._act_limitation_hint(combined, "workflow_dispatch") is None


# --- act artifact-service limitation (#3690) -----------------------------

# The verbatim tail of a real local act run against agent-metrics.yml. act's
# embedded artifact server rejects the protobuf field the current
# actions/upload-artifact client sends, the client reads the rejection as
# malformed JSON, retries five times, then aborts.
_ARTIFACT_TRANSPORT_FAILURE = (
    "[Agent Metrics/Collect]   | Root directory input is valid!\n"
    'level=error msg="Error decode request body: proto: (line 1:143): '
    'unknown field \\"mime_type\\""\n'
    "[Agent Metrics/Collect]   | Attempt 1 of 5 failed with error: "
    "Unexpected end of JSON input. Retrying request in 3000 ms...\n"
    "[Agent Metrics/Collect]   \u2757  ::error::Failed to CreateArtifact: "
    "Failed to make request after 5 attempts: Unexpected end of JSON input\n"
    "[Agent Metrics/Collect]   \u274c  Failure - Main Upload metrics artifact\n"
    "Error: Job 'Collect Agent Metrics' failed"
)


def test_artifact_transport_failure_is_act_limitation() -> None:
    # Positive: the observed CreateArtifact transport failure downgrades.
    assert w._act_limitation_hint(_ARTIFACT_TRANSPORT_FAILURE) is not None


def test_artifact_transport_failure_downgrades_regardless_of_event() -> None:
    # The artifact server gap is not event-scoped: act lacks the service under
    # every event, so the rule must hold for each one the gate can select.
    for event in (None, "push", "workflow_dispatch", "pull_request", "schedule"):
        assert w._act_limitation_hint(_ARTIFACT_TRANSPORT_FAILURE, event) is not None


def test_artifact_transport_failure_matches_any_artifact_verb() -> None:
    # Anchored on the retry-exhaustion suffix, so download- and finalize-side
    # transport failures downgrade too without enumerating every verb.
    for verb in (
        "CreateArtifact",
        "FinalizeArtifact",
        "ListArtifacts",
        "GetSignedArtifactURL",
        "DeleteArtifact",
    ):
        text = (
            f"::error::Failed to {verb}: Failed to make request after "
            "5 attempts: Unexpected end of JSON input"
        )
        assert w._act_limitation_hint(text) is not None, verb


def test_artifact_no_files_found_still_blocks() -> None:
    # Negative control. A real artifact defect carries no retry-exhaustion
    # suffix, so the rule must not swallow it.
    text = (
        "::error::No files were found with the provided path: dist/. No artifacts will be uploaded."
    )
    assert w._act_limitation_hint(text) is None


def test_artifact_invalid_name_still_blocks() -> None:
    # Negative control. An invalid artifact name is a workflow defect.
    text = (
        "::error::The artifact name is not valid: bad/name. "
        "Contains the following character: Forward slash /"
    )
    assert w._act_limitation_hint(text) is None


def test_artifact_limitation_does_not_excuse_a_real_failure() -> None:
    # Edge: a genuine action failure alongside the artifact limitation keeps
    # blocking, because the unexplained annotation vetoes the downgrade.
    combined = (
        _ARTIFACT_TRANSPORT_FAILURE
        + "\n[Agent Metrics/Collect]   ::error::collect_metrics.py exited 2"
    )
    assert w._act_limitation_hint(combined) is None


def test_retry_suffix_without_artifact_verb_does_not_match() -> None:
    # Edge: the rule requires the "Failed to <verb>:" prefix, so an unrelated
    # retry-exhaustion message is not silently downgraded.
    text = "::error::Failed after 5 attempts: Unexpected end of JSON input"
    assert w._act_limitation_hint(text) is None


def test_act_full_artifact_transport_failure_warns(monkeypatch, tmp_path):
    # Integration: the full act stage downgrades to a passing WARN instead of
    # blocking the push. This is the #3690 symptom.
    wf = _write_wf(tmp_path, "name: x\non: workflow_dispatch\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            _ARTIFACT_TRANSPORT_FAILURE,
            "",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is True
    assert "[WARN]" in res.detail
    assert "artifact" in res.detail


def test_act_full_artifact_defect_still_fails(monkeypatch, tmp_path):
    # Integration negative control: a real artifact defect keeps the stage red.
    wf = _write_wf(tmp_path, "name: x\non: workflow_dispatch\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            "::error::No files were found with the provided path: dist/.",
            "",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is False


# ---------------------------------------------------------------------------
# No-repo-context limitation (gh API calls in act containers - issue #3981)
# ---------------------------------------------------------------------------

_NO_REPO_CONTEXT_LOG = (
    "[Workflow Coalescing Metrics/Collect Coalescing Metrics]   "
    "| Could not infer repository info. "
    "Please provide -Owner and -Repo parameters."
)


def test_no_repo_context_is_act_limitation() -> None:
    # Positive: the "could not infer" message downgrades the failure.
    hint = w._act_limitation_hint(_NO_REPO_CONTEXT_LOG)
    assert hint is not None
    assert "repository context" in hint


def test_no_repo_context_limitation_applies_across_events() -> None:
    # The repo-context gap is not event-scoped: act lacks it under every event.
    for event in (None, "push", "workflow_dispatch", "pull_request", "schedule"):
        hint = w._act_limitation_hint(_NO_REPO_CONTEXT_LOG, event)
        assert hint is not None, f"expected hint for event={event!r}"


def test_no_repo_context_limitation_does_not_excuse_genuine_error() -> None:
    # A genuine workflow error alongside the limitation keeps the stage red.
    combined = _NO_REPO_CONTEXT_LOG + "\n[Coalescing/Commit]   ::error::collect_metrics.py exited 2"
    assert w._act_limitation_hint(combined) is None


def test_act_full_no_repo_context_warns(monkeypatch, tmp_path) -> None:
    # Integration: the full act stage downgrades to a passing WARN instead of
    # blocking the push when the act container lacks repo context.
    wf = _write_wf(tmp_path, "name: x\non: workflow_dispatch\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            1,
            _NO_REPO_CONTEXT_LOG,
            "",
        ),
    )
    res = w._act_full_stage([wf.name], tmp_path)
    assert res.ok is True
    assert "[WARN]" in res.detail
    assert "repository context" in res.detail


# ---------------------------------------------------------------------------
# Cold action cache and the stage timeout (issue #3949)
# ---------------------------------------------------------------------------

_CLONE_LINE = (
    "*DRYRUN* [CodeQL Analysis/Analyze (actions)-1]   git clone "
    "'https://github.com/github/codeql-action' # ref=f205ea1c3313d32999d8d6a48b4f6530d4437b38"
)


def _hang_after(text: str) -> list[str]:
    """Command that writes ``text`` to stdout, flushes, then sleeps 30 seconds.

    The sleep only has to outlive the budget its caller passes to ``_run`` (2
    seconds today), so the child is still running when the kill lands.
    """
    script = f"import sys, time; sys.stdout.write({text!r}); sys.stdout.flush(); time.sleep(30)"
    return [sys.executable, "-c", script]


def test_dryrun_budget_covers_a_cold_action_cache() -> None:
    # act clones every referenced action before it can plan, so the dry run needs
    # the same budget as the full run. Measured on codeql-analysis.yml: 17s warm,
    # still cloning at 130s with 787M pulled on an empty --action-cache-path.
    # Equality, not >=: the module derives one constant from the other, and a
    # future edit that re-splits them into independent literals fails here in
    # both directions instead of only when the dry run is made smaller.
    assert w._ACT_DRYRUN_TIMEOUT == w._ACT_FULL_TIMEOUT


def test_run_keeps_partial_stdout_on_timeout() -> None:
    # Positive: the child's pre-kill output is the only evidence of what the run
    # was doing. Before the fix _run returned "" here and the cause was lost.
    rc, out, err = w._run(_hang_after(_CLONE_LINE + "\n"), timeout=2)

    assert rc == -1
    assert _CLONE_LINE in out
    assert "TimeoutExpired" in err


def test_run_returns_empty_output_when_timeout_child_wrote_nothing() -> None:
    # Edge: TimeoutExpired carries None for a stream the child never wrote to.
    # Decoding must yield "" rather than raising or leaking "None".
    rc, out, err = w._run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=2)

    assert rc == -1
    assert out == ""
    assert err.startswith("TimeoutExpired: ")


def test_decode_partial_handles_bytes_str_and_none() -> None:
    # subprocess builds TimeoutExpired from the raw pipe buffers, so the partial
    # output arrives as bytes even though _run passes text=True.
    assert w._decode_partial(b"clone\n") == "clone\n"
    assert w._decode_partial("clone\n") == "clone\n"
    assert w._decode_partial(None) == ""
    assert w._decode_partial(b"\xff") == "�"


def test_timeout_hint_names_the_cold_cache_when_clones_are_present() -> None:
    # Positive: clone lines in the partial output identify the cache, not the
    # workflow, as the cause, and name the re-run as the remedy.
    combined = f"{_CLONE_LINE}\n{_CLONE_LINE}\nTimeoutExpired: timed out after 120 seconds"

    hint = w._stage_timeout_hint(combined)

    assert hint is not None
    assert "2 'git clone' line(s)" in hint
    assert "cold gh act action cache" in hint
    assert "Re-run" in hint


def test_timeout_hint_does_not_blame_the_cache_without_clone_activity() -> None:
    # Negative: a timeout with no clone traffic is a slow run. Claiming a cold
    # cache there would point the operator at the wrong suspect.
    combined = "[Build/Compile]   running tests\nTimeoutExpired: timed out after 600 seconds"

    hint = w._stage_timeout_hint(combined)

    assert hint is not None
    assert "cold gh act action cache is not the cause" in hint
    assert "git clone" not in hint


def test_timeout_hint_is_absent_without_a_timeout() -> None:
    # Negative: an ordinary nonzero exit gets no timeout cause line, even when
    # the output happens to carry clone activity.
    assert w._stage_timeout_hint(f"{_CLONE_LINE}\n::error::step failed") is None


def test_timeout_hint_survives_the_detail_truncation() -> None:
    # Edge: the cap trims the raw output, and the timeout marker sits at its
    # tail. Deriving the hint from the full text keeps the cause visible.
    combined = ("noise\n" * 2000) + _CLONE_LINE + "\nTimeoutExpired: timed out after 120 seconds"

    detail = w._with_timeout_hint(combined)

    assert len(combined) > 4000
    assert "TimeoutExpired" not in detail[:4000]
    assert "cold gh act action cache" in detail


def test_act_dryrun_timeout_fails_with_the_cause(monkeypatch, tmp_path) -> None:
    # Integration: the stage still blocks, but the operator now reads why.
    wf = _write_wf(tmp_path, "name: x\non: workflow_dispatch\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            -1,
            _CLONE_LINE + "\n",
            "TimeoutExpired: Command '['gh', 'act', '-n']' timed out after 120 seconds",
        ),
    )

    res = w._act_dryrun_stage([wf.name], tmp_path)

    assert res.ok is False
    assert "cold gh act action cache" in res.detail
    assert "1 'git clone' line(s)" in res.detail


def test_act_timeout_does_not_downgrade_on_a_limitation_signature(monkeypatch, tmp_path) -> None:
    # Regression guard for the partial-output change: a run killed mid-flight
    # never validated the workflow, so a limitation signature in what it managed
    # to emit must not turn the timeout into a passing WARN.
    wf = _write_wf(tmp_path, "name: x\non: workflow_dispatch\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            -1,
            "fatal: not a git repository\n" + _CLONE_LINE + "\n",
            "TimeoutExpired: Command '['gh', 'act', '-n']' timed out after 120 seconds",
        ),
    )

    res = w._act_dryrun_stage([wf.name], tmp_path)

    assert res.ok is False
    assert "[WARN]" not in res.detail


def test_actionlint_timeout_fails_with_the_cause(monkeypatch, tmp_path) -> None:
    # Sibling call site: actionlint routes through the same _run, so its timeout
    # detail gets the same cause line instead of a bare TimeoutExpired.
    wf = _write_wf(tmp_path, "name: x\non: workflow_dispatch\njobs: {}\n")
    monkeypatch.setattr(
        w,
        "_run",
        lambda cmd, *, timeout, cwd=None, env=None: (
            -1,
            "",
            "TimeoutExpired: Command '['actionlint']' timed out after 60 seconds",
        ),
    )

    res = w._actionlint_stage([wf.name], tmp_path)

    assert res.ok is False
    assert "killed by the stage timeout" in res.detail


# --- process-group teardown (#3948) --------------------------------------


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX-only")
def test_run_calls_killpg_safe_on_timeout() -> None:
    """On timeout, _run calls _killpg_safe to kill the process group.

    Without _killpg_safe, only the direct child is killed (proc.kill() path),
    and grandchildren such as the gh-act artifact server survive to hold ports
    (Issue #3948).  This mock-based test verifies the kill path fires.
    """
    killed_pids: list[int] = []
    original = w._killpg_safe

    def recording(pid: int) -> None:
        killed_pids.append(pid)
        original(pid)

    with mock.patch.object(w, "_killpg_safe", side_effect=recording):
        rc, _out, _err = w._run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=1)

    assert rc == -1  # timed out
    assert len(killed_pids) >= 1, "_killpg_safe was never called on timeout"


def test_run_baseline_success_still_works() -> None:
    """Positive: a fast command succeeds and its output is captured."""
    rc, out, err = w._run([sys.executable, "-c", "print('ok')"], timeout=5)
    assert rc == 0
    assert "ok" in out
    assert err == ""


def test_run_process_group_guard_does_not_signal_own_group() -> None:
    """_killpg_safe must not signal the caller's own process group.

    start_new_session=True creates a new session so the child's PGID differs
    from ours. Verify _killpg_safe with our own PID does nothing (the guard
    compares PGIDs and returns early).
    """
    import os

    # If pgid == our own pgid the function returns without signalling.
    # Calling it with our own PID must not raise or kill this process.
    w._killpg_safe(os.getpid())  # must not raise or kill


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="POSIX-only")
def test_run_passes_start_new_session_to_popen() -> None:
    """Popen is called with start_new_session=True on POSIX (#3948 guard).

    If start_new_session=False, the child's PGID matches ours. _killpg_safe
    then short-circuits (same group = us), and no group kill fires.
    """
    import subprocess as _subprocess

    popen_calls: list[dict] = []
    real_popen = _subprocess.Popen

    def recording_popen(*args, **kwargs):
        popen_calls.append({"start_new_session": kwargs.get("start_new_session")})
        return real_popen(*args, **kwargs)  # subprocess-encoding: strict-ok

    with mock.patch("run_workflow_local_test.subprocess.Popen", side_effect=recording_popen):
        w._run([sys.executable, "-c", "print('hi')"], timeout=5)

    assert popen_calls, "Popen was never called"
    assert popen_calls[0]["start_new_session"] is True, (
        f"start_new_session={popen_calls[0]['start_new_session']!r}; expected True"
    )
