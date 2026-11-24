"""Guard the lossless-queue-reads rule against drift from its cited implementation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULE = (
    REPO_ROOT
    / "src"
    / "claude"
    / "skills"
    / "pr-comment-responder"
    / "references"
    / "rule-lossless-queue-reads.md"
)
TEMPLATE = REPO_ROOT / "templates" / "rules" / "lossless-queue-reads.md"
SKILL_TEMPLATE = REPO_ROOT / "templates" / "skills" / "pr-comment-responder.SKILL.md.tmpl"
CLUSTER = (
    REPO_ROOT
    / "src"
    / "claude"
    / "skills"
    / "pr-comment-responder"
    / "scripts"
    / "cluster_threads.py"
)
MAX_BYTES = 2200
REASONS = (
    "missing pagination info",
    "missing pagination cursor",
    "pagination exceeded 50 pages",
)
CITATION = re.compile(r"`(?P<path>[^`]*cluster_threads\.py):(?P<lo>\d+)-(?P<hi>\d+)`")


def _rule_text() -> str:
    return RULE.read_text(encoding="utf-8")


def test_rule_moved_out_of_the_always_on_rule_set() -> None:
    """The rule is a skill reference now: no template, and the skill links it."""
    assert not TEMPLATE.exists()
    assert RULE.is_file()
    assert "rule-lossless-queue-reads.md" in SKILL_TEMPLATE.read_text(encoding="utf-8")


def test_rule_records_its_former_always_on_scope() -> None:
    first = _rule_text().splitlines()[0]
    assert first.startswith("<!--")
    assert "lossless-queue-reads" in first
    assert "`**`" in first


def test_rule_stays_under_the_size_budget() -> None:
    assert len(RULE.read_bytes()) < MAX_BYTES


def test_rule_has_no_em_or_en_dash() -> None:
    dashes = chr(0x2013) + chr(0x2014)
    assert not re.search(f"[{dashes}]", _rule_text())


@pytest.mark.parametrize("reason", REASONS)
def test_rule_quotes_each_fail_fetch_reason(reason: str) -> None:
    assert f"`{reason}`" in _rule_text()


@pytest.mark.parametrize("reason", REASONS)
def test_cited_line_range_still_holds_each_reason(reason: str) -> None:
    cited = CITATION.search(_rule_text())
    assert cited, "rule must cite cluster_threads.py with a line range"
    assert (REPO_ROOT / cited["path"]) == CLUSTER
    lines = CLUSTER.read_text(encoding="utf-8").splitlines()
    window = lines[int(cited["lo"]) - 1 : int(cited["hi"])]
    assert any(f'_fail_fetch("{reason}"' in line for line in window)


@pytest.mark.parametrize("phrase", ("`head`", "`tail`", "`sed`", "MUST NOT", "fail loud"))
def test_rule_states_the_prohibitions(phrase: str) -> None:
    assert phrase in _rule_text()
