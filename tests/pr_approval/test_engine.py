"""Engine tests: one golden WOULD_APPROVE, then one mutation per condition."""

from __future__ import annotations

import pytest

from scripts.pr_approval import engine
from scripts.pr_approval.classifier import ClassifierResult
from scripts.pr_approval.engine import evaluate, evidence_fingerprint
from scripts.pr_approval.policy import parse_policy
from scripts.pr_approval.registry import parse_registry
from scripts.pr_approval.snapshot import parse_snapshot
from tests.pr_approval.fixtures import (
    AGENT,
    APPROVER,
    BOT,
    CHECK_APP,
    HEAD,
    HUMAN,
    POLICY_TOML,
    REGISTRY_TOML,
    golden,
    run,
)


def _file(raw: dict) -> dict:
    return raw["files"]["items"][0]


def test_golden_would_approve() -> None:
    decision = run(golden())
    assert decision.verdict == "WOULD_APPROVE"
    assert decision.rule_id == "docs-prose-only"
    assert decision.reasons == ("RULE_MATCHED",)
    assert decision.mode == "observe"
    assert decision.head_sha == HEAD
    assert decision.policy_commit == "b" * 40
    assert len(decision.policy_digest) == 64
    assert len(decision.evidence_fingerprint) == 64


def _mutate_state(raw, key, value):
    raw["pull_request"][key] = value


