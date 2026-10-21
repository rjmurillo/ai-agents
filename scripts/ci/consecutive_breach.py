"""Fail a single-sample timing gate only when main breaches twice in a row (issue #6757).

A timing gate that reads one sample from a shared runner fails on noise. The
slow-test budget saw the same module sum to 14.9s and 47.2s on identical code.
The owner decision for #6757, #6796 and #6751 is one policy for all three gates:

* On a pull request the gate warns and never fails.
* On a push to main the gate fails only when the same key breached on the
  previous completed main run too. A first breach warns and is recorded.

This module answers "did the previous completed main run of this workflow also
breach <key>?". Each main run writes a small JSON breach record and uploads it
as the artifact named by :func:`artifact_name`. The next main run lists the
workflow's completed main push runs, takes the newest one before itself, and
downloads that run's record through the GitHub REST API with the workflow token
(``actions: read``).

Unknown prior state fails closed. A missing run, a missing or expired artifact,
a malformed record, or an API failure counts as "the previous run breached", so
a real regression is not hidden behind a lookup problem. The reason is printed.

A gate adopts the policy in three steps: collect its breaches as a key to detail
mapping, call :func:`apply_policy`, and upload the record file that call writes.
Tests inject ``fetch``, so nothing here reaches the network.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import time
import zipfile
import zlib
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from scripts.testing.duration_render import escape_command_data

_T = TypeVar("_T")

SCHEMA_VERSION = 1
RECORD_FILE = "breach-record.json"
ARTIFACT_PREFIX = "breach-record-"
MAIN_BRANCH = "main"
MAIN_REF = f"refs/heads/{MAIN_BRANCH}"
ENFORCED_EVENT = "push"

RUNS_PER_PAGE = 100
MAX_RUN_PAGES = 2
MAX_ZIP_BYTES = 1024 * 1024
MAX_RECORD_BYTES = 256 * 1024
FETCH_TIMEOUT_SECONDS = 30.0
FETCH_ATTEMPTS = 3
FETCH_BACKOFF_SECONDS = 2.0

POLICY_STRICT = "strict"
POLICY_CONSECUTIVE = "consecutive-main"
POLICIES = (POLICY_STRICT, POLICY_CONSECUTIVE)

MODE_STRICT = "strict"
MODE_ADVISORY = "advisory"
MODE_CONSECUTIVE = "consecutive"

Fetch = Callable[[str], bytes]
"""Return the raw body of a GitHub REST ``endpoint``; raise on any failure."""


class PriorStateError(RuntimeError):
    """The previous run's record could not be established."""


def artifact_name(gate: str) -> str:
    """Artifact name a gate's record is uploaded under."""
    return f"{ARTIFACT_PREFIX}{gate}"


@dataclass(frozen=True, slots=True)
class BreachRecord:
    """Keys one gate found over their limit in one main run."""

    gate: str
    run_id: int
    head_sha: str
    breached: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema": SCHEMA_VERSION,
                "gate": self.gate,
                "run_id": self.run_id,
                "head_sha": self.head_sha,
                "breached": sorted(self.breached),
            },
            indent=2,
            sort_keys=True,
        )


