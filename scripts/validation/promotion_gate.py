#!/usr/bin/env python3
"""Compute the release promotion verdict from persisted validator evidence.

ADR-113 decisions 1, 3, 4, 7, 8, and 9, issue #5636. The program reads typed
evidence files, binds each to the candidate commit and tarball digest, applies
the governed exception records, classes every finding as remediated, accepted,
expired, or unresolved, and writes one JSON manifest. Workflow YAML only calls it.

Exit codes (ADR-035): 0 the verdict is ``promote``, or the run is advisory;
1 enforcing mode and the verdict is ``block``; 2 invalid arguments, exceptions
file, or previous manifest; 3 the evidence directory cannot be read.

Advisory is the default. ADR-113 decision 5 says the gate stays advisory until
the default-branch entry point, the integration pin, and the tag ruleset exist,
and the manifest says so in ``enforced``. In advisory mode a ``block`` verdict
prints ``WOULD BLOCK`` and still exits 0.

Approval is not read here. With one code owner, decision 7 accepts no exception,
so this program installs ``deny_all_approvals``: every exception record reads as
unapproved and its finding stays ``unresolved``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.evidence import CheckOutcome  # noqa: E402
from scripts.validation.promotion_applicability import (  # noqa: E402
    ApplicabilityError,
    build_tier_validators,
    load_applicability,
    required_validators,
)
from scripts.validation.promotion_candidate import (  # noqa: E402
    CandidateCheckError,
    candidate_files,
    candidate_on_branch,
    tag_names_candidate,
)
from scripts.validation.promotion_evidence import (  # noqa: E402
    BoundEvidence,
    Candidate,
    EvidenceRecord,
    bind_records,
    load_evidence_dir,
)
from scripts.validation.promotion_exceptions import (  # noqa: E402
    ExceptionsFileError,
    deny_all_approvals,
    load_exceptions,
    utc_today,
)
from scripts.validation.promotion_findings import (  # noqa: E402
    MANIFEST_SCHEMA_VERSION,
    ClassifiedFinding,
    Finding,
    ManifestError,
    PreviousManifest,
    blocks_promotion,
    classify_findings,
    collect_findings,
    counts,
    load_previous_manifest,
    missing_outcomes,
    overall_state,
    passed_scopes,
    remediated_findings,
    unreadable_outcomes,
)

EXIT_OK, EXIT_LOGIC, EXIT_CONFIG, EXIT_EXTERNAL = 0, 1, 2, 3
REASON_NO_APPLICABILITY = "applicability.absent"
MODE_ADVISORY = "advisory"
MODE_ENFORCING = "enforcing"


@dataclass(frozen=True, slots=True)
class GateResult:
    """The manifest and the exit code a run produced."""

    manifest: dict[str, Any]
    exit_code: int


def _digest_bound(
    candidate: Candidate, bound: Sequence[EvidenceRecord], build_validators: frozenset[str]
) -> bool:
    """True when the candidate has a tarball digest and a build result bound to it.

    ADR-113 decision 4 defines the promoted candidate as the commit plus the
    tarball digest. A manifest bound to the commit alone is not that candidate.
    Binding already rejected any build record whose digest differed.
    """
    return bool(candidate.digest) and any(
        record.outcome.validator in build_validators for record in bound
    )


def _no_applicability_outcome(candidate: Candidate) -> CheckOutcome:
    """No applicability table supplied the required set, so nothing says what must have run.

    ADR-113 decision 3 computes the required set from an applicability table. An
    absent or empty table, or an empty set, is not a clean sheet: one unrelated
    ``PASS`` would otherwise promote a candidate no applicable validator
    examined, and a short ``--require`` list could not stand in for the table.
    """
    return CheckOutcome.unknown(
        "promotion",
        reason=REASON_NO_APPLICABILITY,
        scope=f"candidate {candidate.sha[:12]}",
        examined=0,
        detail="the applicability table is absent or empty, or no validators were named",
    )


def _remediated_entries(
    previous: PreviousManifest | None,
    current: Sequence[Finding],
    candidate: Candidate,
    passed: frozenset[tuple[str, str]],
) -> list[dict[str, str]]:
    if previous is None:
        return []
    fixed = remediated_findings(previous.findings, current, passed)
    return [
        {
            "fingerprint": item.fingerprint,
            "validator": item.validator,
            "reason": item.reason,
            "scope": item.scope,
            "item": item.item,
            "fixed_between": f"{previous.candidate_sha}..{candidate.sha}",
        }
        for item in fixed
    ]


def build_manifest(
    *,
    candidate: Candidate,
    bound: BoundEvidence,
    classified: Sequence[ClassifiedFinding],
    remediated: list[dict[str, str]],
    state: str,
    mode: str,
    today: date,
    exceptions_loaded: int,
    digest_bound: bool,
    not_applicable: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Assemble the manifest. ``verdict`` follows decision 9 whatever the mode."""
    tally = counts(classified, len(remediated))
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "candidate": {"sha": candidate.sha, "digest": candidate.digest},
        "mode": mode,
        "enforced": mode == MODE_ENFORCING,
        "date": today.isoformat(),
        "state": state,
        "verdict": "block" if blocks_promotion(tally) else "promote",
        "counts": tally,
        "findings": [entry.to_dict() for entry in classified],
        "remediated": remediated,
        "digest_bound": digest_bound,
        "not_applicable": sorted(not_applicable),
        "evidence": {
            "bound": len(bound.bound),
            "rejected": [item.to_dict() for item in bound.rejected],
        },
        "exceptions": {"loaded": exceptions_loaded},
    }


