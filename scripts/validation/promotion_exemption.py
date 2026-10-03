#!/usr/bin/env python3
"""Accept a path-filter skip as ``policy.exempt``, after checking it, and nothing else.

ADR-113 decision 9 and owner decision D26 (issue #5636), recorded on the issue as
"add a typed `policy.exempt` reason, accepted only when the skip is a path-filter
skip on that SHA. Verify the skip against the workflow's path filter and the
diff. Never accept a blanket exemption."

Quoted from
``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``
decision 9: "`SKIP` with reason `policy.exempt`, or a validator the applicability
table marks not applicable | No" finding; "`SKIP` with any other reason | Yes".

A validator job that skips itself because its paths filter found nothing relevant
uploads ``SKIP`` with reason ``validator.not_run`` (``emit_validator_evidence.py``).
The gate reads that as a finding. This module turns that one record into
``SKIP`` with reason ``policy.exempt`` when, and only when, all of these hold:

1. The record is ``SKIP`` with reason ``validator.not_run``. Any other state or
   reason is returned unchanged, so a ``FAIL`` or an ``UNKNOWN`` is never softened.
2. The applicability row carries a ``path_filter``. A row without one has no
   exemption path, so there is no blanket exemption.
3. The filter is read from the workflow file as the candidate's first parent held
   it, not the candidate's own copy. A commit that narrowed its own filter to
   excuse itself is judged by the filter it replaced.
4. No path the candidate changed against its first parent matches any glob of
   that filter.

Any condition that cannot be checked (no parent, an unreadable file, a filter key
that is missing) declines the exemption. A decline leaves the finding in place.

Stricter/looser/different than canonical: the workflow ran its filter against the
push's own ``before..after`` range, and this module compares the candidate's first
parent diff. A skip means no path in the whole range matched, so none in the last
commit's diff did either, and a matching path in that diff means the job should
not have skipped. The check can therefore decline a valid skip, never accept an
invalid one. Glob matching is wider than the action's for plain
globs: ``fnmatch`` lets ``*`` cross ``/``, and a leading ``**/`` also matches a
top-level file. Wider matching declines more. A filter using brace sets, ``!``,
extglobs, or ``/**/`` is refused whole (``_is_plain_glob``), because ``fnmatch``
can match less than the action for those.

Assumption: the check diffs the candidate against its first parent. The run
payload carries no ``before`` SHA. A push of several commits would leave earlier
commits with no diff here, so the check assumes one commit per push to the
default branch, which holds for squash and merge-commit merges. The shipped
filters all match their own workflow file, so editing a workflow never reads as
an irrelevant diff.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import yaml

from scripts.validation.evidence import REASON_POLICY_EXEMPT, CheckOutcome, EvidenceState
from scripts.validation.promotion_applicability import Applicability
from scripts.validation.promotion_candidate import (
    CandidateCheckError,
    InvalidCandidateNameError,
    changed_files,
    parent_file,
)
from scripts.validation.promotion_evidence import EvidenceRecord

REASON_NOT_RUN = "validator.not_run"
REASON_EXEMPT = REASON_POLICY_EXEMPT
_UNSUPPORTED_GLOB_CHARS = frozenset("{}()!|+@[]")
PATHS_FILTER_ACTION = "dorny/paths-filter"


class DiffSource(Protocol):
    """What the check needs from git. A fake stands in for it in tests."""

    def changed_paths(self, sha: str) -> tuple[str, ...]:
        """Paths the commit changed against its first parent."""

    def parent_text(self, sha: str, path: str) -> str | None:
        """A file as the commit's first parent held it, or None."""


class GitDiffSource:
    """Reads the candidate's diff and its parent's workflow files from a clone."""

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root

    def changed_paths(self, sha: str) -> tuple[str, ...]:
        return changed_files(self._root, sha)

    def parent_text(self, sha: str, path: str) -> str | None:
        return parent_file(self._root, sha, path)


def _filters_in(step: object) -> dict[str, Any] | None:
    if not isinstance(step, dict) or not str(step.get("uses", "")).startswith(PATHS_FILTER_ACTION):
        return None
    options = step.get("with")
    text = options.get("filters") if isinstance(options, dict) else None
    if not isinstance(text, str):
        return None
    try:
        document = yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError):
        return None
    return document if isinstance(document, dict) else None


def _is_plain_glob(value: object) -> bool:
    """True for a glob this module reads at least as widely as the action does.

    The action expands brace sets and reads ``!`` as negation, and ``fnmatch`` does
    neither, so a pattern using them could match less here and accept a skip
    wrongly. It also reads ``a/**/b`` where ``fnmatch`` needs two slashes. Such a
    filter is refused whole, and the exemption declines.
    """
    return (
        isinstance(value, str)
        and bool(value)
        and not (set(value) & _UNSUPPORTED_GLOB_CHARS)
        and "/**/" not in value
    )


def filter_globs(workflow_text: str, key: str) -> tuple[str, ...] | None:
    """Return the globs under ``key`` in the workflow's paths-filter step, or None.

    None when the workflow does not parse, has no such step or key, or the key
    holds anything but a non-empty list of strings. Exactly one step may define
    the key: two definitions are ambiguous and decline.
    """
    try:
        document = yaml.safe_load(workflow_text)
    except (yaml.YAMLError, RecursionError):
        return None
    jobs = document.get("jobs") if isinstance(document, dict) else None
    found: list[tuple[str, ...]] = []
    for job in jobs.values() if isinstance(jobs, dict) else []:
        steps = job.get("steps") if isinstance(job, dict) else None
        for step in steps if isinstance(steps, list) else []:
            filters = _filters_in(step)
            globs = filters.get(key) if filters else None
            if isinstance(globs, list) and globs and all(_is_plain_glob(g) for g in globs):
                found.append(tuple(globs))
    return found[0] if len(found) == 1 else None


def path_matches(path: str, globs: Sequence[str]) -> bool:
    """True when ``path`` matches any glob, reading each one as wide as is plausible."""
    for pattern in globs:
        if fnmatch.fnmatchcase(path, pattern):
            return True
        if pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:]):
            return True
    return False


def _exempt_record(record: EvidenceRecord, key: str, changed: int) -> EvidenceRecord:
    outcome = record.outcome
    exempt = CheckOutcome(
        validator=outcome.validator,
        state=EvidenceState.SKIP,
        revision=outcome.revision,
        scope=outcome.scope,
        reason=REASON_EXEMPT,
        detail=f"path filter '{key}': none of the {changed} changed paths match",
        duration_seconds=outcome.duration_seconds,
    )
    return EvidenceRecord(
        outcome=exempt, digest=record.digest, items=record.items, source=record.source
    )


def is_not_run_skip(record: EvidenceRecord) -> bool:
    """True for the one record this module may exempt."""
    outcome = record.outcome
    return outcome.state is EvidenceState.SKIP and outcome.reason == REASON_NOT_RUN


def apply_exemption(
    record: EvidenceRecord, entry: Applicability, sha: str, source: DiffSource
) -> EvidenceRecord:
    """Return the record exempted when the skip checks out, else the record unchanged."""
    if entry.path_filter is None or not is_not_run_skip(record):
        return record
    try:
        text = source.parent_text(sha, entry.workflow)
        changed = source.changed_paths(sha)
    except (CandidateCheckError, InvalidCandidateNameError):
        return record
    globs = filter_globs(text, entry.path_filter.key) if text is not None else None
    if globs is None or any(path_matches(path, globs) for path in changed):
        return record
    return _exempt_record(record, entry.path_filter.key, len(changed))
