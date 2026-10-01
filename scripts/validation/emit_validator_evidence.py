#!/usr/bin/env python3
"""Write one typed evidence file for the validator job that calls it.

ADR-113 decision 2, issue #5636. Quoted from
``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``:

    "Each job that runs a validator uploads its `CheckOutcome.to_dict()`
    output as a JSON evidence artifact. [...] The artifact name is the
    validator name."

and decision 5: "its results are the `push` and `merge_group` runs for that SHA."

This program writes ``<validator>.json`` for the upload step. It writes nothing
for any other event or ref, so a pull request run or a feature branch push does
not add evidence the gate would reject.

What the file claims: the job's own conclusion, not step-level or item-level
results. ``success`` with the validator's work done is ``PASS``. ``success``
with that work skipped is ``SKIP`` with reason ``validator.not_run``: a green
job that did nothing must not read as a pass. ``failure`` is ``FAIL``.
``cancelled`` and any unrecognized status are ``UNKNOWN``. ADR-113 decision 2
adds the check-run conclusion as a second source and takes the worse of the
two, and the aggregator verifies the producing workflow run (decision 5).

Different than canonical: ``CheckOutcome`` ``PASS`` allows ``examined`` to be
``None`` and this program leaves it ``None``, because a job conclusion counts no
items. ``ci-scripts.md`` MUST 12 asks for an examined count where a checker can
supply one; this program is not the checker.

Stdlib only transitively (``ci-scripts.md`` MUST 18): the calling jobs run it
with bare ``python3``.

Exit codes (ADR-035): 0 written or deliberately not emitted, 1 the built record
failed the strict evidence parser, 2 invalid arguments, 3 the file cannot be
written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.evidence import CheckOutcome, EvidenceState  # noqa: E402
from scripts.validation.promotion_evidence import EvidenceError, parse_evidence  # noqa: E402

EXIT_OK, EXIT_LOGIC, EXIT_CONFIG, EXIT_EXTERNAL = 0, 1, 2, 3
REASON_NOT_RUN = "validator.not_run"
REASON_JOB_FAILED = "job.failed"
REASON_JOB_CANCELLED = "job.cancelled"
REASON_STATUS_UNRECOGNIZED = "job.status_unrecognized"
MERGE_QUEUE_REF_PREFIX = "refs/heads/gh-readonly-queue/"
_VALIDATOR_RE = re.compile(r"[a-z0-9_]{1,100}")
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_SCOPE_LIMIT = 200


def emits_for(event: str, ref: str, default_branch: str) -> bool:
    """True for a default-branch ``push`` or a merge-queue ``merge_group`` run.

    The candidate is a merged default-branch commit (decision 5). A pull request
    run and a feature branch push describe a commit the promotion never names.
    """
    if event == "push":
        return bool(default_branch) and ref == f"refs/heads/{default_branch}"
    if event == "merge_group":
        return ref.startswith(MERGE_QUEUE_REF_PREFIX)
    return False


def _printable(value: str) -> str:
    """Return ``value`` control-free and bounded: workflow context text is not trusted."""
    cleaned = "".join(char if char.isprintable() else "?" for char in value)
    return cleaned[:_SCOPE_LIMIT]


def build_outcome(
    *, validator: str, job_status: str, ran: bool, revision: str, scope: str
) -> CheckOutcome:
    """Map a job conclusion to a typed outcome, never reading a no-op as a pass."""
    if job_status == "failure":
        return CheckOutcome.failed(
            validator,
            reason=REASON_JOB_FAILED,
            revision=revision,
            scope=scope,
            detail="the job concluded failure",
        )
    if job_status == "cancelled":
        return CheckOutcome.unknown(
            validator,
            reason=REASON_JOB_CANCELLED,
            revision=revision,
            scope=scope,
            detail="the job was cancelled before it finished",
        )
    if job_status != "success":
        return CheckOutcome.unknown(
            validator,
            reason=REASON_STATUS_UNRECOGNIZED,
            revision=revision,
            scope=scope,
            detail=f"job status {_printable(job_status)!r} is not one this program maps",
        )
    if not ran:
        return CheckOutcome(
            validator=validator,
            state=EvidenceState.SKIP,
            revision=revision,
            scope=scope,
            reason=REASON_NOT_RUN,
            detail="the job concluded success but its validation steps did not run",
        )
    return CheckOutcome.passed(validator, revision=revision, scope=scope)


def write_evidence(outcome: CheckOutcome, output_dir: Path) -> Path:
    """Write the outcome as ``<validator>.json`` after the strict parser accepts it.

    Raises ``EvidenceError`` when the parser refuses the record and ``OSError``
    when the file cannot be written.
    """
    document = outcome.to_dict()
    parse_evidence(document, f"{outcome.validator}.json")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{outcome.validator}.json"
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _boolean(text: str) -> bool:
    if text not in ("true", "false"):
        raise argparse.ArgumentTypeError("expected 'true' or 'false'")
    return text == "true"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--validator", required=True)
    parser.add_argument("--job-status", required=True)
    parser.add_argument("--ran", type=_boolean, default=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--default-branch", default="")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--github-output", type=Path, default=None)
    return parser


def _argument_problem(args: argparse.Namespace) -> str | None:
    if not _VALIDATOR_RE.fullmatch(args.validator):
        return "--validator must be lowercase letters, digits, and underscores, 1 to 100 long"
    if not _SHA_RE.fullmatch(args.revision):
        return "--revision must be a 40-character lowercase hex commit SHA"
    return None


def _report_emitted(args: argparse.Namespace, emitted: bool) -> None:
    if args.github_output is None:
        return
    with args.github_output.open("a", encoding="utf-8") as handle:
        handle.write(f"emitted={'true' if emitted else 'false'}\n")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = _parser().parse_args(argv)
    problem = _argument_problem(args)
    if problem:
        print(f"[FAIL] validator evidence: {json.dumps(problem)}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        if not emits_for(args.event, args.ref, args.default_branch):
            print(f"[INFO] validator evidence: none for event {_printable(args.event)!r}")
            _report_emitted(args, False)
            return EXIT_OK
        scope = _printable(f"job {args.job_id} on {args.event}")
        outcome = build_outcome(
            validator=args.validator,
            job_status=args.job_status,
            ran=args.ran,
            revision=args.revision,
            scope=scope,
        )
        path = write_evidence(outcome, args.output_dir)
        _report_emitted(args, True)
    except EvidenceError as exc:
        print(f"[FAIL] validator evidence: {json.dumps(str(exc))}", file=sys.stderr)
        return EXIT_LOGIC
    except OSError as exc:
        print(f"[BLOCKED] validator evidence: cannot write {type(exc).__name__}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(f"[INFO] validator evidence: state {outcome.state.value} written to {path.name}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
