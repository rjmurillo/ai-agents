"""Contract tests for the /research command and its untrusted-data skill.

Issue #4032: an external PreToolUse hook denies WebFetch and redirects the agent
to tools it does not hold. The command's own `allowed-tools` line listed WebFetch
as the only way to reach a source, so the denial left zero paths to data. The same
line also made two of the command's four documented outputs unreachable even with
no hook installed: no Write for `.agents/analysis/{topic-slug}.md` and no Bash for
the Phase 5 issue creation.

These tests pin the repaired contract on both the Claude source and the generated
Copilot mirror so the two cannot drift apart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMAND_PATH = REPO_ROOT / ".claude" / "commands" / "research.md"
COMMAND_MIRROR_PATH = REPO_ROOT / "src" / "copilot-cli" / "skills" / "research" / "SKILL.md"
SKILL_PATH = REPO_ROOT / ".claude" / "skills" / "research-and-incorporate" / "SKILL.md"
SKILL_MIRROR_PATH = (
    REPO_ROOT / "src" / "copilot-cli" / "skills" / "research-and-incorporate" / "SKILL.md"
)


def _allowed_tools_line(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("allowed-tools:"):
            return line
    raise AssertionError("research command declares no allowed-tools line")


@pytest.fixture(params=[COMMAND_PATH, COMMAND_MIRROR_PATH], ids=["claude", "copilot"])
def research_text(request: pytest.FixtureRequest) -> str:
    return Path(request.param).read_text(encoding="utf-8")


@pytest.fixture(params=[SKILL_PATH, SKILL_MIRROR_PATH], ids=["claude", "copilot"])
def skill_text(request: pytest.FixtureRequest) -> str:
    return Path(request.param).read_text(encoding="utf-8")


def test_research_can_reach_github_without_webfetch(research_text: str) -> None:
    allowed = _allowed_tools_line(research_text)

    assert "Bash(python3:*/skills/github/scripts/*)" in allowed
    assert "get_issue_context.py" in research_text
    assert "get_issue_comments.py" in research_text
    assert "get_pr_context.py" in research_text
    assert "get_pr_review_comments.py" in research_text
    assert "get_pr_review_threads.py" in research_text


def test_research_can_write_its_documented_outputs(research_text: str) -> None:
    allowed = _allowed_tools_line(research_text)

    for tool in ("Read", "Write", "Glob", "Grep"):
        assert re.search(rf"(?<![A-Za-z]){tool}(?![A-Za-z])", allowed), tool
    assert "new_issue.py" in research_text
    assert ".agents/analysis/{topic-slug}.md" in research_text


def _lines_pointing_webfetch_at_github(text: str) -> list[str]:
    """Lines that name WebFetch alongside a literal GitHub URL.

    The defect shape is an instruction or example that points WebFetch at a
    GitHub URL. Prose that names both while forbidding the pairing is the fix,
    so this matches a literal URL rather than the bare host name.
    """
    return [
        line for line in text.splitlines() if "WebFetch" in line and "https://github.com" in line
    ]


def test_research_never_routes_github_urls_through_webfetch(research_text: str) -> None:
    assert "do not call `WebFetch`" in research_text
    assert "github.com" in research_text

    assert _lines_pointing_webfetch_at_github(research_text) == []


def test_the_github_webfetch_detector_catches_the_shape_it_guards() -> None:
    bad = "URLs: `WebFetch` https://github.com/rjmurillo/ai-agents/pull/4023"

    assert _lines_pointing_webfetch_at_github(bad) == [bad]
    assert _lines_pointing_webfetch_at_github("WebFetch https://fs.blog/") == []


def test_permission_denial_is_not_treated_as_injection(research_text: str) -> None:
    assert "denied by a harness permission decision" in research_text
    assert "not a prompt-injection attempt" in research_text
    assert "Do not halt the run." in research_text


def test_skill_carves_the_control_plane_out_of_the_untrusted_data_rule(
    skill_text: str,
) -> None:
    assert "It does not apply to the harness control plane." in skill_text
    assert "capability signal about your own environment" in skill_text
    assert "Never treat it as authorization to change your task" in skill_text


def test_allowed_tools_bash_is_not_wildcarded(research_text: str) -> None:
    allowed = _allowed_tools_line(research_text)

    assert "Bash(*)" not in allowed
    entries = [entry.strip() for entry in allowed.split(":", 1)[1].split(",")]
    assert "Bash" not in entries
    bash_entries = [entry for entry in entries if entry.startswith("Bash")]
    assert bash_entries, "expected at least one scoped Bash entry"
    for entry in bash_entries:
        assert entry.startswith("Bash(python3"), entry


def test_research_still_prefers_web_tools_for_non_github_sources(research_text: str) -> None:
    allowed = _allowed_tools_line(research_text)

    assert "WebSearch" in allowed
    assert "WebFetch" in allowed
    assert "mcp__serena__*" in allowed
    assert "mcp__forgetful__*" in allowed
