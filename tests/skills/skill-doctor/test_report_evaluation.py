"""Evaluation provenance (issue #7245) and handoff candidates (issue #7247)."""

from __future__ import annotations

import html
import json
from pathlib import Path

import pytest
import report_evaluation as ev
from render_report import main, render_page

SKILL_ROOT = Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "skill-doctor"
SCORES = {
    "efficiency": 0.7,
    "code_quality": 0.7,
    "procedure_compliance": 0.7,
    "verbosity": 0.7,
    "skill_coverage": 0.5,
    "overall": 0.7,
}


def _candidate(**overrides):
    candidate = {
        "skill": "deploy",
        "status": "unevaluated",
        "owner": "skill",
        "target": "/repo/.claude/skills/deploy/SKILL.md",
        "change": "Add a preflight check for the staging token.",
        "evidence": "session abc123, efficiency 0.25: agent retried deploy 4 times without a token",
        "mechanism": "A preflight step makes the missing token visible before the first deploy.",
        "expected_improvement": "One deploy attempt instead of four.",
        "reproduction": "Run deploy with STAGING_TOKEN unset.",
        "acceptance_checks": ["agent reports the missing token before deploying"],
        "risks": ["token check may be redundant in CI"],
    }
    candidate.update(overrides)
    return candidate


def _measured(status):
    return _candidate(
        status=status,
        evaluation={
            "baseline": "skillopt run 7 baseline 0.41",
            "candidate": "skillopt run 7 candidate 0.63",
        },
    )


def _report(suggestions=(), evaluation=None, findings=("finding",), summary=None):
    report = {"scores": SCORES, "top_findings": list(findings), "suggestions": list(suggestions)}
    if evaluation is not None:
        report["evaluation"] = evaluation
    if summary is not None:
        report["summary"] = summary
    return report


def _run_cli(tmp_path, report, capsys):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    code = 0
    try:
        main([str(path)])
    except SystemExit as exc:
        code = exc.code
    out = capsys.readouterr()
    return code, out.out, out.err, tmp_path / "report.html"


# Provenance (issue #7245)


def test_report_without_evaluation_block_is_static_only():
    assert ev.evaluation_of({}) == {"diagnosis": "static", "optimization": "not_run"}


def test_static_only_run_states_candidates_remain_unevaluated():
    summary = ev.evaluation_summary(_report([_candidate()]))

    assert "Diagnosis: static. Optimization: not run." in summary
    assert "1 unevaluated" in summary
    assert "candidate effectiveness remains unevaluated" in summary


def test_empty_static_run_is_not_evidence_against_improvement():
    page = render_page(_report())

    assert html.escape(ev.EMPTY_STATIC_STATEMENT, quote=True) in page
    assert "cleared the bar" not in page


def test_html_and_text_expose_the_same_evaluation_status(tmp_path, capsys):
    report = _report([_candidate()])

    code, out, _, html_path = _run_cli(tmp_path, report, capsys)

    line = ev.evaluation_summary(report)
    assert code == 0
    assert f"evaluation: {line}" in out
    assert f'id="evaluation-status">{html.escape(line, quote=True)}</p>' in html_path.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "text",
    [
        "No skill changes were justified for this window.",
        "No change is warranted.",
        "No beneficial change was found.",
        "A tighter preflight would not improve outcomes.",
    ],
)
def test_static_run_rejects_unsupported_no_change_verdict(tmp_path, capsys, text):
    code, _, err, html_path = _run_cli(tmp_path, _report(findings=[text]), capsys)

    assert code == 1
    assert "measured no-change verdict" in err
    assert not html_path.exists()


def test_unsupported_verdict_in_summary_is_rejected():
    errors = ev.validate_report(_report(summary="No skill edits are needed."))

    assert any(error.startswith("summary:") for error in errors)


def test_neutral_static_wording_is_accepted():
    report = _report(
        findings=["No candidates proposed through static triage; effectiveness unevaluated."]
    )

    assert ev.validate_report(report) == []


@pytest.mark.parametrize("status", ev.MEASURED_STATUSES)
def test_measured_status_needs_baseline_and_candidate_evidence(status):
    report = _report([_candidate(status=status)], evaluation={"optimization": "run"})

    errors = ev.validate_report(report)

    assert any("needs evaluation.baseline and evaluation.candidate" in e for e in errors)


