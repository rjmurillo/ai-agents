"""Guard replay attribution, matching, and failure accounting."""

from pathlib import Path

from scripts.eval import docs_review_agent_skill_docs_replay as replay
from scripts.validation import check_agent_skill_docs as gate


def test_match_requires_file_class_and_nearby_line():
    expected = {"file": "docs/skills/alpha.md", "defect_class": "missing-page", "line": 10}
    assert replay.matches(expected, dict(expected, line=13))
    assert not replay.matches(expected, dict(expected, line=14))
    assert not replay.matches(expected, dict(expected, file="docs/skills/beta.md"))
    assert not replay.matches(expected, dict(expected, defect_class="orphan-page"))


def test_structural_scope_keeps_only_changed_source_identities():
    affected = {"skills": {"alpha"}, "agents": {"reviewer"}}
    missing = replay.classify(gate.Finding("docs/skills/alpha.md", "skill 'alpha' has no page"))
    baseline = dict(missing, file="docs/skills/old.md")
    row = replay.classify(gate.Finding("docs/skills/README.md", "no table row links alpha.md"))
    agent = dict(missing, file="docs/agents/reviewer.md")
    assert replay.attributable(missing, affected)
    assert replay.attributable(row, affected)
    assert replay.attributable(agent, affected)
    assert not replay.attributable(baseline, affected)


def test_score_counts_advisories_on_negatives():
    warning = replay.classify(gate.Finding("docs/skills/alpha.md", "facts changed"), freshness=True)
    rows = [{"scope": "automated", "caught": True, "findings": []}]
    rows += [{"scope": "negative", "caught": None, "findings": []} for _ in range(12)]
    assert replay.score(rows)["passed"]
    rows[-1]["findings"] = [warning]
    result = replay.score(rows)
    assert result["false_positives"] == 1
    assert not result["passed"]
    rows[-1]["findings"] = []
    rows[0]["caught"] = False
    assert not replay.score(rows)["passed"]


def test_inspect_tree_does_not_filter_freshness(monkeypatch, tmp_path):
    monkeypatch.setattr(replay, "source_members", lambda *a: {"skills": set(), "agents": set()})
    monkeypatch.setattr(gate, "find_page_findings", lambda *a: gate.Report(0))
    warning = gate.Finding("docs/skills/existing.md", "facts changed")
    monkeypatch.setattr(gate, "find_stale_pages", lambda *a: gate.Report(1, [warning]))
    result = replay.inspect_tree(tmp_path, "base")
    assert result["findings"][0]["defect_class"] == "stale-page"
    assert result["excluded_preexisting"] == []


def test_cleanup_fetched_ref_when_checkout_fails(monkeypatch, tmp_path):
    calls = []

    def command(root: Path, *args: str) -> str:
        calls.append(args)
        if args[0] == "gh":
            return '{"baseRefOid":"base", "headRefOid":"head"}'
        if args[:3] == ("git", "worktree", "add"):
            raise RuntimeError("checkout failed")
        return "sha"

    monkeypatch.setattr(replay, "command", command)
    import pytest

    with pytest.raises(RuntimeError, match="checkout failed"):
        replay.replay(tmp_path, {"pr": 1, "sha": "abcdef1"}, "rjmurillo/ai-agents", "owned")
    assert calls[-1] == ("git", "update-ref", "-d", "refs/docs-review-agent-skill-docs/owned/1")
    assert not any(c[:3] == ("git", "worktree", "remove") for c in calls)


def test_replay_rejects_option_shaped_inputs():
    import pytest

    with pytest.raises(ValueError, match="revision"):
        replay.git_sha("--upload-pack=evil")
    with pytest.raises(ValueError, match="repository"):
        replay.repo_slug("--repo")
    with pytest.raises(ValueError, match="pull request"):
        replay.pr_number("1;rm")
    with pytest.raises(ValueError, match="ref token"):
        replay.ref_token("owned/../x")
