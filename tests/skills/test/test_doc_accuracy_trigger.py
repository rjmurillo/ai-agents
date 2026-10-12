"""Routing tests for the ``/test`` Gate 5 documentation-accuracy trigger (issue #5398).

Gate 5 composes the ``doc-accuracy`` skill only when a change can invalidate a
durable claim or alter executable prose. These tests drive
``doc_accuracy_trigger.py`` directly, so each row of the activation and skip
table is an assertion on real output, not on prose. Each stale-documentation
fixture from the issue also runs against a trigger stubbed to always skip, and
that stub fails every one of them.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

from tests.lib.vendored_copy import copy_vendored_entry

mod = import_skill_script(
    ".claude/skills/test/scripts/doc_accuracy_trigger.py",
    module_name="test_doc_accuracy_trigger_mod",
)

SKILLS_ROOT = PROJECT_ROOT / ".claude" / "skills"
SRC_CLAUDE_SKILLS_ROOT = PROJECT_ROOT / "src" / "claude" / "skills"
COPILOT_SKILLS_ROOT = PROJECT_ROOT / "src" / "copilot-cli" / "skills"
TEST_SKILL_MD = SKILLS_ROOT / "test" / "SKILL.md"
GATE_REFERENCE = SKILLS_ROOT / "test" / "references" / "doc-accuracy-gate.md"
BASE = "origin/main"
_TIMEOUT_S = 60
GATE5_HEADING = "Gate 5: Developer Experience (DX) and Documentation Accuracy"


@pytest.fixture(scope="module")
def classifier():
    return mod.load_classifier()


def _decide(classifier, paths, effects=(), base=BASE):
    return mod.decide(list(paths), list(effects), base, classifier)


# The eight fixtures the issue requires. Each row is a change whose stale
# documentation the gate must not let through, so each must activate.
STALE_DOC_FIXTURES = [
    pytest.param(
        ["src/filters.py"],
        ["quantitative-claim"],
        "required",
        id="fixture1-cardinality-3-to-4",
    ),
    pytest.param(["src/api.py"], [], "required", id="fixture2-public-api-signature"),
    pytest.param(
        [".claude/skills/example/SKILL.md"], [], "on-findings", id="fixture4-markdown-rule-edit"
    ),
    pytest.param(
        ["templates/rules/builder-ethos.md", ".claude/rules/builder-ethos.md"],
        ["generated-input"],
        "on-findings",
        id="fixture5-generated-projection",
    ),
]


@pytest.mark.parametrize(("paths", "effects", "escalation"), STALE_DOC_FIXTURES)
def test_stale_doc_fixture_activates(classifier, paths, effects, escalation) -> None:
    result = _decide(classifier, paths, effects)
    assert result["decision"] == "activate", result["reason"]
    assert result["activation_causes"], result
    assert result["behavioral_escalation"] == escalation


@pytest.mark.parametrize(("paths", "effects", "escalation"), STALE_DOC_FIXTURES)
def test_always_skip_stub_lets_every_stale_doc_fixture_escape(paths, effects, escalation) -> None:
    """Negative control: remove the composition and the fixtures escape."""
    always_skip = SimpleNamespace(classify_paths=lambda p: (["tests-or-fixtures"], []))
    stub = mod.decide(["tests/a.py"], [], BASE, always_skip)
    assert stub["decision"] == "skip"
    real = mod.decide(paths, effects, BASE, mod.load_classifier())
    assert real["decision"] != stub["decision"]


def test_fixture3_code_with_no_documentation_impact_skips_with_a_reason(classifier) -> None:
    result = _decide(classifier, ["src/retry_loop.py"])
    assert result["decision"] == "skip"
    assert result["activate"] is False
    assert result["activation_causes"] == []
    assert result["behavioral_escalation"] == "none"
    assert result["reason"].startswith("skip - no change can invalidate a durable claim")
    assert "src/retry_loop.py (code or configuration with no verified" in result["reason"]


def test_fixture6_historical_retrospective_skips_as_dated_evidence(classifier) -> None:
    path = ".agents/retrospective/2026-09-29-5582-migrate-skill-tests.md"
    result = _decide(classifier, [path])
    assert result["decision"] == "skip"
    assert result["historical_paths"] == [path]
    assert result["changed_documents"] == []
    assert "historical evidence" in result["reason"]


def test_historical_path_is_reported_when_another_cause_activates(classifier) -> None:
    history = "docs/CHANGELOG.md"
    result = _decide(classifier, [history, "docs/guide.md"])
    assert result["decision"] == "activate"
    assert result["historical_paths"] == [history]
    assert result["changed_documents"] == ["docs/guide.md"]


def test_fixture7_inconclusive_phase_is_never_a_pass_in_gate5() -> None:
    gate5 = _section(TEST_SKILL_MD.read_text(encoding="utf-8"), GATE5_HEADING)
    assert "`UNKNOWN`, `DID_NOT_RUN`, or an unrun required phase is `ERROR`" in gate5
    reference = GATE_REFERENCE.read_text(encoding="utf-8")
    verdict_rule = reference.split("## 5. Verdict", 1)[1].split("## Report", 1)[0]
    assert "none of them is ever" in verdict_rule
    assert "a PASS" in verdict_rule
    assert "`ERROR`" in verdict_rule


# Skip table: every path that cannot invalidate a durable claim.
SKIP_CASES = [
    pytest.param("tests/test_a.py", "test or fixture only", id="test-module"),
    pytest.param("tests/fixtures/README.md", "test or fixture only", id="fixture-markdown"),
    pytest.param("src/service.py", "code or configuration", id="plain-code"),
    pytest.param(".github/workflows/ci.yml", "code or configuration", id="ci-workflow-no-effect"),
]


@pytest.mark.parametrize(("path", "why"), SKIP_CASES)
def test_skip_table_names_the_reason_per_path(classifier, path, why) -> None:
    result = _decide(classifier, [path])
    assert result["decision"] == "skip"
    assert path in result["reason"]
    assert why in result["reason"]


# Activation table: path-driven causes.
ACTIVATE_CASES = [
    pytest.param("README.md", "changed_documents", id="readme"),
    pytest.param("docs/guide.md", "changed_documents", id="guide"),
    pytest.param(".claude/rules/universal.md", "changed_documents", id="rule-markdown"),
    pytest.param(".agents/governance/golden-principles.md", "changed_documents", id="governance"),
    pytest.param(".claude/agents/analyst.md", "changed_documents", id="agent-markdown"),
    pytest.param("build/AGENTS.md", "unreadable_documents", id="scanner-excluded-markdown"),
]


@pytest.mark.parametrize(("path", "field"), ACTIVATE_CASES)
def test_document_paths_activate_and_land_in_the_right_field(classifier, path, field) -> None:
    result = _decide(classifier, [path])
    assert result["decision"] == "activate", result["reason"]
    assert result[field] == [path]


def test_unreadable_document_is_not_counted_as_scannable(classifier) -> None:
    result = _decide(classifier, ["build/AGENTS.md"])
    assert result["changed_documents"] == []
    assert result["coupled_documents_needed"] is True


def test_agent_artifact_script_activates_without_a_document(classifier) -> None:
    result = _decide(classifier, [".claude/skills/test/scripts/doc_accuracy_trigger.py"])
    assert result["decision"] == "activate"
    assert result["changed_documents"] == []
    assert result["coupled_documents_needed"] is True


def test_template_source_of_a_skill_activates(classifier) -> None:
    result = _decide(classifier, ["templates/skills/test.SKILL.md.tmpl"])
    assert result["decision"] == "activate"


def test_code_path_activates_only_through_a_verified_effect(classifier) -> None:
    assert _decide(classifier, ["src/service.py"])["decision"] == "skip"
    result = _decide(classifier, ["src/service.py"], ["behavioral-claim"])
    assert result["decision"] == "activate"
    assert result["coupled_documents_needed"] is True
    assert result["behavioral_escalation"] == "required"


@pytest.mark.parametrize("effect", mod.EFFECTS)
def test_every_known_effect_activates_on_an_otherwise_skipped_path(classifier, effect) -> None:
    result = _decide(classifier, ["tests/test_a.py"], [effect])
    assert result["decision"] == "activate"
    assert result["unknown_effects"] == []
    assert f"effect: {effect}" in result["activation_causes"]


@pytest.mark.parametrize("effect", sorted(mod.REQUIRED_ESCALATION))
def test_value_claim_effects_require_behavioral_verification(classifier, effect) -> None:
    result = _decide(classifier, ["tests/test_a.py"], [effect])
    assert result["behavioral_escalation"] == "required"


@pytest.mark.parametrize("effect", sorted(set(mod.EFFECTS) - mod.REQUIRED_ESCALATION))
def test_other_effects_escalate_only_on_findings(classifier, effect) -> None:
    result = _decide(classifier, ["tests/test_a.py"], [effect])
    assert result["behavioral_escalation"] == "on-findings"


def test_required_escalation_effects_are_all_known_effects() -> None:
    assert mod.REQUIRED_ESCALATION <= set(mod.EFFECTS)


def test_effect_names_are_case_and_space_insensitive(classifier) -> None:
    result = _decide(classifier, ["tests/test_a.py"], ["  CLI-Surface ", "cli-surface"])
    assert result["unknown_effects"] == []
    assert result["activation_causes"] == ["effect: cli-surface"]


def test_unknown_effect_fails_closed(classifier) -> None:
    result = _decide(classifier, ["tests/test_a.py"], ["vibes"])
    assert result["decision"] == "activate"
    assert result["unknown_effects"] == ["vibes"]
    assert "fail-closed: unknown effect vibes" in result["reason"]


def test_empty_path_list_fails_closed(classifier) -> None:
    for paths in ([], [""], ["  "]):
        result = _decide(classifier, paths)
        assert result["decision"] == "activate"
        assert "no changed paths supplied" in result["reason"]


def test_unclassified_path_fails_closed(classifier) -> None:
    result = _decide(classifier, ["assets/diagram.png"])
    assert result["decision"] == "activate"
    assert "assets/diagram.png" in result["reason"]
    assert "not provably claim-neutral" in result["reason"]


def test_windows_separators_classify_like_posix(classifier) -> None:
    result = _decide(classifier, ["tests\\skills\\test_a.py"])
    assert result["decision"] == "skip"


def test_diff_base_and_scope_are_echoed(classifier) -> None:
    result = _decide(classifier, ["docs/guide.md"], base="origin/develop")
    assert result["diff_base"] == "origin/develop"
    assert result["scope"] == "incremental: origin/develop...HEAD"


def test_changed_document_with_other_changes_does_not_need_coupled_documents(classifier) -> None:
    result = _decide(classifier, ["docs/guide.md", "src/service.py"], ["quantitative-claim"])
    assert result["coupled_documents_needed"] is False
    assert result["changed_documents"] == ["docs/guide.md"]


def test_review_categories_drive_the_decision() -> None:
    """The decision comes from the #4981 classifier, not a private taxonomy."""
    as_docs = SimpleNamespace(
        classify_paths=lambda paths: (["docs-and-instructions"], []),
        unreviewable_paths=lambda paths: [],
    )
    as_unreadable = SimpleNamespace(
        classify_paths=lambda paths: (["docs-and-instructions"], []),
        unreviewable_paths=lambda paths: list(paths),
    )
    as_code = SimpleNamespace(classify_paths=lambda paths: (["executable-code"], []))
    assert mod.decide(["zz/plain.dat"], [], BASE, as_docs)["changed_documents"] == ["zz/plain.dat"]
    assert mod.decide(["zz/plain.dat"], [], BASE, as_unreadable)["unreadable_documents"] == [
        "zz/plain.dat"
    ]
    assert mod.decide(["zz/plain.dat"], [], BASE, as_code)["decision"] == "skip"


