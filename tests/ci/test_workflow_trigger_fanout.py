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
    {"feat/**", "fix/**", "chore/**", "copilot/**", "agent/**", "*", "**"}
)

# Reported when push carries no ``branches`` list. GitHub then fires it for
# every branch push: a bare ``push:``, a ``paths``-only filter, and a
# ``branches-ignore`` list all match feature branches. PR #4192 reopened
# pytest.yml this way and the glob check above could not see it.
EVERY_BRANCH = "<every branch>"
_TAG_FILTERS = frozenset({"tags", "tags-ignore"})


def _triggers(path: pathlib.Path) -> dict | None:
    """Return a trigger mapping, or None when the file cannot be read as one.

    ``on`` is the YAML 1.1 boolean ``True`` once parsed, so both keys are
    tried. The list and string forms (``on: [push, pull_request]``) carry no
    filters, so each event maps to ``None``, the same value a bare ``push:``
    key parses to. Mapping them rather than skipping keeps a broken workflow
    from hiding.
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
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return dict.fromkeys(on)
    return None


def double_triggered_branches(on: dict) -> list[str]:
    """Return the branch globs that make ``on`` fire twice for one commit."""
    if "push" not in on or "pull_request" not in on:
        return []
    push = on["push"] or {}
    if not isinstance(push, dict):
        return []
    branches = push.get("branches")
    if isinstance(branches, str):
        branches = [branches]
    if isinstance(branches, list):
        return [b for b in branches if b in _PR_ONLY_BRANCH_GLOBS]
    if "branches-ignore" not in push and _TAG_FILTERS & push.keys():
        return []
    return [EVERY_BRANCH]


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


_MAIN_PR = {"branches": ["main"]}


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        # Negative: the shapes this test forbids are detected.
        ({"push": {"branches": ["main", "fix/**"]}, "pull_request": _MAIN_PR}, ["fix/**"]),
        ({"push": {"branches": ["**"]}, "pull_request": _MAIN_PR}, ["**"]),
        ({"push": None, "pull_request": _MAIN_PR}, [EVERY_BRANCH]),
        ({"push": {"paths": ["src/**"]}, "pull_request": _MAIN_PR}, [EVERY_BRANCH]),
        # The PR #4192 shape: ignoring the queue glob still matches feature branches.
        (
            {"push": {"branches-ignore": ["gh-readonly-queue/**"]}, "pull_request": _MAIN_PR},
            [EVERY_BRANCH],
        ),
        (dict.fromkeys(["push", "pull_request"]), [EVERY_BRANCH]),
        # Edge: post-merge validation on main is not what this test forbids.
        ({"push": {"branches": ["main"]}, "pull_request": _MAIN_PR}, []),
        ({"push": {"branches": "main"}, "pull_request": _MAIN_PR}, []),
        # Edge: a tag filter with no branch filter fires on tag pushes only.
        ({"push": {"tags": ["v*"]}, "pull_request": _MAIN_PR}, []),
        # Edge: without pull_request there is no second run to collide with.
        ({"push": {"branches": ["main", "fix/**"]}}, []),
    ],
    ids=[
        "feature-glob",
        "wildcard-glob",
        "bare-push",
        "paths-only",
        "branches-ignore",
        "list-form",
        "main-only",
        "main-scalar",
        "tags-only",
        "push-only",
    ],
)
def test_the_detector_classifies_each_trigger_shape(on: dict, expected: list[str]) -> None:
    assert double_triggered_branches(on) == expected


def test_a_list_form_trigger_maps_each_event_to_no_filter() -> None:
    """Edge: ``on: [pull_request]`` is safe and must not be skipped."""
    assert _triggers(WORKFLOW_DIR / "dependency-review.yml") == {"pull_request": None}


def test_merge_state_runs_on_feature_branch_pushes_only() -> None:
    """A conflicting PR gets no pull_request run, so only a push can report it."""
    workflow = yaml.safe_load((WORKFLOW_DIR / "pr-merge-state.yml").read_text(encoding="utf-8"))
    on = _triggers(WORKFLOW_DIR / "pr-merge-state.yml")

    assert on is not None
    assert set(on) == {"push"}
    assert {"main", "gh-readonly-queue/**"} <= set(on["push"]["branches-ignore"])
    steps = workflow["jobs"]["pr-merge-state"]["steps"]
    assert any(step.get("run") == "python scripts/ci/check_pr_merge_state.py" for step in steps)


def test_python_tests_no_longer_host_the_merge_state_job() -> None:
    """Hosting it there made every PR commit run the full test matrix twice (PR #4192)."""
    workflow = yaml.safe_load((WORKFLOW_DIR / "pytest.yml").read_text(encoding="utf-8"))
    assert "pr-merge-state" not in workflow["jobs"]


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
