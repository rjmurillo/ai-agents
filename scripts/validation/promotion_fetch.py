#!/usr/bin/env python3
"""Fetch evidence artifacts for a promotion candidate and keep only what passes provenance.

ADR-113 decisions 2 and 5, issue #5636. For each commit-tier validator in the
applicability table, this module finds the workflow runs for the candidate
commit, applies :func:`scripts.validation.promotion_provenance.run_problem` to
each, and downloads an artifact only from a run that passes. Quoted from the
ADR, decision 5: "The aggregator never deserializes an artifact from a run that
fails them, per ADR-101." It then corroborates the artifact with the job's
check-run and writes the worse of the two as one evidence file for
``promotion_gate.py`` to load.

Three trust points, each a hard rule here:

- An artifact is selected by the verified run's id and the validator name, then
  its API record must name that run and the candidate SHA.
- The archive is read in memory with a size cap. Exactly one member, named
  ``<validator>.json``, is read. Nothing is extracted to disk, so no member name
  becomes a path.
- The text goes through ``parse_evidence_text`` in
  ``scripts/validation/promotion_evidence.py`` (line 267 at this commit), the
  loader the gate already uses through ``load_evidence_dir``: strict JSON,
  duplicate keys refused, unknown keys refused. The record's validator must also
  equal the artifact name.
- An artifact must have been created at or after the run's latest attempt
  started, and its download must be the size its listing reported.

Build-tier rows are skipped here. Their results come from the build job in the
promotion entry workflow's own run, which is separate work, so they stay missing
and the gate reports them.

An API failure raises ``GitHubApiError``. The caller exits 3: a source that could
not answer is not an empty answer.

Stricter/looser/different than canonical: decision 2 says the aggregator "reads
the job's check-run conclusion for the candidate SHA". This module reads the run's
jobs and the commit's check-runs and joins them by id, as ``promotion_provenance``
documents.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import zipfile
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from scripts.validation.evidence import CheckOutcome, EvidenceState
from scripts.validation.promotion_applicability import TIER_COMMIT, Applicability
from scripts.validation.promotion_evidence import (
    MAX_EVIDENCE_BYTES,
    EvidenceRecord,
    parse_evidence_text,
)
from scripts.validation.promotion_provenance import (
    combine,
    corroborate,
    is_repository_name,
    run_problem,
)

PAGE_SIZE = 100
MAX_PAGES = 20
GH_TIMEOUT_SECONDS = 120
MAX_ARCHIVE_BYTES = 4 * MAX_EVIDENCE_BYTES
REASON_ARTIFACT_ABSENT = "artifact.absent"
REASON_ARTIFACT_AMBIGUOUS = "artifact.ambiguous"
REASON_ARTIFACT_EXPIRED = "artifact.expired"
REASON_ARTIFACT_RUN = "artifact.run_mismatch"
REASON_ARTIFACT_SIZE = "artifact.too_large"
REASON_ARTIFACT_STALE = "artifact.stale"
REASON_ARTIFACT_REVISION = "artifact.revision_mismatch"
REASON_ARTIFACT_FORMAT = "artifact.malformed"
REASON_RUN_ABSENT = "run.absent"
REASON_ACCEPTED = "accepted"
_SHA_RE = re.compile(r"[0-9a-f]{40}")
_BRANCH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


class RevisionMismatchError(ValueError):
    """An artifact's record names a commit other than the candidate."""


class GitHubApiError(Exception):
    """GitHub could not answer, so the check proves nothing."""


class GitHubReader(Protocol):
    """The two reads this module needs. A fake stands in for it in tests."""

    def get_json(self, path: str, params: Mapping[str, str] | None = None) -> object:
        """Return the decoded JSON body of a GET."""

    def get_bytes(self, path: str) -> bytes:
        """Return the raw body of a GET, following redirects."""


