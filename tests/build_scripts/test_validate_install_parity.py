"""Tests for build/scripts/validate_install_parity.py.

Covers:
- positive: clean diffs pass
- negative: diffs missing siblings fail with named missing paths
- edge: freestanding agents (no template) are not flagged
- edge: blocklisted filenames (AGENTS.md, CLAUDE.md) are ignored
- edge: unknown paths do not crash and are not classified
- CLI: --files mode short-circuits git diff
- CLI: --format json emits structured output
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import validate_install_parity as vip  # noqa: E402


# --- Fixtures ------------------------------------------------------------


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A repo skeleton with a single shared agent ``alpha`` and one rule ``beta``.

    Files on disk represent the "current world" the validator consults to decide
    whether a name is a shared-agent group or freestanding. The diff (touched
    set) is supplied independently per test.
    """
    (tmp_path / "templates" / "agents").mkdir(parents=True)
    (tmp_path / "templates" / "agents" / "alpha.shared.md").write_text("# alpha\n")
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "alpha.md").write_text("# alpha\n")
    (tmp_path / ".github" / "agents").mkdir(parents=True)
    (tmp_path / ".github" / "agents" / "alpha.agent.md").write_text("# alpha\n")
    # Freestanding Copilot agent: only one file in .github/agents/.
    (tmp_path / ".github" / "agents" / "gamma.agent.md").write_text("# gamma\n")
    (tmp_path / "src" / "claude").mkdir(parents=True)
    (tmp_path / "src" / "claude" / "alpha.md").write_text("# alpha\n")
    (tmp_path / "src" / "copilot-cli" / "agents").mkdir(parents=True)
    (tmp_path / "src" / "copilot-cli" / "agents" / "alpha.agent.md").write_text("# alpha\n")
    (tmp_path / "src" / "vs-code-agents").mkdir(parents=True)
    (tmp_path / "src" / "vs-code-agents" / "alpha.agent.md").write_text("# alpha\n")

    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / ".claude" / "rules" / "beta.md").write_text("# beta\n")
    (tmp_path / ".github" / "instructions").mkdir(parents=True)
    (tmp_path / ".github" / "instructions" / "beta.instructions.md").write_text("# beta\n")
    (tmp_path / "src" / "copilot-cli" / "instructions").mkdir(parents=True)
    (tmp_path / "src" / "copilot-cli" / "instructions" / "beta.instructions.md").write_text(
        "# beta\n"
    )
    return tmp_path


# --- classify ------------------------------------------------------------


def test_classify_shared_agent_template() -> None:
    assert vip.classify("templates/agents/qa.shared.md") == ("SHARED_AGENT", "qa")


def test_classify_shared_agent_install() -> None:
    assert vip.classify(".claude/agents/qa.md") == ("SHARED_AGENT", "qa")
    assert vip.classify(".github/agents/qa.agent.md") == ("SHARED_AGENT", "qa")
    assert vip.classify("src/claude/qa.md") == ("SHARED_AGENT", "qa")
    assert vip.classify("src/copilot-cli/agents/qa.agent.md") == ("SHARED_AGENT", "qa")
    assert vip.classify("src/vs-code-agents/qa.agent.md") == ("SHARED_AGENT", "qa")


def test_classify_rule() -> None:
    assert vip.classify(".claude/rules/security.md") == ("RULE", "security")
    assert vip.classify(".github/instructions/security.instructions.md") == (
        "RULE",
        "security",
    )
    assert vip.classify("src/copilot-cli/instructions/security.instructions.md") == (
        "RULE",
        "security",
    )


def test_classify_ignores_agent_dir_metadata() -> None:
    assert vip.classify(".claude/agents/AGENTS.md") is None
    assert vip.classify(".claude/agents/CLAUDE.md") is None
    assert vip.classify("src/claude/AGENTS.md") is None


def test_classify_ignores_rule_dir_metadata() -> None:
    assert vip.classify(".claude/rules/CLAUDE.md") is None


def test_classify_ignores_non_agent_src_claude_files() -> None:
    # documentation/templates that happen to land under src/claude/ but are
    # not agent prompts.
    assert vip.classify("src/claude/claude-instructions.template.md") is None


def test_classify_unknown_paths_return_none() -> None:
    assert vip.classify("README.md") is None
    assert vip.classify("scripts/validation/pre_pr.py") is None
    assert vip.classify("tests/build_scripts/test_build_all.py") is None
    assert vip.classify("") is None


# --- find_violations -----------------------------------------------------


