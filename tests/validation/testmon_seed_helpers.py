"""Shared fakes for the testmon seed tests (issue #6239).

The name does not match `test_*.py`, so pytest never walks it.
"""

from __future__ import annotations

import io
import json
import subprocess
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from scripts.validation import testmon_seed as seed
from scripts.validation.testmon_seed_archive import SQLITE_MAGIC

REPO = seed.CANONICAL_REPO
DATABASE = SQLITE_MAGIC + b"rest-of-file"


def write_inputs(root: Path, lock: str = "lock-v1", project: str = "project-v1") -> None:
    (root / "uv.lock").write_text(lock, encoding="utf-8")
    (root / "pyproject.toml").write_text(project, encoding="utf-8")


def make_zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def make_run(run_id: int, **overrides: object) -> dict:
    """A trusted run object (successful push to main); overrides replace fields."""
    run: dict[str, object] = {
        "id": run_id,
        "event": "push",
        "head_branch": "main",
        "head_repository": {"full_name": REPO},
        "conclusion": "success",
        "path": ".github/workflows/pytest.yml",
        "head_sha": f"{run_id:040x}",
    }
    return run | overrides


def artifact_entry(root: Path, **overrides: object) -> dict:
    entry: dict[str, object] = {"id": 900, "name": seed.seed_artifact_name(root), "expired": False}
    return entry | overrides


def make_routes(runs: list[dict], artifacts: dict[int, list[dict]]) -> dict:
    """Endpoint-substring routes: the run list and each run's artifacts."""
    routes: dict[str, bytes | int] = {
        "/workflows/pytest.yml/runs": json.dumps({"workflow_runs": runs}).encode()
    }
    for run_id, listing in artifacts.items():
        routes[f"/runs/{run_id}/artifacts"] = json.dumps({"artifacts": listing}).encode()
    return routes


@dataclass
class FakeGh:
    """A `gh api` stand-in keyed by endpoint substring; records every endpoint."""

    routes: dict[str, bytes | int]
    calls: list[str] = field(default_factory=list)
    downloads: list[Path] = field(default_factory=list)
    zip_bytes: bytes = b""

    def __call__(self, args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(args[0])
        for needle, payload in self.routes.items():
            if needle in args[0]:
                if isinstance(payload, int):
                    return subprocess.CompletedProcess(args, payload, b"", b"gh: not logged in")
                return subprocess.CompletedProcess(args, 0, payload, b"")
        return subprocess.CompletedProcess(args, 1, b"", b"gh: HTTP 404")

    def download(self, endpoint: str, destination: Path, timeout: float, max_bytes: int) -> None:
        self.calls.append(endpoint)
        destination.write_bytes(self.zip_bytes)
        self.downloads.append(destination)

    def fetch(
        self,
        root: Path,
        ancestor: Callable[[Path, str, float], bool] = lambda _root, _sha, _t: True,
        has_origin_main: Callable[[Path, float], bool] = lambda _root, _t: True,
        timeout_seconds: float = 30.0,
    ) -> seed.SeedResult:
        return seed.fetch_seed(
            root,
            runner=self,
            downloader=self.download,
            gh_available=lambda: True,
            has_origin_main=has_origin_main,
            ancestor=ancestor,
            timeout_seconds=timeout_seconds,
        )