class GhCliReader:
    """Reads the GitHub REST API through ``gh api``, which carries ``GH_TOKEN``."""

    def _run(self, argv: list[str]) -> bytes:
        try:
            result = subprocess.run(
                ["gh", "api", "--method", "GET", *argv],
                capture_output=True,
                timeout=GH_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitHubApiError(f"gh api could not run: {type(exc).__name__}") from exc
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[:200]
            raise GitHubApiError(f"gh api exited {result.returncode}: {detail}")
        return result.stdout

    def get_json(self, path: str, params: Mapping[str, str] | None = None) -> object:
        fields = [
            token for key, value in (params or {}).items() for token in ("-f", f"{key}={value}")
        ]
        body = self._run([path, *fields]).decode("utf-8", errors="replace")
        try:
            return json.loads(body)
        except ValueError as exc:
            raise GitHubApiError(f"gh api returned invalid JSON for {path}") from exc

    def get_bytes(self, path: str) -> bytes:
        return self._run([path])


@dataclass(frozen=True, slots=True)
class Disposition:
    """What happened to one validator's evidence in one run.

    ``state`` is the typed state written for the validator, or empty when the run
    wrote nothing. A verified run whose artifact is unusable is not accepted, and
    still writes an ``UNKNOWN`` record so a sibling run's ``PASS`` cannot hide it.
    """

    validator: str
    run_id: int
    accepted: bool
    reason: str
    state: str = ""

    def line(self) -> str:
        """One log line, built only from validated names and codes."""
        head = f"provenance: {self.validator} run {self.run_id}"
        if self.accepted:
            return f"{head} accepted {self.state}"
        recorded = f" recorded {self.state}" if self.state else ""
        return f"{head} rejected {self.reason}{recorded}"


def paginate(reader: GitHubReader, path: str, key: str, params: Mapping[str, str]) -> list[Any]:
    """Return every item under ``key`` across pages, failing closed on a short read.

    A page limit reached with a full page means more items exist, so the list is
    refused rather than returned truncated.
    """
    items: list[Any] = []
    for page in range(1, MAX_PAGES + 1):
        body = reader.get_json(path, {**params, "per_page": str(PAGE_SIZE), "page": str(page)})
        batch = body.get(key) if isinstance(body, dict) else None
        if not isinstance(batch, list):
            raise GitHubApiError(f"{path} did not return a '{key}' list")
        items.extend(batch)
        if len(batch) < PAGE_SIZE:
            return items
    raise GitHubApiError(f"{path} has more than {MAX_PAGES * PAGE_SIZE} {key}")


def read_evidence_member(archive: bytes, validator: str) -> str:
    """Return the text of the one ``<validator>.json`` member, or raise ``ValueError``."""
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise ValueError("archive is too large")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = bundle.infolist()
            expected = f"{validator}.json"
            if [member.filename for member in members] != [expected]:
                raise ValueError("archive must hold exactly one member named for the validator")
            if members[0].file_size > MAX_EVIDENCE_BYTES:
                raise ValueError("member is too large")
            # zipfile stops a member at its declared size and raises BadZipFile on a
            # mismatch, so the check above bounds what ``read`` can return.
            with bundle.open(members[0]) as handle:
                data = handle.read()
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, zlib.error, EOFError) as exc:
        # zipfile raises NotImplementedError for a compression method it lacks and
        # RuntimeError for an encrypted member, neither of which is a ValueError.
        raise ValueError(f"archive cannot be read: {type(exc).__name__}") from exc
    return data.decode("utf-8")


@dataclass(frozen=True, slots=True)
class _Context:
    reader: GitHubReader
    repo: str
    candidate_sha: str
    default_branch: str
    check_runs: dict[int, Mapping[str, Any]]
    evidence_dir: Path


