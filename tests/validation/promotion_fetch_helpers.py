"""Fixtures for the promotion evidence fetch tests: a fake GitHub reader and payload builders."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Mapping
from typing import Any

from scripts.validation.promotion_applicability import Applicability

SHA = "a" * 40
REPO = "owner/repo"
RUN = 900
JOB = 5001
APP = 15368
WORKFLOW = ".github/workflows/pytest.yml"


def _entry(
    validator: str = "run_python_tests", job: str = "Run Python Tests", tier: str = "commit"
):
    return Applicability(validator, tier, WORKFLOW, job, ("always",), "test row")


def _zip(name: str, text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(name, text)
    return buffer.getvalue()


def _evidence(validator: str = "run_python_tests", state: str = "PASS", revision: str = SHA) -> str:
    document: dict[str, Any] = {
        "validator": validator,
        "state": state,
        "revision": revision,
        "scope": "job x",
    }
    if state == "PASS":
        document["findings"] = 0
    else:
        document["reason"] = "job.failed"
    return json.dumps(document)


class FakeReader:
    """Answers from canned payloads and records every path requested."""

    def __init__(self, runs: list[dict[str, Any]], **fixtures: Any) -> None:
        self.runs = runs
        self.artifacts: dict[str, list[dict[str, Any]]] = fixtures.get("artifacts", {})
        self.jobs: list[dict[str, Any]] = fixtures.get("jobs", [])
        self.checks: list[dict[str, Any]] = fixtures.get("checks", [])
        self.archives: dict[int, bytes] = fixtures.get("archives", {})
        self.calls: list[str] = []

    def get_json(self, path: str, params: Mapping[str, str] | None = None) -> object:
        self.calls.append(path)
        if path.endswith("/actions/runs"):
            return {"workflow_runs": self.runs}
        if path.endswith("/artifacts"):
            return {"artifacts": self._listed((params or {}).get("name", ""))}
        if path.endswith("/jobs"):
            return {"jobs": self.jobs}
        if path.endswith("/check-runs"):
            return {"check_runs": self.checks}
        raise AssertionError(f"unexpected path {path}")

    def _listed(self, name: str) -> list[Any]:
        """Artifacts for ``name``, with ``"auto"`` sizes resolved to the archive length."""
        listed = []
        for item in self.artifacts.get(name, []):
            if isinstance(item, dict) and item.get("size_in_bytes") == "auto":
                identifier = item.get("id")
                archive = self.archives.get(identifier, b"") if isinstance(identifier, int) else b""
                item = {**item, "size_in_bytes": len(archive)}
            listed.append(item)
        return listed

    def get_bytes(self, path: str) -> bytes:
        self.calls.append(path)
        return self.archives[int(path.split("/")[-2])]


def _run(**overrides: Any) -> dict[str, Any]:
    run = {
        "id": RUN, "status": "completed", "head_sha": SHA, "event": "push", "path": WORKFLOW,
        "run_started_at": "2026-10-01T10:00:00Z",
        "head_branch": "main", "repository": {"id": 7}, "head_repository": {"id": 7},
    }  # fmt: skip
    run.update(overrides)
    return run


def _artifact(**overrides: Any) -> dict[str, Any]:
    artifact = {
        "id": 77, "name": "run_python_tests", "expired": False, "size_in_bytes": "auto",
        "created_at": "2026-10-01T10:05:00Z",
        "workflow_run": {"id": RUN, "head_sha": SHA},
    }  # fmt: skip
    artifact.update(overrides)
    return artifact


def _good(**overrides: Any) -> FakeReader:
    fixtures: dict[str, Any] = {
        "artifacts": {"run_python_tests": [_artifact()]},
        "jobs": [{"id": JOB, "name": "Run Python Tests", "run_id": RUN, "status": "completed"}],
        "checks": [
            {
                "id": JOB, "name": "Run Python Tests", "status": "completed",
                "conclusion": "success", "app": {"id": APP},
                "details_url": f"https://github.com/{REPO}/actions/runs/{RUN}/job/{JOB}",
            }
        ],
        "archives": {77: _zip("run_python_tests.json", _evidence())},
    }  # fmt: skip
    fixtures.update(overrides)
    return FakeReader([_run()], **fixtures)
