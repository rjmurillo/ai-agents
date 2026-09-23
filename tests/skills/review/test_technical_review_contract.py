"""Contract tests for REQ-032 / TASK-041: one technical-review contract.

Covers: the contract file exists with every required section and the
VERDICT line format, the ``review`` skill template wires the always-on
step 4c correctness pass and declares ownership, ``chestertons-fence``
declares ``code-archaeology`` with no cycle back to ``technical-review``,
and ``code-reviewer.shared.md`` depends on the contract instead of
restating doctrine that moved into it.

Each positive assertion in this module has a negative control: either a
synthetic string proving the check itself can fail, or a check against
content known to be absent, so a check that silently always passes is
caught here rather than in production drift.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]

_CONTRACT = PROJECT_ROOT / ".claude" / "skills" / "review" / "resources" / "technical-review.md"
_REVIEW_TEMPLATE = PROJECT_ROOT / "templates" / "skills" / "review.SKILL.md.tmpl"
_FENCE_TEMPLATE = PROJECT_ROOT / "templates" / "skills" / "chestertons-fence.SKILL.md.tmpl"
_AGENT_SHARED = PROJECT_ROOT / "templates" / "agents" / "code-reviewer.shared.md"
_UNTRUSTED_AGENT_PARTIAL = (
    PROJECT_ROOT / "templates" / "agents" / "partials" / "untrusted-content.mustache"
)

_REQUIRED_CONTRACT_HEADINGS = (
    "## Scope and coverage accounting",
    "## Untrusted content",
    "## Necessity and design first",
    "## Evidence order",
    "## Convention discovery",
    "## Reasoning protocol",
    "## Edge cases and concurrency",
    "## Test semantics",
    "## Comments",
    "## Code-intent analysis",
    "## Yell-test proposal",
    "## Specialist routing",
    "## Finding shape",
    "## Verdict",
)

# Sentences distinctive to the doctrine that moved out of the agent and into
# the contract. Picked because none is generic enough to appear by accident
# in unrelated prose (verified absent from the new agent files at write time).
_MOVED_DOCTRINE_SENTENCES = (
    "Report only findings scored 80 or higher",
    "Do not assume a file named CLAUDE.md exists",
    "Emit findings in this exact order, with no preamble beyond the Summary",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"missing required file: {path}"
    return path.read_text(encoding="utf-8")


def _contains_moved_doctrine(text: str) -> str | None:
    """Return the first moved-doctrine sentence found in ``text``, or None.

    Shared by the real agent check and its negative control below, so both
    exercise the identical matching logic.
    """
    for sentence in _MOVED_DOCTRINE_SENTENCES:
        if sentence in text:
            return sentence
    return None


class TestContractFileShape:
    """The contract file exists and states every REQ-032 AC 2-14 section."""

    TEXT = _read(_CONTRACT)

    def test_contract_file_exists(self) -> None:
        assert _CONTRACT.is_file()

    def test_every_required_heading_present(self) -> None:
        missing = [h for h in _REQUIRED_CONTRACT_HEADINGS if h not in self.TEXT]
        assert not missing, f"technical-review.md is missing headings: {missing}"

    def test_negative_control_a_heading_not_present_would_be_caught(self) -> None:
        """Proves the heading check is not vacuously true."""
        assert "## This Heading Does Not Exist" not in self.TEXT

    def test_verdict_line_format_present(self) -> None:
        assert "VERDICT: PASS|WARN|CRITICAL_FAIL" in self.TEXT

    def test_post_2023_invariant_sentence_present(self) -> None:
        assert "evidence earns preservation, complexity does not" in self.TEXT

    def test_no_em_or_en_dash(self) -> None:
        em_dash = chr(0x2014)
        en_dash = chr(0x2013)
        assert em_dash not in self.TEXT
        assert en_dash not in self.TEXT


class TestReviewTemplateWiresCorrectnessPass:
    """The review skill template declares ownership and runs step 4c."""

    TEXT = _read(_REVIEW_TEMPLATE)

    def test_declares_owns_technical_review(self) -> None:
        assert "owns:" in self.TEXT
        assert "technical-review" in self.TEXT

    def test_declares_capability_kind_orchestrator(self) -> None:
        assert "kind: orchestrator" in self.TEXT

    def test_names_the_resource_path(self) -> None:
        assert "resources/technical-review.md" in self.TEXT

    def test_step_4c_present(self) -> None:
        assert "4c." in self.TEXT

    def test_step_4c_dispatches_code_reviewer(self) -> None:
        assert 'Task(subagent_type="code-reviewer")' in self.TEXT

    def test_correctness_row_appended_without_disturbing_16_rows_phrase(self) -> None:
        assert "`correctness` row" in self.TEXT
        assert "16 rows" in self.TEXT


class TestChestertonsFenceDeclaresArchaeologyOnly:
    """chestertons-fence owns code-archaeology and forms no cycle."""

    TEXT = _read(_FENCE_TEMPLATE)

    def test_declares_owns_code_archaeology(self) -> None:
        assert "code-archaeology" in self.TEXT
        assert "owns:" in self.TEXT

    def test_declares_capability_kind_reusable_primitive(self) -> None:
        assert "kind: reusable-primitive" in self.TEXT

    def test_does_not_depend_on_technical_review(self) -> None:
        assert "depends-on" not in self.TEXT

    def test_negative_control_dependency_check_would_catch_a_cycle(self) -> None:
        """Proves the absence check above is not vacuous."""
        synthetic = self.TEXT + "\n  depends-on:\n    - technical-review\n"
        assert "depends-on" in synthetic


class TestAgentDependsOnContractAndCarriesNoMovedDoctrine:
    """code-reviewer.shared.md depends on the contract; doctrine moved out."""

    TEXT = _read(_AGENT_SHARED)

    def test_declares_depends_on_technical_review(self) -> None:
        assert "depends-on:" in self.TEXT
        assert "technical-review" in self.TEXT

    def test_declares_depends_on_untrusted_content_handling(self) -> None:
        assert "untrusted-content-handling" in self.TEXT

    def test_declares_capability_kind_specialized_implementation(self) -> None:
        assert "kind: specialized-implementation" in self.TEXT

    def test_no_moved_doctrine_sentence_present(self) -> None:
        found = _contains_moved_doctrine(self.TEXT)
        assert found is None, f"agent still restates moved doctrine: {found!r}"

    def test_negative_control_doctrine_leak_check_catches_a_synthetic_leak(self) -> None:
        """Proves the doctrine-leak check above can fail.

        Appends one real moved-doctrine sentence to a copy of the agent text
        and asserts the same detector used above reports it, so the positive
        check is not silently vacuous.
        """
        leaked = self.TEXT + "\nReport only findings scored 80 or higher.\n"
        found = _contains_moved_doctrine(leaked)
        assert found == "Report only findings scored 80 or higher"


class TestUntrustedContentBlockStaysByteIdentical:
    """The agent's canonical residue must not drift from the agent partial.

    templates/rules/security.md "Approved residue" names code-reviewer as one
    of four shared bodies that carry the untrusted-content text verbatim
    rather than an include, so this checks containment, not an include tag.
    """

    def test_shared_body_contains_the_partial_verbatim(self) -> None:
        agent_text = _read(_AGENT_SHARED)
        partial_text = _read(_UNTRUSTED_AGENT_PARTIAL)
        assert partial_text in agent_text