@pytest.mark.parametrize("status", ev.MEASURED_STATUSES)
def test_measured_status_needs_an_optimization_run(status):
    errors = ev.validate_report(_report([_measured(status)]))

    assert any("needs evaluation.optimization 'run'" in e for e in errors)


@pytest.mark.parametrize("status", ev.MEASURED_STATUSES)
def test_scored_candidates_later_accepted_rejected_or_inconclusive_render(tmp_path, capsys, status):
    report = _report([_measured(status)], evaluation={"diagnosis": "static", "optimization": "run"})

    code, out, _, html_path = _run_cli(tmp_path, report, capsys)

    page = html_path.read_text(encoding="utf-8")
    assert code == 0
    assert f"1 {status}" in out
    assert f"[{status}]" in page
    assert "skillopt run 7 baseline 0.41" in page
    assert "skillopt run 7 candidate 0.63" in page


def test_scored_rejection_may_state_a_no_change_verdict():
    report = _report(
        [_measured("rejected")],
        evaluation={"optimization": "run"},
        findings=["No beneficial change: the candidate regressed held-out tasks."],
    )

    assert ev.validate_report(report) == []


@pytest.mark.parametrize("field", ["change", "mechanism", "expected_improvement"])
def test_unmeasured_suggestion_prose_cannot_claim_a_no_change_verdict(field):
    report = _report([_candidate(**{field: "No beneficial change is possible."})])

    errors = ev.validate_report(report)

    assert any(f"suggestions[0] (deploy).{field}" in e for e in errors)


def test_measured_rejection_may_state_its_own_no_change_verdict():
    candidate = _measured("rejected")
    candidate["change"] = "No beneficial change: the candidate regressed held-out tasks."

    assert ev.validate_report(_report([candidate], evaluation={"optimization": "run"})) == []


def test_report_wide_verdict_is_rejected_when_a_candidate_was_accepted():
    report = _report(
        [_measured("accepted"), _measured("rejected")],
        evaluation={"optimization": "run"},
        findings=["No beneficial change was found."],
    )

    assert any("top_findings[0]" in e for e in ev.validate_report(report))


def test_report_wide_verdict_is_rejected_while_a_candidate_stays_unevaluated():
    report = _report(
        [_measured("rejected"), _candidate()],
        evaluation={"optimization": "run"},
        findings=["No beneficial change was found."],
    )

    assert any("top_findings[0]" in e for e in ev.validate_report(report))


def test_unknown_status_and_owner_are_rejected():
    errors = ev.validate_report(_report([_candidate(status="proven", owner="someone")]))
    errors += ev.validate_report(_report([_candidate(owner="someone")]))

    assert any("status must be one of" in e for e in errors)
    assert any("owner must be one of" in e for e in errors)


def test_unknown_optimization_stage_is_rejected():
    assert ev.validate_report(_report(evaluation={"optimization": "maybe"}))


# Candidates and handoff prompts (issue #7247)


def test_evidence_backed_failure_renders_a_visible_unevaluated_candidate():
    page = render_page(_report([_candidate()]))

    assert "[unevaluated]" in page
    assert "Observed (fact)" in page
    assert "Hypothesis" in page
    assert "Expected improvement (unmeasured)" in page


def test_each_candidate_renders_both_copyable_prompts():
    page = render_page(_report([_candidate()]))

    assert page.count('<pre class="prompt">') == 2
    assert "skillopt handoff prompt" in page
    assert "skillforge handoff prompt" in page


@pytest.mark.parametrize("builder", [ev.skillopt_prompt, ev.skillforge_prompt])
def test_prompts_carry_evidence_target_and_acceptance_checks(builder):
    candidate = _candidate()

    prompt = builder(candidate)

    assert candidate["evidence"] in prompt
    assert candidate["target"] in prompt
    assert candidate["acceptance_checks"][0] in prompt
    assert "without authorization" in prompt


def test_skillopt_prompt_requires_scored_baseline_before_claims():
    prompt = ev.skillopt_prompt(_candidate())

    assert "First establish a scored baseline" in prompt
    assert "Do not claim improvement without passing the evaluation gate." in prompt


def test_missing_fields_are_disclosed_not_invented():
    candidate = {"skill": "deploy", "change": "Add a check."}

    gaps = ev.missing_evidence(candidate)
    prompt = ev.skillopt_prompt(candidate)

    assert "acceptance checks not supplied" in gaps
    assert "reproduction not supplied" in gaps
    assert "edit target unresolved" in gaps
    assert "Acceptance checks: not supplied." in prompt


