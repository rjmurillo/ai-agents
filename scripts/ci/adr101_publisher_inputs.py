"""Shared contract for the ADR-101 requirement 2a publisher (issue #5245).

Decision D23 split ADR-101 requirement 2. This publisher is the (2a) half: a
dedicated GitHub App publishes a check run under an identity the pull request
cannot assume, bound to a head and base SHA, from a job that runs no candidate
code. It does NOT authenticate that the tests ran or passed. That is (2b), open
research. A candidate that controls the test process can forge the result the
publisher is told, so the published label never says "verified".

This module holds what every stage reads: the environment contract, the typed
reason codes, the input validators, and the credential gate. Standard library
plus ``scripts.validation.evidence`` only, so a step invoking ``python3`` with
no environment installed can use it (``.claude/rules/ci-scripts.md`` MUST 18).

Canonical source mirrored: ``scripts/validation/evidence.py`` defines
``CheckOutcome`` and the five states. Its reason pattern is quoted verbatim:

    _REASON_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]*(\\.[a-z0-9_]+)*$")

The reason codes below are dotted lowercase slugs, which that pattern accepts.

Different from canonical: ``evidence.exit_code_for`` maps a rejected SKIP to
exit 2, because a blocking gate was asked for a check it cannot supply. This
publisher is disabled by default, so a SKIP exits 0 here. It publishes no check
run in any non-PASS state, so a SKIP can never satisfy a required context.

EXIT CODES (ADR-035):
  0 - PASS, or SKIP (flag off, or an event this publisher does not serve)
  1 - FAIL or UNKNOWN: a violation or untrustworthy evidence
  3 - BLOCKED on an external dependency
  4 - BLOCKED on authentication: the App id, key or token is absent or refused
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.evidence import (  # noqa: E402
    REASON_AUTH_UNAVAILABLE,
    CheckOutcome,
    EvidenceState,
)

VALIDATOR = "adr101_publisher"
CHECK_NAME = "ADR-101 Published Result"
SERVED_EVENT = "pull_request"
SHA_LENGTH = 40

# What a successful check run says. It never says "verified": under (2b) the
# publisher cannot know the tests ran. A test pins the absence of that word.
PUBLISHED_LABEL = (
    "published by the pinned App for this head and base; "
    "execution authenticity bounded by ADR-101 requirement 2b"
)

REASON_DISABLED = "publisher.disabled"
REASON_EVENT_NOT_SERVED = "event.not_served"
REASON_INPUT_INVALID = "input.invalid"
REASON_REVISION_MOVED = "revision.moved"
REASON_EVIDENCE_MISMATCH = "evidence.mismatch"
REASON_EXECUTION_FAILED = "execution.failed"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

ENV_ENABLED = "ADR101_PUBLISHER_ENABLED"
ENV_APP_ID = "ADR101_PUBLISHER_APP_ID"
ENV_HAS_KEY = "ADR101_HAS_KEY"
ENV_APP_TOKEN = "ADR101_APP_TOKEN"
ENV_TOKEN_OUTCOME = "ADR101_APP_TOKEN_OUTCOME"
ENV_READ_TOKEN = "ADR101_READ_TOKEN"
ENV_REPOSITORY = "ADR101_REPOSITORY"
ENV_HEAD_SHA = "ADR101_HEAD_SHA"
ENV_PULL_NUMBER = "ADR101_PULL_NUMBER"
ENV_RUN_ID = "ADR101_TRIGGER_RUN_ID"
ENV_EVENT = "ADR101_TRIGGER_EVENT"
ENV_EXECUTE_RESULT = "ADR101_EXECUTE_RESULT"

_SHA_RE = re.compile(r"[0-9a-f]{40}")
_NUMBER_RE = re.compile(r"[0-9]{1,20}")
_REPO_PART = r"[A-Za-z0-9_.-]{1,100}"
_REPO_RE = re.compile(rf"{_REPO_PART}/{_REPO_PART}")
_EXECUTE_RESULTS = frozenset({"success", "failure", "cancelled", "skipped"})


def is_sha(value: str) -> bool:
    """True for exactly 40 lowercase hex characters, nothing else."""
    return _SHA_RE.fullmatch(value) is not None


def is_number(value: str) -> bool:
    """True for a short run of ASCII digits (a pull request or run id)."""
    return _NUMBER_RE.fullmatch(value) is not None


def is_repository(value: str) -> bool:
    """True for ``owner/name`` with no path traversal segment."""
    if _REPO_RE.fullmatch(value) is None:
        return False
    return all(part not in {".", ".."} for part in value.split("/"))


def revision_digest(head_sha: str, base_sha: str) -> str:
    """Correlation digest of the captured head and base pair.

    Used as the check run's ``external_id``. The key holder controls that field,
    so it correlates a run with its inputs and is never audit evidence.
    """
    return hashlib.sha256(f"{head_sha}:{base_sha}".encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PublisherEnv:
    """Every input the stages read, all strings, none trusted until validated."""

    enabled: str
    app_id: str
    has_key: str
    app_token: str
    token_outcome: str
    read_token: str
    repository: str
    head_sha: str
    pull_number: str
    run_id: str
    event: str
    execute_result: str

    @classmethod
    def from_environ(cls, environ: Mapping[str, str] | None = None) -> PublisherEnv:
        """Read the contract from ``environ`` (default: the process environment)."""
        source = os.environ if environ is None else environ

        def read(name: str) -> str:
            return source.get(name, "").strip()

        return cls(
            enabled=read(ENV_ENABLED),
            app_id=read(ENV_APP_ID),
            has_key=read(ENV_HAS_KEY),
            app_token=read(ENV_APP_TOKEN),
            token_outcome=read(ENV_TOKEN_OUTCOME),
            read_token=read(ENV_READ_TOKEN),
            repository=read(ENV_REPOSITORY),
            head_sha=read(ENV_HEAD_SHA),
            pull_number=read(ENV_PULL_NUMBER),
            run_id=read(ENV_RUN_ID),
            event=read(ENV_EVENT),
            execute_result=read(ENV_EXECUTE_RESULT),
        )

    def flag_on(self) -> bool:
        """Only the exact text ``true`` enables. Any other value is off."""
        return self.enabled == "true"


def gate_outcome(env: PublisherEnv) -> CheckOutcome | None:
    """Return a SKIP when the publisher does not apply, else None.

    Order matters: the flag first, so a disabled publisher says so regardless of
    the event, then the event. Both are SKIP and publish nothing.
    """
    if not env.flag_on():
        detail = "ADR101_PUBLISHER_ENABLED is not 'true'; nothing is published"
        if env.enabled not in {"", "false"}:
            detail = f"ADR101_PUBLISHER_ENABLED has unrecognized value; {detail}"
        return CheckOutcome.skipped(VALIDATOR, reason=REASON_DISABLED, detail=detail)
    if env.event != SERVED_EVENT:
        return CheckOutcome.skipped(
            VALIDATOR,
            reason=REASON_EVENT_NOT_SERVED,
            detail=f"triggering event is not {SERVED_EVENT}; nothing is published",
        )
    return None


def key_gate_outcome(env: PublisherEnv) -> CheckOutcome | None:
    """Return BLOCKED when the App id or key is absent, else None.

    The flag is on when this runs, so absence is a configuration the owner owes,
    and the publisher fails closed instead of reporting a quiet pass.
    """
    if is_number(env.app_id) and env.has_key == "true":
        return None
    return CheckOutcome.blocked(
        VALIDATOR,
        reason=REASON_AUTH_UNAVAILABLE,
        detail="flag is on but the App id or private key is absent in environment adr101-publisher",
    )


def token_gate_outcome(env: PublisherEnv) -> CheckOutcome | None:
    """Return BLOCKED when minting the installation token did not succeed."""
    if env.token_outcome == "success" and env.app_token:
        return None
    return CheckOutcome.blocked(
        VALIDATOR,
        reason=REASON_AUTH_UNAVAILABLE,
        detail="the App installation token was not minted; the key or App install is refused",
    )


def validate_event_inputs(env: PublisherEnv) -> CheckOutcome | None:
    """Return FAIL when any value taken from the event is not the expected shape.

    Nothing here is repaired or coerced. A malformed SHA, id or repository name
    stops the run before any API call, and nothing is published.
    """
    problems = []
    if not is_sha(env.head_sha):
        problems.append("head SHA is not 40 lowercase hex characters")
    if not is_repository(env.repository):
        problems.append("repository is not owner/name")
    if not is_number(env.run_id):
        problems.append("triggering run id is not numeric")
    if env.pull_number and not is_number(env.pull_number):
        problems.append("pull request number is not numeric")
    if env.execute_result not in _EXECUTE_RESULTS:
        problems.append("execute job result is not success, failure, cancelled or skipped")
    if not problems:
        return None
    return CheckOutcome.failed(
        VALIDATOR, reason=REASON_INPUT_INVALID, findings=len(problems), detail="; ".join(problems)
    )


def first_stop(
    env: PublisherEnv, *gates: Callable[[PublisherEnv], CheckOutcome | None]
) -> CheckOutcome | None:
    """Return the first gate's outcome that stops the run, else None.

    A ``CheckOutcome`` has no truth value by design (it raises), so gates chain
    here and never with ``or``.
    """
    for gate in gates:
        stop = gate(env)
        if stop is not None:
            return stop
    return None


def exit_code(outcome: CheckOutcome) -> int:
    """Map a typed outcome to the ADR-035 exit code this module documents."""
    if outcome.state in (EvidenceState.PASS, EvidenceState.SKIP):
        return EXIT_OK
    if outcome.state is EvidenceState.BLOCKED:
        return EXIT_AUTH if outcome.reason == REASON_AUTH_UNAVAILABLE else EXIT_EXTERNAL
    return EXIT_VIOLATION


def write_output(key: str, value: str, environ: Mapping[str, str] | None = None) -> None:
    """Append ``key=value`` to ``GITHUB_OUTPUT`` when running under Actions."""
    source = os.environ if environ is None else environ
    path = source.get("GITHUB_OUTPUT", "")
    if not path:
        return
    if "\n" in value or "\r" in value or "\n" in key:
        raise ValueError("an Actions output value must be a single line")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"{key}={value}\n")


def report(outcome: CheckOutcome, environ: Mapping[str, str] | None = None) -> None:
    """Print the typed line, annotate non-pass states, and record the summary.

    Never prints a token, a response body or a traceback. The run log of a
    public repository is world readable.
    """
    source = os.environ if environ is None else environ
    line = outcome.report_line()
    print(line)
    if outcome.state not in (EvidenceState.PASS, EvidenceState.SKIP):
        print(f"::error title={VALIDATOR}::{line}")
    summary = source.get("GITHUB_STEP_SUMMARY", "")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"{line}\n\n")
