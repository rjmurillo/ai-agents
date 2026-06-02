"""Tests for scripts/validation/spec_contradiction.py.

Covers the Issue #1920 shift-left check that flags contradictions between a
PR description, its linked issues, and the committed agent frontmatter. The
canonical regression is the PR #1897 round-7 loop: Issue #1894 claimed
``model_tier: sonnet`` while the committed implementer frontmatter shipped
``model: opus``.

gh CLI and git I/O are mocked at the subprocess boundary (monkeypatching the
module's ``fetch_*`` and ``_changed_agent_files`` seams) so the tests never
touch the network or the live repository state.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "spec_contradiction.py"


def _load_module():
    """Load the script as a module under a stable name."""
    spec = importlib.util.spec_from_file_location("spec_contradiction", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sc = _load_module()


# --- Frontmatter fixtures --------------------------------------------------

_OPUS_AGENT = """---
name: implementer
description: Ships code.
model: opus
metadata:
  tier: builder
---

# Implementer
"""

_SONNET_AGENT = """---
name: helper
model: sonnet
---

# Helper
"""

_NO_FRONTMATTER = "# Just a heading\n\nNo frontmatter here.\n"


# --- extract_linked_issues -------------------------------------------------


def test_extract_linked_issues_finds_all_keywords():
    body = (
        "Closes #1894\n"
        "Fixes #100\n"
        "Resolves: #200\n"
        "Implements #300\n"
        "Refs #400\n"
    )
    assert sc.extract_linked_issues(body) == [1894, 100, 200, 300, 400]


def test_extract_linked_issues_deduplicates_preserving_order():
    body = "Fixes #5 and also closes #5 and resolves #7"
    assert sc.extract_linked_issues(body) == [5, 7]


def test_extract_linked_issues_empty_when_no_refs():
    assert sc.extract_linked_issues("No issue links here.") == []


def test_extract_linked_issues_handles_none():
    assert sc.extract_linked_issues("") == []


# --- extract_model_claims --------------------------------------------------


def test_extract_model_claims_matches_tier_variants():
    text = "model: sonnet and model_tier: opus and model-tier = haiku"
    assert sc.extract_model_claims(text) == {"sonnet", "opus", "haiku"}


def test_extract_model_claims_normalizes_case_and_backticks():
    text = "`model: Sonnet`"
    assert sc.extract_model_claims(text) == {"sonnet"}


def test_extract_model_claims_empty_when_no_tier():
    assert sc.extract_model_claims("model: gpt-4 is unsupported") == set()


# --- extract_numeric_claims ------------------------------------------------


def test_extract_numeric_claims_only_known_keys():
    text = "priority: 2 and version: 5 and unrelated: 99"
    claims = sc.extract_numeric_claims(text)
    assert claims == {"priority": {2}, "version": {5}}


def test_extract_numeric_claims_collects_multiple_values():
    text = "timeout: 30 then later timeout = 60"
    assert sc.extract_numeric_claims(text) == {"timeout": {30, 60}}


# --- parse_frontmatter -----------------------------------------------------


def test_parse_frontmatter_top_level_keys():
    front = sc.parse_frontmatter(_OPUS_AGENT)
    assert front["name"] == "implementer"
    assert front["model"] == "opus"


def test_parse_frontmatter_skips_nested_block():
    # `metadata:` opens a nested block; `tier:` is indented and must be skipped.
    front = sc.parse_frontmatter(_OPUS_AGENT)
    assert "tier" not in front
    assert "metadata" not in front


def test_parse_frontmatter_no_fence_returns_empty():
    assert sc.parse_frontmatter(_NO_FRONTMATTER) == {}


# --- find_contradictions (the core comparison) -----------------------------


def test_find_contradictions_flags_sonnet_spec_vs_opus_code():
    """PR #1897 regression: spec says sonnet, committed code is opus."""
    spec = "The implementer uses model_tier: sonnet per the spec."
    files = {"src/claude/implementer.md": _OPUS_AGENT}
    found = sc.find_contradictions(spec, "issue #1894", files)
    assert len(found) == 1
    c = found[0]
    assert c.axis == "model-tier"
    assert c.claimed == "sonnet"
    assert c.committed == "opus"
    assert c.file == "src/claude/implementer.md"
    assert c.source == "issue #1894"


