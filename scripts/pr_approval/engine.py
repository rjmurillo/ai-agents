"""Observe-mode decision engine.

Order: repository mode, hard stops, deterministic rules, then the classifier
for residue only. ``HOLD`` is the default. ``WOULD_APPROVE`` has one return
site, reached only when no hard stop fired and exactly one allow rule matched.
The engine records a decision. It posts nothing and approves nothing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from scripts.pr_approval.classifier import Classifier, StubClassifier
from scripts.pr_approval.codeowners import CodeownersRule, owners_for
from scripts.pr_approval.globs import any_match
from scripts.pr_approval.policy import Policy, Rule
from scripts.pr_approval.registry import Registry
from scripts.pr_approval.snapshot import FILE_STATUSES, MERGEABLE_STATES, REVIEW_STATES, Snapshot

STOP_LABEL = "approval:stop"

# Trust roots and sensitive paths. Policy can add to this list, never remove.
POLICY_PATHS = (
    ".github/pr-approval-policy.toml",
    ".github/pr-approval-registry.toml",
    ".github/workflows/**",
    ".github/actions/**",
    "scripts/pr_approval/**",
    "tests/pr_approval/**",
)
FIXED_PROTECTED_PATHS = (
    ".github/cli-smoke/**",
    ".github/CODEOWNERS",
    "CODEOWNERS",
    "docs/CODEOWNERS",
    ".githooks/**",
    "lefthook.yml",
    "**/.env",
    "**/.env.*",
)


@dataclass(frozen=True)
class Decision:
    verdict: str
    mode: str
    rule_id: str | None
    reasons: tuple[str, ...]
    repository_id: int | None
    pr_number: int | None
    head_sha: str | None
    base_sha: str | None
    merge_base_sha: str | None
    policy_commit: str | None
    policy_digest: str | None
    evidence_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


def evidence_fingerprint(raw_snapshot: object) -> str:
    """SHA-256 of the canonical JSON form of the raw evidence."""
    canonical = json.dumps(raw_snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _changed_paths(snapshot: Snapshot) -> list[str]:
    paths: list[str] = []
    for changed in snapshot.files.items:
        if changed.path:
            paths.append(changed.path)
        if changed.previous_path:
            paths.append(changed.previous_path)
    return paths


def _evidence_stops(snapshot: Snapshot) -> list[str]:
    reasons: list[str] = []
    required = (
        snapshot.repository_id,
        snapshot.default_branch,
        snapshot.number,
        snapshot.state,
        snapshot.draft,
        snapshot.head_sha,
        snapshot.head_repository_id,
        snapshot.base_ref,
        snapshot.mergeable,
        snapshot.unresolved_threads,
        snapshot.repo_stop,
    )
    sections_complete = (
        snapshot.labels.complete,
        snapshot.reviews.complete,
        snapshot.threads_complete,
        snapshot.required_checks.complete,
        snapshot.check_results.complete,
    )
    if any(value is None for value in required) or not all(sections_complete):
        reasons.append("EVIDENCE_INCOMPLETE")
    files = snapshot.files
    if not files.complete or not files.items:
        reasons.append("FILES_INCOMPLETE")
    for changed in files.items:
        if (
            changed.path is None
            or changed.status not in FILE_STATUSES
            or changed.additions is None
            or changed.deletions is None
            or changed.binary is None
        ):
            reasons.append("FILES_INCOMPLETE")
        elif not changed.binary and changed.patch_present is not True:
            # An absent patch is unknown content, never an empty diff.
            reasons.append("PATCH_MISSING")
    if any(review.state not in REVIEW_STATES for review in snapshot.reviews.items):
        reasons.append("EVIDENCE_INCOMPLETE")
    return reasons


def _state_stops(snapshot: Snapshot) -> list[str]:
    reasons: list[str] = []
    if snapshot.state is not None and snapshot.state != "open":
        reasons.append("PR_NOT_OPEN")
    if snapshot.draft is not False:
        reasons.append("DRAFT")
    if snapshot.base_ref != snapshot.default_branch or snapshot.base_ref is None:
        reasons.append("BASE_NOT_DEFAULT")
    if snapshot.head_repository_id != snapshot.repository_id or snapshot.head_repository_id is None:
        reasons.append("FORK")
    if snapshot.mergeable == "CONFLICTING":
        reasons.append("MERGE_CONFLICT")
    elif snapshot.mergeable != "MERGEABLE" or snapshot.mergeable not in MERGEABLE_STATES:
        reasons.append("MERGEABLE_UNKNOWN")
    if snapshot.repo_stop is not False:
        reasons.append("REPO_STOP")
    if any(label.name == STOP_LABEL for label in snapshot.labels.items):
        reasons.append("STOP_LABEL")
    return reasons


def _path_stops(
    snapshot: Snapshot, policy: Policy, codeowners: tuple[CodeownersRule, ...] | None
) -> list[str]:
    reasons: list[str] = []
    protected = FIXED_PROTECTED_PATHS + policy.extra_protected_paths
    if codeowners is None:
        reasons.append("EVIDENCE_INCOMPLETE")
    for path in _changed_paths(snapshot):
        if any_match(POLICY_PATHS, path):
            reasons.append("POLICY_EDIT")
        if any_match(protected, path):
            reasons.append("PROTECTED_PATH")
        if codeowners is not None and owners_for(codeowners, path):
            reasons.append("CODEOWNERS_PATH")
    return reasons


def author_class(snapshot: Snapshot, registry: Registry) -> str | None:
    """Return ``independent``, ``agent``, or None when provenance is unproven."""
    author = snapshot.author_id
    if author is None:
        return None
    independent = author in registry.independent_authors
    agent = author in registry.agent_accounts or author in registry.bot_accounts
    if independent == agent:
        return None  # Unregistered, or registered as both.
    return "independent" if independent else "agent"


def _identity_stops(snapshot: Snapshot, registry: Registry) -> list[str]:
    reasons: list[str] = []
    if author_class(snapshot, registry) is None:
        reasons.append("AUTHOR_UNKNOWN")
    if not registry.approver_principals:
        reasons.append("APPROVER_UNCONFIGURED")
    if snapshot.author_id is not None:
        author_principal = registry.principal(snapshot.author_id)
        for approver in registry.approver_principals:
            if registry.principal(approver) & author_principal:
                reasons.append("SAME_IDENTITY")
                break
    return reasons


def _review_stops(snapshot: Snapshot, registry: Registry) -> list[str]:
    reasons: list[str] = []
    effective: dict[int, str] = {}
    for review in snapshot.reviews.items:
        if review.reviewer_id is None:
            # Unknown identity counts as human for vetoes, never for clearance.
            if review.state == "CHANGES_REQUESTED":
                reasons.append("HUMAN_CHANGES_REQUESTED")
            continue
        # COMMENTED and PENDING never clear a veto. A dismissed review no longer
        # counts, so an earlier undismissed decision from that reviewer stands.
        if review.state in ("APPROVED", "CHANGES_REQUESTED"):
            effective[review.reviewer_id] = review.state
    for reviewer, state in effective.items():
        if state == "CHANGES_REQUESTED":
            reasons.append(
                "BOT_CHANGES_REQUESTED" if registry.is_bot(reviewer) else "HUMAN_CHANGES_REQUESTED"
            )
    if snapshot.unresolved_threads is not None and snapshot.unresolved_threads != 0:
        reasons.append("UNRESOLVED_THREADS")
    return reasons


def _check_stops(snapshot: Snapshot) -> list[str]:
    for required in snapshot.required_checks.items:
        if required.context is None:
            return ["REQUIRED_CHECK_NOT_GREEN"]
        matches = [
            result
            for result in snapshot.check_results.items
            if result.context == required.context
            and result.head_sha == snapshot.head_sha
            and (required.app_id is None or result.app_id == required.app_id)
        ]
        # Every same-publisher result for the head must be success.
        if not matches or any(result.conclusion != "success" for result in matches):
            return ["REQUIRED_CHECK_NOT_GREEN"]
    return []


def hard_stops(
    snapshot: Snapshot,
    policy: Policy,
    registry: Registry,
    codeowners: tuple[CodeownersRule, ...] | None,
) -> list[str]:
    """Return every hard-stop reason code. Empty means no hard stop fired."""
    reasons = (
        _evidence_stops(snapshot)
        + _state_stops(snapshot)
        + _path_stops(snapshot, policy, codeowners)
        + _identity_stops(snapshot, registry)
        + _review_stops(snapshot, registry)
        + _check_stops(snapshot)
    )
    return list(dict.fromkeys(reasons))


def _paths_match(rule: Rule, snapshot: Snapshot) -> bool:
    """Allow rules need every changed path; hold rules need any changed path."""
    globs = rule.selector.paths
    if globs is None:
        return True
    paths = _changed_paths(snapshot)
    if rule.effect == "hold":
        return any(any_match(globs, path) for path in paths)
    return bool(paths) and all(any_match(globs, path) for path in paths)


def _size_matches(rule: Rule, snapshot: Snapshot) -> bool:
    selector = rule.selector
    files = snapshot.files.items
    if selector.max_files is not None and len(files) > selector.max_files:
        return False
    total = sum((f.additions or 0) + (f.deletions or 0) for f in files)
    return selector.max_changed_lines is None or total <= selector.max_changed_lines


def _content_matches(rule: Rule, snapshot: Snapshot) -> bool:
    """Forbid flags fail closed: an unknown flag value counts as present."""
    selector = rule.selector
    files = snapshot.files.items
    renamed = any(f.status in ("renamed", "copied") or f.previous_path for f in files)
    binary = any(f.binary is not False for f in files)
    fenced = any(f.touches_code_fence is not False for f in files)
    return not (
        (selector.forbid_renames and renamed)
        or (selector.forbid_binary and binary)
        or (selector.forbid_code_fences and fenced)
    )


def rule_matches(rule: Rule, snapshot: Snapshot, registry: Registry) -> bool:
    """Return True when every supplied selector matches. Unknown values fail."""
    wanted_class = rule.selector.author_class
    if wanted_class is not None and author_class(snapshot, registry) != wanted_class:
        return False
    return (
        _paths_match(rule, snapshot)
        and _size_matches(rule, snapshot)
        and _content_matches(rule, snapshot)
    )


def _hold(
    snapshot: Snapshot,
    policy: Policy | None,
    fingerprint: str,
    mode: str,
    reasons: list[str],
    rule_id: str | None = None,
) -> Decision:
    return Decision(
        verdict="HOLD",
        mode=mode,
        rule_id=rule_id,
        reasons=tuple(reasons),
        repository_id=snapshot.repository_id,
        pr_number=snapshot.number,
        head_sha=snapshot.head_sha,
        base_sha=snapshot.base_sha,
        merge_base_sha=snapshot.merge_base_sha,
        policy_commit=snapshot.default_branch_sha,
        policy_digest=policy.digest if policy else None,
        evidence_fingerprint=fingerprint,
    )


def _classify(rule: Rule, snapshot: Snapshot, policy: Policy, classifier: Classifier) -> str:
    if policy.budget.max_classifier_calls < 1 or policy.budget.max_spend_usd <= 0:
        return "CLASSIFIER_BUDGET"
    evidence: dict[str, object] = {"paths": _changed_paths(snapshot)}
    result = classifier.classify(rule.classifier or "", evidence)
    if result is None:
        return "CLASSIFIER_UNAVAILABLE"
    return {
        "hold": "CLASSIFIER_HOLD",
        "abstain": "CLASSIFIER_ABSTAIN",
    }.get(result.verdict, "CLASSIFIER_ALLOW_DISABLED")


def evaluate(
    snapshot: Snapshot,
    policy: Policy | None,
    registry: Registry | None,
    codeowners: tuple[CodeownersRule, ...] | None,
    fingerprint: str,
    classifier: Classifier | None = None,
) -> Decision:
    """Evaluate one snapshot. Any defect or exception yields HOLD."""
    if policy is None:
        return _hold(snapshot, None, fingerprint, "unknown", ["POLICY_INVALID"])
    if registry is None:
        return _hold(snapshot, policy, fingerprint, policy.mode, ["REGISTRY_INVALID"])
    try:
        return _evaluate(
            snapshot, policy, registry, codeowners, fingerprint, classifier or StubClassifier()
        )
    except Exception:
        return _hold(snapshot, policy, fingerprint, policy.mode, ["ENGINE_ERROR"])


def _evaluate(
    snapshot: Snapshot,
    policy: Policy,
    registry: Registry,
    codeowners: tuple[CodeownersRule, ...] | None,
    fingerprint: str,
    classifier: Classifier,
) -> Decision:
    if policy.mode == "off":
        decision = _hold(snapshot, policy, fingerprint, "off", ["MODE_OFF"])
        return Decision(**{**decision.__dict__, "verdict": "OFF"})
    if policy.mode != "observe":
        return _hold(snapshot, policy, fingerprint, policy.mode, ["ENFORCE_NOT_IMPLEMENTED"])
    stops = hard_stops(snapshot, policy, registry, codeowners)
    if stops:
        return _hold(snapshot, policy, fingerprint, "observe", stops)
    active = [rule for rule in policy.rules if rule.mode == "observe"]
    matched = [rule for rule in active if rule_matches(rule, snapshot, registry)]
    holds = [rule for rule in matched if rule.effect == "hold"]
    if holds:
        return _hold(snapshot, policy, fingerprint, "observe", ["HOLD_RULE"], holds[0].id)
    classified = [rule for rule in matched if rule.effect == "classify"]
    if classified:
        reasons = [_classify(rule, snapshot, policy, classifier) for rule in classified[:1]]
        return _hold(snapshot, policy, fingerprint, "observe", reasons, classified[0].id)
    allows = [rule for rule in matched if rule.effect == "allow"]
    if not allows:
        return _hold(snapshot, policy, fingerprint, "observe", ["NO_MATCH"])
    if len(allows) > 1:
        return _hold(snapshot, policy, fingerprint, "observe", ["AMBIGUOUS_RULES"])
    decision = _hold(snapshot, policy, fingerprint, "observe", ["RULE_MATCHED"], allows[0].id)
    return Decision(**{**decision.__dict__, "verdict": "WOULD_APPROVE"})