def test_clean_diff_all_six_shared_agent_members(fake_repo: Path) -> None:
    touched = [
        "templates/agents/alpha.shared.md",
        ".claude/agents/alpha.md",
        ".github/agents/alpha.agent.md",
        "src/claude/alpha.md",
        "src/copilot-cli/agents/alpha.agent.md",
        "src/vs-code-agents/alpha.agent.md",
    ]
    assert vip.find_violations(touched, repo_root=fake_repo) == []


def test_shared_agent_template_only_drift_detected(fake_repo: Path) -> None:
    touched = ["templates/agents/alpha.shared.md"]
    violations = vip.find_violations(touched, repo_root=fake_repo)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == "SHARED_AGENT"
    assert v.name == "alpha"
    assert "templates/agents/alpha.shared.md" in v.touched
    # Every other sibling is missing.
    assert ".claude/agents/alpha.md" in v.missing
    assert ".github/agents/alpha.agent.md" in v.missing
    assert "src/claude/alpha.md" in v.missing
    assert "src/copilot-cli/agents/alpha.agent.md" in v.missing
    assert "src/vs-code-agents/alpha.agent.md" in v.missing


def test_shared_agent_skipped_claude_install_is_drift(fake_repo: Path) -> None:
    """PR #2087 / #2083 shape: template + src/* updated, .claude/ install skipped."""
    touched = [
        "templates/agents/alpha.shared.md",
        "src/claude/alpha.md",
        "src/copilot-cli/agents/alpha.agent.md",
        "src/vs-code-agents/alpha.agent.md",
    ]
    violations = vip.find_violations(touched, repo_root=fake_repo)
    assert len(violations) == 1
    v = violations[0]
    assert ".claude/agents/alpha.md" in v.missing
    assert ".github/agents/alpha.agent.md" in v.missing
    # Members that were touched are NOT in missing.
    assert "templates/agents/alpha.shared.md" not in v.missing
    assert "src/claude/alpha.md" not in v.missing


def test_freestanding_copilot_agent_is_not_flagged(fake_repo: Path) -> None:
    """A .github/agents/X.agent.md without a template anchor is its own group."""
    touched = [".github/agents/gamma.agent.md"]
    assert vip.find_violations(touched, repo_root=fake_repo) == []


def test_freestanding_claude_agent_is_not_flagged(fake_repo: Path) -> None:
    """A .claude/agents/X.md without a template anchor is its own group.

    Regression test for agents like context-retrieval, adr-generator, and
    quality-auditor that exist only under .claude/agents/ without a shared
    template or .github/agents/ sibling. Solo edits should not trigger
    missing-sibling violations.
    """
    # Create a Claude-only agent with no template or GitHub sibling.
    (fake_repo / ".claude" / "agents" / "delta.md").write_text("# delta\n")
    touched = [".claude/agents/delta.md"]
    assert vip.find_violations(touched, repo_root=fake_repo) == []


def test_pure_install_resync_is_allowed_both_sides(fake_repo: Path) -> None:
    """Catch-up resync: install copies updated, canonical untouched. Allow."""
    touched = [
        ".claude/agents/alpha.md",
        ".github/agents/alpha.agent.md",
    ]
    assert vip.find_violations(touched, repo_root=fake_repo) == []


def test_pure_install_resync_is_allowed_claude_only(fake_repo: Path) -> None:
    """Partial resync (only Claude install) is still allowed."""
    touched = [".claude/agents/alpha.md"]
    assert vip.find_violations(touched, repo_root=fake_repo) == []


def test_pure_install_resync_is_allowed_github_only(fake_repo: Path) -> None:
    """Partial resync (only GitHub install) is still allowed."""
    touched = [".github/agents/alpha.agent.md"]
    assert vip.find_violations(touched, repo_root=fake_repo) == []


def test_install_plus_canonical_partial_is_still_drift(fake_repo: Path) -> None:
    """Carve-out applies only when touched set is ENTIRELY install members.

    The moment canonical (template) or a vendored copy enters the diff,
    every sibling must be present.
    """
    touched = [
        "templates/agents/alpha.shared.md",
        ".claude/agents/alpha.md",
    ]
    violations = vip.find_violations(touched, repo_root=fake_repo)
    assert len(violations) == 1
    v = violations[0]
    assert ".github/agents/alpha.agent.md" in v.missing
    assert "src/claude/alpha.md" in v.missing


def test_install_plus_src_partial_is_still_drift(fake_repo: Path) -> None:
    """src/ is vendored, not install; carve-out does not apply."""
    touched = [
        "src/claude/alpha.md",
        ".claude/agents/alpha.md",
    ]
    violations = vip.find_violations(touched, repo_root=fake_repo)
    assert len(violations) == 1
    v = violations[0]
    assert "templates/agents/alpha.shared.md" in v.missing


