"""Guards for the doc review gate's history ordering.

Rule: ``templates/rules/agent-skill-docs.md`` MUST 2. A page edit or a
``Docs-Reviewed:`` trailer counts only at or after each change to the
source. Merge commits and whitespace-only commits are skipped, so a GitHub
merge checkout and a formatter run cannot open or wedge the gate.
"""

from __future__ import annotations

from scripts.validation import check_agent_skill_doc_review as review
from tests.validation.test_check_agent_skill_doc_review import (
    _BODY_NEW,
    _BODY_OLD,
    _with_agent,
)
from tests.validation.test_check_agent_skill_docs import (
    _commit,
    _edit,
    _git,
    _paths,
)

# A review must not predate any change it covers


def test_trailer_before_a_later_source_change_does_not_clear(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha\n\nDocs-Reviewed: alpha")
    _edit(skill / "SKILL.md", _BODY_NEW, "A second, unreviewed change.")
    _commit(repo, "change alpha again")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/skills/alpha.md"]


def test_page_edit_before_a_later_source_change_does_not_clear(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(repo / "docs" / "skills" / "alpha.md", "## Related\n\nText.", "## Related\n\nEarly.")
    _commit(repo, "edit page first")
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha later")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/skills/alpha.md"]


def test_committed_trailer_does_not_cover_an_uncommitted_change(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha\n\nDocs-Reviewed: alpha")
    _edit(skill / "SKILL.md", _BODY_NEW, "Still being edited.")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/skills/alpha.md"]


def test_rendered_copilot_agent_change_counts(tmp_path):
    repo, _, _ = _with_agent(tmp_path)
    rendered = repo / "src" / "copilot-cli" / "agents" / "critic.agent.md"
    rendered.parent.mkdir(parents=True)
    rendered.write_text("Old Copilot body.\n", encoding="utf-8")
    _commit(repo, "render critic for Copilot")
    _git(repo, "branch", "-f", "base", "HEAD")
    rendered.write_text("Body from a changed Copilot-only partial.\n", encoding="utf-8")
    _commit(repo, "copilot partial edit")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/agents/critic.md"]


def test_missing_git_is_config_error(tmp_path, monkeypatch):
    repo, _, _ = _with_agent(tmp_path)

    def absent(_root, *_args):
        raise FileNotFoundError("git")

    monkeypatch.setattr(review, "_git", absent)

    assert review.main([str(repo), "--base-ref", "base"]) == 2


# Merge checkouts and whitespace-only commits


def test_ci_merge_where_base_also_changed_the_source_honours_trailer(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", "| 0 | Success |", "| 0 | Success, all checks clean |")
    _commit(repo, "base edits the same source far away")
    _git(repo, "branch", "-f", "base", "HEAD")
    _git(repo, "checkout", "-q", "HEAD~1")
    _git(repo, "checkout", "-q", "-b", "feature")
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha\n\nDocs-Reviewed: alpha")
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

    assert review.main([str(repo), "--base-ref", "base"]) == 0


def test_whitespace_page_commit_after_source_change_does_not_clear(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    page = repo / "docs" / "skills" / "alpha.md"
    _edit(page, "## Related\n\nText.", "## Related\n\nReal early edit.")
    _commit(repo, "page edit first")
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha")
    page.write_text(page.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    _commit(repo, "format page")

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/skills/alpha.md"]


def test_whitespace_source_commit_after_trailer_still_clears(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha\n\nDocs-Reviewed: alpha")
    (skill / "SKILL.md").write_text(
        (skill / "SKILL.md").read_text(encoding="utf-8") + "\n\n", encoding="utf-8"
    )
    _commit(repo, "format source")

    assert review.find_unreviewed(repo, "base").findings == []


def test_whitespace_only_dirty_source_keeps_its_trailer(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "change alpha\n\nDocs-Reviewed: alpha")
    _edit(skill / "SKILL.md", _BODY_NEW, f"{_BODY_NEW}   \n\n")
    assert review.find_unreviewed(repo, "base").findings == []


def test_untracked_source_is_not_covered_by_an_older_trailer(tmp_path):
    repo, _, _ = _with_agent(tmp_path)
    _git(
        repo,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=t",
        "commit",
        "--allow-empty",
        "-qm",
        "early\n\nDocs-Reviewed: critic",
    )
    (repo / "templates/agents/critic.claude.md.tmpl").write_text("New.\n", encoding="utf-8")
    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/agents/critic.md"]


def test_sibling_source_commits_each_need_a_review(tmp_path):
    repo, skill, _ = _with_agent(tmp_path)
    _git(repo, "checkout", "-q", "-b", "side")
    _edit(skill / "SKILL.md", "| 0 | Success |", "| 0 | Success, unreviewed |")
    _commit(repo, "side edits alpha with no review")
    _git(repo, "checkout", "-q", "-b", "feature", "base")
    _edit(skill / "SKILL.md", _BODY_OLD, _BODY_NEW)
    _commit(repo, "feature edits alpha\n\nDocs-Reviewed: alpha")
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
        "merge side",
        "side",
    )

    assert _paths(review.find_unreviewed(repo, "base")) == ["docs/skills/alpha.md"]