def test_find_contradictions_no_flag_when_tiers_agree():
    spec = "The implementer uses model: opus."
    files = {"src/claude/implementer.md": _OPUS_AGENT}
    assert sc.find_contradictions(spec, "PR description", files) == []


def test_find_contradictions_no_claim_no_flag():
    spec = "This PR refactors logging. No model tier mentioned."
    files = {"src/claude/implementer.md": _OPUS_AGENT}
    assert sc.find_contradictions(spec, "PR description", files) == []


def test_find_contradictions_skips_files_without_model_frontmatter():
    spec = "model: sonnet"
    files = {"docs/readme.md": _NO_FRONTMATTER}
    assert sc.find_contradictions(spec, "PR description", files) == []


def test_find_contradictions_numeric_threshold_mismatch():
    spec = "Set priority: 1 in the spec."
    agent = "---\nname: a\nmodel: opus\npriority: 2\n---\n"
    files = {"src/claude/a.md": agent}
    found = sc.find_contradictions(spec, "PR description", files)
    numeric = [c for c in found if c.axis == "numeric"]
    assert len(numeric) == 1
    assert numeric[0].key == "priority"
    assert numeric[0].claimed == "1"
    assert numeric[0].committed == "2"


def test_find_contradictions_numeric_agrees_no_flag():
    spec = "priority: 2"
    agent = "---\nname: a\nmodel: opus\npriority: 2\n---\n"
    files = {"src/claude/a.md": agent}
    found = sc.find_contradictions(spec, "PR description", files)
    assert [c for c in found if c.axis == "numeric"] == []


# --- format_report ---------------------------------------------------------


def test_format_report_pass_message():
    assert "[PASS]" in sc.format_report([])


def test_format_report_lists_contradictions():
    c = sc.Contradiction(
        axis="model-tier",
        key="model",
        claimed="sonnet",
        committed="opus",
        file="src/claude/implementer.md",
        source="issue #1894",
    )
    report = sc.format_report([c])
    assert "[WARN]" in report
    assert "implementer.md" in report
    assert "issue #1894" in report
    assert "sonnet" in report
    assert "opus" in report


# --- collect_contradictions (mocked gh + git seams) ------------------------


def test_collect_contradictions_no_pr_returns_empty(monkeypatch):
    monkeypatch.setattr(sc, "fetch_current_pr_body", lambda owner, repo: None)
    result = sc.collect_contradictions(REPO_ROOT, "o", "r")
    assert result == []


def test_collect_contradictions_no_changed_files_returns_empty(monkeypatch):
    monkeypatch.setattr(
        sc, "fetch_current_pr_body", lambda owner, repo: "Fixes #1894"
    )
    monkeypatch.setattr(sc, "_resolve_base_ref", lambda repo_root: "origin/main")
    monkeypatch.setattr(sc, "_changed_agent_files", lambda repo_root, base: {})
    assert sc.collect_contradictions(REPO_ROOT, "o", "r") == []