def test_tooling_candidate_names_owner_without_instruction_causality():
    candidate = _candidate(owner="tooling", owner_target="collect_sessions.py session filter")

    prompt = ev.skillforge_prompt(candidate)

    assert "Owner: tooling (collect_sessions.py session filter)" in prompt
    assert "not proven to be an instruction defect" in prompt


def test_tooling_candidate_gets_a_routing_note_instead_of_a_skillopt_run():
    candidate = _candidate(owner="tooling", owner_target="collect_sessions.py", target="")

    prompt = ev.skillopt_prompt(candidate)

    assert prompt.startswith("This candidate is not a skillopt target")
    assert "collect_sessions.py" in prompt
    assert "First establish a scored baseline" not in prompt
    assert candidate["evidence"] in prompt


def test_new_skill_candidate_routes_through_skillforge_before_skillopt():
    prompt = ev.skillopt_prompt(_candidate(owner="new-skill", target="", skill="token-preflight"))

    assert prompt.startswith("No existing skill exists for skillopt to optimize")
    assert "skillforge first" in prompt


def test_tooling_candidate_with_owner_target_is_not_marked_unresolved():
    candidate = _candidate(owner="tooling", owner_target="collect_sessions.py", target="")

    gaps = ev.missing_evidence(candidate)

    assert "edit target unresolved" not in gaps
    assert "tooling owner unresolved" not in gaps


def test_tooling_candidate_without_owner_target_is_marked_unresolved():
    gaps = ev.missing_evidence(_candidate(owner="tooling", target=""))

    assert "tooling owner unresolved" in gaps


def test_unresolved_variants_are_not_selected_as_edit_target():
    candidate = _candidate(
        target="",
        variants=[
            {"path": "/repo/a/SKILL.md", "sha256": "a" * 64},
            {"path": "/home/b/SKILL.md", "sha256": "b" * 64},
        ],
    )

    identity = ev.target_identity(candidate)
    prompt = ev.skillopt_prompt(candidate)

    assert identity.startswith("unresolved: deploy")
    assert "/repo/a/SKILL.md" in identity and "/home/b/SKILL.md" in identity
    assert "Ask the user to select one variant as the edit target" in prompt
    assert ev.validate_report(_report([candidate])) == []


def test_unresolved_variants_with_a_drafted_diff_are_rejected():
    candidate = _candidate(
        target="", variants=[{"path": "/repo/a/SKILL.md", "sha256": "a" * 64}], diff="+x"
    )

    errors = ev.validate_report(_report([candidate]))

    assert any("unresolved variants carry a drafted diff" in e for e in errors)


@pytest.mark.parametrize("target", ["", "   ", "\t", None])
def test_blank_target_with_variants_and_a_diff_is_rejected(target):
    candidate = _candidate(target=target, variants=[{"path": "/a", "sha256": "a" * 64}], diff="+x")

    errors = ev.validate_report(_report([candidate]))

    assert any("unresolved variants carry a drafted diff" in e for e in errors)


def test_new_skill_candidate_has_proposed_identity():
    candidate = _candidate(owner="new-skill", target="", skill="token-preflight")

    assert ev.target_identity(candidate) == "proposed new skill: token-preflight"
    assert "edit target unresolved" not in ev.missing_evidence(candidate)


def test_prompt_text_is_escaped_in_html():
    page = render_page(_report([_candidate(evidence="<script>alert(1)</script>")]))

    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_legacy_suggestion_without_new_fields_renders_as_unevaluated():
    page = render_page(_report([{"skill": "deploy", "change": "x", "evidence": "y"}]))

    assert "[unevaluated]" in page


# SKILL.md contract


def test_skill_md_forbids_starting_skillopt_skillforge_or_edits():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "Do not start skillopt or skillforge, and do not edit installed skill files." in text
    assert "Drafts under `$REPORT_DIR/proposed/` are diagnosis output, not edits." in text
    assert "Do not apply suggested edits without the user's explicit instruction." in text
    assert "Never describe an empty or static-only suggestion list" in text


def test_improvement_reference_has_no_static_change_bar():
    text = (SKILL_ROOT / "references" / "skill-improvements.md").read_text(encoding="utf-8")

    assert "Do not propose changes by default" not in text
    assert "No static bar suppresses a candidate." in text
    assert "It is not evidence against improvement." in text
