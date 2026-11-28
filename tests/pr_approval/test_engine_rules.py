"""Engine tests: rule overlap, the classifier seam, and repository modes."""

from __future__ import annotations

import pytest

from scripts.pr_approval import engine
from scripts.pr_approval.classifier import ClassifierResult
from scripts.pr_approval.engine import evaluate, evidence_fingerprint
from scripts.pr_approval.policy import parse_policy
from scripts.pr_approval.registry import parse_registry
from scripts.pr_approval.snapshot import parse_snapshot
from tests.pr_approval.fixtures import POLICY_TOML, REGISTRY_TOML, golden, run


def _file(raw: dict) -> dict:
    return raw["files"]["items"][0]


def _with_rule(extra: str) -> str:
    return POLICY_TOML + extra


HOLD_RULE = """
[[rules]]
id = "hold-design"
mode = "observe"
effect = "hold"
[rules.all]
paths = ["docs/design/**"]
"""

SECOND_ALLOW = """
[[rules]]
id = "design-also"
mode = "observe"
effect = "allow"
[rules.all]
paths = ["docs/design/**/*.md"]
"""

CLASSIFY_RULE = """
[[rules]]
id = "design-residue"
mode = "observe"
effect = "classify"
classifier = "docs-prose-residue"
[rules.all]
paths = ["docs/design/**/*.md"]
"""


def test_hold_rule_wins_over_allow() -> None:
    decision = run(golden(), policy_toml=_with_rule(HOLD_RULE))
    assert (decision.verdict, decision.reasons, decision.rule_id) == (
        "HOLD",
        ("HOLD_RULE",),
        "hold-design",
    )


def test_hold_rule_matches_any_path() -> None:
    raw = golden()
    raw["files"]["items"].append({**_file(raw), "path": "docs/runbooks/x.md"})
    assert run(raw, policy_toml=_with_rule(HOLD_RULE)).reasons == ("HOLD_RULE",)


def test_hold_rule_without_match_passes_through() -> None:
    policy = _with_rule(HOLD_RULE.replace("docs/design/**", "docs/patterns/**"))
    assert run(golden(), policy_toml=policy).verdict == "WOULD_APPROVE"


def test_two_allow_rules_are_ambiguous() -> None:
    assert run(golden(), policy_toml=_with_rule(SECOND_ALLOW)).reasons == ("AMBIGUOUS_RULES",)


def test_off_rule_is_skipped() -> None:
    policy = _with_rule(SECOND_ALLOW.replace('mode = "observe"', 'mode = "off"'))
    assert run(golden(), policy_toml=policy).verdict == "WOULD_APPROVE"


class _Fixed:
    def __init__(self, verdict: str | None) -> None:
        self.verdict = verdict
        self.calls = 0

    def classify(self, classifier_id: str, evidence: dict):
        self.calls += 1
        return None if self.verdict is None else ClassifierResult(self.verdict, "ok")


def _run_classify(verdict: str | None, policy_text: str | None = None):
    raw = golden()
    classifier = _Fixed(verdict)
    decision = evaluate(
        parse_snapshot(raw),
        parse_policy((policy_text or _with_rule(CLASSIFY_RULE)).encode()),
        parse_registry(REGISTRY_TOML.encode()),
        (),
        evidence_fingerprint(raw),
        classifier,
    )
    return decision, classifier


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [
        ("pass", "CLASSIFIER_ALLOW_DISABLED"),
        ("hold", "CLASSIFIER_HOLD"),
        ("abstain", "CLASSIFIER_ABSTAIN"),
        (None, "CLASSIFIER_UNAVAILABLE"),
    ],
)
def test_classifier_may_only_hold(verdict, reason) -> None:
    decision, classifier = _run_classify(verdict)
    assert decision.verdict == "HOLD"
    assert decision.reasons == (reason,)
    assert decision.rule_id == "design-residue"
    assert classifier.calls == 1


def test_default_classifier_is_stub() -> None:
    decision = run(golden(), policy_toml=_with_rule(CLASSIFY_RULE))
    assert decision.reasons == ("CLASSIFIER_UNAVAILABLE",)


def test_classifier_budget_zero_holds_without_call() -> None:
    policy = _with_rule(CLASSIFY_RULE).replace(
        "max_classifier_calls = 1", "max_classifier_calls = 0"
    )
    decision, classifier = _run_classify("pass", policy)
    assert decision.reasons == ("CLASSIFIER_BUDGET",)
    assert classifier.calls == 0


def test_classifier_not_called_when_hard_stop_fires() -> None:
    raw = golden()
    raw["pull_request"]["draft"] = True
    classifier = _Fixed("pass")
    evaluate(
        parse_snapshot(raw),
        parse_policy(_with_rule(CLASSIFY_RULE).encode()),
        parse_registry(REGISTRY_TOML.encode()),
        (),
        evidence_fingerprint(raw),
        classifier,
    )
    assert classifier.calls == 0


def test_mode_off() -> None:
    policy = POLICY_TOML.replace('mode = "observe"', 'mode = "off"')
    decision = run(golden(), policy_toml=policy)
    assert (decision.verdict, decision.reasons) == ("OFF", ("MODE_OFF",))


def test_mode_enforce_holds() -> None:
    policy = POLICY_TOML.replace('mode = "observe"\n\n[budget]', 'mode = "enforce"\n\n[budget]')
    decision = run(golden(), policy_toml=policy)
    assert (decision.verdict, decision.reasons) == ("HOLD", ("ENFORCE_NOT_IMPLEMENTED",))


def test_missing_policy_holds() -> None:
    raw = golden()
    decision = evaluate(parse_snapshot(raw), None, None, (), evidence_fingerprint(raw))
    assert (decision.verdict, decision.reasons, decision.policy_digest) == (
        "HOLD",
        ("POLICY_INVALID",),
        None,
    )


def test_missing_registry_holds() -> None:
    raw = golden()
    decision = evaluate(
        parse_snapshot(raw), parse_policy(POLICY_TOML.encode()), None, (), evidence_fingerprint(raw)
    )
    assert decision.reasons == ("REGISTRY_INVALID",)


def test_engine_exception_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("defect")

    monkeypatch.setattr(engine, "hard_stops", boom)
    decision = run(golden())
    assert (decision.verdict, decision.reasons) == ("HOLD", ("ENGINE_ERROR",))


def test_garbage_snapshot_holds() -> None:
    decision = run({"pull_request": "nope", "files": [1, 2]})
    assert decision.verdict == "HOLD"
    assert {"EVIDENCE_INCOMPLETE", "FILES_INCOMPLETE"} <= set(decision.reasons)


def test_non_dict_snapshot_holds() -> None:
    assert run(["not", "a", "dict"]).verdict == "HOLD"


def test_fingerprint_changes_with_evidence() -> None:
    raw = golden()
    first = evidence_fingerprint(raw)
    raw["pull_request"]["head_sha"] = "f" * 40
    assert evidence_fingerprint(raw) != first


def test_decision_to_dict_lists_reasons() -> None:
    data = run(golden()).to_dict()
    assert data["reasons"] == ["RULE_MATCHED"]
    assert data["verdict"] == "WOULD_APPROVE"


def test_rule_without_paths_selector() -> None:
    extra = (
        '\n[[rules]]\nid = "small"\nmode = "observe"\neffect = "allow"\n'
        "[rules.all]\nmax_files = 5\n"
    )
    assert run(golden(), policy_toml=_with_rule(extra)).reasons == ("AMBIGUOUS_RULES",)