def test_rule_clean_diff(fake_repo: Path) -> None:
    touched = [
        ".claude/rules/beta.md",
        ".github/instructions/beta.instructions.md",
        "src/copilot-cli/instructions/beta.instructions.md",
    ]
    assert vip.find_violations(touched, repo_root=fake_repo) == []


def test_rule_canonical_only_drift_detected(fake_repo: Path) -> None:
    touched = [".claude/rules/beta.md"]
    violations = vip.find_violations(touched, repo_root=fake_repo)
    assert len(violations) == 1
    v = violations[0]
    assert v.kind == "RULE"
    assert v.name == "beta"
    assert ".github/instructions/beta.instructions.md" in v.missing
    assert "src/copilot-cli/instructions/beta.instructions.md" in v.missing


def test_rule_install_only_drift_detected(fake_repo: Path) -> None:
    """If only the install mirror moves, canonical must move too."""
    touched = [".github/instructions/beta.instructions.md"]
    violations = vip.find_violations(touched, repo_root=fake_repo)
    assert len(violations) == 1
    v = violations[0]
    assert ".claude/rules/beta.md" in v.missing


def test_multiple_independent_groups_each_validated(fake_repo: Path) -> None:
    touched = [
        "templates/agents/alpha.shared.md",  # drift: missing 5 siblings
        ".claude/rules/beta.md",  # drift: missing 2 mirrors
    ]
    violations = vip.find_violations(touched, repo_root=fake_repo)
    kinds = sorted(v.kind for v in violations)
    assert kinds == ["RULE", "SHARED_AGENT"]


def test_unrelated_paths_do_not_create_groups(fake_repo: Path) -> None:
    touched = ["README.md", "scripts/validation/pre_pr.py"]
    assert vip.find_violations(touched, repo_root=fake_repo) == []


def test_diff_with_path_prefix_normalization(fake_repo: Path) -> None:
    """``git diff`` may emit forward-slash paths; the validator normalizes."""
    touched = [
        "./templates/agents/alpha.shared.md",
        "./.claude/agents/alpha.md",
        "./.github/agents/alpha.agent.md",
        "./src/claude/alpha.md",
        "./src/copilot-cli/agents/alpha.agent.md",
        "./src/vs-code-agents/alpha.agent.md",
    ]
    assert vip.find_violations(touched, repo_root=fake_repo) == []


# --- CLI -----------------------------------------------------------------


def test_cli_files_mode_exit_zero_when_clean(
    capsys: pytest.CaptureFixture[str], fake_repo: Path
) -> None:
    argv = [
        "--repo-root",
        str(fake_repo),
        "--files",
        "templates/agents/alpha.shared.md",
        ".claude/agents/alpha.md",
        ".github/agents/alpha.agent.md",
        "src/claude/alpha.md",
        "src/copilot-cli/agents/alpha.agent.md",
        "src/vs-code-agents/alpha.agent.md",
    ]
    rc = vip.main(argv)
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out


def test_cli_files_mode_exit_one_on_drift(
    capsys: pytest.CaptureFixture[str], fake_repo: Path
) -> None:
    argv = [
        "--repo-root",
        str(fake_repo),
        "--files",
        "templates/agents/alpha.shared.md",
    ]
    rc = vip.main(argv)
    out = capsys.readouterr().out
    assert rc == 1
    assert "DRIFT" in out
    assert ".claude/agents/alpha.md" in out


def test_cli_json_format(
    capsys: pytest.CaptureFixture[str], fake_repo: Path
) -> None:
    argv = [
        "--repo-root",
        str(fake_repo),
        "--format",
        "json",
        "--files",
        "templates/agents/alpha.shared.md",
    ]
    rc = vip.main(argv)
    out = capsys.readouterr().out
    assert rc == 1
    payload = json.loads(out)
    assert payload["drift"] is True
    assert len(payload["violations"]) == 1
    v = payload["violations"][0]
    assert v["kind"] == "SHARED_AGENT"
    assert v["name"] == "alpha"
    assert ".claude/agents/alpha.md" in v["missing"]


def test_cli_repo_root_missing_returns_two(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    missing = tmp_path / "does-not-exist"
    argv = ["--repo-root", str(missing), "--files"]
    rc = vip.main(argv)
    err = capsys.readouterr().err
    assert rc == 2
    assert "repo root not found" in err


def test_cli_empty_files_list_passes(
    capsys: pytest.CaptureFixture[str], fake_repo: Path
) -> None:
    argv = ["--repo-root", str(fake_repo), "--files"]
    rc = vip.main(argv)
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out
