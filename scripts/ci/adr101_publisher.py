#!/usr/bin/env python3
"""ADR-101 requirement 2a publisher: an App-authored check run bound to a SHA.

Issue #5245, owner decision D23, spike PR #6103. ADR-101 requirement 2 is split.
This module is the (2a) half. A dedicated GitHub App publishes a check run
named "ADR-101 Published Result" under an identity a head-defined workflow
cannot assume and a ruleset can pin by ``integration_id``. The run is bound to
the head SHA of the pull request and keyed by a digest of the head and base
pair. The publishing job runs no candidate code.

It does NOT close (2b), forged-result resistance. The execute job runs the
candidate's tests, and a candidate that controls the test process can make that
job conclude ``success`` three measured ways (the spike, Evidence 1). The
publisher carries ``needs.execute.result`` and nothing stronger, so its label
reads "published by the pinned App for this head and base; execution
authenticity bounded by ADR-101 requirement 2b" and never "verified".

Four subcommands, each called by one workflow step:

``gate``
    Reads the repository variable and the triggering event. Writes
    ``enabled=true|false`` for the jobs that follow, and prints a typed SKIP when
    the publisher does not apply. Flag off is the default.
``execute``
    Runs the candidate under the base-owned harness. See
    ``adr101_publisher_execute.py``.
``preflight``
    Runs in the environment-bound job. Writes ``mint=true`` only when the App id
    is numeric and the private key exists, so the token step is skipped, and the
    final step reports BLOCKED, when either is absent.
``publish``
    Validates, binds, publishes, reads back, and reports one typed outcome.

States and what each does to the check run:

  PASS     the check run was published and read back with the right App, SHA and
           name. Publishes ``success``.
  FAIL     a violation, or evidence that does not match. Publishes ``failure``
           when the head has not moved, and nothing when it has (the next push
           re-triggers the run).
  UNKNOWN  the evidence is incomplete. Same publishing rule as FAIL.
  BLOCKED  a credential or service was unavailable. Publishes nothing.
  SKIP     disabled or not applicable. Publishes nothing, so a pinned context
           never arrives and the pull request waits (the deadlock property).

No state publishes ``skipped`` or ``neutral``, so a non-PASS state cannot satisfy
a required context. This publisher is in no ruleset and no required context.

EXIT CODES: see ``adr101_publisher_inputs.py``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.ci.adr101_publisher_execute import run_execute  # noqa: E402
from scripts.ci.adr101_publisher_github import (  # noqa: E402
    ApiError,
    GitHubApi,
    PublisherApi,
    PullState,
)
from scripts.ci.adr101_publisher_inputs import (  # noqa: E402
    CHECK_NAME,
    EXIT_CONFIG,
    PUBLISHED_LABEL,
    REASON_BASE_NOT_SERVED,
    REASON_EVIDENCE_MISMATCH,
    REASON_EXECUTION_FAILED,
    REASON_REVISION_MOVED,
    SERVED_BASE_REF,
    VALIDATOR,
    PublisherEnv,
    exit_code,
    first_stop,
    gate_outcome,
    key_gate_outcome,
    report,
    revision_digest,
    token_gate_outcome,
    validate_event_inputs,
    write_output,
)
from scripts.validation.evidence import (  # noqa: E402
    REASON_AUTH_UNAVAILABLE,
    REASON_INCOMPLETE_EVIDENCE,
    REASON_LOOKUP_FAILED,
    REASON_PR_UNRESOLVED,
    CheckOutcome,
    EvidenceState,
)

ApiFactory = Callable[[PublisherEnv], PublisherApi]


def _real_api(env: PublisherEnv) -> PublisherApi:
    return GitHubApi(env.repository, env.read_token, env.app_token)


def _api_failure(exc: ApiError) -> CheckOutcome:
    """Map an API failure that stopped the run before anything was published."""
    if exc.status in (401, 403):
        return CheckOutcome.blocked(
            VALIDATOR,
            reason=REASON_AUTH_UNAVAILABLE,
            detail=f"GitHub refused the token ({exc.status}); nothing was published",
        )
    return CheckOutcome.blocked(
        VALIDATOR,
        reason=REASON_LOOKUP_FAILED,
        detail=f"GitHub API call failed ({exc.phrase}); nothing was published",
    )


def _moved(detail: str) -> CheckOutcome:
    return CheckOutcome.failed(VALIDATOR, reason=REASON_REVISION_MOVED, detail=detail)


def _still_bound(api: PublisherApi, env: PublisherEnv, pull: PullState) -> CheckOutcome | None:
    """Re-read the pointers immediately before publishing; a change aborts.

    ADR-101: "compare both against the pull request's current pointers
    immediately before publishing, and abort without publishing if either moved."
    The window between this read and the write is accepted there as CWE-367.
    """
    current = api.get_pull(env.pull_number)
    if current != pull:
        return _moved("the pull request head or base changed during the run")
    return None


def _run_mismatch(env: PublisherEnv, api: PublisherApi) -> CheckOutcome | None:
    """Cross-check the triggering workflow run against the event's head SHA."""
    run = api.get_run(env.run_id)
    if run.head_sha != env.head_sha or run.status != "completed":
        return CheckOutcome.failed(
            VALIDATOR,
            reason=REASON_EVIDENCE_MISMATCH,
            detail="the triggering workflow run does not match the event's head SHA",
        )
    return None