def run_gate(
    *,
    repo_root: Path,
    evidence_dir: Path,
    candidate: Candidate,
    required: Sequence[str] = (),
    build_validators: frozenset[str] = frozenset(),
    previous: PreviousManifest | None = None,
    mode: str = MODE_ADVISORY,
    today: date | None = None,
    applicability_absent: bool = False,
    not_applicable: frozenset[str] = frozenset(),
) -> GateResult:
    """Compute the manifest and exit code.

    ``not_applicable`` names validators the table lists but marks not applicable
    to this candidate (decision 9). Their evidence is not consulted. A validator
    the table does not list at all stays consulted, so an unknown failing result
    still blocks.

    Raises ``ExceptionsFileError`` for a bad exceptions file and ``OSError`` for
    an evidence directory that cannot be read.
    """
    day = today or utc_today()
    exceptions = load_exceptions(repo_root)
    records, malformed = load_evidence_dir(evidence_dir)
    records = tuple(r for r in records if r.outcome.validator not in not_applicable)
    malformed = tuple(m for m in malformed if m.validator not in not_applicable)
    bound = bind_records(records, candidate, build_validators)
    evidence = BoundEvidence(bound.bound, (*malformed, *bound.rejected))
    synthesized = (
        *missing_outcomes(required, bound.bound, candidate),
        *unreadable_outcomes(malformed),
    )
    if applicability_absent or not required:
        synthesized = (*synthesized, _no_applicability_outcome(candidate))
    findings = collect_findings(bound.bound, synthesized)
    classified = classify_findings(findings, exceptions, day, deny_all_approvals)
    outcomes = (*(record.outcome for record in bound.bound), *synthesized)
    manifest = build_manifest(
        candidate=candidate,
        bound=evidence,
        classified=classified,
        remediated=_remediated_entries(previous, findings, candidate, passed_scopes(bound.bound)),
        state=overall_state(outcomes).state.value,
        mode=mode,
        today=day,
        exceptions_loaded=len(exceptions),
        digest_bound=_digest_bound(candidate, bound.bound, build_validators),
        not_applicable=not_applicable,
    )
    blocked = manifest["verdict"] == "block"
    code = EXIT_LOGIC if blocked and mode == MODE_ENFORCING else EXIT_OK
    return GateResult(manifest, code)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=_PROJECT_ROOT)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--candidate-digest", default="")
    parser.add_argument("--require", action="append", default=[], metavar="VALIDATOR")
    parser.add_argument("--build-validator", action="append", default=[], metavar="VALIDATOR")
    parser.add_argument("--previous-manifest", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--github-output",
        type=Path,
        default=None,
        help="append verdict=promote|block to this file, for a workflow job output",
    )
    parser.add_argument(
        "--ancestor-of",
        default=None,
        metavar="REF",
        help="refuse a candidate that is not an ancestor of this ref (the default branch head)",
    )
    parser.add_argument(
        "--expect-tag",
        default=None,
        metavar="TAG",
        help="refuse unless this existing tag resolves to the candidate commit",
    )
    parser.add_argument("--mode", choices=(MODE_ADVISORY, MODE_ENFORCING), default=MODE_ADVISORY)
    parser.add_argument("--today", type=date.fromisoformat, default=None, help="test seam")
    return parser


def _summary(manifest: dict[str, Any]) -> str:
    tally = manifest["counts"]
    shown = " ".join(f"{name}={tally[name]}" for name in sorted(tally))
    verdict = manifest["verdict"]
    if verdict == "block" and not manifest["enforced"]:
        verdict = "WOULD BLOCK (advisory)"
    return f"promotion gate: {verdict} state={manifest['state']} {shown}"


