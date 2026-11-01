"""Lifecycle composition tests for ``doc-accuracy`` (issue #5398).

``/build``, ``/test``, and ``/review`` compose ``doc-accuracy`` instead of
copying it. These tests pin where each skill composes it, that no skill carries
a second copy of the ``doc-accuracy`` phases, and that removing the composition
makes the placement predicate fail. Each predicate is also run against the text
with its composition lines deleted, so a predicate that passes on any text
fails here.

The detail lives in on-demand reference files, not in the ``SKILL.md`` bodies,
because the per-fixture instruction-bytes ceilings leave the three lifecycle
skills almost no headroom (``scripts/validation/instruction_bytes.py``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS = PROJECT_ROOT / ".claude" / "skills"
SCENARIOS = PROJECT_ROOT / "tests" / "evals" / "skill-scenarios"
GATE_REFERENCE = SKILLS / "test" / "references" / "doc-accuracy-gate.md"
REVIEW_RESOURCE = SKILLS / "review" / "resources" / "documentation-findings.md"
REMEDIATION_CLASSES = (
    "correct durable claim",
    "delete derived claim",
    "reference canonical source",
    "generate projection",
    "consolidate authority",
)
# doc-accuracy owns its phases and taxonomy; no lifecycle skill may repeat them.
COPIED_POLICY = (
    "Asymmetric Verification",
    "Phase 1: Assessment",
    "Phase 2: Claim Extraction",
    "Phase 3: Compilability",
    "Issue Taxonomy",
    "Spec vs Behavior",
)
COMPOSITION_TOKENS = (
    "doc_accuracy_trigger",
    "doc-accuracy",
    "documentation-findings",
    "Build handoff",
    "--build-record",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _skill(name: str) -> str:
    return _read(SKILLS / name / "SKILL.md")


def _find_section(text: str, heading: str) -> str | None:
    match = re.search(rf"^#+ {re.escape(heading)}\n(.*?)(?=^#+ |\Z)", text, re.M | re.S)
    return match.group(1) if match else None


def _section(text: str, heading: str) -> str:
    body = _find_section(text, heading)
    assert body is not None, f"section {heading!r} missing"
    return body


def _without_composition(text: str) -> str:
    """The text as it reads when every doc-accuracy composition line is removed."""
    return "\n".join(
        line for line in text.splitlines() if not any(token in line for token in COMPOSITION_TOKENS)
    )


def _build_composes(text: str) -> bool:
    gate = _find_section(text, "Mandatory Exit Gates") or ""
    line = next((row for row in gate.splitlines() if "doc_accuracy_trigger.py" in row), "")
    return (
        "test/references/doc-accuracy-gate.md" in line
        and "Build handoff" in line
        and '"activate"' in line
        and ('Skill(skill="doc-accuracy")' in line or 'skill: "doc-accuracy"' in line)
        and "--diff-base" in line
    )


def _gate_reference_composes(text: str) -> bool:
    handoff = _find_section(text, "Build handoff") or ""
    return (
        "--build-record" in text
        and "build_record" in text
        and "DOC ACCURACY: SKIPPED" in handoff
        and "doc-impact record" in handoff
        and "A missing record is not a" in handoff
    )


def _review_composes(text: str) -> bool:
    return any(
        "doc_accuracy_trigger.py" in row and "resources/documentation-findings.md" in row
        for row in text.splitlines()
    )


def _review_resource_composes(text: str) -> bool:
    lowered = text.lower()
    return (
        "doc_accuracy_trigger.py" in text
        and "select_axes.py" in text
        and "local_selected" in text
        and "DOC ACCURACY REPORT" in text
        and "never a skip" in lowered
        and "`UNKNOWN`" in text
        and all(cls in text for cls in REMEDIATION_CLASSES)
    )


PLACEMENTS: dict[str, tuple[Callable[[str], bool], Callable[[], str]]] = {
    "build SKILL.md exit gate 3": (_build_composes, lambda: _skill("build")),
    "test gate reference build handoff": (_gate_reference_composes, lambda: _read(GATE_REFERENCE)),
    "review SKILL.md local axis 2": (_review_composes, lambda: _skill("review")),
    "review documentation-findings resource": (
        _review_resource_composes,
        lambda: _read(REVIEW_RESOURCE),
    ),
}


@pytest.mark.parametrize("place", sorted(PLACEMENTS))
def test_doc_accuracy_is_composed_at_its_insertion_point(place: str) -> None:
    predicate, load = PLACEMENTS[place]
    assert predicate(load())


@pytest.mark.parametrize("place", sorted(PLACEMENTS))
def test_mutation_control_removing_composition_is_detected(place: str) -> None:
    """Issue fixture 8: without the composition the placement predicate fails."""
    predicate, load = PLACEMENTS[place]
    original = load()
    mutated = _without_composition(original)
    assert mutated != original
    assert not predicate(mutated)


@pytest.mark.parametrize("skill", ["build", "test", "review"])
def test_lifecycle_skill_does_not_copy_doc_accuracy_policy(skill: str) -> None:
    texts = [_skill(skill)]
    if skill == "test":
        texts.append(_read(GATE_REFERENCE))
    if skill == "review":
        texts.append(_read(REVIEW_RESOURCE))
    for text in texts:
        for copied in COPIED_POLICY:
            assert copied not in text, f"{skill} repeats doc-accuracy policy: {copied}"


def test_build_exit_gate_is_conditional_not_an_unconditional_audit() -> None:
    gate = _section(_skill("build"), "Mandatory Exit Gates")
    assert "so it audits changed comments, docstrings, and prose" not in gate
    assert "--diff-base main" not in gate


def test_build_handoff_stays_incremental() -> None:
    handoff = _section(_read(GATE_REFERENCE), "Build handoff")
    assert "so it does not\naudit after every edit" in handoff
    assert "incremental scan" in handoff
    assert "behavioral phases" in handoff


def test_review_separates_historical_evidence_from_the_verdict() -> None:
    lowered = _read(REVIEW_RESOURCE).lower()
    assert "historical evidence" in lowered
    assert "leave it out of the verdict" in lowered


def test_review_resource_ships_with_the_skill_in_every_distribution() -> None:
    expected = _read(REVIEW_RESOURCE)
    for tree in ("src/claude", "src/copilot-cli", "src/codex"):
        shipped = PROJECT_ROOT / tree / "skills" / "review" / "resources"
        assert _read(shipped / "documentation-findings.md") == expected, tree


@pytest.mark.parametrize("name", ["build", "review"])
def test_generated_copies_carry_the_composition(name: str) -> None:
    claude = PROJECT_ROOT / "src" / "claude" / "skills" / name / "SKILL.md"
    copilot = PROJECT_ROOT / "src" / "copilot-cli" / "skills" / name / "SKILL.md"
    assert claude.read_bytes() == (SKILLS / name / "SKILL.md").read_bytes()
    predicate = _build_composes if name == "build" else _review_composes
    assert predicate(_read(copilot))


def _scenarios(name: str) -> dict:
    return json.loads(_read(SCENARIOS / f"{name}.json"))


def test_build_scenarios_cover_the_doc_impact_record_and_its_skip() -> None:
    data = _scenarios("build")
    assert data["skill_path"] == ".claude/skills/build/SKILL.md"
    by_id = {item["id"]: item for item in data["scenarios"]}
    assert {"doc_accuracy_trigger", "doc-impact record"} <= set(by_id["S6"]["expected_signals"])
    assert {"doc_accuracy_trigger", "DOC ACCURACY: SKIPPED"} <= set(by_id["S7"]["expected_signals"])


def test_review_scenarios_cover_remediation_classes_and_the_direct_invocation_guard() -> None:
    data = _scenarios("review")
    assert data["skill_path"] == ".claude/skills/review/SKILL.md"
    assert data["skill_id"] == "review"
    signals = [set(item["expected_signals"]) for item in data["scenarios"]]
    assert any("delete derived claim" in s for s in signals)
    assert any("generate projection" in s for s in signals)
    assert any({"doc_accuracy_trigger", "never a skip"} <= s for s in signals)
    assert "skip-rule-not-applicable" in {item["expected_gate"] for item in data["scenarios"]}


def test_new_scenarios_carry_the_fields_the_runner_reads() -> None:
    build_new = [item for item in _scenarios("build")["scenarios"] if item["id"] in {"S6", "S7"}]
    review_all = _scenarios("review")["scenarios"]
    assert len(build_new) == 2
    for item in build_new + review_all:
        for key in ("id", "desc", "input", "expected_signals", "expected_gate", "rationale"):
            assert item[key], (item["id"], key)
        assert "Do not modify any files" in item["input"]


def _phase_names(text: str) -> set[str]:
    return set(re.findall(r"Phase \d+[a-z]?", text))


def test_build_scenarios_cite_only_phases_the_build_skill_defines() -> None:
    """A scenario that expects a phase the skill lacks scores a made-up name."""
    defined = _phase_names(_skill("build"))
    cited = _phase_names(_read(SCENARIOS / "build.json"))
    assert cited <= defined, sorted(cited - defined)


def test_review_resource_names_the_owner_of_the_remediation_classes() -> None:
    """The class names are authored once, in the gate reference Report block."""
    resource = _read(REVIEW_RESOURCE)
    assert "executable-nl-artifacts" not in resource
    assert "doc-accuracy-gate.md" in resource
    report = _section(_read(GATE_REFERENCE), "Report")
    assert all(cls in report for cls in REMEDIATION_CLASSES)


def test_build_exit_gate_scans_only_when_changed_documents_exist() -> None:
    gate = _section(_skill("build"), "Mandatory Exit Gates")
    assert "a non-empty `changed_documents`" in gate


def test_review_select_names_every_required_trigger_flag() -> None:
    select = _read(REVIEW_RESOURCE).split("2. **Reuse.**")[0]
    for flag in ("--diff-base", "--changed-path", "--effect", "--build-record"):
        assert flag in select, flag


def test_review_table_uses_only_report_block_class_names() -> None:
    table = _read(REVIEW_RESOURCE).split("| Finding | Remediation class |")[1]
    rows = [r for r in table.splitlines()[2:] if r.startswith("|")]
    assert rows
    for row in rows:
        remediation = row.rsplit("|", 2)[-2].strip()
        for option in remediation.split(", or "):
            assert option.strip() in REMEDIATION_CLASSES, option


def test_gate_verdict_takes_classes_from_the_report_block() -> None:
    verdict = _section(_read(GATE_REFERENCE), "5. Verdict")
    assert "from the Report block" in verdict


def test_gate_exit_two_summary_covers_a_malformed_build_record() -> None:
    decide = _section(_read(GATE_REFERENCE), "1. Decide")
    summary = decide.split("Exit `2` means")[1]
    assert "build record" in summary


def test_gate_scan_of_changed_documents_runs_in_git_mode() -> None:
    """The trigger shares the review selector's `_doc_accuracy_reads`.

    That predicate mirrors doc-accuracy's git-mode exclusions, so the gate's
    changed-document scan must pass `--diff-base`. Without it the scanner walks
    the tree, prunes build/ and bin/, and reads none of a file the trigger
    called readable. `/review` pins its own call in
    tests/skills/review/test_select_axes.py.
    """
    text = _read(GATE_REFERENCE)
    scan = _section(text, "3. Scan the changed documents")
    command = next(line for line in scan.splitlines() if "doc_accuracy.py" in line)
    assert '--diff-base "origin/<base-branch>"' in command
    assert "--format gate" in command
