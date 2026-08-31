"""Shared CLI-level helpers for the bulk cancellation guard tests (issue #4835).

Split out of ``tests/ci/test_bulk_cancel_guard.py`` when that file crossed the
500-line taste ceiling. Both that module and
``tests/ci/test_bulk_cancel_guard_replay.py`` drive the same CLI, so the
workflow-corpus writers live here rather than being duplicated.

Plain helpers only. The pytest fixtures built on them (``workflows``,
``workflows_missing_reopened``, and the default-manifest redirect) live in
``tests/ci/conftest.py``, because importing a fixture into a test module makes
every test that names it as a parameter shadow the imported symbol.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.ci.bulk_cancel_fixtures import (
    OPTIONAL_WORKFLOW,
    REQUIRED_WORKFLOW,
    SECOND_REQUIRED_WORKFLOW,
)

HEALTHY_TYPES = {
    REQUIRED_WORKFLOW: ["opened", "synchronize", "reopened"],
    SECOND_REQUIRED_WORKFLOW: ["opened", "synchronize", "reopened"],
    OPTIONAL_WORKFLOW: ["opened", "synchronize", "reopened"],
}
REOPEN_OMITTED_TYPES = dict(
    HEALTHY_TYPES, **{REQUIRED_WORKFLOW: ["opened", "synchronize"]}
)


def write_workflows(
    directory: Path,
    types: dict[str, list[str]],
    *,
    paths: list[str] | None = None,
) -> Path:
    """Materialize one workflow file per name with the given PR activity types.

    ``jobs`` is written empty on purpose. The planner unions the API-derived
    contexts with the ones the workflow file declares, so a populated jobs block
    would change what every pre-existing case scores; a case that wants the
    static union opts in by declaring jobs itself.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for index, (name, pr_types) in enumerate(types.items()):
        trigger: dict[str, object] = {"types": list(pr_types)}
        if paths is not None:
            trigger["paths"] = list(paths)
        body = {"name": name, "on": {"pull_request": trigger}, "jobs": {}}
        (directory / f"wf{index}.yml").write_text(json.dumps(body), encoding="utf-8")
    return directory


def write_runs(path: Path, runs) -> Path:
    """Serialize run records into the CLI's --runs-file shape."""
    path.write_text(
        json.dumps(
            [
                {
                    "run_id": run.run_id,
                    "workflow_name": run.workflow_name,
                    "pr_number": run.pr_number,
                    "branch": run.branch,
                    "event": run.event,
                    "status": run.status,
                    "contexts": list(run.contexts),
                }
                for run in runs
            ]
        ),
        encoding="utf-8",
    )
    return path


def argv(runs_file: Path, workflows_dir: Path, *extra: str) -> list[str]:
    """Build the argument vector every CLI case starts from."""
    return [
        "--runs-file",
        str(runs_file),
        "--workflows-dir",
        str(workflows_dir),
        *extra,
    ]
