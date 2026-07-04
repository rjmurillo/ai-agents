"""Tests for scripts/validation/run_workflow_local_test.py.

Covers the belt-and-suspenders gate: stage ordering and short-circuit,
tool/Docker gaps -> exit 3, bypass env, --no-full, and CLI exit codes. All
external commands (actionlint, gh act, docker) are mocked; no Docker required.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VALIDATION_DIR = str(REPO_ROOT / "scripts" / "validation")
if _VALIDATION_DIR not in sys.path:
    sys.path.insert(0, _VALIDATION_DIR)

import run_workflow_local_test as w  # noqa: E402

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
    r = w.run_local_test(
        [".github/actions/foo/action.yml", "README.md"], tmp_path
    )
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
    monkeypatch.setattr(w, "_have", lambda tool: tool != "actionlint")
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
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


def test_gh_act_missing_in_remote_container_downgrades_to_warning(
    monkeypatch, tmp_path
):
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


def test_gh_act_missing_in_ci_still_blocks_even_with_container_signal(
    monkeypatch, tmp_path
):
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
    # docker is installed but the daemon is down -> "not running" note.
    monkeypatch.setattr(w, "_docker_ready", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "daemon is not running" in r.note


def test_docker_not_installed_is_exit_3_with_distinct_note(monkeypatch, tmp_path):
    # docker binary absent -> "not installed" note, distinct from daemon-down.
    monkeypatch.setattr(w, "_have", lambda tool: tool != "docker")
    monkeypatch.setattr(w, "_gh_act_available", lambda: True)
    monkeypatch.setattr(w, "_docker_ready", lambda: False)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.delenv(w._BYPASS_ENV, raising=False)
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 3
    assert "Docker is not installed" in r.note


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
    assert "1 locally absent secret(s)" in r.note


def test_quoted_empty_env_secret_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setenv("BOT_PAT_2841", '""')
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 4
    assert r.secret_skipped is True


def test_all_workflows_secret_blocked_is_exit_4(monkeypatch, tmp_path):
    # A changed workflow that needs a locally-absent secret cannot run under
    # act. actionlint (static, no secrets) still runs; only the act run is
    # skipped audibly (exit 4). The actionlint stage is recorded (#2841 review).
    monkeypatch.setattr(w, "_have", lambda tool: True)
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    _write_wf_secrets(tmp_path, WF, "BOT_PAT_2841")
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 4
    assert r.secret_skipped is True
    assert "BOT_PAT_2841" not in r.note
    assert "1 locally absent secret(s)" in r.note
    assert [s.stage for s in r.stages] == ["actionlint"]


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
    # (exit 3) even when every workflow is secret-blocked.
    monkeypatch.setattr(w, "_have", lambda tool: tool != "actionlint")
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
        'on: push\njobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n'
        '      - run: echo "the literal text secrets.ABSENT_SECRET is fine"\n',
        encoding="utf-8",
    )
    assert w._referenced_secrets(path) == set()
    r = w.run_local_test([WF], tmp_path)
    assert r.exit_code == 0
    assert len(r.stages) == 3


def test_mixed_runs_only_runnable_and_notes_skip(all_tools, monkeypatch, tmp_path):
    # One workflow needs an absent secret (skipped), one is clean (runs).
    # actionlint lints BOTH; the act stages receive only the runnable file; the
    # skipped file is surfaced in the note (exit 0 preserved).
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
    r = w.run_local_test([blocked, clean], tmp_path)
    assert r.exit_code == 0
    assert r.secret_skipped is True
    assert seen["lint"] == [blocked, clean]
    assert seen["act"] == [clean]
    assert "BOT_PAT_2841" not in r.note
    assert "1 locally absent secret(s)" in r.note
    assert "blocked.yml" in r.note


def test_mixed_skip_note_visible_in_text_format(all_tools, monkeypatch, tmp_path):
    # The mixed-batch skip note must appear in exit-0 text output so the hook
    # can surface it instead of reporting a silent clean pass (#2841 review).
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    clean = ".github/workflows/clean.yml"
    blocked = ".github/workflows/blocked.yml"
    _write_wf_secrets(tmp_path, clean)
    _write_wf_secrets(tmp_path, blocked, "BOT_PAT_2841")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))
    r = w.run_local_test([blocked, clean], tmp_path)
    text = w._format_text(r)
    assert "OK" in text
    assert "skipped (secrets absent locally)" in text
    assert "blocked.yml" in text


def test_format_json_exposes_secret_skipped(all_tools, monkeypatch, tmp_path):
    monkeypatch.delenv("BOT_PAT_2841", raising=False)
    clean = ".github/workflows/clean.yml"
    blocked = ".github/workflows/blocked.yml"
    _write_wf_secrets(tmp_path, clean)
    _write_wf_secrets(tmp_path, blocked, "BOT_PAT_2841")
    monkeypatch.setattr(w, "_actionlint_stage", lambda f, r: _ok("actionlint"))
    monkeypatch.setattr(w, "_act_dryrun_stage", lambda f, r: _ok("gh act -n"))
    monkeypatch.setattr(w, "_act_full_stage", lambda f, r: _ok("gh act (full)"))
    r = w.run_local_test([blocked, clean], tmp_path)
    payload = json.loads(w._format_json(r))
    assert payload["secret_skipped"] is True
    assert payload["exit_code"] == 0


def test_exit_4_text_format_omits_secret_name():
    report = w.Report(
        exit_code=4, note="unrunnable-locally: x.yml needs 1 locally absent secret(s)."
    )
    text = w._format_text(report)
    assert "SKIPPED" in text
    assert "locally absent secret" in text
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
    (worktree / ".git").write_text(
        "gitdir: ../.git/worktrees/feat\n", encoding="utf-8"
    )
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


def test_act_full_workflow_dispatch_pr_context_error_still_blocks(
    monkeypatch, tmp_path
):
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


def test_format_text_surfaces_warning_detail_on_ok() -> None:
    report = w.Report(
        exit_code=0,
        stages=[
            w.StageResult("actionlint", True),
            w.StageResult(
                "gh act (full)", True, "[WARN] x.yml: act container lacks .git"
            ),
        ],
    )
    out = w._format_text(report)
    assert out.startswith("workflow-local-test: OK")
    assert "[WARN]" in out
