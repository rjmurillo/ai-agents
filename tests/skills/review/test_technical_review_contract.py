"""Contract tests for the review skill's technical-review contract (issue #5395).

Covers: the contract file states every required section and a verdict rule
that `extract_verdict` parses; the capability blocks declare the owners and
edges the graph relies on; the `review` template runs the step 4c pass with
the CONTEXT_MODE-prefixed diff; and `code-reviewer` depends on the contract
instead of restating the doctrine that moved into it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from scripts.ai_review_common.verdict import extract_verdict, merge_verdicts

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_CONTRACT = PROJECT_ROOT / ".claude" / "skills" / "review" / "resources" / "technical-review.md"
_REVIEW_TEMPLATE = PROJECT_ROOT / "templates" / "skills" / "review.SKILL.md.tmpl"
_FENCE_TEMPLATE = PROJECT_ROOT / "templates" / "skills" / "chestertons-fence.SKILL.md.tmpl"
_AGENT_SHARED = PROJECT_ROOT / "templates" / "agents" / "code-reviewer.shared.md"
_UNTRUSTED_AGENT_PARTIAL = (
    PROJECT_ROOT / "templates" / "agents" / "partials" / "untrusted-content.mustache"
)

_REQUIRED_CONTRACT_HEADINGS = (
    "Scope and coverage accounting",
    "Untrusted content",
    "Necessity and design first",
    "Evidence order",
    "Convention discovery",
    "Reasoning protocol",
    "Edge cases and concurrency",
    "Test semantics",
    "Comments",
    "Code-intent analysis",
    "Yell-test proposal",
    "Specialist routing",
    "Finding shape",
    "Verdict",
)

# Sentences distinctive to the doctrine that moved out of the agent.
_MOVED_DOCTRINE_SENTENCES = (
    "Report only findings scored 80 or higher",
    "Do not assume a file named CLAUDE.md exists",
    "Emit findings in this exact order, with no preamble beyond the Summary",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing required file: {path}"
    return path.read_text(encoding="utf-8")


def _headings(text: str) -> set[str]:
    return set(re.findall(r"(?m)^## (.+?)\s*$", text))


def _capability(text: str) -> dict:
    """Return the parsed metadata.capability block of a frontmatter file."""
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, "no frontmatter block"
    front = yaml.safe_load(match.group(1)) or {}
    return (front.get("metadata") or {}).get("capability") or {}


def _moved_doctrine_in(text: str) -> str | None:
    return next((s for s in _MOVED_DOCTRINE_SENTENCES if s in text), None)


def _verdict_rules(text: str) -> dict[str, str]:
    """Map each numbered verdict rule's lead clause to the token it names."""
    section = text.split("## Verdict", 1)[1]
    rules = re.findall(r"(?ms)^\d+\. (.+?): `(PASS|WARN|CRITICAL_FAIL)`\.", section)
    return {clause.split(",")[0].strip(): token for clause, token in rules}


class TestContractShape:
    TEXT = _read(_CONTRACT)

    def test_every_required_heading_is_a_real_h2(self) -> None:
        missing = set(_REQUIRED_CONTRACT_HEADINGS) - _headings(self.TEXT)
        assert not missing, missing

    def test_heading_parser_rejects_a_heading_that_is_only_prose(self) -> None:
        assert "Verdict" not in _headings("The Verdict section says ## Verdict inline.")

    def test_post_2023_invariant_is_stated(self) -> None:
        assert "evidence earns preservation, complexity does not" in self.TEXT

    def test_context_mode_other_than_full_is_partial(self) -> None:
        assert "anything but `full` is partial context" in self.TEXT

    def test_no_em_or_en_dash(self) -> None:
        assert not {chr(0x2013), chr(0x2014)} & set(self.TEXT)


