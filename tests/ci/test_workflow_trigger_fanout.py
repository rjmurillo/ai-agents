"""A workflow may not fire twice for the same commit.

Twelve workflows listed feature-branch globs under ``push:`` while also
listing ``pull_request: branches: [main]``. Pushing a commit to a branch that
already has a PR started both runs, and both produced check runs with
identical job names, so every one of those jobs ran twice against the same
SHA.

Measured on PR #3836 before the fix: 146 check runs, 40 of them a repeat of a
name already present. That is the measured waste and it is the whole case for
this change.

An earlier version of this docstring attributed a set of blocked PRs to that
waste starving the required checks. Re-measured: the blocking came from the
branch ruleset requiring ``code_quality`` and ``copilot_code_review``, not from
queue pressure. The starvation story is withdrawn. The duplicate runs are still
pure waste, which is reason enough to remove them.

Keeping ``main`` under ``push:`` preserves post-merge validation. A branch
without a PR loses pre-PR feedback, which the ``pull_request`` trigger
restores the moment a PR exists.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# Branches that only ever exist to carry a pull request. A push to one of
# these is always followed by the pull_request trigger for the same SHA.
_PR_ONLY_BRANCH_GLOBS = frozenset(
    {"feat/**", "fix/**", "chore/**", "copilot/**", "agent/**"}
)


def _triggers(path: pathlib.Path) -> dict | None:
    """Return a trigger mapping, or None when the file cannot be read as one.

    ``on`` is the YAML 1.1 boolean ``True`` once parsed, so both keys are
    tried. The list form (``on: [pull_request]``) carries no ``push:`` mapping
    and so cannot double-trigger; it maps to an empty mapping rather than a
    skip, because a skip would also hide a workflow whose YAML had broken.
    """
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:  # pragma: no cover - actionlint owns malformed YAML
        return None
    if not isinstance(loaded, dict):
        return None
    on = loaded.get(True, loaded.get("on"))
    if isinstance(on, dict):
        return on
    return {} if isinstance(on, (list, str)) else None


def double_triggered_branches(on: dict) -> list[str]:
    """Return the branch globs that make ``on`` fire twice for one commit."""
    push = on.get("push")
    if not isinstance(push, dict) or "pull_request" not in on:
        return []
    branches = push.get("branches")
    if not isinstance(branches, list):
        return []
    return [b for b in branches if b in _PR_ONLY_BRANCH_GLOBS]


def _workflows() -> list[pathlib.Path]:
    return sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


@pytest.mark.parametrize("path", _workflows(), ids=lambda p: p.name)
def test_no_workflow_fires_on_both_a_branch_push_and_its_pull_request(
    path: pathlib.Path,
) -> None:
    """Positive: no live workflow carries the double trigger."""
    on = _triggers(path)
    if on is None:
        pytest.skip(f"{path.name} is not a parseable workflow mapping")
    assert double_triggered_branches(on) == [], (
        f"{path.name} runs twice for every commit on a PR branch. "
        "Drop the feature-branch globs from push: and let pull_request cover them."
    )


def test_the_detector_reports_a_double_trigger() -> None:
    """Negative: the shape this test forbids is actually detected."""
    on = {
        "push": {"branches": ["main", "fix/**"]},
        "pull_request": {"branches": ["main"]},
    }
    assert double_triggered_branches(on) == ["fix/**"]


def test_a_push_only_workflow_is_not_double_triggered() -> None:
    """Negative: without pull_request there is no second run to collide with."""
    on = {"push": {"branches": ["main", "fix/**"]}}
    assert double_triggered_branches(on) == []


def test_a_list_form_trigger_carries_no_push_mapping() -> None:
    """Edge: ``on: [pull_request]`` is safe and must not be skipped."""
    assert _triggers(WORKFLOW_DIR / "dependency-review.yml") == {}


def test_main_stays_allowed_under_push() -> None:
    """Edge: post-merge validation on main is not what this test forbids."""
    on = {"push": {"branches": ["main"]}, "pull_request": {"branches": ["main"]}}
    assert double_triggered_branches(on) == []


def test_a_push_trigger_without_branches_is_not_flagged() -> None:
    """Edge: ``push:`` with only ``paths`` carries no branch list to read."""
    on = {"push": {"paths": ["src/**"]}, "pull_request": {"branches": ["main"]}}
    assert double_triggered_branches(on) == []


def test_a_bare_push_trigger_is_not_flagged() -> None:
    """Edge: ``push:`` with a null body parses to None, not a mapping."""
    on = {"push": None, "pull_request": {"branches": ["main"]}}
    assert double_triggered_branches(on) == []


def test_every_repaired_workflow_still_validates_main() -> None:
    """Edge: removing the globs must not remove post-merge coverage."""
    repaired = (
        "pytest.yml",
        "cli-smoke.yml",
        "skillbook-validation.yml",
        "validate-adr-number-uniqueness.yml",
        "validate-planning-artifacts.yml",
        "validate-plugin-manifests.yml",
        "validate-plugin-version-bump.yml",
        "validate-rule-activation-coverage.yml",
        "validate-spec-id-uniqueness.yml",
        "validate-vendor-portability.yml",
        "validate-generated-agents.yml",
        "validate-paths.yml",
    )
    for name in repaired:
        on = _triggers(WORKFLOW_DIR / name)
        assert on is not None, name
        assert on["push"]["branches"] == ["main"], name
        assert on["pull_request"]["branches"] == ["main"], name


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