def test_collect_contradictions_full_regression_flow(monkeypatch):
    """End-to-end PR #1897 scenario with all I/O mocked.

    PR body links Issue #1894; the issue body claims sonnet; the committed
    implementer frontmatter is opus. The check must surface one contradiction
    sourced from the issue.
    """
    monkeypatch.setattr(
        sc,
        "fetch_current_pr_body",
        lambda owner, repo: "This PR ships the implementer. Fixes #1894.",
    )
    monkeypatch.setattr(sc, "_resolve_base_ref", lambda repo_root: "origin/main")
    monkeypatch.setattr(
        sc,
        "_changed_agent_files",
        lambda repo_root, base: {"src/claude/implementer.md": _OPUS_AGENT},
    )
    monkeypatch.setattr(
        sc,
        "fetch_issue_body",
        lambda number, owner, repo: "Spec: the implementer must use model_tier: sonnet.",
    )

    result = sc.collect_contradictions(REPO_ROOT, "o", "r")
    assert len(result) == 1
    assert result[0].source == "issue #1894"
    assert result[0].claimed == "sonnet"
    assert result[0].committed == "opus"


def test_collect_contradictions_pr_body_claim_flagged(monkeypatch):
    """A contradiction in the PR body itself (not just the issue) is flagged."""
    monkeypatch.setattr(
        sc,
        "fetch_current_pr_body",
        lambda owner, repo: "The implementer uses model: sonnet.",
    )
    monkeypatch.setattr(sc, "_resolve_base_ref", lambda repo_root: "origin/main")
    monkeypatch.setattr(
        sc,
        "_changed_agent_files",
        lambda repo_root, base: {"src/claude/implementer.md": _OPUS_AGENT},
    )
    result = sc.collect_contradictions(REPO_ROOT, "o", "r")
    assert any(c.source == "PR description" for c in result)


def test_collect_contradictions_issue_fetch_failure_skipped(monkeypatch):
    """An unreachable linked issue is skipped, not fatal."""
    monkeypatch.setattr(
        sc, "fetch_current_pr_body", lambda owner, repo: "Fixes #1894"
    )
    monkeypatch.setattr(sc, "_resolve_base_ref", lambda repo_root: "origin/main")
    monkeypatch.setattr(
        sc,
        "_changed_agent_files",
        lambda repo_root, base: {"src/claude/implementer.md": _OPUS_AGENT},
    )
    monkeypatch.setattr(sc, "fetch_issue_body", lambda number, owner, repo: None)
    # PR body has no model claim and the only issue is unreachable, so no flag.
    assert sc.collect_contradictions(REPO_ROOT, "o", "r") == []


# --- main (exit codes; ADR-035) --------------------------------------------


def test_main_advisory_exits_zero_on_contradiction(monkeypatch, capsys):
    monkeypatch.setattr(sc, "get_repo_info", lambda: sc.RepoInfo("o", "r"))
    c = sc.Contradiction("model-tier", "model", "sonnet", "opus", "f.md", "issue #1")
    monkeypatch.setattr(
        sc, "collect_contradictions", lambda root, owner, repo: [c]
    )
    code = sc.main(["--advisory"])
    assert code == 0
    assert "[WARN]" in capsys.readouterr().out


def test_main_strict_exits_one_on_contradiction(monkeypatch, capsys):
    monkeypatch.setattr(sc, "get_repo_info", lambda: sc.RepoInfo("o", "r"))
    c = sc.Contradiction("model-tier", "model", "sonnet", "opus", "f.md", "issue #1")
    monkeypatch.setattr(
        sc, "collect_contradictions", lambda root, owner, repo: [c]
    )
    code = sc.main([])
    assert code == 1


def test_main_exits_zero_when_clean(monkeypatch, capsys):
    monkeypatch.setattr(sc, "get_repo_info", lambda: sc.RepoInfo("o", "r"))
    monkeypatch.setattr(sc, "collect_contradictions", lambda root, owner, repo: [])
    code = sc.main([])
    assert code == 0
    assert "[PASS]" in capsys.readouterr().out


def test_main_config_error_when_repo_unresolvable(monkeypatch):
    def _raise() -> sc.RepoInfo:
        raise RuntimeError("Could not determine git remote origin")

    monkeypatch.setattr(sc, "get_repo_info", _raise)
    # No --owner/--repo provided, so the script must resolve and fail with 2.
    code = sc.main([])
    assert code == 2