HARD_STOP_CASES = [
    ("closed", lambda r: _mutate_state(r, "state", "closed"), "PR_NOT_OPEN"),
    ("draft", lambda r: _mutate_state(r, "draft", True), "DRAFT"),
    ("draft missing", lambda r: r["pull_request"].pop("draft"), "DRAFT"),
    ("other base", lambda r: _mutate_state(r, "base_ref", "release"), "BASE_NOT_DEFAULT"),
    ("fork", lambda r: _mutate_state(r, "head_repository_id", 999), "FORK"),
    ("conflict", lambda r: _mutate_state(r, "mergeable", "CONFLICTING"), "MERGE_CONFLICT"),
    ("mergeable unknown", lambda r: _mutate_state(r, "mergeable", "UNKNOWN"), "MERGEABLE_UNKNOWN"),
    ("mergeable garbage", lambda r: _mutate_state(r, "mergeable", "maybe"), "MERGEABLE_UNKNOWN"),
    ("stop label", lambda r: r["labels"]["items"].append({"name": "approval:stop"}), "STOP_LABEL"),
    ("repo stop", lambda r: r["stops"].update(repository=True), "REPO_STOP"),
    ("repo stop unreadable", lambda r: r.pop("stops"), "REPO_STOP"),
    ("workflow edit", lambda r: _file(r).update(path=".github/workflows/ci.yml"), "POLICY_EDIT"),
    (
        "policy edit",
        lambda r: _file(r).update(path=".github/pr-approval-policy.toml"),
        "POLICY_EDIT",
    ),
    (
        "registry edit",
        lambda r: _file(r).update(path=".github/pr-approval-registry.toml"),
        "POLICY_EDIT",
    ),
    (
        "policy code edit",
        lambda r: _file(r).update(path="scripts/pr_approval/engine.py"),
        "POLICY_EDIT",
    ),
    ("codeowners file", lambda r: _file(r).update(path=".github/CODEOWNERS"), "PROTECTED_PATH"),
    ("hooks", lambda r: _file(r).update(path=".githooks/pre-push"), "PROTECTED_PATH"),
    ("env file", lambda r: _file(r).update(path="docs/design/.env"), "PROTECTED_PATH"),
    (
        "codeowners path",
        lambda r: _file(r).update(path="scripts/validation/x.py"),
        "CODEOWNERS_PATH",
    ),
    (
        "codeowners old path on rename",
        lambda r: _file(r).update(previous_path="scripts/validation/x.md", status="renamed"),
        "CODEOWNERS_PATH",
    ),
    ("author missing", lambda r: r["pull_request"]["author"].pop("id"), "AUTHOR_UNKNOWN"),
    (
        "author unregistered",
        lambda r: r["pull_request"]["author"].update(id=6006),
        "AUTHOR_UNKNOWN",
    ),
    (
        "author is approver",
        lambda r: r["pull_request"]["author"].update(id=APPROVER),
        "SAME_IDENTITY",
    ),
    (
        "human changes requested",
        lambda r: r["reviews"]["items"].append(
            {"reviewer_id": HUMAN, "state": "CHANGES_REQUESTED"}
        ),
        "HUMAN_CHANGES_REQUESTED",
    ),
    (
        "unknown reviewer veto counts as human",
        lambda r: r["reviews"]["items"].append({"state": "CHANGES_REQUESTED"}),
        "HUMAN_CHANGES_REQUESTED",
    ),
    (
        "bot changes requested",
        lambda r: r["reviews"]["items"].append({"reviewer_id": BOT, "state": "CHANGES_REQUESTED"}),
        "BOT_CHANGES_REQUESTED",
    ),
    (
        "comment does not clear veto",
        lambda r: r["reviews"]["items"].extend(
            [
                {"reviewer_id": HUMAN, "state": "CHANGES_REQUESTED"},
                {"reviewer_id": HUMAN, "state": "COMMENTED"},
            ]
        ),
        "HUMAN_CHANGES_REQUESTED",
    ),
    (
        "dismissed later approval leaves earlier veto",
        lambda r: r["reviews"]["items"].extend(
            [
                {"reviewer_id": HUMAN, "state": "CHANGES_REQUESTED"},
                {"reviewer_id": HUMAN, "state": "DISMISSED"},
            ]
        ),
        "HUMAN_CHANGES_REQUESTED",
    ),
    (
        "unknown review state",
        lambda r: r["reviews"]["items"].append({"reviewer_id": HUMAN, "state": "SUPER_APPROVED"}),
        "EVIDENCE_INCOMPLETE",
    ),
    (
        "unresolved threads",
        lambda r: r["review_threads"].update(unresolved=1),
        "UNRESOLVED_THREADS",
    ),
    (
        "threads incomplete",
        lambda r: r["review_threads"].update(complete=False),
        "EVIDENCE_INCOMPLETE",
    ),
    (
        "threads count missing",
        lambda r: r["review_threads"].pop("unresolved"),
        "EVIDENCE_INCOMPLETE",
    ),
    ("reviews incomplete", lambda r: r["reviews"].update(complete=False), "EVIDENCE_INCOMPLETE"),
    ("labels incomplete", lambda r: r["labels"].update(complete=False), "EVIDENCE_INCOMPLETE"),
    ("labels not a list", lambda r: r["labels"].update(items="x"), "EVIDENCE_INCOMPLETE"),
    (
        "required checks incomplete",
        lambda r: r["checks"]["required"].update(complete=False),
        "EVIDENCE_INCOMPLETE",
    ),
    (
        "check results incomplete",
        lambda r: r["checks"]["results"].update(complete=False),
        "EVIDENCE_INCOMPLETE",
    ),
    (
        "check neutral",
        lambda r: r["checks"]["results"]["items"][0].update(conclusion="neutral"),
        "REQUIRED_CHECK_NOT_GREEN",
    ),
    (
        "check skipped",
        lambda r: r["checks"]["results"]["items"][0].update(conclusion="skipped"),
        "REQUIRED_CHECK_NOT_GREEN",
    ),
    (
        "check on old head",
        lambda r: r["checks"]["results"]["items"][0].update(head_sha="e" * 40),
        "REQUIRED_CHECK_NOT_GREEN",
    ),
    (
        "check from other publisher",
        lambda r: r["checks"]["results"]["items"][0].update(app_id=CHECK_APP + 1),
        "REQUIRED_CHECK_NOT_GREEN",
    ),
    (
        "same publisher failure beside success",
        lambda r: r["checks"]["results"]["items"].append(
            {
                "context": "Validate PR",
                "app_id": CHECK_APP,
                "conclusion": "failure",
                "head_sha": HEAD,
            }
        ),
        "REQUIRED_CHECK_NOT_GREEN",
    ),
    (
        "check missing",
        lambda r: r["checks"]["results"].update(items=[]),
        "REQUIRED_CHECK_NOT_GREEN",
    ),
    (
        "required context unnamed",
        lambda r: r["checks"]["required"]["items"].append({"app_id": CHECK_APP}),
        "REQUIRED_CHECK_NOT_GREEN",
    ),
    ("files incomplete", lambda r: r["files"].update(complete=False), "FILES_INCOMPLETE"),
    ("no files", lambda r: r["files"].update(items=[]), "FILES_INCOMPLETE"),
    ("file status unknown", lambda r: _file(r).update(status="mystery"), "FILES_INCOMPLETE"),
    ("file additions missing", lambda r: _file(r).pop("additions"), "FILES_INCOMPLETE"),
    ("binary flag missing", lambda r: _file(r).pop("binary"), "FILES_INCOMPLETE"),
    ("patch absent", lambda r: _file(r).update(patch_present=False), "PATCH_MISSING"),
    ("repo id missing", lambda r: r["repository"].pop("id"), "EVIDENCE_INCOMPLETE"),
]


@pytest.mark.parametrize(
    ("name", "mutate", "reason"), HARD_STOP_CASES, ids=[c[0] for c in HARD_STOP_CASES]
)
def test_hard_stop_holds(name: str, mutate, reason: str) -> None:
    raw = golden()
    mutate(raw)
    decision = run(raw)
    assert decision.verdict == "HOLD"
    assert reason in decision.reasons


