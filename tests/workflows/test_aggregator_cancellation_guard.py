"""Regression guard for #5097 and #5104: superseded runs must not publish red.

Every workflow here uses `cancel-in-progress`, so pushing to a branch while a
run is live cancels that run and leaves its jobs reporting `cancelled`. A
result-aggregator job gated on `always()` runs anyway, reads those `cancelled`
values, and exits non-zero, so GitHub records a red check run against the PR
head for a run nobody is waiting on. The next push repeats it. Contributors
then triage CI failures that describe nothing but their own typing speed.

The fix is `!cancelled()` in place of `always()`. The vendor documents the
substitution directly (docs.github.com, expressions reference): `always()`
"Causes the step to always execute, and returns true, even when canceled",
and "If you want to run a job or step regardless of its success or failure,
use the recommended alternative: `if: ${{ !cancelled() }}`". So the guarded
job still runs when a dependency FAILED or was SKIPPED, which is what the
aggregators exist for.

GitHub re-evaluates a job's `if:` condition for every currently running job
when the run is cancelled (docs.github.com, workflow cancellation
reference): "To cancel the workflow run, the server re-evaluates `if`
conditions for all currently running jobs. If the condition evaluates to
`true`, the job will not get canceled." A job already running when
cancellation lands has `!cancelled()` flip to false on that re-evaluation
and is itself cancelled as a result, concluding `cancelled`. Verified
against a real superseded run on this repository (`actions_get
get_workflow_run` on run `31896264033`): overall conclusion `cancelled`,
with its "Run Python Tests" and "Main failure alert" jobs both reporting
`"conclusion":"cancelled"`. This module makes no claim about the exact
conclusion a not-yet-started job reports; the guard's requirement is only
that no PR-head aggregator conclude the red `failure` that `always()`
produced, and `cancelled` is (like `skipped`) neither `success` nor
`failure`, so branch protection keeps waiting on a superseded run instead
of reading a false green.

A job can depend on an upstream job's work in two ways, and both go red the
same way under `always()`. #5097 covered the first: the job reads
`needs.<job>.result`, scores the `cancelled` value, and exits non-zero. #5104
is the second: the job downloads an artifact the upstream job never uploaded
because cancellation reached it first, and `actions/download-artifact` errors
on the missing artifact. `codeql-analysis.yml::check-blocking-issues` is that
second shape, which is why the #5097 sweep walked past it: it mentions no
`needs.<job>.result` anywhere. `depends_on_upstream_output` now recognizes
both, so the sweep covers both.

Two workflows fixed for #2347 with the equivalent `always() && !cancelled()`
spelling (`ai-pr-quality-gate.yml`, `ai-session-protocol.yml`) were later
deleted (#5132, #5135); `MINIMUM_AGGREGATORS_EXAMINED` below reflects what
the sweep examines today, not the seven jobs that existed when #5097 was
fixed.

Assertions run against `yaml.safe_load` output, never against workflow text
(`.claude/rules/testing.md` MUST 9).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# A job that reads a dependency's outcome. `needs.<job>.result` covers the
# per-job spelling; `toJSON(needs)` covers the whole-context spelling used by
# `pytest.yml::main-failure-alert` and `installed-plugin-hook-guard.yml`.
CONSUMES_NEEDS_RESULT = re.compile(r"needs\.[A-Za-z0-9_-]+\.result|toJSON\(\s*needs\s*\)")

# The second way a job depends on upstream work: it downloads an artifact an
# upstream job uploaded. Issue #5104. `codeql-analysis.yml::check-blocking-issues`
# reads no `needs.<job>.result` at all, so the result-only classifier above
# never examined it, and the #5097 sweep reported clean while that job still
# carried `always()`. A cancelled run leaves the analyze legs with nothing
# uploaded, and `actions/download-artifact` errors on the missing artifacts
# instead of the job skipping. Matching the action reference (rather than a
# step name) keeps this literal: `actions/upload-artifact` does not match, so
# a producer is never mistaken for a consumer.
CONSUMES_DEPENDENCY_ARTIFACTS = re.compile(r"actions/download-artifact")

# Events that put a check run on a pull request head. A schedule-only or
# dispatch-only aggregate cannot produce the #5097 noise, so it is out of scope.
PR_HEAD_EVENTS = frozenset({"pull_request", "push"})

# Every job converted to the guard, across #5097 and #5104. Workflow file to
# job id.
FIXED_AGGREGATORS: tuple[tuple[str, str], ...] = (
    ("pytest.yml", "test-result"),
    ("pytest.yml", "main-failure-alert"),
    ("cli-smoke.yml", "smoke-result"),
    ("installed-plugin-hook-guard.yml", "guard-result"),
    ("test-codeql-integration.yml", "aggregate-results"),
    # Added for #5104. Depends on upstream output through downloaded SARIF
    # artifacts, not through `needs.<job>.result`.
    ("codeql-analysis.yml", "check-blocking-issues"),
)

# The `if` each fixed job carried before this change, read verbatim from
# `git show origin/main:<workflow>` and parsed with the same loader the tests
# use, so the folded block scalars appear here exactly as GitHub would see
# them. These drive the negative controls: the checkers below must reject
# every one of them.
PRE_FIX_CONDITIONS: dict[tuple[str, str], str] = {
    ("pytest.yml", "test-result"): (
        "always() && (needs.check-paths.result != 'success' || "
        "needs.check-paths.outputs.python-changed == 'true')"
    ),
    ("pytest.yml", "main-failure-alert"): (
        "always() && github.event_name == 'push' && "
        "github.ref_name == github.event.repository.default_branch"
    ),
    ("cli-smoke.yml", "smoke-result"): "always()",
    ("installed-plugin-hook-guard.yml", "guard-result"): "always()",
    ("test-codeql-integration.yml", "aggregate-results"): "always()",
    ("codeql-analysis.yml", "check-blocking-issues"): (
        "always() && needs.check-paths.outputs.should-run-analysis == 'true'"
    ),
}

# Lower bound on what the repository-wide sweep must examine. Without it a
# broken classifier that matches nothing reports a clean sweep
# (`.claude/rules/testing.md` MUST 10: report the scope size, not only the
# finding count). Measured at 7 by running the sweep against
# `.github/workflows/*.yml` at this commit: the six jobs in FIXED_AGGREGATORS
# plus `pytest.yml::coverage`, which the artifact classifier added for #5104
# and which was already guarded (`needs.check-paths.outputs.python-changed ==
# 'true' && !cancelled() && needs.test.result == 'success'`), so widening the
# classifier flagged nothing beyond the job #5104 reports.
# Two more (`ai-pr-quality-gate.yml::aggregate`, `ai-session-protocol.yml::aggregate`,
# guarded for #2347) counted toward this bound until #5132 and #5135 deleted
# those workflows in full, a legitimate cleanup and not a classifier
# regression (issue #5142). Drop this count again if a future PR removes one
# of the jobs that remain, rather than raising MINIMUM_AGGREGATORS_EXAMINED
# to paper over a real regression.
MINIMUM_AGGREGATORS_EXAMINED = 7


def _load_workflow(name: str) -> Mapping[Any, Any]:
    path = WORKFLOW_DIR / name
    assert path.is_file(), f"missing workflow file: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _job(workflow_name: str, job_id: str) -> dict[str, Any]:
    jobs = _load_workflow(workflow_name).get("jobs") or {}
    assert job_id in jobs, f"{workflow_name} has no job {job_id!r}"
    return jobs[job_id]


def _strings(node: Any):
    """Yield every string reachable in a parsed YAML node."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _triggers(workflow: Mapping[Any, Any]) -> set[str]:
    """Event names for a workflow.

    PyYAML resolves an unquoted `on:` key to the boolean True, so read both.
    """
    on = workflow.get(True, workflow.get("on")) or {}
    if isinstance(on, (dict, list)):
        return set(on)
    return {on}