class TestContractVerdictRule:
    TEXT = _read(_CONTRACT)

    def test_blocking_maps_to_critical_fail(self) -> None:
        assert _verdict_rules(self.TEXT)["Any `blocking` finding remaining"] == "CRITICAL_FAIL"

    def test_unverified_state_cannot_reach_pass(self) -> None:
        section = self.TEXT.split("## Verdict", 1)[1]
        warn_rule = re.search(r"(?ms)^2\. (.+?)`WARN`", section)
        assert warn_rule, "no WARN rule"
        for state in ("partial", "hazard", "skipped specialist", "neither reviewed nor excluded"):
            assert state in warn_rule.group(1), state

    def test_rule_parser_rejects_a_rule_with_no_token(self) -> None:
        assert _verdict_rules("## Verdict\n\n1. Any finding: `MAYBE`.\n") == {}

    @pytest.mark.parametrize("token", ["PASS", "WARN", "CRITICAL_FAIL"])
    def test_every_emitted_token_parses(self, token: str) -> None:
        assert extract_verdict(f"findings\nVERDICT: {token}\n") == token

    def test_template_form_line_does_not_parse_as_a_verdict(self) -> None:
        assert extract_verdict("VERDICT: PASS|WARN|CRITICAL_FAIL\n") != "PASS"

    def test_correctness_warn_is_not_hidden_by_other_passes(self) -> None:
        assert merge_verdicts(["PASS", "PASS", "WARN"]) == "WARN"


class TestCapabilityBlocks:
    def test_review_owns_technical_review_and_depends_on_archaeology(self) -> None:
        cap = _capability(_read(_REVIEW_TEMPLATE))
        assert cap["kind"] == "orchestrator"
        assert cap["owns"] == ["technical-review"]
        assert set(cap["depends-on"]) == {"code-archaeology", "untrusted-content-handling"}

    def test_fence_owns_archaeology_with_no_edge_back(self) -> None:
        cap = _capability(_read(_FENCE_TEMPLATE))
        assert cap["kind"] == "reusable-primitive"
        assert cap["owns"] == ["code-archaeology"]
        assert "technical-review" not in (cap.get("depends-on") or [])

    def test_agent_owns_nothing_and_depends_on_the_contract(self) -> None:
        cap = _capability(_read(_AGENT_SHARED))
        assert cap["kind"] == "specialized-implementation"
        assert not cap.get("owns")
        assert set(cap["depends-on"]) == {"technical-review", "untrusted-content-handling"}

    def test_capability_parser_sees_a_wrong_owner(self) -> None:
        text = "---\nmetadata:\n  capability:\n    owns: [other]\n---\nbody\n"
        assert _capability(text)["owns"] != ["technical-review"]


class TestReviewTemplateRunsTheCorrectnessPass:
    TEXT = _read(_REVIEW_TEMPLATE)

    def _step_4c(self) -> str:
        match = re.search(r"(?m)^4c\. .+$", self.TEXT)
        assert match, "step 4c missing"
        return match.group(0)

    def test_step_4c_dispatches_code_reviewer_with_the_contract(self) -> None:
        step = self._step_4c()
        assert 'Task(subagent_type="code-reviewer")' in step
        assert "resources/technical-review.md" in step
        assert "general-purpose" in step

    def test_step_4c_passes_the_context_mode_prefixed_diff(self) -> None:
        assert "CONTEXT_MODE-prefixed diff" in self._step_4c()

    def test_merge_step_includes_the_correctness_verdict(self) -> None:
        merge = re.search(r"(?m)^7\. .+$", self.TEXT)
        assert merge and "step 4c correctness verdict" in merge.group(0)


class TestAgentCarriesNoMovedDoctrine:
    TEXT = _read(_AGENT_SHARED)

    def test_no_moved_doctrine_sentence(self) -> None:
        assert _moved_doctrine_in(self.TEXT) is None

    def test_leak_detector_reports_a_leak(self) -> None:
        leaked = "Some prose. Report only findings scored 80 or higher. More prose."
        assert _moved_doctrine_in(leaked) == "Report only findings scored 80 or higher"

    def test_agent_loads_the_contract_from_the_copilot_root_first(self) -> None:
        first = re.search(r"(?m)^1\. `(.+?)`$", self.TEXT)
        assert first and first.group(1).startswith("${COPILOT_PLUGIN_ROOT:-")

    def test_untrusted_block_stays_byte_identical_to_the_partial(self) -> None:
        assert _read(_UNTRUSTED_AGENT_PARTIAL) in self.TEXT