def test_approval_from_same_reviewer_clears_veto() -> None:
    raw = golden()
    raw["reviews"]["items"] = [
        {"reviewer_id": HUMAN, "state": "CHANGES_REQUESTED"},
        {"reviewer_id": HUMAN, "state": "APPROVED"},
    ]
    assert run(raw).verdict == "WOULD_APPROVE"


def test_dismissed_veto_does_not_count() -> None:
    raw = golden()
    raw["reviews"]["items"] = [{"reviewer_id": HUMAN, "state": "DISMISSED"}]
    assert run(raw).verdict == "WOULD_APPROVE"


def test_alias_of_approver_is_same_identity() -> None:
    registry = REGISTRY_TOML + "\n[[aliases]]\nids = [1001, 2002]\n"
    decision = run(golden(), registry_toml=registry)
    assert "SAME_IDENTITY" in decision.reasons


def test_author_in_both_classes_is_unknown() -> None:
    registry = REGISTRY_TOML.replace(
        "agent_accounts = [{ id = 5005 }]", "agent_accounts = [{ id = 1001 }]"
    )
    assert "AUTHOR_UNKNOWN" in run(golden(), registry_toml=registry).reasons


def test_empty_approver_principals_hold() -> None:
    registry = REGISTRY_TOML.replace(
        'approver_principals = [{ id = 2002, login = "approver-app" }]', ""
    )
    assert "APPROVER_UNCONFIGURED" in run(golden(), registry_toml=registry).reasons


def test_missing_codeowners_holds() -> None:
    assert "EVIDENCE_INCOMPLETE" in run(golden(), codeowners=None).reasons


def test_policy_extra_paths_add_protection() -> None:
    policy = POLICY_TOML.replace(
        'mode = "observe"\n', 'mode = "observe"\n[protected]\nextra_paths = ["docs/design/**"]\n', 1
    )
    assert "PROTECTED_PATH" in run(golden(), policy_toml=policy).reasons


RULE_CASES = [
    ("agent author", lambda r: r["pull_request"]["author"].update(id=AGENT)),
    ("path outside allowlist", lambda r: _file(r).update(path="docs/faq.md")),
    ("nested runbook", lambda r: _file(r).update(path="docs/runbooks/sub/x.md")),
    ("non-markdown", lambda r: _file(r).update(path="docs/design/x.py")),
    ("case differs", lambda r: _file(r).update(path="Docs/design/x.md")),
    ("too many lines", lambda r: _file(r).update(additions=99, deletions=2)),
    ("rename", lambda r: _file(r).update(status="renamed", previous_path="docs/design/old.md")),
    ("copy", lambda r: _file(r).update(status="copied")),
    ("binary", lambda r: _file(r).update(binary=True)),
    ("code fence", lambda r: _file(r).update(touches_code_fence=True)),
    ("code fence unknown", lambda r: _file(r).pop("touches_code_fence")),
]


@pytest.mark.parametrize(("name", "mutate"), RULE_CASES, ids=[c[0] for c in RULE_CASES])
def test_rule_condition_no_match(name: str, mutate) -> None:
    raw = golden()
    mutate(raw)
    decision = run(raw)
    assert decision.verdict == "HOLD"
    assert decision.reasons == ("NO_MATCH",)


def test_too_many_files_no_match() -> None:
    raw = golden()
    base = _file(raw)
    raw["files"]["items"] = [
        {**base, "path": f"docs/design/f{i}.md", "additions": 1, "deletions": 0} for i in range(6)
    ]
    assert run(raw).reasons == ("NO_MATCH",)


def test_five_files_at_limit_still_match() -> None:
    raw = golden()
    base = _file(raw)
    raw["files"]["items"] = [
        {**base, "path": f"docs/design/f{i}.md", "additions": 20, "deletions": 0} for i in range(5)
    ]
    assert run(raw).verdict == "WOULD_APPROVE"


def test_removed_file_still_matches() -> None:
    raw = golden()
    _file(raw).update(status="removed", additions=0, deletions=8)
    assert run(raw).verdict == "WOULD_APPROVE"


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


def test_file_path_missing_holds() -> None:
    raw = golden()
    _file(raw).pop("path")
    assert "FILES_INCOMPLETE" in run(raw).reasons


def test_unknown_identity_comment_is_ignored() -> None:
    raw = golden()
    raw["reviews"]["items"] = [{"state": "COMMENTED"}]
    assert run(raw).verdict == "WOULD_APPROVE"


def test_rule_without_paths_selector() -> None:
    extra = (
        '\n[[rules]]\nid = "small"\nmode = "observe"\neffect = "allow"\n'
        "[rules.all]\nmax_files = 5\n"
    )
    assert run(golden(), policy_toml=_with_rule(extra)).reasons == ("AMBIGUOUS_RULES",)