def _publish_failure(
    env: PublisherEnv, api: PublisherApi, pull: PullState, outcome: CheckOutcome
) -> CheckOutcome:
    """Publish a ``failure`` check run for ``outcome``, then return it unchanged.

    If the publish itself fails the original outcome still stands, with a note,
    so a worse state is never replaced by a milder one.
    """
    summary = f"{outcome.state.value} {outcome.reason}: {outcome.detail}"
    try:
        stale = _still_bound(api, env, pull)
        if stale is not None:
            return stale
        api.create_check_run(
            env.head_sha,
            "failure",
            revision_digest(env.head_sha, pull.base_sha),
            CHECK_NAME,
            summary,
        )
    except ApiError:
        return CheckOutcome(
            validator=outcome.validator,
            state=outcome.state,
            revision=outcome.revision,
            scope=outcome.scope,
            reason=outcome.reason,
            detail=f"{outcome.detail}; the failure check run could not be published",
        )
    return outcome


def _retract(api: PublisherApi, check_id: int) -> str:
    """Best-effort downgrade of a success that could not be confirmed.

    Returns a sentence for the outcome's detail. If the downgrade fails, a
    success check run remains on the head, and the detail says so.
    """
    try:
        api.set_conclusion(check_id, "failure", "read-back did not confirm; retracted")
    except ApiError:
        return "the retraction failed, so a success check run remains on the head"
    return "the check run was retracted"


def _verify_read_back(
    api: PublisherApi, env: PublisherEnv, check_id: int, external_id: str
) -> CheckOutcome | None:
    """Read the check run back and compare App, head, name, conclusion, digest."""
    try:
        seen = api.get_check_run(check_id)
    except ApiError:
        return CheckOutcome.unknown(
            VALIDATOR,
            reason=REASON_INCOMPLETE_EVIDENCE,
            detail=f"the published check run could not be read back; {_retract(api, check_id)}",
        )
    expected = (env.app_id, env.head_sha, CHECK_NAME, "success", external_id)
    actual = (seen.app_id, seen.head_sha, seen.name, seen.conclusion, seen.external_id)
    if actual == expected:
        return None
    return CheckOutcome.failed(
        VALIDATOR,
        reason=REASON_EVIDENCE_MISMATCH,
        detail=(
            "the published check run does not match the App, head SHA, name or digest; "
            f"{_retract(api, check_id)}"
        ),
    )


def _publish_success(env: PublisherEnv, api: PublisherApi, pull: PullState) -> CheckOutcome:
    external_id = revision_digest(env.head_sha, pull.base_sha)
    stale = _still_bound(api, env, pull)
    if stale is not None:
        return stale
    check_id = api.create_check_run(
        env.head_sha, "success", external_id, CHECK_NAME, PUBLISHED_LABEL
    )
    mismatch = _verify_read_back(api, env, check_id, external_id)
    if mismatch is not None:
        return mismatch
    return CheckOutcome.passed(
        VALIDATOR,
        revision=f"{env.head_sha}+{pull.base_sha}",
        scope="check run for this pull request head and base",
        examined=1,
        detail=PUBLISHED_LABEL,
    )


