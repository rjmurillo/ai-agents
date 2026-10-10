"""Seed the local pytest-testmon database from main's CI (issue #6239, ADR-104).

A first pre-push run with no ``.testmondata`` has to run the whole suite to
build one (575 s at 4 workers). The ``testmon-seed`` job in
``.github/workflows/pytest.yml`` builds that database on every push to ``main``
and uploads it as ``testmon-db-<key>``. This module fetches the newest such
artifact so the first local run selects only what changed since main.

Trust. The artifact is an SQLite file that testmon reads and trusts. Anything
that pushes to ``main`` (an administrator who bypasses review included) and any
code that runs inside the seed job can produce one. A poisoned database can only
suppress local selection or exercise SQLite's parser: testmon 2.2.0 has no
pickle, marshal or exec path, and CI still runs every test. This module
therefore:

- lists only runs of ``pytest.yml`` with ``event=push`` on branch ``main``, and
  re-checks on every run object (the query filter is not the check) the event,
  head branch, head repository, ``conclusion == "success"``, the workflow path,
  and a full 40 character head SHA;
- requires that SHA to be an ancestor of local ``origin/main``, and falls back to
  the full run when ``origin/main`` is missing;
- never reads a ``pull_request`` or fork run;
- accepts only an artifact named exactly ``testmon-db-<key>`` for this
  checkout's ``uv.lock`` and ``pyproject.toml`` that is not expired;
- streams the zip into a fresh private directory under a size cap, reads one
  member by the exact name ``.testmondata``, requires the SQLite magic bytes,
  and stages the database through a file opened with O_CREAT|O_EXCL|O_NOFOLLOW.

Every failure falls back to the full run: ``gh`` missing or unauthenticated,
offline, no matching artifact, a timeout, or a bad download. The whole fetch
shares one deadline, ``SEED_FETCH_TIMEOUT_SECONDS``, and runs read-only
``gh api`` GET requests with fixed argument lists (no shell).

The key is computed here and by the workflow's seed job calling
`seed_key`, not by ``hashFiles``: the Actions runtime implements ``hashFiles``
and its exact byte recipe cannot be verified from this checkout, and a key that
differs by one byte would silently disable the seed.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:  # direct file execution puts only this directory first
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.testmon_seed_archive import (  # noqa: E402
    DATABASE_NAME,
    database_from_zip,
    write_database,
)
from scripts.validation.testmon_seed_gh import (  # noqa: E402
    Budget,
    Downloader,
    GhRunner,
    download_to_file,
    run_gh,
)
from scripts.validation.testmon_seed_trust import (  # noqa: E402
    CANONICAL_REPO,
    MAIN_BRANCH,
    WORKFLOW_FILE,
    is_main_ancestor,
    object_list,
    origin_main_present,
    run_is_trusted,
    select_artifact_id,
)

SEED_ARTIFACT_PREFIX = "testmon-db-"
SEED_FETCH_TIMEOUT_SECONDS = 30.0
RUNS_TO_SCAN = 10
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
_KEY_INPUTS = ("uv.lock", "pyproject.toml")
_ID = re.compile(r"[0-9]{1,20}")


@dataclass(frozen=True)
class SeedResult:
    """Outcome of one fetch. ``seeded`` is true only when a database was written."""

    seeded: bool
    detail: str


def seed_key(repo_root: Path) -> str:
    """Return the artifact key for this checkout's dependency inputs.

    A testmon database also records installed package versions and rejects a
    mismatch, so the key only has to separate dependency sets, not Python
    builds. Each input is length-prefixed so two files cannot trade bytes.
    """
    digest = hashlib.sha256()
    for name in _KEY_INPUTS:
        content = (repo_root / name).read_bytes()
        digest.update(f"{name}:{len(content)}:".encode())
        digest.update(content)
    return digest.hexdigest()


def seed_artifact_name(repo_root: Path) -> str:
    return f"{SEED_ARTIFACT_PREFIX}{seed_key(repo_root)}"


def _json_object(raw: bytes) -> dict[str, object]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


def _find_artifact_id(
    budget: Budget, name: str, repo_root: Path, ancestor: Callable[[Path, str], bool]
) -> int | None:
    runs_endpoint = (
        f"repos/{CANONICAL_REPO}/actions/workflows/{WORKFLOW_FILE}/runs"
        f"?event=push&branch={MAIN_BRANCH}&per_page={RUNS_TO_SCAN}"
    )
    runs = object_list(_json_object(budget.get(runs_endpoint)).get("workflow_runs"))
    for run in runs:
        # Trusted by the run object, then reachable from local origin/main: a
        # push to main whose commit is not in main's history is not accepted.
        if not run_is_trusted(run) or not ancestor(repo_root, str(run["head_sha"])):
            continue
        run_id = str(run["id"])
        if not _ID.fullmatch(run_id):
            continue
        listing = _json_object(
            budget.get(f"repos/{CANONICAL_REPO}/actions/runs/{run_id}/artifacts")
        )
        found = select_artifact_id(listing.get("artifacts"), name)
        if found is not None:
            return found
    return None


def _download_and_place(
    repo_root: Path, artifact_id: int, budget: Budget, downloader: Downloader
) -> None:
    """Stream the zip into a fresh private directory, check it, then place the database."""
    workdir = Path(tempfile.mkdtemp(prefix="testmon-seed-"))
    try:
        endpoint = f"repos/{CANONICAL_REPO}/actions/artifacts/{artifact_id}/zip"
        archive = workdir / "seed.zip"
        downloader(endpoint, archive, budget.remaining(), MAX_ARCHIVE_BYTES)
        write_database(repo_root, database_from_zip(archive))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def fetch_seed(
    repo_root: Path,
    *,
    runner: GhRunner = run_gh,
    downloader: Downloader = download_to_file,
    timeout_seconds: float = SEED_FETCH_TIMEOUT_SECONDS,
    gh_available: Callable[[], bool] | None = None,
    has_origin_main: Callable[[Path], bool] = origin_main_present,
    ancestor: Callable[[Path, str], bool] = is_main_ancestor,
) -> SeedResult:
    """Fetch main's newest matching database into ``repo_root``, or say why not.

    Never raises: every failure becomes a ``SeedResult(False, reason)`` and the
    caller runs the full suite. An existing ``.testmondata`` is never replaced.
    """
    available = gh_available or (lambda: shutil.which("gh") is not None)
    if (repo_root / DATABASE_NAME).exists():
        return SeedResult(False, "a local database already exists")
    if not available():
        return SeedResult(False, "gh is not installed")
    if not has_origin_main(repo_root):
        return SeedResult(False, "origin/main is not available locally; run git fetch")
    try:
        name = seed_artifact_name(repo_root)
        budget = Budget(timeout_seconds, runner)
        artifact_id = _find_artifact_id(budget, name, repo_root, ancestor)
        if artifact_id is None:
            return SeedResult(False, f"no main push run has an unexpired {name} artifact")
        _download_and_place(repo_root, artifact_id, budget, downloader)
    except (OSError, ValueError, RuntimeError, TimeoutError, KeyError, zipfile.BadZipFile) as error:
        return SeedResult(False, f"{type(error).__name__}: {error}")
    return SeedResult(True, f"seeded {DATABASE_NAME} from {name}")


def main(argv: list[str]) -> int:
    """Print the key for a checkout; the workflow's seed job names its artifact with it."""
    root = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    print(seed_artifact_name(root))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by the workflow job
    sys.exit(main(sys.argv))