def test_every_review_category_the_trigger_names_exists(classifier) -> None:
    real = {row[0] for row in classifier._RISK_TABLE}
    named = {"tests-or-fixtures", "docs-and-instructions", "agent-artifacts", "types-or-public-api"}
    assert named <= real, named - real


def test_load_classifier_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        mod.load_classifier(tmp_path / "missing.py")


def test_load_classifier_rejects_an_unloadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "select_axes.py"
    target.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod.importlib.util, "spec_from_file_location", lambda *a, **k: None)
    with pytest.raises(ImportError, match="cannot load review-axis classifier"):
        mod.load_classifier(target)


def _run(script: Path, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_S,
        check=False,
    )


@pytest.fixture(params=["vendored-copy", "copilot-generated"])
def shipped_script(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """The trigger as a consumer gets it, with its sibling review skill."""
    if request.param == "copilot-generated":
        return COPILOT_SKILLS_ROOT / "test" / "scripts" / "doc_accuracy_trigger.py"
    plugin_skills = tmp_path / "plugin" / "skills"
    plugin_skills.mkdir(parents=True)
    for name in ("test", "review"):
        copy_vendored_entry(SKILLS_ROOT / name, plugin_skills / name)
    return plugin_skills / "test" / "scripts" / "doc_accuracy_trigger.py"


def test_cli_emits_decision_from_a_foreign_cwd(shipped_script: Path, tmp_path: Path) -> None:
    cwd = tmp_path / "consumer-repo"
    cwd.mkdir()
    result = _run(shipped_script, cwd, "--diff-base", BASE, "--changed-path", "README.md")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "activate"
    assert payload["changed_documents"] == ["README.md"]

    skipped = _run(shipped_script, cwd, "--diff-base", BASE, "--changed-path", "tests/test_a.py")
    assert skipped.returncode == 0, skipped.stderr
    assert json.loads(skipped.stdout)["decision"] == "skip"


@pytest.mark.parametrize(
    "name",
    [
        Path("test") / "scripts" / "doc_accuracy_trigger.py",
        Path("test") / "references" / "doc-accuracy-gate.md",
    ],
)
def test_shipped_copies_are_byte_identical(name: Path) -> None:
    canonical = (SKILLS_ROOT / name).read_bytes()
    assert (SRC_CLAUDE_SKILLS_ROOT / name).read_bytes() == canonical
    assert (COPILOT_SKILLS_ROOT / name).read_bytes() == canonical


def test_cli_exits_2_when_the_classifier_is_missing(tmp_path: Path) -> None:
    script = SKILLS_ROOT / "test" / "scripts" / "doc_accuracy_trigger.py"
    result = _run(
        script,
        tmp_path,
        "--diff-base",
        BASE,
        "--classifier",
        str(tmp_path / "nope.py"),
        "--changed-path",
        "README.md",
    )
    assert result.returncode == 2
    assert "review-axis classifier not found" in result.stderr
    assert result.stdout == ""


def test_cli_exits_2_when_the_sibling_review_skill_is_absent(tmp_path: Path) -> None:
    """Negative control for the vendored test: without review/, no decision."""
    plugin_skills = tmp_path / "plugin" / "skills"
    plugin_skills.mkdir(parents=True)
    copy_vendored_entry(SKILLS_ROOT / "test", plugin_skills / "test")
    result = _run(
        plugin_skills / "test" / "scripts" / "doc_accuracy_trigger.py",
        tmp_path,
        "--diff-base",
        BASE,
        "--changed-path",
        "README.md",
    )
    assert result.returncode == 2


def test_main_returns_2_on_a_blank_diff_base(capsys: pytest.CaptureFixture[str]) -> None:
    assert mod.main(["--diff-base", "  ", "--changed-path", "README.md"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--diff-base is blank" in captured.err


def test_main_requires_a_diff_base(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        mod.main(["--changed-path", "README.md"])
    assert exc.value.code == 2
    assert "--diff-base" in capsys.readouterr().err


def test_main_prints_the_decision_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = mod.main(
        ["--diff-base", BASE, "--changed-path", "src/service.py", "--effect", "public-api"]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "activate"
    assert payload["behavioral_escalation"] == "required"


def test_main_returns_2_on_a_missing_classifier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert mod.main(["--diff-base", BASE, "--classifier", str(tmp_path / "nope.py")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "doc_accuracy_trigger: review-axis classifier not found" in captured.err


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## )", text, re.M | re.S)
    assert match, f"section {heading!r} missing"
    return match.group(1)


def test_gate5_composes_doc_accuracy_instead_of_a_checklist() -> None:
    gate5 = _section(TEST_SKILL_MD.read_text(encoding="utf-8"), GATE5_HEADING)
    assert "references/doc-accuracy-gate.md" in gate5
    assert "doc_accuracy_trigger.py" in gate5
    assert "DOC ACCURACY: SKIPPED" in gate5
    assert "DOC ACCURACY REPORT" in gate5
    reference = GATE_REFERENCE.read_text(encoding="utf-8")
    assert 'Skill(skill="doc-accuracy")' in reference
    assert "skills/test/scripts/doc_accuracy_trigger.py" in reference
    assert "--diff-base" in reference
    assert "adapt_local_axis_verdict" in reference
    assert "Exit `2`" in reference
    # doc-accuracy owns its phases and taxonomy; Gate 5 must not copy them.
    for copied in (
        "Asymmetric Verification",
        "Phase 1: Assessment",
        "Phase 2: Claim Extraction",
        "Phase 3: Compilability",
        "Issue Taxonomy",
        "Spec vs Behavior",
    ):
        assert copied not in gate5
        assert copied not in reference


def test_gate_reference_effect_list_matches_the_script() -> None:
    reference = GATE_REFERENCE.read_text(encoding="utf-8")
    effects_line = reference.split("Effects:", 1)[1].split(". ", 1)[0]
    assert set(re.findall(r"`([a-z-]+)`", effects_line)) == set(mod.EFFECTS)


def test_gate_reference_output_contract_exposes_every_field_the_issue_requires() -> None:
    reference = GATE_REFERENCE.read_text(encoding="utf-8")
    block = reference.split("DOC ACCURACY REPORT", 1)[1].split("```", 1)[0]
    for field in (
        "Activation:",
        "Diff base:",
        "Phases executed:",
        "Deterministic scan:",
        "Behavioral and cross-document:",
        "FINDINGS:",
        "Remediation:",
    ):
        assert field in block, field
    for remediation in (
        "correct durable claim",
        "delete derived claim",
        "reference canonical source",
        "generate projection",
        "consolidate authority",
    ):
        assert remediation in block, remediation


def test_gate_reference_names_every_trigger_output_field_it_consumes() -> None:
    reference = GATE_REFERENCE.read_text(encoding="utf-8")
    payload = mod.decide(["README.md"], [], BASE, mod.load_classifier())
    for field in (
        "changed_documents",
        "behavioral_escalation",
        "coupled_documents_needed",
        "historical_paths",
        "unreadable_documents",
        "reason",
        "diff_base",
    ):
        assert field in reference, field
        assert field in payload, field
