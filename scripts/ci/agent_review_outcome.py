"""Resolve what an agent-review job records when the model never ran.

Single source of truth for the three ``.github/actions/agent-review`` steps that
each need the same answer: ``agent_review_save_results.py`` (writes the artifact
the aggregate downloads), ``agent_review_check_verdict.py`` (decides the job's
own pass/fail), and ``agent_review_generate_summary.py`` (renders the step
summary). Before issue #4778 each restated the fallback inline and they could
drift apart.

Why an infrastructure skip must still write an artifact (issue #4778)
---------------------------------------------------------------------
``AI Quality Gate Results`` downloads ``review-*`` artifacts and validates them.
The canonical requirement, verbatim from
``scripts/quality_gate/validate_artifact_download.py``::

    Exit codes (ADR-035):
        0 - all required verdict files are present
        1 - one or more verdict files are missing (logic/validation error)

So a preflight skip that writes nothing crashes aggregation before it can post a
report. The gate would fail, but with ``Artifact download incomplete`` instead of
a readable statement of what happened. Recording ``DID_NOT_RUN`` keeps the report
intact AND keeps the merge blocked.

Why ``DID_NOT_RUN`` and not ``NEEDS_REVIEW``
--------------------------------------------
``scripts/quality_gate/check_critical_failures.py`` documents the blocking set
verbatim::

    # FAIL_VERDICTS plus UNKNOWN and DID_NOT_RUN; see module docstring.
    BLOCKING_VERDICTS = frozenset(FAIL_VERDICTS | {"UNKNOWN", "DID_NOT_RUN"})

Both verdicts block, so both fail closed. ``DID_NOT_RUN`` is chosen because
``.github/scripts/aggregate_quality_verdicts.py`` reads it as an explicit
infrastructure outcome, categorizes it ``INFRASTRUCTURE`` rather than
``CODE_QUALITY``, and reports the security axis as not having run. It also
matches the verdict the in-review infrastructure gate already writes, verbatim
from ``scripts/ci/check_ai_review_infra_gate.py``::

    DID_NOT_RUN_VERDICT = "DID_NOT_RUN"

Stricter/looser/different than canonical
----------------------------------------
Same verdict token as ``check_ai_review_infra_gate``; different trigger. That
module fires when the context build fails inside a running review job. This one
fires when the preflight said the toolchain could not run a review at all, so
the job never reaches the context build.

Precedence rule: a verdict that already exists always wins. A cache hit restores
a real review result for the same commit, and an unavailable preflight must not
overwrite it with ``DID_NOT_RUN``.
"""

from __future__ import annotations

from dataclasses import dataclass

INFRA_SKIP_VERDICT = "DID_NOT_RUN"
EMPTY_VERDICT_FALLBACK = "NEEDS_REVIEW"
INFRA_TRUE = "true"

INFRA_SKIP_FINDINGS = (
    "Infrastructure preflight reported that agent reviews cannot run "
    "(Copilot CLI binary missing, or COPILOT_GITHUB_TOKEN absent or rejected). "
    "This review did not execute and this verdict is not a code-quality "
    "judgment. See the Infrastructure Check job for the specific cause."
)

INFRA_SKIP_ANNOTATION = (
    "::warning::Review skipped: infrastructure preflight reported agent reviews "
    "cannot run. Recorded DID_NOT_RUN so AI Quality Gate Results blocks the merge."
)

EMPTY_VERDICT_ANNOTATION = "::warning::Verdict was empty, defaulting to NEEDS_REVIEW"

EMPTY_OUTPUT_ANNOTATION = (
    "::warning::Both verdict and findings are empty, marking as infrastructure failure"
)


@dataclass(frozen=True, slots=True)
class ReviewOutcome:
    """What the job records, after fallbacks are applied.

    ``infrastructure_failure`` stays a string because every consumer writes it
    straight to an artifact file or a GitHub output, where ``"true"`` is the
    only value the downstream comparisons accept.
    """

    verdict: str
    findings: str
    infrastructure_failure: str
    annotations: tuple[str, ...] = ()


def infra_ready(value: str | None) -> bool:
    """Whether the preflight cleared this job to invoke the model.

    Only the exact string ``"true"`` clears it. An empty value means the
    preflight job failed, was skipped, or never published the output, and that
    must read as not-ready so the gate fails closed rather than launching
    reviews against an unverified toolchain (issue #4778).
    """
    return value == INFRA_TRUE


def resolve_outcome(
    *,
    verdict: str,
    findings: str,
    infrastructure_failure: str,
    infra_ready_value: str | None,
) -> ReviewOutcome:
    """Apply the fallback ladder to one job's raw step outputs.

    Order matters and is the whole contract:

    1. A non-empty verdict passes through untouched. A real or cached review
       result outranks any preflight opinion.
    2. An empty verdict with a not-ready preflight records ``DID_NOT_RUN`` plus
       an infrastructure failure, because the reason is known.
    3. An empty verdict with a ready preflight keeps the pre-existing
       ``NEEDS_REVIEW`` fallback: the review was attempted and produced nothing,
       which is a different fault worth a different token.
    """
    verdict = verdict.strip()
    if verdict:
        return ReviewOutcome(verdict, findings, infrastructure_failure)

    if not infra_ready(infra_ready_value):
        return ReviewOutcome(
            INFRA_SKIP_VERDICT,
            findings or INFRA_SKIP_FINDINGS,
            INFRA_TRUE,
            (INFRA_SKIP_ANNOTATION,),
        )

    annotations = [EMPTY_VERDICT_ANNOTATION]
    if not findings:
        infrastructure_failure = INFRA_TRUE
        annotations.append(EMPTY_OUTPUT_ANNOTATION)
    return ReviewOutcome(
        EMPTY_VERDICT_FALLBACK,
        findings,
        infrastructure_failure,
        tuple(annotations),
    )