def parse_record(raw: bytes, gate: str) -> BreachRecord:
    """Validate a downloaded record. Any deviation raises ``ValueError``."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("record is not a JSON object")
    if data.get("schema") != SCHEMA_VERSION:
        raise ValueError(f"unsupported record schema {data.get('schema')!r}")
    if data.get("gate") != gate:
        raise ValueError(f"record is for gate {data.get('gate')!r}, not {gate!r}")
    run_id, head_sha, breached = data.get("run_id"), data.get("head_sha"), data.get("breached")
    if not isinstance(run_id, int) or isinstance(run_id, bool):
        raise ValueError("run_id is not an integer")
    if not isinstance(head_sha, str):
        raise ValueError("head_sha is not a string")
    if not isinstance(breached, list) or not all(isinstance(k, str) for k in breached):
        raise ValueError("breached is not a list of strings")
    return BreachRecord(gate, run_id, head_sha, tuple(breached))


@dataclass(frozen=True, slots=True)
class PriorLookup:
    """Outcome of looking up the previous completed main run.

    ``record`` is ``None`` when the prior state is unknown; ``reason`` says why.
    """

    record: BreachRecord | None
    reason: str

    @property
    def known(self) -> bool:
        return self.record is not None

    def breached(self, key: str) -> bool:
        """True when ``key`` breached last run, or when that is unknown (fail closed)."""
        return self.record is None or key in self.record.breached


_NO_LOOKUP = PriorLookup(None, "no lookup was made")


def gh_fetch(
    endpoint: str,
    timeout: float = FETCH_TIMEOUT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Read a GitHub REST endpoint through ``gh api``, which follows redirects.

    Fixed argument list, no shell. ``GH_TOKEN`` carries the workflow token. A
    502 or a rate-limit blip would turn a first breach into a red main, so a
    failed call is tried ``FETCH_ATTEMPTS`` times with a short backoff first.
    """
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            return _gh_once(endpoint, timeout)
        except PriorStateError:
            if attempt == FETCH_ATTEMPTS:
                raise
            sleep(FETCH_BACKOFF_SECONDS * attempt)
    raise AssertionError("unreachable")  # pragma: no cover


def _gh_once(endpoint: str, timeout: float) -> bytes:
    try:
        result = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PriorStateError(f"gh api {endpoint} did not run: {exc}") from exc
    if result.returncode != 0:
        tail = result.stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:]
        raise PriorStateError(f"gh api {endpoint} failed: {tail[0] if tail else 'no output'}")
    return result.stdout


def _json_object(raw: bytes, what: str) -> dict[str, object]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{what} is not a JSON object")
    return parsed


def _runs_endpoint(repository: str, workflow: str, page: int) -> str:
    return (
        f"repos/{repository}/actions/workflows/{workflow}/runs"
        f"?event={ENFORCED_EVENT}&branch={MAIN_BRANCH}&status=completed"
        f"&per_page={RUNS_PER_PAGE}&page={page}"
    )


def _previous_run_id(fetch: Fetch, repository: str, workflow: str, current_run_id: int) -> int:
    """Newest completed main push run older than ``current_run_id``."""
    best: int | None = None
    for page in range(1, MAX_RUN_PAGES + 1):
        body = _json_object(fetch(_runs_endpoint(repository, workflow, page)), "runs page")
        runs = body.get("workflow_runs")
        if not isinstance(runs, list):
            raise ValueError("runs page has no workflow_runs list")
        for run in runs:
            if not isinstance(run, dict):
                continue
            run_id = run.get("id")
            if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id >= current_run_id:
                continue
            # The query filters these, and the response is checked again so a
            # run from another branch or event is never taken as main's.
            if run.get("head_branch") != MAIN_BRANCH or run.get("event") != ENFORCED_EVENT:
                continue
            if best is None or run_id > best:
                best = run_id
        if best is not None:
            return best
        if len(runs) < RUNS_PER_PAGE:
            break
    raise PriorStateError(
        f"no completed main push run of {workflow} before run {current_run_id} "
        f"within {MAX_RUN_PAGES} pages"
    )


def _record_bytes(fetch: Fetch, repository: str, run_id: int, gate: str) -> bytes:
    name = artifact_name(gate)
    listing = _json_object(
        fetch(f"repos/{repository}/actions/runs/{run_id}/artifacts?name={name}&per_page=100"),
        "artifact list",
    )
    artifacts = listing.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("artifact list has no artifacts list")
    live = [
        a
        for a in artifacts
        if isinstance(a, dict) and a.get("name") == name and not a.get("expired")
    ]
    if not live:
        raise PriorStateError(f"run {run_id} has no live artifact named {name}")
    artifact_id = live[0].get("id")
    if not isinstance(artifact_id, int) or isinstance(artifact_id, bool):
        raise ValueError("artifact id is not an integer")
    archive = fetch(f"repos/{repository}/actions/artifacts/{artifact_id}/zip")
    if len(archive) > MAX_ZIP_BYTES:
        raise ValueError("record archive is larger than the size cap")
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        members = [i for i in zf.infolist() if Path(i.filename).name == RECORD_FILE]
        if len(members) != 1:
            raise ValueError(f"archive holds {len(members)} files named {RECORD_FILE}")
        if members[0].file_size > MAX_RECORD_BYTES:
            raise ValueError("record is larger than the size cap")
        return zf.read(members[0])


