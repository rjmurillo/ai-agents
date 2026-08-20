"""Disposition-routing and reply-template contract tests for reviewer-findings.

Split out of ``test_reviewer_findings_premise_verification.py`` to keep that
file under the repository's 500-line ceiling
(``scripts/ci/taste_count_ratchet.py``); the premise-verification file kept
growing across PR #5178's review rounds as new CWE-78 and correctness gaps
were found, and this half (disposition-to-outcome routing, the responder's
gate ordering, and the reply template's evidence fields) is a distinct
concern from the git-invocation mechanics that stayed behind. Shares the
``plugin_root`` fixture (``conftest.py``) and the parsing/lookup helpers
(``_helpers.py``) with the sibling test files; both apply to every test
module in this directory, not just the one that first imported them.

Covers the remainder of issue #5069's acceptance criteria not already in the
sibling file: the premise-true/false/unverifiable triage branch pairs each
row with its own disposition (not just token presence anywhere in the file),
a refuted premise gates ``Action: Implement`` and requires thread resolution,
and the evidence-bearing reply template carries every required field.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# pytest here runs under --import-mode=importlib (pyproject.toml), which never
# inserts a test file's own directory onto sys.path, so a plain
# `import _helpers` cannot resolve. Load the sibling module by file path
# instead, matching the wrapper idiom already used in
# tests/skills/pr-comment-responder/test_cluster_threads.py.
_HELPERS_PATH = Path(__file__).resolve().parent / "_helpers.py"
_helpers_spec = importlib.util.spec_from_file_location(
    "reviewer_findings_test_helpers", _HELPERS_PATH
)
assert _helpers_spec is not None and _helpers_spec.loader is not None
_helpers = importlib.util.module_from_spec(_helpers_spec)
_helpers_spec.loader.exec_module(_helpers)

DISPOSITION_TOKENS = _helpers.DISPOSITION_TOKENS
ROUTER_SKILL = _helpers.ROUTER_SKILL
SKILL_NAME = _helpers.SKILL_NAME
TRIAGE_PHASE = _helpers.TRIAGE_PHASE
_bounded_section = _helpers._bounded_section
_missing_disposition_tokens = _helpers._missing_disposition_tokens
_phase_section = _helpers._phase_section
_read = _helpers._read
_read_reference = _helpers._read_reference
_row_disposition = _helpers._row_disposition
_workflow_phase_section = _helpers._workflow_phase_section


class TestPremiseDispositionRouting:
    def test_reviewer_findings_maps_premise_to_disposition(self, plugin_root: Path) -> None:
        """Positive: the three-way triage outcome the issue's acceptance criteria name."""
        text = _read(plugin_root, SKILL_NAME)
        missing = _missing_disposition_tokens(text)
        assert not missing, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} dropped {missing} from "
            f"the premise disposition mapping"
        )

    def test_reviewer_findings_pairs_each_premise_row_with_its_own_disposition(
        self, plugin_root: Path
    ) -> None:
        """Positive: row-level pairing, not just presence anywhere in the file.

        A token-presence check (all six words appear somewhere) passes even if
        the table pairs True with Declined and False with Confirmed. Parse the
        actual table row for each premise and check its own Disposition cell.
        """
        text = _read(plugin_root, SKILL_NAME)
        expected = {"True": "Confirmed", "False": "Declined", "Unverifiable": "Unreproduced"}
        for premise, disposition in expected.items():
            cell = _row_disposition(text, premise)
            assert cell is not None, (
                f"{SKILL_NAME}/SKILL.md in {plugin_root} has no "
                f"'| {premise} | ... | ... |' table row in the premise "
                f"disposition table"
            )
            assert disposition in cell, (
                f"{SKILL_NAME}/SKILL.md in {plugin_root}'s '{premise}' row's "
                f"Disposition cell ({cell!r}) no longer names '{disposition}'"
            )

    def test_a_swapped_disposition_row_fails_the_pairing_check(self) -> None:
        """Negative control: the same helper the positive test calls must reject a swap."""
        swapped = (
            "| Premise | What settles it | Disposition |\n"
            "|---|---|---|\n"
            "| True | some check | Declined; reply with the evidence |\n"
            "| False | some check | Confirmed; proceed to fix |\n"
            "| Unverifiable | neither | Unreproduced; leave the thread open |\n"
        )
        cell = _row_disposition(swapped, "True")
        assert cell is not None, "the swapped fixture has no 'True' row to read at all"
        assert "Confirmed" not in cell, (
            "_row_disposition, the same helper the positive pairing test "
            "calls, did not flag the swapped True row, so it would not catch "
            "a real swapped mapping either"
        )

    def test_reviewer_findings_requires_resolution_on_refutation(self, plugin_root: Path) -> None:
        """Positive: a refuted premise must resolve the thread, not just decline."""
        text = _read(plugin_root, SKILL_NAME)
        assert "resolve the thread" in text, (
            f"{SKILL_NAME}/SKILL.md in {plugin_root} no longer instructs "
            f"resolving the thread after a refuted-premise reply"
        )

    def test_a_bare_mention_of_premise_is_not_the_disposition_mapping(self) -> None:
        """Negative control: the same helper must report every token missing on bare prose."""
        prose = "Findings carry a premise. Verify it before acting."
        missing = _missing_disposition_tokens(prose)
        assert missing == list(DISPOSITION_TOKENS), (
            "_missing_disposition_tokens, the same helper the positive "
            "mapping test calls, did not report every token missing on "
            "prose with no real mapping, so it would not catch a real "
            "regression either"
        )

    def test_responder_gates_implement_on_premise_verification(self, plugin_root: Path) -> None:
        """Positive: Phase 2 step 4 requires the git check before implementing."""
        router = _read(plugin_root, ROUTER_SKILL)
        triage = _phase_section(router, TRIAGE_PHASE)
        assert "git grep -n -F" in triage or "git log -S" in triage, (
            f"{ROUTER_SKILL}/SKILL.md in {plugin_root} Phase {TRIAGE_PHASE} "
            f"no longer requires a git-based premise check before "
            f"implementing a finding"
        )
        assert "reply" in triage.lower(), (
            f"{ROUTER_SKILL}/SKILL.md in {plugin_root} Phase {TRIAGE_PHASE} "
            f"no longer routes a refuted premise to a reply instead of a "
            f"code change"
        )

    def test_responder_skill_md_also_covers_the_unverifiable_branch(
        self, plugin_root: Path
    ) -> None:
        """Positive: SKILL.md itself, not only workflow.md, names the Clarify routing.

        An agent that reads Phase 2 without following the reference link to
        workflow.md must still learn what happens to an unsettled premise.
        """
        router = _read(plugin_root, ROUTER_SKILL)
        triage = _phase_section(router, TRIAGE_PHASE)
        assert "Clarify" in triage, (
            f"{ROUTER_SKILL}/SKILL.md in {plugin_root} Phase {TRIAGE_PHASE} "
            f"no longer names Action: Clarify for an unverifiable premise; "
            f"only workflow.md does"
        )

    def test_responder_workflow_requires_premise_check_before_action_implement(
        self, plugin_root: Path
    ) -> None:
        """Edge: ordering. The check must precede the Task() delegation, not follow it.

        Matches on "grep -n -F" rather than "git grep -n -F": the command is
        prefixed with "git --literal-pathspecs grep" (CWE-20 pathspec-magic
        guard), so a literal "git grep" search would miss it and silently
        stop proving this ordering property the moment that prefix landed.
        """
        workflow = _read_reference(plugin_root, ROUTER_SKILL, "workflow.md")
        phase3 = _workflow_phase_section(workflow, "3")
        check_pos = phase3.find("grep -n -F")
        delegate_pos = phase3.find("Task(subagent_type=")
        assert check_pos != -1, (
            f"{ROUTER_SKILL}/references/workflow.md in {plugin_root} Phase 3 "
            f"no longer names the premise-verification command"
        )
        assert delegate_pos != -1, (
            f"{ROUTER_SKILL}/references/workflow.md in {plugin_root} Phase 3 "
            f"no longer delegates via Task(subagent_type=...)"
        )
        assert check_pos < delegate_pos, (
            f"{ROUTER_SKILL}/references/workflow.md in {plugin_root} Phase 3 "
            f"verifies the premise after delegating instead of before, so "
            f"Action: Implement can be chosen before the check runs"
        )
        assert "Reply Only" in phase3, (
            f"{ROUTER_SKILL}/references/workflow.md in {plugin_root} Phase 3 "
            f"no longer routes a refuted premise to Action: Reply Only"
        )

    def test_templates_carry_a_premise_refuted_reply(self, plugin_root: Path) -> None:
        """Positive: the evidence-rich reply template the issue's acceptance criteria require."""
        templates = _read_reference(plugin_root, ROUTER_SKILL, "templates.md")
        section = _bounded_section(templates, "### Premise Refuted")
        assert section is not None, (
            f"{ROUTER_SKILL}/references/templates.md in {plugin_root} "
            f"dropped the Premise Refuted template heading"
        )
        for field in ("File:", "Line:", "Claimed:", "Verified with:", "Commit:", "Disposition:"):
            assert field in section, (
                f"{ROUTER_SKILL}/references/templates.md in {plugin_root} "
                f"Premise Refuted template is missing the '{field}' "
                f"evidence field"
            )

    def test_a_heading_substring_elsewhere_does_not_satisfy_the_template_check(self) -> None:
        """Negative control: the same helper must find no section in prose without the heading."""
        prose = "A premise can be refuted. File a reply and move on."
        assert _bounded_section(prose, "### Premise Refuted") is None, (
            "_bounded_section, the same helper the positive template test "
            "calls, found a section in prose that never contains the "
            "heading, so it would not catch a real missing-template "
            "regression either"
        )

    def test_bounded_section_excludes_a_later_heading(self) -> None:
        """Edge: a field belonging to the next template must not satisfy this one's check."""
        doc = (
            "### Premise Refuted\n"
            "- File: `a.py`\n"
            "### Another Template\n"
            "- Line: `not this one's`\n"
        )
        section = _bounded_section(doc, "### Premise Refuted")
        assert section is not None
        assert "Line:" not in section, (
            "the section slice leaked past the next '### ' heading, so a "
            "field belonging to a different template could satisfy this "
            "template's field check"
        )