class _GateExitError(Exception):
    """Stops the run with an ADR-035 exit code after the message is printed."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def _refuse(message: str) -> _GateExitError:
    """Bad input or configuration: exit 2."""
    print(f"[FAIL] promotion gate: {json.dumps(message)}", file=sys.stderr)
    return _GateExitError(EXIT_CONFIG)


def _blocked(message: str) -> _GateExitError:
    """An external dependency (git, the filesystem) could not answer: exit 3."""
    print(f"[BLOCKED] promotion gate: {json.dumps(message)}", file=sys.stderr)
    return _GateExitError(EXIT_EXTERNAL)


def _argument_problem(args: argparse.Namespace) -> str | None:
    """Return why the arguments cannot describe a run, or None."""
    names = [*args.require, *args.build_validator]
    if any(not name.strip() or not name.isprintable() for name in names):
        return "--require and --build-validator names must be non-blank printable text"
    if args.mode == MODE_ENFORCING and not args.ancestor_of:
        return "enforcing mode requires --ancestor-of, so the candidate is a default-branch commit"
    return None


def _applicable(
    args: argparse.Namespace, candidate: Candidate
) -> tuple[tuple[str, ...], frozenset[str], bool, frozenset[str]]:
    """Return the required validators, the build-tier set, and whether a table supplied them.

    The table (decision 3) supplies them from the candidate's own tree. Names
    given on the command line add to the table and never replace it, so an
    absent or empty table cannot be replaced by a short list: the third value
    is False then, and ``run_gate`` blocks on ``applicability.absent``.
    """
    table = load_applicability(args.repo_root)
    paths = candidate_files(args.repo_root, candidate.sha) if table else ()
    required = {*required_validators(table, paths), *args.require}
    build = build_tier_validators(table) | frozenset(args.build_validator)
    skipped = frozenset(entry.validator for entry in table) - required
    return tuple(sorted(required)), build, bool(table), skipped


def _inputs(args: argparse.Namespace) -> tuple[Candidate, PreviousManifest | None]:
    candidate = Candidate(args.candidate_sha, args.candidate_digest)
    previous = load_previous_manifest(args.previous_manifest) if args.previous_manifest else None
    return candidate, previous


def _candidate_problem(args: argparse.Namespace, candidate: Candidate) -> str | None:
    """Return why the candidate is not where decision 5 requires, or None.

    Raises ``CandidateCheckError`` when git cannot answer.
    """
    if args.ancestor_of:
        ok, detail = candidate_on_branch(args.repo_root, candidate.sha, args.ancestor_of)
        if not ok:
            return detail
    if args.expect_tag:
        ok, detail = tag_names_candidate(args.repo_root, args.expect_tag, candidate.sha)
        if not ok:
            return detail
    return None


def _write_outputs(args: argparse.Namespace, manifest: dict[str, Any]) -> None:
    if args.output:
        text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        args.output.write_text(text, encoding="utf-8")
    if args.github_output:
        eligible = (
            manifest["verdict"] == "promote"
            and manifest["enforced"]
            and manifest["digest_bound"]
            and bool(args.expect_tag)
        )
        with args.github_output.open("a", encoding="utf-8") as handle:
            handle.write(f"verdict={manifest['verdict']}\n")
            handle.write(f"release_eligible={'true' if eligible else 'false'}\n")


@dataclass(frozen=True, slots=True)
class _Prepared:
    candidate: Candidate
    previous: PreviousManifest | None
    required: tuple[str, ...]
    build: frozenset[str]
    table_present: bool
    not_applicable: frozenset[str]


def _prepare(args: argparse.Namespace) -> _Prepared:
    """Validate arguments and resolve the candidate and applicable validators."""
    problem = _argument_problem(args)
    if problem:
        raise _refuse(problem)
    try:
        candidate, previous = _inputs(args)
        problem = _candidate_problem(args, candidate)
        required, build, table_present, skipped = _applicable(args, candidate)
    except (ValueError, ManifestError, OSError, ApplicabilityError) as exc:
        raise _refuse(f"{type(exc).__name__}: {exc}") from exc
    except CandidateCheckError as exc:
        raise _blocked(str(exc)) from exc
    if problem:
        raise _refuse(problem)
    return _Prepared(candidate, previous, required, build, table_present, skipped)


def _execute(args: argparse.Namespace, prepared: _Prepared) -> GateResult:
    try:
        return run_gate(
            repo_root=args.repo_root,
            evidence_dir=args.evidence_dir,
            candidate=prepared.candidate,
            required=prepared.required,
            build_validators=prepared.build,
            applicability_absent=not prepared.table_present,
            not_applicable=prepared.not_applicable,
            previous=prepared.previous,
            mode=args.mode,
            today=args.today,
        )
    except ExceptionsFileError as exc:
        raise _refuse(str(exc)) from exc
    except OSError as exc:
        raise _blocked(type(exc).__name__) from exc


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    args = _parser().parse_args(argv)
    try:
        result = _execute(args, _prepare(args))
        try:
            _write_outputs(args, result.manifest)
        except OSError as exc:
            raise _blocked(f"cannot write {type(exc).__name__}") from exc
    except _GateExitError as stop:
        return stop.code
    print(_summary(result.manifest))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
