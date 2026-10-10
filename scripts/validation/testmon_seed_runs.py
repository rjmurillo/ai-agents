"""Find the newest trusted main push run that has this checkout's seed artifact (issue #6239).

`scripts/validation/testmon_seed.py` documents the trust model.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from scripts.validation.testmon_seed_gh import Budget
from scripts.validation.testmon_seed_trust import (
    CANONICAL_REPO,
    MAIN_BRANCH,
    WORKFLOW_FILE,
    object_list,
    run_is_trusted,
    select_artifact_id,
)

RUNS_TO_SCAN = 10
_ID = re.compile(r"[0-9]{1,20}")


def json_object(raw: bytes) -> dict[str, object]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


def find_artifact_id(
    budget: Budget, name: str, repo_root: Path, ancestor: Callable[[Path, str], bool]
) -> int | None:
    runs_endpoint = (
        f"repos/{CANONICAL_REPO}/actions/workflows/{WORKFLOW_FILE}/runs"
        f"?event=push&branch={MAIN_BRANCH}&per_page={RUNS_TO_SCAN}"
    )
    runs = object_list(json_object(budget.get(runs_endpoint)).get("workflow_runs"))
    for run in runs:
        # Trusted by the run object, then reachable from local origin/main: a
        # push to main whose commit is not in main's history is not accepted.
        if not run_is_trusted(run) or not ancestor(repo_root, str(run["head_sha"])):
            continue
        run_id = str(run["id"])
        if not _ID.fullmatch(run_id):
            continue
        listing = json_object(budget.get(f"repos/{CANONICAL_REPO}/actions/runs/{run_id}/artifacts"))
        found = select_artifact_id(listing.get("artifacts"), name)
        if found is not None:
            return found
    return None