def _publish_bound(env: PublisherEnv, api: PublisherApi) -> CheckOutcome:
    if not env.pull_number:
        # A fork pull request can carry any upstream commit SHA as its head and
        # arrives with no pull request attached. Publishing a failure for a SHA
        # nothing binds would let an anonymous fork write App-authored checks.
        return CheckOutcome.unknown(
            VALIDATOR,
            reason=REASON_PR_UNRESOLVED,
            detail="the event names no pull request; nothing was published",
        )
    pull = api.get_pull(env.pull_number)
    if pull.base_ref != SERVED_BASE_REF:
        return CheckOutcome.skipped(
            VALIDATOR,
            reason=REASON_BASE_NOT_SERVED,
            detail=f"the pull request base is not {SERVED_BASE_REF}; nothing was published",
        )
    if pull.head_sha != env.head_sha:
        return _moved("the pull request head is not the SHA the event named")
    if pull.base_sha != env.base_sha:
        return _moved("the pull request base is not the SHA the event named")
    mismatch = _run_mismatch(env, api)
    if mismatch is not None:
        return mismatch
    if env.execute_result != "success":
        failed = CheckOutcome.failed(
            VALIDATOR,
            reason=REASON_EXECUTION_FAILED,
            detail=f"the execute job concluded {env.execute_result}",
        )
        return _publish_failure(env, api, pull, failed)
    return _publish_success(env, api, pull)


def publish(env: PublisherEnv, api_for: ApiFactory = _real_api) -> CheckOutcome:
    """Run the publication stage and return its typed outcome."""
    stop = first_stop(
        env, gate_outcome, key_gate_outcome, token_gate_outcome, validate_event_inputs
    )
    if stop is not None:
        return stop
    try:
        return _publish_bound(env, api_for(env))
    except ApiError as exc:
        return _api_failure(exc)


def _command_gate(env: PublisherEnv, environ: Mapping[str, str] | None) -> CheckOutcome | None:
    stop = gate_outcome(env)
    write_output("enabled", "false" if stop is not None else "true", environ)
    return stop


def _command_preflight(env: PublisherEnv, environ: Mapping[str, str] | None) -> CheckOutcome | None:
    mint = gate_outcome(env) is None and key_gate_outcome(env) is None
    write_output("mint", "true" if mint else "false", environ)
    return None


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=("gate", "preflight", "execute", "publish"))
    return parser


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    api_for: ApiFactory = _real_api,
) -> int:
    """Dispatch one stage and return its exit code."""
    args = build_parser().parse_args(argv)
    env = PublisherEnv.from_environ(environ)
    outcome: CheckOutcome | None
    if args.command == "gate":
        outcome = _command_gate(env, environ)
    elif args.command == "preflight":
        outcome = _command_preflight(env, environ)
    elif args.command == "execute":
        outcome = run_execute(env, environ)
    else:
        outcome = publish(env, api_for)
    if outcome is None:
        return 0
    if args.command == "execute" and outcome.state is EvidenceState.SKIP:
        return _execute_disagreed(outcome, environ)
    report(outcome, environ)
    return exit_code(outcome)


def _execute_disagreed(outcome: CheckOutcome, environ: Mapping[str, str] | None) -> int:
    """Fail the execute job when it skips after the gate said to run.

    The gate job read the flag and the event. If execute reads them differently,
    the flag changed between the two jobs. A SKIP exit 0 here would let
    ``needs.execute.result`` read success though no test ran, and the publish job
    would post a green check run for it.
    """
    note = CheckOutcome.skipped(
        VALIDATOR,
        reason=outcome.reason,
        detail=f"{outcome.detail}; the gate saw the publisher enabled, so this run is refused",
    )
    report(note, environ)
    print(f"::error title={VALIDATOR}::execute skipped after the gate enabled the publisher")
    return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