# Control-only keys: `needs` lists job ids (never `.result` text, so scanning
# it cannot produce a false match) and `if` decides whether the job runs at
# all rather than consuming a result as part of its own execution. Excluding
# them keeps "does this job operationally consume a dependency result" a
# distinct question from "does its guard condition mention one", which
# `cancellation_guard_violations` already answers by reading `if` directly.
_CONTROL_ONLY_KEYS = frozenset({"if", "needs"})


def _consumes_dependency_results(job: Mapping[str, Any]) -> bool:
    """True if the job's own execution payload reads a dependency result.

    Scans every field except `if` and `needs`. A normal job carries the
    reference inside `steps` (an `env:` value or a `run:` line); a
    reusable-workflow call job (`uses: ./.github/workflows/x.yml`) has no
    `steps` at all and instead passes dependency-derived values through
    `with:`. Scanning only `steps` misses that second shape entirely, so an
    unguarded reusable-workflow aggregator would pass through the sweep
    unexamined instead of failing it.
    """
    payload = {key: value for key, value in job.items() if key not in _CONTROL_ONLY_KEYS}
    return any(CONSUMES_NEEDS_RESULT.search(text) for text in _strings(payload))


def _consumes_dependency_artifacts(job: Mapping[str, Any]) -> bool:
    """True if the job's own execution payload downloads an artifact.

    Same payload scan as `_consumes_dependency_results`, for the same reason:
    the reference lives in a step's `uses`, and a reusable-workflow call job
    carries no `steps` at all. `if` and `needs` stay excluded so this answers
    "does this job operationally consume upstream output" rather than "does
    its guard mention one".
    """
    payload = {key: value for key, value in job.items() if key not in _CONTROL_ONLY_KEYS}
    return any(CONSUMES_DEPENDENCY_ARTIFACTS.search(text) for text in _strings(payload))


