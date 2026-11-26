"""AC-DUP-3: Shared skill bootstrap preserves installed path selection."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "src/claude/skills/github/scripts"
ENTRYPOINTS = [
    "issue/check_existing_pr_for_issue.py",
    "issue/claim_issue.py",
    "issue/close_issue.py",
    "issue/edit_issue_body.py",
    "issue/get_issue_comments.py",
    "issue/get_issue_context.py",
    "issue/get_issue_relationships.py",
    "issue/invoke_copilot_assignment.py",
    "issue/list_issues.py",
    "issue/new_issue.py",
    "issue/post_issue_comment.py",
    "issue/reopen_issue.py",
    "issue/set_issue_assignee.py",
    "issue/set_issue_labels.py",
    "issue/set_issue_milestone.py",
    "issue/set_issue_relationship.py",
    "milestone/get_latest_semantic_milestone.py",
    "milestone/set_item_milestone.py",
    "notifications/get_actionable_items.py",
    "pr/add_pr_review_thread_reply.py",
    "pr/audit_closing_claims.py",
    "pr/auto_merge_guard.py",
    "pr/check_pr_live_state.py",
    "pr/check_pr_round_cap.py",
    "pr/check_review_thread_resolution_shas.py",
    "pr/check_suppressed_review_findings.py",
    "pr/close_pr.py",
    "pr/detect_copilot_followup_pr.py",
    "pr/detect_stale_bot_review.py",
    "pr/detect_stale_pr_comments.py",
    "pr/edit_pr_body.py",
    "pr/get_pr_check_logs.py",
    "pr/get_pr_checks.py",
    "pr/get_pr_code_scanning_alerts.py",
    "pr/get_pr_comments_by_reviewer.py",
    "pr/get_pr_context.py",
    "pr/get_pr_review_comments.py",
    "pr/get_pr_review_threads.py",
    "pr/get_pr_reviewers.py",
    "pr/get_pr_reviews.py",
    "pr/get_pull_requests.py",
    "pr/get_thread_by_id.py",
    "pr/get_thread_conversation_history.py",
    "pr/get_unaddressed_comments.py",
    "pr/get_unresolved_review_threads.py",
    "pr/invoke_pr_comment_processing.py",
    "pr/merge_pr.py",
    "pr/new_pr_review_comment.py",
    "pr/post_pr_comment_reply.py",
    "pr/pr_context_helpers.py",
    "pr/reopen_pr.py",
    "pr/rerun_failed_jobs.py",
    "pr/resolve_pr_review_thread.py",
    "pr/set_pr_auto_merge.py",
    "pr/set_pr_ready.py",
    "pr/test_pr_merge_ready.py",
    "pr/test_pr_merged.py",
    "pr/triage_red_check.py",
    "pr/unresolve_pr_review_thread.py",
    "pr/update_pr_branch.py",
    "pr/why_pr_blocked.py",
    "reactions/add_comment_reaction.py",
    "repo/manage_squash_merge_message.py",
    "utils/check_github_transport.py",
]


def test_legacy_fallback_collection_keeps_every_shared_consumer() -> None:
    from tests.skills.github import test_bootstrap_fallback as legacy

    checked = {
        path.relative_to(legacy._SCRIPTS_DIR).as_posix()
        for path in legacy.TestBootstrapSourceCode()._bootstrap_scripts()
    }

    assert set(ENTRYPOINTS) <= checked


def _load_bootstrap() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "github_skill_bootstrap", SCRIPTS / "skill_bootstrap.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "policy",
    ["ancestors", "manifest", "manifest-fallback", "ancestors-missing", "manifest-missing"],
)
def test_shared_lookup_preserves_nonstandard_depth_and_missing_libraries(
    policy: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mod = _load_bootstrap()
    monkeypatch.setattr(sys, "path", list(sys.path))
    for variable in ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"):
        monkeypatch.delenv(variable, raising=False)
    plugin = tmp_path / "plugin"
    script = plugin / "custom/deep/example.py"
    discovery = policy.split("-")[0]
    if policy == "manifest-fallback":
        script = plugin / "skills/github/scripts/pr/example.py"
    if policy.startswith("manifest") and policy != "manifest-fallback":
        manifest = plugin / ".claude-plugin/plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}", encoding="utf-8")
    if policy.endswith("missing"):
        with pytest.raises(SystemExit) as error:
            mod.ensure_plugin_paths(str(script), discovery=discovery)
        assert error.value.code == 2
        return
    (plugin / "lib/github_core").mkdir(parents=True)

    mod.ensure_plugin_paths(str(script), discovery=discovery)

    assert sys.path[0] == str(plugin / "lib")


@pytest.mark.parametrize(
    "selection", ["copilot", "claude", "both", "invalid-copilot", "invalid-claude"]
)
def test_shared_plugin_roots_keep_precedence_over_workspace(
    selection: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mod = _load_bootstrap()
    monkeypatch.setattr(sys, "path", list(sys.path))
    copilot = tmp_path / "copilot"
    claude = tmp_path / "claude"
    workspace = tmp_path / "workspace"
    for plugin in (copilot, claude, workspace / ".claude"):
        (plugin / "lib/github_core").mkdir(parents=True)
    for variable in ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"):
        monkeypatch.delenv(variable, raising=False)
    if selection in ("copilot", "both"):
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(copilot))
    if selection in ("claude", "both", "invalid-copilot"):
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude))
    if selection.startswith("invalid"):
        variable = "COPILOT_PLUGIN_ROOT" if selection == "invalid-copilot" else "CLAUDE_PLUGIN_ROOT"
        monkeypatch.setenv(variable, str(tmp_path / "missing"))
    expected = copilot if selection in ("copilot", "both") else claude
    if selection.startswith("invalid"):
        expected = workspace / ".claude"

    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    mod.ensure_plugin_paths(str(tmp_path / "script.py"), (".claude", "lib"))

    assert sys.path[0] == str(expected / "lib")


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_entrypoint_delegates_shared_bootstrap(entrypoint: str, tmp_path: Path) -> None:
    scripts = tmp_path / "plugin/skills/github/scripts"
    target = scripts / entrypoint
    target.parent.mkdir(parents=True)
    shutil.copyfile(SCRIPTS / entrypoint, target)
    (scripts / "skill_bootstrap.py").write_text(
        "def ensure_plugin_paths(script_file, workspace=None, *, discovery='relative'):\n"
        "    raise SystemExit(73)\n",
        encoding="utf-8",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT", "GITHUB_WORKSPACE", "PYTHONPATH")
    }

    result = subprocess.run(
        [sys.executable, str(target), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )

    assert result.returncode == 73, result.stderr


def test_set_pr_ready_bare_bootstrap_ignores_workspace_lib(tmp_path: Path) -> None:
    plugin = tmp_path / "plugin"
    shutil.copytree(SCRIPTS, plugin / "skills/github/scripts")
    shutil.copytree(ROOT / "src/claude/lib", plugin / "lib", symlinks=False)
    script = plugin / "skills/github/scripts/pr/set_pr_ready.py"
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT", "PYTHONPATH")
    }
    env["PATH"] = str(tmp_path / "no-external-tools")
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT / "src/claude/lib", workspace / ".claude/lib", symlinks=False)
    env["GITHUB_WORKSPACE"] = str(workspace)
    (plugin / "lib").rename(plugin / "lib-unavailable")

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )

    assert result.returncode == 2
    assert "Plugin lib directory not found:" in result.stderr
    assert str(plugin / "lib") in result.stderr


@pytest.mark.parametrize("delegation", ["actual", "comment", "uncalled", "wrong_module"])
def test_path_validation_reads_only_actual_shared_delegation(
    delegation: str, tmp_path: Path
) -> None:
    from tests import plugin_bootstrap_helpers as contract

    script = tmp_path / "scripts/pr/consumer.py"
    script.parent.mkdir(parents=True)
    source = "from github_core.api import gh_graphql\n"
    if delegation == "actual":
        source += "from skill_bootstrap import ensure_plugin_paths\nensure_plugin_paths(__file__)\n"
    elif delegation == "comment":
        source += (
            "# from skill_bootstrap import ensure_plugin_paths\n# ensure_plugin_paths(__file__)\n"
        )
    elif delegation == "uncalled":
        source += "from skill_bootstrap import ensure_plugin_paths\n"
    else:
        source += (
            "from unrelated_bootstrap import ensure_plugin_paths\nensure_plugin_paths(__file__)\n"
        )
    script.write_text(source, encoding="utf-8")
    helper_source = "SHARED_BOOTSTRAP_CONTRACT = True\n"
    helper = script.parent.parent / "skill_bootstrap.py"
    helper.write_text(helper_source, encoding="utf-8")

    resolved = contract.skill_resolution_source(script)

    assert (helper_source in resolved) == (delegation == "actual")
    helper.unlink()
    assert contract.skill_resolution_source(script) == source


@pytest.mark.parametrize("workspace", [None, "workspace", ""])
def test_shared_fallback_and_registration_preserve_paths(
    workspace: str | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mod = _load_bootstrap()
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.chdir(tmp_path)
    relative = tmp_path / "relative"
    script = relative / "skills/github/scripts/issue/example.py"
    chosen = Path(workspace) / ".claude" if workspace else relative

    for variable in ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"):
        monkeypatch.delenv(variable, raising=False)
    selected = str(chosen / "lib")
    (chosen / "lib").mkdir(parents=True)
    if workspace is None:
        monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
    else:
        monkeypatch.setenv("GITHUB_WORKSPACE", workspace)
    mod.ensure_plugin_paths(str(script), (".claude", "lib"))
    before = list(sys.path)
    mod.ensure_plugin_paths(str(script), (".claude", "lib"))

    assert selected == str(chosen / "lib")
    assert sys.path == before
    assert sys.path[0] == selected


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_isolated_installed_entrypoint_and_missing_lib_control(
    entrypoint: str, tmp_path: Path
) -> None:
    plugin = tmp_path / "plugin"
    shutil.copytree(SCRIPTS, plugin / "skills/github/scripts")
    shutil.copytree(ROOT / "src/claude/lib", plugin / "lib", symlinks=False)
    script = plugin / "skills/github/scripts" / entrypoint
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in ("CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT", "GITHUB_WORKSPACE", "PYTHONPATH")
    }
    env["PATH"] = str(tmp_path / "no-external-tools")
    command = [sys.executable, str(script), "--help"]

    available = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    assert available.returncode == 0, available.stderr
    (plugin / "lib").rename(plugin / "lib-unavailable")
    unavailable = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=False,
    )
    assert unavailable.returncode == 2
    assert "Plugin lib directory not found:" in unavailable.stderr