def _int_id(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_current(artifact: Mapping[str, Any], run: Mapping[str, Any]) -> bool:
    """True when the artifact was created after the latest attempt started.

    A re-run replaces an earlier attempt's artifact (``overwrite: true``), so an
    artifact older than the attempt the check-runs describe belongs to another
    attempt. An equal time cannot tell the attempts apart, so it fails too, as does a missing or
    unparseable one.
    """
    created, started = _instant(artifact.get("created_at")), _instant(run.get("run_started_at"))
    if created is None or started is None:
        return False
    try:
        return created > started
    except TypeError:
        return False


def _artifact_problem(
    ctx: _Context, run: Mapping[str, Any], artifact: Mapping[str, Any]
) -> str | None:
    run_id = run["id"]
    if artifact.get("expired") is not False:
        return REASON_ARTIFACT_EXPIRED
    size = _int_id(artifact.get("size_in_bytes"))
    if size is None or size > MAX_ARCHIVE_BYTES:
        return REASON_ARTIFACT_SIZE
    origin = artifact.get("workflow_run")
    names_run = (
        isinstance(origin, dict)
        and origin.get("id") == run_id
        and origin.get("head_sha") == ctx.candidate_sha
        and _int_id(artifact.get("id")) is not None
    )
    if not names_run:
        return REASON_ARTIFACT_RUN
    return None if _is_current(artifact, run) else REASON_ARTIFACT_STALE


def _select_artifact(
    ctx: _Context, run: Mapping[str, Any], validator: str
) -> tuple[Mapping[str, Any] | None, str]:
    path = f"repos/{ctx.repo}/actions/runs/{run['id']}/artifacts"
    found = paginate(ctx.reader, path, "artifacts", {"name": validator})
    named = [a for a in found if isinstance(a, dict) and a.get("name") == validator]
    if not named:
        return None, REASON_ARTIFACT_ABSENT
    if len(named) > 1:
        return None, REASON_ARTIFACT_AMBIGUOUS
    problem = _artifact_problem(ctx, run, named[0])
    return (None, problem) if problem else (named[0], "")


def _download_record(ctx: _Context, artifact: Mapping[str, Any], validator: str) -> EvidenceRecord:
    """Download one selected artifact and parse it, raising ``ValueError`` if it is not evidence."""
    archive = ctx.reader.get_bytes(f"repos/{ctx.repo}/actions/artifacts/{artifact['id']}/zip")
    if len(archive) != artifact["size_in_bytes"]:
        raise ValueError("the download is not the size its listing reported")
    record = parse_evidence_text(read_evidence_member(archive, validator), f"{validator}.json")
    if record.outcome.validator != validator:
        raise ValueError("the record names a different validator than its artifact")
    if record.outcome.revision != ctx.candidate_sha:
        raise RevisionMismatchError("the record names a commit other than the candidate")
    return record


def _latest_jobs(ctx: _Context, run_id: int) -> list[Mapping[str, Any]]:
    path = f"repos/{ctx.repo}/actions/runs/{run_id}/jobs"
    jobs = paginate(ctx.reader, path, "jobs", {"filter": "latest"})
    return [job for job in jobs if isinstance(job, dict)]


def _write(ctx: _Context, record: EvidenceRecord, run_id: int) -> None:
    document = record.outcome.to_dict()
    if record.digest:
        document["digest"] = record.digest
    if record.items:
        document["items"] = list(record.items)
    ctx.evidence_dir.mkdir(parents=True, exist_ok=True)
    target = ctx.evidence_dir / f"{record.outcome.validator}.{run_id}.json"
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _unusable(ctx: _Context, entry: Applicability, run_id: int, reason: str) -> Disposition:
    """Record ``UNKNOWN`` for a verified run whose artifact cannot be used.

    The run is the right workflow on the right commit, so a validator with no
    usable result there is a finding. Writing it keeps a sibling run's ``PASS``
    from hiding it, since the gate takes the worst of the records it loads.
    """
    outcome = CheckOutcome.unknown(
        entry.validator,
        reason=reason,
        revision=ctx.candidate_sha,
        scope=f"workflow run {run_id}",
        detail="the run passed provenance but its evidence artifact could not be used",
    )
    _write(ctx, EvidenceRecord(outcome=outcome), run_id)
    return Disposition(entry.validator, run_id, False, reason, EvidenceState.UNKNOWN.value)


def _handle_run(ctx: _Context, entry: Applicability, run: Mapping[str, Any]) -> Disposition:
    run_id = _int_id(run.get("id"))
    if run_id is None:
        return Disposition(entry.validator, 0, False, "run.malformed")
    problem = run_problem(
        run,
        candidate_sha=ctx.candidate_sha,
        workflow=entry.workflow,
        default_branch=ctx.default_branch,
    )
    if problem:
        return Disposition(entry.validator, run_id, False, problem)
    artifact, reason = _select_artifact(ctx, run, entry.validator)
    if artifact is None:
        return _unusable(ctx, entry, run_id, reason)
    try:
        record = _download_record(ctx, artifact, entry.validator)
    except RevisionMismatchError:
        return _unusable(ctx, entry, run_id, REASON_ARTIFACT_REVISION)
    except (ValueError, RecursionError):
        return _unusable(ctx, entry, run_id, REASON_ARTIFACT_FORMAT)
    corroboration = corroborate(
        job_name=entry.job,
        run_id=run_id,
        repository=ctx.repo,
        latest_jobs=_latest_jobs(ctx, run_id),
        check_runs=ctx.check_runs,
    )
    written = combine(record, corroboration)
    _write(ctx, written, run_id)
    return Disposition(entry.validator, run_id, True, REASON_ACCEPTED, written.outcome.state.value)


def _check_runs_by_id(reader: GitHubReader, repo: str, sha: str) -> dict[int, Mapping[str, Any]]:
    found = paginate(reader, f"repos/{repo}/commits/{sha}/check-runs", "check_runs", {})
    return {
        identifier: item
        for item in found
        if isinstance(item, dict) and (identifier := _int_id(item.get("id"))) is not None
    }


def fetch_verified_evidence(
    reader: GitHubReader,
    *,
    repo: str,
    candidate_sha: str,
    default_branch: str,
    entries: Sequence[Applicability],
    evidence_dir: Path,
) -> list[Disposition]:
    """Write one evidence file per accepted artifact and return every disposition.

    A validator whose workflow has no passing run writes nothing, so the gate
    counts it missing, and one whose workflow has no run for the candidate gets a
    ``run.absent`` disposition so the log says why. A run that passes provenance
    but has no usable artifact writes an ``UNKNOWN`` record instead (see
    ``_unusable``).

    Raises ``GitHubApiError`` when GitHub cannot answer, and ``ValueError`` for a
    malformed repository, SHA, or branch name.
    """
    if not is_repository_name(repo):
        raise ValueError("repo must be owner/name")
    if not _SHA_RE.fullmatch(candidate_sha):
        raise ValueError("candidate_sha must be a 40-character lowercase SHA")
    if not _BRANCH_RE.fullmatch(default_branch):
        raise ValueError("default_branch is not a plain branch name")
    wanted = [e for e in entries if e.tier == TIER_COMMIT and not e.never]
    if not wanted:
        return []
    runs = paginate(
        reader, f"repos/{repo}/actions/runs", "workflow_runs", {"head_sha": candidate_sha}
    )
    ctx = _Context(
        reader, repo, candidate_sha, default_branch,
        _check_runs_by_id(reader, repo, candidate_sha), evidence_dir,
    )  # fmt: skip
    dispositions: list[Disposition] = []
    for entry in wanted:
        matching = [r for r in runs if isinstance(r, dict) and r.get("path") == entry.workflow]
        if not matching:
            dispositions.append(Disposition(entry.validator, 0, False, REASON_RUN_ABSENT))
        dispositions.extend(_handle_run(ctx, entry, run) for run in matching)
    return dispositions