def depends_on_upstream_output(job: Mapping[str, Any]) -> bool:
    """True if the job reads a dependency result or downloads its artifacts.

    Either shape turns a cancelled upstream into a red check when the job is
    gated on `always()`: the result reader scores a `cancelled` value, and the
    artifact consumer errors on a download that was never uploaded. #5097
    fixed the first shape; #5104 is the second.
    """
    return _consumes_dependency_results(job) or _consumes_dependency_artifacts(job)


def _strip_expression_wrapper(condition: str) -> str:
    """Strip a single outer `${{ ... }}` wrapper, if the whole string is one.

    GitHub Actions accepts a bare expression (`always() && foo`) or the same
    expression wrapped once (`${{ always() && foo }}`) on an `if:` key. Only
    a wrapper spanning the entire condition is stripped; `${{ }}` appearing
    inside a larger string is left alone (no real `if` condition in this
    repository nests one).
    """
    stripped = condition.strip()
    if stripped.startswith("${{") and stripped.endswith("}}"):
        return stripped[3:-2].strip()
    return stripped


def _split_top_level(expression: str, operator: str) -> list[str]:
    """Split on occurrences of `operator` ('&&' or '||') outside parentheses.

    A `&&` or `||` inside `(...)` is not a split point; splitting on every
    occurrence regardless of depth would wrongly cut `(a && b) || c` into
    pieces that lose the grouping.
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    i = 0
    op_len = len(operator)
    while i < len(expression):
        char = expression[i]
        if char in "([":
            depth += 1
            current.append(char)
        elif char in ")]":
            depth -= 1
            current.append(char)
        elif depth == 0 and expression[i : i + op_len] == operator:
            parts.append("".join(current))
            current = []
            i += op_len
            continue
        else:
            current.append(char)
        i += 1
    parts.append("".join(current))
    return parts


# The only two spellings this repository uses for the cancellation guard.
# `_has_cancellation_guard_term` requires an EXACT match against one of
# these on a top-level conjunct of a top-level-`||`-free expression, not a
# substring of the whole condition.
_CANCELLATION_GUARD_TERMS = frozenset({"!cancelled()", "cancelled() == false"})


def _has_cancellation_guard_term(condition: str) -> bool:
    """True only if the guard term is an unconditional top-level requirement.

    A substring check (`"!cancelled()" in condition`) accepts three
    conditions that are not real guards:

    - `always() || !cancelled()`: the OR means `!cancelled()` never actually
      excludes anything, because `always()` already returns true during
      cancellation.
    - `!cancelled() == false`: parses as `(!cancelled()) == false`,
      backwards logic that is true only WHILE the run is cancelled.
    - `!cancelled() && success() || always()` (Copilot review finding on
      PR #5141): GitHub Actions binds `&&` tighter than `||`
      (docs.github.com, expressions reference, "Operators"), so this parses
      as `(!cancelled() && success()) || always()`. `always()` alone can
      make the whole expression true during cancellation, so the guard in
      the first disjunct provides no protection. An earlier version of this
      checker split only on top-level `&&` and accepted this condition,
      because `!cancelled()` alone happened to be one of the two `&&`
      conjuncts; the trailing `|| always()` outside that conjunct defeated
      it and the splitter never looked for a top-level `||` at all.

    All three contain the substring `!cancelled()` (or `cancelled() ==
    false`) and none of them guards against cancellation. The fix: a
    top-level `||` (outside any parentheses) means the expression is not an
    unconditional requirement, whatever its other operands contain, so it
    is rejected before any conjunct is inspected. Only when there is no
    top-level `||` does this check split on top-level `&&` and require an
    exact match on one conjunct. Verified against every real `if:` in
    `.github/workflows/*.yml` today (the five fixed aggregators, none of
    which has a top-level `||`; their nested `||` groups such as
    `(a != 'success' || b == 'true')` sit inside parentheses) plus the
    `cancelled() == false` and `always() && !cancelled()` spellings and all
    three adversarial conditions above, covered by `TestCheckerEdges`.
    """
    expression = _strip_expression_wrapper(condition)
    if len(_split_top_level(expression, "||")) > 1:
        return False
    conjuncts = _split_top_level(expression, "&&")
    return any(part.strip() in _CANCELLATION_GUARD_TERMS for part in conjuncts)


def cancellation_guard_violations(job: Mapping[str, Any]) -> list[str]:
    """Reasons this job would publish a red check for a superseded run.

    Empty list means the job is safe. Shared by the real-workflow assertions
    and by the negative controls, so a control that passes proves the same
    code path the real assertion runs.
    """
    violations: list[str] = []
    if not job.get("needs"):
        violations.append("job declares no needs, so it is not an aggregator")
    condition = job.get("if")
    if condition is None:
        violations.append("job has no `if`, so a cancelled run cannot be excluded")
        return violations
    condition = str(condition)
    if not _has_cancellation_guard_term(condition):
        violations.append(f"`if` does not guard on cancellation: {condition!r}")
    return violations


def bare_always_violations(job: Mapping[str, Any]) -> list[str]:
    """Reject a leftover `always()` term in a job this change converted."""
    condition = str(job.get("if") or "")
    if "always()" in condition:
        return [f"`if` still carries always(): {condition!r}"]
    return []


def unguarded_pr_head_aggregators(workflow: Mapping[Any, Any]) -> tuple[list[str], int]:
    """Return (violating job ids, number of aggregator jobs examined)."""
    if not (_triggers(workflow) & PR_HEAD_EVENTS):
        return [], 0
    violations: list[str] = []
    examined = 0
    for job_id, job in (workflow.get("jobs") or {}).items():
        if not isinstance(job, dict) or not job.get("needs"):
            continue
        if not depends_on_upstream_output(job):
            continue
        examined += 1
        if cancellation_guard_violations(job):
            violations.append(job_id)
    return violations, examined


@pytest.fixture(params=FIXED_AGGREGATORS, ids=lambda t: f"{t[0]}::{t[1]}")
def fixed_aggregator(request: pytest.FixtureRequest) -> tuple[tuple[str, str], dict[str, Any]]:
    workflow_name, job_id = request.param
    return request.param, _job(workflow_name, job_id)


class TestFixedAggregators:
    def test_aggregator_skips_a_cancelled_run(
        self, fixed_aggregator: tuple[tuple[str, str], dict[str, Any]]
    ) -> None:
        key, job = fixed_aggregator
        assert cancellation_guard_violations(job) == [], f"{key[0]}::{key[1]} is unguarded"

    def test_aggregator_drops_bare_always(
        self, fixed_aggregator: tuple[tuple[str, str], dict[str, Any]]
    ) -> None:
        key, job = fixed_aggregator
        assert bare_always_violations(job) == [], f"{key[0]}::{key[1]} kept always()"

    def test_aggregator_still_depends_on_upstream_output(
        self, fixed_aggregator: tuple[tuple[str, str], dict[str, Any]]
    ) -> None:
        """Guards the premise, not the fix.

        If a job stops reading `needs.<job>.result` AND stops downloading a
        dependency's artifacts, it is no longer the aggregator these
        assertions describe, and the sweep below would stop examining it.
        Failing here is a signal to re-derive the list, not to delete the case.
        """
        key, job = fixed_aggregator
        assert depends_on_upstream_output(job), (
            f"{key[0]}::{key[1]} neither reads a dependency result nor downloads its artifacts"
        )

    def test_pre_fix_condition_is_rejected(
        self, fixed_aggregator: tuple[tuple[str, str], dict[str, Any]]
    ) -> None:
        """Negative control: the condition that shipped #5097 must fail.

        Rebuilds each job as it stood on origin/main, then runs the same
        checker the assertions above use. Without this, a checker that
        accepted everything would report a clean pass.
        """
        key, job = fixed_aggregator
        pre_fix = copy.deepcopy(job)
        pre_fix["if"] = PRE_FIX_CONDITIONS[key]

        violations = cancellation_guard_violations(pre_fix)

        assert violations, f"checker accepted the pre-fix condition for {key[0]}::{key[1]}"
        assert any("guard on cancellation" in reason for reason in violations)
        assert bare_always_violations(pre_fix)


class TestCheckerEdges:
    """Inputs the real workflows do not currently produce."""

    def test_missing_if_is_a_violation(self) -> None:
        violations = cancellation_guard_violations({"needs": ["build"], "steps": []})
        assert any("no `if`" in reason for reason in violations)

    def test_missing_needs_is_a_violation(self) -> None:
        violations = cancellation_guard_violations({"if": "${{ !cancelled() }}"})
        assert any("no needs" in reason for reason in violations)

    def test_equality_spelling_of_the_guard_is_accepted(self) -> None:
        """A cosmetic rewrite must not read as a dropped guard."""
        job = {"needs": ["build"], "if": "cancelled() == false && github.event_name == 'push'"}
        assert cancellation_guard_violations(job) == []

    def test_success_only_condition_is_a_violation(self) -> None:
        job = {"needs": ["build"], "if": "needs.build.result == 'success'"}
        violations = cancellation_guard_violations(job)
        assert any("guard on cancellation" in reason for reason in violations)

    def test_guard_combined_with_always_passes_the_semantic_check(self) -> None:
        """The #2347 spelling is redundant, not unsafe.

        `always() && !cancelled()` evaluates false during cancellation, so the
        semantic sweep must accept it while the spelling check rejects it.
        """
        job = {"needs": ["build"], "if": "always() && !cancelled()"}
        assert cancellation_guard_violations(job) == []
        assert bare_always_violations(job)

    def test_the_unsafe_or_spelling_is_rejected(self) -> None:
        """`!cancelled()` under an OR never actually excludes anything.

        A substring check on the whole condition accepts this: the text
        `!cancelled()` is present. It should not be accepted, because
        `always()` already returns true during cancellation
        (docs.github.com, expressions reference), so ORing in `!cancelled()`
        changes nothing. Regression for a Copilot review finding on PR #5103
        (issue #5139 item 2): `cancellation_guard_violations` originally
        matched `"!cancelled()" in condition` and passed this condition.
        """
        job = {"needs": ["build"], "if": "always() || !cancelled()"}
        violations = cancellation_guard_violations(job)
        assert any("guard on cancellation" in reason for reason in violations)

    def test_the_backwards_equality_spelling_is_rejected(self) -> None:
        """`!cancelled() == false` parses as `(!cancelled()) == false`.

        That is true only WHILE the run is cancelled, the opposite of the
        intended guard. A substring check accepts this too, because the text
        `!cancelled()` is present. Sibling of
        `test_equality_spelling_of_the_guard_is_accepted`, which pins the
        correct (non-negated) equality spelling as accepted.
        """
        job = {"needs": ["build"], "if": "!cancelled() == false"}
        violations = cancellation_guard_violations(job)
        assert any("guard on cancellation" in reason for reason in violations)

    def test_the_guard_defeated_by_a_trailing_or_always_is_rejected(self) -> None:
        """`&&` binds tighter than `||`, so a trailing `|| always()` wins.

        Regression for a Copilot review finding on PR #5141: an earlier
        version of this checker split only on top-level `&&`, so
        `!cancelled() && success() || always()` was accepted because
        `!cancelled()` alone was one of the two `&&` conjuncts. Per the
        GitHub Actions operator precedence (docs.github.com, expressions
        reference), this condition actually parses as
        `(!cancelled() && success()) || always()`: `always()` is a second,
        unconditional top-level disjunct, so the whole expression is true
        during cancellation regardless of the first disjunct's guard.
        """
        job = {"needs": ["build"], "if": "!cancelled() && success() || always()"}
        violations = cancellation_guard_violations(job)
        assert any("guard on cancellation" in reason for reason in violations)


class TestRepositoryWideSweep:
    """No PR-head aggregator anywhere may convert a cancellation into red."""

    def test_every_pr_head_aggregator_is_guarded(self) -> None:
        offenders: list[str] = []
        examined = 0
        for path in sorted(WORKFLOW_DIR.glob("*.yml")):
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                continue
            violations, count = unguarded_pr_head_aggregators(document)
            examined += count
            offenders.extend(f"{path.name}::{job_id}" for job_id in violations)

        assert examined >= MINIMUM_AGGREGATORS_EXAMINED, (
            f"sweep examined only {examined} aggregator jobs, expected at least "
            f"{MINIMUM_AGGREGATORS_EXAMINED}; the classifier stopped matching rather "
            "than the repository getting cleaner"
        )
        assert offenders == [], f"unguarded PR-head aggregators: {offenders}"

    def test_sweep_reports_an_unguarded_aggregator(self) -> None:
        """Negative control for the sweep itself."""
        document = {
            "on": {"pull_request": None},
            "jobs": {
                "build": {"runs-on": "ubuntu-latest", "steps": []},
                "result": {
                    "needs": ["build"],
                    "if": "always()",
                    "steps": [{"env": {"BUILD": "${{ needs.build.result }}"}, "run": "true"}],
                },
            },
        }

        violations, examined = unguarded_pr_head_aggregators(document)

        assert examined == 1
        assert violations == ["result"]

    def test_sweep_ignores_a_workflow_off_the_pr_head(self) -> None:
        """A schedule-only aggregate publishes no check run on a PR."""
        document = {
            "on": {"schedule": [{"cron": "0 3 * * *"}]},
            "jobs": {
                "result": {
                    "needs": ["build"],
                    "if": "always()",
                    "steps": [{"env": {"BUILD": "${{ needs.build.result }}"}, "run": "true"}],
                },
            },
        }

        assert unguarded_pr_head_aggregators(document) == ([], 0)

    def test_sweep_catches_a_reusable_workflow_call_aggregator(self) -> None:
        """A `uses:` job has no `steps`; the payload scan must still see `with`.

        Regression for a Copilot review finding on PR #5103: the classifier
        originally scanned only `job.get("steps")`, so a reusable-workflow
        call job that passes a dependency result through `with:` (its only
        execution payload) was invisible to `_consumes_dependency_results`
        and never counted as examined, let alone flagged when unguarded.
        """
        document = {
            "on": {"pull_request": None},
            "jobs": {
                "build": {"runs-on": "ubuntu-latest", "steps": []},
                "result": {
                    "needs": ["build"],
                    "if": "always()",
                    "uses": "./.github/workflows/report-status.yml",
                    "with": {"build_status": "${{ needs.build.result }}"},
                },
            },
        }

        violations, examined = unguarded_pr_head_aggregators(document)

        assert examined == 1
        assert violations == ["result"]

    def test_sweep_reads_the_boolean_on_key(self) -> None:
        """PyYAML resolves an unquoted `on:` to True; the sweep must still see it."""
        document = {
            True: {"push": None},
            "jobs": {
                "result": {
                    "needs": ["build"],
                    "if": "always()",
                    "steps": [{"env": {"BUILD": "${{ needs.build.result }}"}, "run": "true"}],
                },
            },
        }

        assert unguarded_pr_head_aggregators(document) == (["result"], 1)


class TestArtifactConsumerClassifier:
    """The #5104 shape: depends on upstream output without reading a result.

    `codeql-analysis.yml::check-blocking-issues` scores downloaded SARIF and
    never mentions `needs.<job>.result`, so the result-only classifier walked
    past it and the #5097 sweep reported clean while the job still carried
    `always()`. These cases pin the widened classifier in both directions: it
    must see a consumer, and it must not invent one.
    """

    def test_downloading_an_artifact_counts_as_depending_on_upstream(self) -> None:
        job = {
            "needs": ["analyze"],
            "if": "always()",
            "steps": [{"uses": "actions/download-artifact@v8", "with": {"pattern": "results-*"}}],
        }

        assert _consumes_dependency_results(job) is False
        assert depends_on_upstream_output(job) is True

    def test_uploading_an_artifact_does_not_count(self) -> None:
        """Negative control: a producer is not a consumer.

        `actions/upload-artifact` is the step the analyze legs run. Matching
        it here would classify every producer job as an aggregator and demand
        a cancellation guard from jobs that depend on nothing.
        """
        job = {
            "needs": ["build"],
            "if": "always()",
            "steps": [{"uses": "actions/upload-artifact@v7", "with": {"name": "results"}}],
        }

        assert _consumes_dependency_artifacts(job) is False
        assert depends_on_upstream_output(job) is False

    def test_sweep_flags_an_unguarded_artifact_consumer(self) -> None:
        document = {
            "on": {"pull_request": None},
            "jobs": {
                "analyze": {"runs-on": "ubuntu-latest", "steps": []},
                "check": {
                    "needs": ["analyze"],
                    "if": "always()",
                    "steps": [{"uses": "actions/download-artifact@v8"}],
                },
            },
        }

        violations, examined = unguarded_pr_head_aggregators(document)

        assert examined == 1
        assert violations == ["check"]

    def test_sweep_examines_but_clears_a_guarded_artifact_consumer(self) -> None:
        """Shape of `pytest.yml::coverage`: examined, and already safe.

        Distinguishes "the classifier now sees artifact consumers" from "the
        classifier now fails them", which a flag-everything regression would
        conflate.
        """
        document = {
            "on": {"pull_request": None},
            "jobs": {
                "test": {"runs-on": "ubuntu-latest", "steps": []},
                "coverage": {
                    "needs": ["test"],
                    "if": "!cancelled() && needs.test.result == 'success'",
                    "steps": [{"uses": "actions/download-artifact@v8"}],
                },
            },
        }

        assert unguarded_pr_head_aggregators(document) == ([], 1)

    def test_sweep_ignores_an_artifact_consumer_with_no_needs(self) -> None:
        """A job with no dependencies cannot be orphaned by a cancelled one."""
        document = {
            "on": {"pull_request": None},
            "jobs": {
                "check": {
                    "if": "always()",
                    "steps": [{"uses": "actions/download-artifact@v8"}],
                },
            },
        }

        assert unguarded_pr_head_aggregators(document) == ([], 0)


class TestConcurrencyStaysOn:
    """The fix belongs in the gate, not in disabling cancellation.

    Reverting `cancel-in-progress` would also silence #5097, at the cost of
    every superseded run burning a full runner. Pin it so that repair is not
    mistaken for this one.
    """

    @pytest.mark.parametrize(
        "workflow_name",
        sorted({workflow for workflow, _ in FIXED_AGGREGATORS}),
    )
    def test_cancel_in_progress_remains_enabled(self, workflow_name: str) -> None:
        concurrency = _load_workflow(workflow_name).get("concurrency") or {}
        setting = concurrency.get("cancel-in-progress")
        assert setting not in (None, False, "false"), (
            f"{workflow_name} no longer cancels superseded runs; the #5097 fix is "
            "in the aggregate gate, not in disabling concurrency cancellation"
        )