def find_previous_record(
    fetch: Fetch, *, repository: str, workflow: str, gate: str, current_run_id: int
) -> PriorLookup:
    """Load the previous completed main run's breach record, never raising.

    Every expected failure becomes an unknown :class:`PriorLookup` whose
    ``breached`` answers True for every key.
    """
    try:
        run_id = _previous_run_id(fetch, repository, workflow, current_run_id)
        record = parse_record(_record_bytes(fetch, repository, run_id, gate), gate)
        if record.run_id != run_id:
            raise ValueError(f"record names run {record.run_id}, not the selected run {run_id}")
    except (
        PriorStateError,
        ValueError,
        OSError,
        KeyError,
        EOFError,
        zlib.error,
        NotImplementedError,
        RuntimeError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
    ) as exc:
        return PriorLookup(None, f"{type(exc).__name__}: {exc}")
    return PriorLookup(record, f"run {run_id}")


@dataclass(frozen=True, slots=True)
class Policy:
    """How one gate turns breaches into a verdict for the run it is in."""

    name: str = POLICY_STRICT
    event: str | None = None
    ref: str | None = None
    run_id: int | None = None
    sha: str = "unknown"
    repository: str | None = None
    workflow: str | None = None
    record_out: Path | None = None

    @property
    def mode(self) -> str:
        if self.name == POLICY_STRICT:
            return MODE_STRICT
        if self.event == ENFORCED_EVENT and self.ref == MAIN_REF:
            return MODE_CONSECUTIVE
        return MODE_ADVISORY


@dataclass(frozen=True, slots=True)
class Verdict:
    """Breaches split by consequence. ``failing`` non-empty means exit 1."""

    failing: tuple[str, ...] = ()
    warning: tuple[str, ...] = ()


def annotation(level: str, title: str, message: str) -> str:
    """One GitHub Actions workflow command line."""
    # A property value also ends at ":" and ",", which the message does not.
    prop = escape_command_data(title).replace(":", "%3A").replace(",", "%2C")
    return f"::{level} title={prop}::{escape_command_data(message)}"


def apply_policy(
    gate: str,
    breaches: Mapping[str, str],
    policy: Policy,
    fetch: Fetch | None = None,
    *,
    title: str | None = None,
) -> Verdict:
    """Decide and report. Writes the record on a main run, before returning.

    ``breaches`` maps each breached key to a one-line detail. Annotations go to
    stdout, where the Actions runner reads them.
    """
    label = title or gate
    fetch = gh_fetch if fetch is None else fetch
    keys = sorted(breaches)
    mode = policy.mode
    lookup = _NO_LOOKUP
    if mode == MODE_CONSECUTIVE and keys:
        lookup = find_previous_record(
            fetch,
            repository=_required(policy.repository, "repository"),
            workflow=_required(policy.workflow, "workflow"),
            gate=gate,
            current_run_id=_required(policy.run_id, "run id"),
        )
    failing: list[str] = []
    warning: list[str] = []
    for key in keys:
        if mode == MODE_STRICT or (mode == MODE_CONSECUTIVE and lookup.breached(key)):
            failing.append(key)
        else:
            warning.append(key)
    # Strict mode is the pre-policy contract: the caller's own stderr lines
    # report the overrun, so no workflow annotation is added.
    if mode != MODE_STRICT:
        for key in warning:
            print(annotation("warning", label, _warning_text(key, breaches[key], mode)))
        for key in failing:
            print(annotation("error", label, _failure_text(key, breaches[key], lookup)))
    # After the annotations, so an unwritable record never hides a real breach.
    if mode == MODE_CONSECUTIVE:
        _write_record(policy, gate, keys)
    return Verdict(tuple(failing), tuple(warning))


