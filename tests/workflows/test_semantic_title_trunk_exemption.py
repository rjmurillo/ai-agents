"""Pin the Trunk Merge Queue exemption in the semantic PR title check.

Trunk tests a queued pull request by opening a draft pull request whose title
is its own branch name, `trunk-merge/pr-<n>/<uuid>`. That can never satisfy a
conventional-commit title, so `Validate PR title` failed on every queued pull
request and removed it from the queue.

Measured 2026-08-10: 18 Trunk draft pull requests, zero merges, and every
`Failed Required Status` table Trunk posted named `Validate PR title`. The two
that also named `Validate PR` were cancellations, not independent failures:
dropping the pull request from the queue closes the draft, which cancels the
runs still in flight.

The exemption has three parts and all of them matter:

1. The validation steps skip for a `trunk-merge/` head branch.
2. The skip applies only to same-repository branches, so a fork cannot claim
   it by naming its branch `trunk-merge/anything`.
3. The gating is per step, never a job-level `if:`.

Part 3 is the load-bearing one. This job's name is the required status check
context, and a job-level `if:` changes what conclusion that context reports on
every queued pull request. Trunk advances the queue from that conclusion, so
the job runs unconditionally and reports a real success.

Behaviour was verified by running the expression through `act` on 2026-08-10
across five cases: `feature/normal` (false), `trunk-merge/pr-4747/<uuid>` in
this repository (true), the same branch name on a fork (false),
`trunk-merge-evil/x` (false, no prefix confusion), and actor `dependabot[bot]`
(true). Those runs also confirmed that a step-level `if:` reads job-level
`env`, and that the folded expression yields the literal string `true`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "semantic-pr-title-check.yml"
)

# Pinned in full rather than by substring. A substring assertion still passes
# when the expression is negated or short-circuited (`false && ...`), which
# would silently disable either the exemption or the bot skips.
_EXPECTED_SKIP_EXPRESSION = (
    "${{ github.actor == 'dependabot[bot]' "
    "|| github.actor == 'github-actions[bot]' "
    "|| github.actor == 'renovate[bot]' "
    "|| (startsWith(github.head_ref, 'trunk-merge/') "
    "&& github.event.pull_request.head.repo.full_name == github.repository) }}"
)


@pytest.fixture(scope="module")
def job() -> dict:
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    return data["jobs"]["main"]


def test_required_context_name_is_unchanged(job: dict) -> None:
    """The job name is the required status check context; renaming it is a
    branch-protection change (`.claude/rules/ci-scripts.md` MUST 22)."""
    assert job["name"] == "Validate PR title"


def test_job_has_no_top_level_if(job: dict) -> None:
    """Negative control. A job-level `if:` changes the conclusion the required
    context reports, which is what Trunk reads to advance the queue."""
    assert "if" not in job


def test_skip_expression_is_exactly_as_pinned(job: dict) -> None:
    """Positive: the whole expression, so a negation or a short-circuit fails
    here instead of silently disabling the gate."""
    assert job["env"]["SKIP_TITLE_CHECK"] == _EXPECTED_SKIP_EXPRESSION


def test_skip_expression_covers_trunk_merge_branches(job: dict) -> None:
    expression = job["env"]["SKIP_TITLE_CHECK"]
    assert "startsWith(github.head_ref, 'trunk-merge/')" in expression


def test_trunk_exemption_is_limited_to_this_repository(job: dict) -> None:
    """Negative: a fork must not reach the exemption by branch name alone."""
    expression = job["env"]["SKIP_TITLE_CHECK"]
    assert (
        "github.event.pull_request.head.repo.full_name == github.repository"
        in expression
    )
    trunk_clause = expression.split("|| (", 1)[1]
    assert trunk_clause.startswith("startsWith(github.head_ref, 'trunk-merge/') &&")


def test_skip_expression_still_covers_every_bot_actor(job: dict) -> None:
    """Edge: the exemption must add to the bot skips, never replace them."""
    expression = job["env"]["SKIP_TITLE_CHECK"]
    for actor in ("dependabot[bot]", "github-actions[bot]", "renovate[bot]"):
        assert f"github.actor == '{actor}'" in expression


def test_every_validating_step_is_gated_on_the_skip(job: dict) -> None:
    """Positive: each step that does real work honours the skip. A step added
    later without the guard would run against a trunk-merge title and fail."""
    validating = [s for s in job["steps"] if s.get("name") != "Skip title validation"]
    assert validating, "no validating steps found"
    for step in validating:
        assert step.get("if") == "env.SKIP_TITLE_CHECK != 'true'"


def test_notice_step_fires_only_when_skipping(job: dict) -> None:
    notice = [s for s in job["steps"] if s.get("name") == "Skip title validation"]
    assert len(notice) == 1
    assert notice[0].get("if") == "env.SKIP_TITLE_CHECK == 'true'"
