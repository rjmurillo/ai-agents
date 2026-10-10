"""Seed the local pytest-testmon database from main's CI (issue #6239, ADR-104).

A first pre-push run with no ``.testmondata`` has to run the whole suite to
build one (575 s at 4 workers). The ``testmon-seed`` job in
``.github/workflows/pytest.yml`` builds that database on every push to ``main``
and uploads it as ``testmon-db-<key>``. This module fetches the newest such
artifact so the first local run selects only what changed since main.

Trust. The artifact is an SQLite file that testmon reads and trusts, so it must
come only from code that passed review on ``main``. This module therefore:

- lists only runs of ``pytest.yml`` with ``event=push`` on branch ``main`` of
  the canonical repository, and re-checks ``event``, ``head_branch`` and
  ``head_repository`` on every run it accepts (the query filter is not the
  check);
- never reads a ``pull_request`` or fork run;
- accepts only an artifact named exactly ``testmon-db-<key>`` for this
  checkout's ``uv.lock`` and ``pyproject.toml`` that is not expired;
- writes only a file that starts with the SQLite magic bytes, from one exact
  zip member name, never a path taken from the archive.

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
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CANONICAL_REPO = "rjmurillo/ai-agents"
WORKFLOW_FILE = "pytest.yml"
MAIN_BRANCH = "main"
SEED_ARTIFACT_PREFIX = "testmon-db-"
DATABASE_NAME = ".testmondata"
SEED_FETCH_TIMEOUT_SECONDS = 30.0
RUNS_TO_SCAN = 10
MAX_DATABASE_BYTES = 512 * 1024 * 1024
SQLITE_MAGIC = b"SQLite format 3\x00"
_KEY_INPUTS = ("uv.lock", "pyproject.toml")
_ID = re.compile(r"[0-9]{1,20}")

GhRunner = Callable[[list[str], float], "subprocess.CompletedProcess[bytes]"]


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


def _run_gh(args: list[str], timeout_seconds: float) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["gh", "api", *args],
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )


class _Budget:
    """One shared deadline for every request in a fetch."""

    def __init__(self, seconds: float, runner: GhRunner) -> None:
        self._deadline = time.monotonic() + seconds
        self._runner = runner

    def get(self, endpoint: str) -> bytes:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("seed fetch deadline passed")
        try:
            result = self._runner([endpoint], remaining)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("gh api timed out") from error
        if result.returncode != 0:
            tail = result.stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:]
            raise RuntimeError(f"gh api failed: {tail[0] if tail else 'no output'}")
        return result.stdout


def _json_object(raw: bytes) -> dict[str, object]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


def _object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def run_is_trusted(run: dict[str, object]) -> bool:
    """True only for a push to ``main`` of the canonical repository.

    Checks the run object itself, not the query that found it, so a changed or
    ignored query parameter cannot admit a pull request run.
    """
    head_repo = run.get("head_repository")
    repo_name = head_repo.get("full_name") if isinstance(head_repo, dict) else None
    return (
        run.get("event") == "push"
        and run.get("head_branch") == MAIN_BRANCH
        and repo_name == CANONICAL_REPO
        and isinstance(run.get("id"), int)
    )


def select_artifact_id(artifacts: object, name: str) -> int | None:
    """Return the id of the unexpired artifact called exactly ``name``, or None."""
    for artifact in _object_list(artifacts):
        artifact_id = artifact.get("id")
        if (
            artifact.get("name") == name
            and artifact.get("expired") is False
            and isinstance(artifact_id, int)
        ):
            return artifact_id
    return None


def _find_artifact_id(budget: _Budget, name: str) -> int | None:
    runs_endpoint = (
        f"repos/{CANONICAL_REPO}/actions/workflows/{WORKFLOW_FILE}/runs"
        f"?event=push&branch={MAIN_BRANCH}&per_page={RUNS_TO_SCAN}"
    )
    runs = _object_list(_json_object(budget.get(runs_endpoint)).get("workflow_runs"))
    for run in runs:
        if not run_is_trusted(run):
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


def _database_from_zip(payload: bytes) -> bytes:
    """Read the one expected member by exact name; reject anything else."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        info = archive.getinfo(DATABASE_NAME)
        if info.file_size > MAX_DATABASE_BYTES:
            raise ValueError("database larger than the size cap")
        data = archive.read(info)
    if not data.startswith(SQLITE_MAGIC):
        raise ValueError("artifact is not an SQLite database")
    return data


def _write_database(repo_root: Path, data: bytes) -> None:
    target = repo_root / DATABASE_NAME
    partial = repo_root / f"{DATABASE_NAME}.seed.{os.getpid()}.tmp"
    try:
        partial.write_bytes(data)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def fetch_seed(
    repo_root: Path,
    *,
    runner: GhRunner = _run_gh,
    timeout_seconds: float = SEED_FETCH_TIMEOUT_SECONDS,
    gh_available: Callable[[], bool] | None = None,
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
    try:
        name = seed_artifact_name(repo_root)
        budget = _Budget(timeout_seconds, runner)
        artifact_id = _find_artifact_id(budget, name)
        if artifact_id is None:
            return SeedResult(False, f"no main push run has an unexpired {name} artifact")
        payload = budget.get(f"repos/{CANONICAL_REPO}/actions/artifacts/{artifact_id}/zip")
        _write_database(repo_root, _database_from_zip(payload))
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
