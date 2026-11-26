"""Guards for the skill and agent doc review gate.

Rule: ``templates/rules/agent-skill-docs.md`` MUST 2. Past miss this
reproduces: PR #7572 changed what ``ship`` does and left ``docs/skills/ship.md``
describing the old flow, and no check flagged it.

Coverage:

- positive: a changed source passes with a page edit (committed or not), or
  with a ``Docs-Reviewed:`` trailer that names it, alone or in a list.
- negative: a changed skill or agent with neither fails, a trailer naming
  another source does not clear it, and a trailer on the base branch after
  the fork does not clear it.
- edge: whitespace-only edits, new sources, and deleted sources are skipped;
  a bad base ref is exit 3; the failure prints the exact trailer to paste.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.validation import check_agent_skill_doc_review as review
from tests.validation.test_check_agent_skill_docs import (
    _agent,
    _commit,
    _committed_repo,
    _edit,
    _git,
    _page,
    _paths,
    _row,
    _skill,
)

_BODY_OLD = "Plain wording."
_BODY_NEW = "The skill now opens the PR through push-pr."


def _with_agent(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo, skill = _committed_repo(tmp_path)
    _agent(repo, "critic")
    _page(repo, "agents", "critic")
    _row(repo, "agents", "critic")
    _commit(repo, "add critic")
    _git(repo, "branch", "base")
    return repo, skill, repo / "templates" / "agents" / "critic.shared.md"


# Negative


def test_pr_7572_ship_body_change_without_page_or_trailer_fails(tmp_path, capsys):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "refactor(skills): move PR creation")

    report = review.find_unreviewed(repo, "base")

    assert _paths(report) == ["docs/skills/alpha.md"]
    assert report.examined == 1
    assert review.main([str(repo), "--base-ref", "base"]) == 1
    assert "Docs-Reviewed: alpha" in capsys.readouterr().err


def test_agent_template_change_without_page_fails(tmp_path):
    repo, _, agent = _with_agent(tmp_path)
    agent.write_text("---\nname: critic\n---\n\nNow writes a verdict file.\n", encoding="utf-8")
    _commit(repo, "change critic")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/agents/critic.md"]


def test_trailer_naming_another_source_does_not_clear(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha\n\nDocs-Reviewed: beta")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/skills/alpha.md"]


def test_trailer_on_base_after_fork_does_not_clear(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature")
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha")
    _git(repo, "checkout", "-q", "base")
    (repo / "notes.txt").write_text("x\n", encoding="utf-8")
    _commit(repo, "unrelated\n\nDocs-Reviewed: alpha")
    _git(repo, "checkout", "-q", "feature")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/skills/alpha.md"]


# Positive


def test_committed_page_edit_clears(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _edit(repo / "docs" / "skills" / "alpha.md", "## Related\n\nText.", "## Related\n\nNew.")
    _commit(repo, "change alpha and its page")

    report = review.find_unreviewed(repo, "base")

    assert report.findings == []
    assert report.examined == 1


def test_uncommitted_page_edit_clears(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _edit(repo / "docs" / "skills" / "alpha.md", "## Related\n\nText.", "## Related\n\nNew.")

    assert review.find_unreviewed(repo, "base").findings == []


def test_trailer_list_clears_skill_and_agent(tmp_path, capsys):
    repo, skill, agent = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    agent.write_text("---\nname: critic\n---\n\nChanged.\n", encoding="utf-8")
    _commit(repo, "bulk refactor\n\nDocs-Reviewed: alpha, critic")

    report = review.find_unreviewed(repo, "base")

    assert report.findings == []
    assert report.examined == 2
    assert review.main([str(repo), "--base-ref", "base"]) == 0
    assert "0 unreviewed of 2 changed" in capsys.readouterr().out


def test_trailers_across_commits_combine(tmp_path):
    repo, skill, agent = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "one\n\nDocs-Reviewed: alpha")
    agent.write_text("---\nname: critic\n---\n\nChanged.\n", encoding="utf-8")
    _commit(repo, "two\n\nDocs-Reviewed: critic")

    assert review.find_unreviewed(repo, "base").findings == []


# Edge


def test_whitespace_only_change_is_not_examined(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, "Plain   wording.\n\n")

    report = review.find_unreviewed(repo, "base")

    assert report.examined == 0
    assert report.findings == []


def test_new_skill_is_left_to_the_page_check(tmp_path):
    repo, _, _ = _with_agent(tmp_path)
    _skill(repo, "beta")

    assert review.find_unreviewed(repo, "base").examined == 0


def test_deleted_skill_is_left_to_the_page_check(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    (skill / "SKILL.md").unlink()
    _commit(repo, "remove alpha")

    assert review.find_unreviewed(repo, "base").examined == 0


def test_bad_base_ref_is_external_error(tmp_path, capsys):
    repo, _, _ = _with_agent(tmp_path)

    assert review.main([str(repo), "--base-ref", "no-such-ref"]) == 3
    assert "merge-base" in capsys.readouterr().err


def test_invalid_root_is_config_error(tmp_path):
    assert review.main([str(tmp_path / "missing"), "--base-ref", "main"]) == 2


def test_no_base_ref_is_config_error(tmp_path, monkeypatch):
    repo, _, _ = _with_agent(tmp_path)
    monkeypatch.setattr(review, "_resolve_default_base_ref", lambda _root: None)

    assert review.run(repo, None) == 2


def test_changed_sources_maps_both_trees_and_agents():
    sources = review.changed_sources(
        {
            "src/claude/skills/ship/SKILL.md",
            ".claude/skills/local/SKILL.md",
            "templates/agents/critic.shared.md",
            "src/claude/skills/ship/references/x.md",
            "docs/skills/ship.md",
        }
    )

    assert sources == {
        "src/claude/skills/ship/SKILL.md": ("skills", "ship"),
        ".claude/skills/local/SKILL.md": ("skills", "local"),
        "templates/agents/critic.shared.md": ("agents", "critic"),
    }


def test_template_edits_require_review_once_per_page(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    template = repo / "templates/skills/alpha.SKILL.md.tmpl"
    template.parent.mkdir()
    template.write_text("New template.\n", encoding="utf-8")
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    host = repo / "templates/agents/critic.claude.md.tmpl"
    host.write_text("New host template.\n", encoding="utf-8")

    report = review.find_unreviewed(repo, "base")

    assert report.examined == 2
    assert _paths(report) == ["docs/agents/critic.md", "docs/skills/alpha.md"]
    assert "alpha.SKILL.md.tmpl" in report.findings[1].message


def test_ambiguous_trailer_requires_qualified_name(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _agent(repo, "alpha")
    _page(repo, "agents", "alpha")
    _row(repo, "agents", "alpha")
    _commit(repo, "add alpha agent")
    _git(repo, "branch", "-f", "base", "HEAD")
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha skill\n\nDocs-Reviewed: alpha")

    report = review.find_unreviewed(repo, "base")
    assert _paths(report) == ["docs/skills/alpha.md"]
    assert "skills/alpha" in report.findings[0].message

    _git(
        repo,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "--allow-empty",
        "-qm",
        "record review\n\nDocs-Reviewed: skills/alpha",
    )
    assert review.find_unreviewed(repo, "base").findings == []


# Rendered agents, whitespace, CI merge checkouts, and git error paths


def test_whitespace_only_page_edit_does_not_clear(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    page = repo / "docs" / "skills" / "alpha.md"
    page.write_text(page.read_text(encoding="utf-8") + "\n\n   \n", encoding="utf-8")
    _commit(repo, "change alpha, touch page whitespace")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/skills/alpha.md"]


def test_page_edit_on_base_after_fork_does_not_clear_branch_change(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _git(repo, "checkout", "-q", "-b", "feature")
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha")
    _git(repo, "checkout", "-q", "base")
    _edit(repo / "docs" / "skills" / "alpha.md", "## Related\n\nText.", "## Related\n\nBase.")
    _commit(repo, "base edits the page")
    _git(repo, "checkout", "-q", "feature")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/skills/alpha.md"]


def _ci_merge_head(repo: Path, message: str) -> None:
    """Build the GitHub pull_request checkout shape: a merge of feature into base."""
    _git(repo, "checkout", "-q", "-b", "feature")
    skill_md = repo / "src" / "claude" / "skills" / "alpha" / "SKILL.md"
    _edit(skill_md, _BODY_OLD, _BODY_NEW)
    _commit(repo, message)
    _git(repo, "checkout", "-q", "base")
    (repo / "base.txt").write_text("moved on\n", encoding="utf-8")
    _commit(repo, "base moves on")
    _git(repo, "checkout", "-q", "--detach", "base")
    _git(
        repo,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "merge",
        "-q",
        "--no-ff",
        "-m",
        "Merge feature into base",
        "feature",
    )


def test_ci_merge_commit_head_honours_branch_trailer(tmp_path):
    repo, _, _ = _with_agent(tmp_path)
    _ci_merge_head(repo, "change alpha\n\nDocs-Reviewed: alpha")

    assert review.main([str(repo), "--base-ref", "base"]) == 0


def test_ci_merge_commit_head_without_trailer_fails(tmp_path):
    repo, _, _ = _with_agent(tmp_path)
    _ci_merge_head(repo, "change alpha")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/skills/alpha.md"]


def test_rendered_agent_change_from_partial_counts(tmp_path):
    repo, _, _ = _with_agent(tmp_path)
    rendered = repo / "src" / "claude" / "agents" / "critic.md"
    rendered.parent.mkdir(parents=True)
    rendered.write_text("Old rendered body.\n", encoding="utf-8")
    _commit(repo, "render critic")
    _git(repo, "branch", "-f", "base", "HEAD")
    rendered.write_text("Body from a changed partial.\n", encoding="utf-8")
    _commit(repo, "partial edit re-renders critic")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/agents/critic.md"]


def test_fix_text_puts_trailer_before_findings(tmp_path, capsys):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha")

    assert review.main([str(repo), "--base-ref", "base"]) == 1
    err = capsys.readouterr().err
    assert err.index("Docs-Reviewed: alpha") < err.index("docs/skills/alpha.md:")
    assert "final trailer block" in err
    assert "Commit the source change first" in err


def test_git_log_failure_is_external_error(tmp_path, monkeypatch, capsys):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    real = review._git

    def failing(root, *args):
        if args[0] == "log":
            return subprocess.CompletedProcess(args, 128, "", "fatal: bad revision\n")
        return real(root, *args)

    monkeypatch.setattr(review, "_git", failing)

    assert review.main([str(repo), "--base-ref", "base"]) == 3
    assert "fatal: bad revision" in capsys.readouterr().err


def test_git_timeout_is_external_error(tmp_path, monkeypatch):
    repo, _, _ = _with_agent(tmp_path)

    def hung(_root, *args):
        raise subprocess.TimeoutExpired(["git", *args], 60)

    monkeypatch.setattr(review, "_git", hung)

    assert review.main([str(repo), "--base-ref", "base"]) == 3


def test_option_shaped_base_ref_is_config_error(tmp_path):
    repo, _, _ = _with_agent(tmp_path)

    assert review.main([str(repo), "--base-ref=--output=/tmp/x"]) == 2