def _warning_text(key: str, detail: str, mode: str) -> str:
    if mode == MODE_ADVISORY:
        return f"{key}: {detail}. Advisory on this event; only a push to main can fail."
    return f"{key}: {detail}. First breach on main; the previous main run did not breach it."


def _failure_text(key: str, detail: str, lookup: PriorLookup) -> str:
    if lookup.known:
        return f"{key}: {detail}. Breached on {lookup.reason} too, two main runs in a row."
    return f"{key}: {detail}. Previous main run unknown ({lookup.reason}); failing closed."


def _required(value: _T | None, what: str) -> _T:
    if value is None or value == "":
        raise ValueError(f"the consecutive-main policy needs the {what}")
    return value


def _write_record(policy: Policy, gate: str, keys: Sequence[str]) -> None:
    if policy.record_out is None:
        raise ValueError("the consecutive-main policy needs --breach-record-out")
    record = BreachRecord(gate, _required(policy.run_id, "run id"), policy.sha, tuple(keys))
    policy.record_out.parent.mkdir(parents=True, exist_ok=True)
    policy.record_out.write_text(record.to_json() + "\n", encoding="utf-8")


def add_policy_arguments(
    parser: argparse.ArgumentParser, *, already_defined: Collection[str] = ()
) -> None:
    """Register the flags every gate shares. Defaults read the Actions environment.

    A gate that already owns some of these flags with the same meaning, such as
    ``--event``, ``--ref`` and ``--sha`` on the duration trend, names them in
    ``already_defined`` so argparse does not see a duplicate.
    """
    group = parser.add_argument_group("breach policy (issues #6757, #6796, #6751)")
    group.add_argument(
        "--breach-policy",
        choices=POLICIES,
        default=POLICY_STRICT,
        help="strict fails on any breach (default). consecutive-main warns on pull "
        "requests and fails on main only after two main runs in a row breach. Only a "
        "push to refs/heads/main is enforced; any other event or ref warns.",
    )
    if "--event" not in already_defined:
        group.add_argument("--event", help="Event name (default: GITHUB_EVENT_NAME).")
    if "--ref" not in already_defined:
        group.add_argument("--ref", help="Ref (default: GITHUB_REF).")
    group.add_argument("--run-id", type=int, help="Run id (default: GITHUB_RUN_ID).")
    if "--sha" not in already_defined:
        group.add_argument("--sha", help="Commit SHA (default: GITHUB_SHA).")
    group.add_argument("--repository", help="owner/repo (default: GITHUB_REPOSITORY).")
    group.add_argument("--workflow", help="Workflow file name, e.g. pytest.yml.")
    group.add_argument(
        "--breach-record-out",
        type=Path,
        metavar="PATH",
        help=f"Where a main run writes its record. The file must be named {RECORD_FILE}.",
    )


def policy_from_args(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> Policy:
    """Build a :class:`Policy`. Raises ``ValueError`` when the flags are unusable."""
    env = os.environ if env is None else env
    name = args.breach_policy
    if name == POLICY_STRICT:
        return Policy()
    raw_run_id = args.run_id if args.run_id is not None else env.get("GITHUB_RUN_ID")
    try:
        run_id = int(raw_run_id) if raw_run_id not in (None, "") else None
    except ValueError as exc:
        raise ValueError(f"run id {raw_run_id!r} is not an integer") from exc
    policy = Policy(
        name=name,
        event=args.event or env.get("GITHUB_EVENT_NAME"),
        ref=args.ref or env.get("GITHUB_REF"),
        run_id=run_id,
        sha=args.sha or env.get("GITHUB_SHA") or "unknown",
        repository=args.repository or env.get("GITHUB_REPOSITORY"),
        workflow=args.workflow,
        record_out=args.breach_record_out,
    )
    if policy.event is None or policy.ref is None:
        raise ValueError("the consecutive-main policy needs the event and the ref")
    if policy.mode == MODE_CONSECUTIVE:
        _required(policy.run_id, "run id")
        _required(policy.repository, "repository")
        _required(policy.workflow, "workflow (--workflow)")
        if policy.record_out is None or policy.record_out.name != RECORD_FILE:
            raise ValueError(f"--breach-record-out must name a file called {RECORD_FILE}")
    return policy
