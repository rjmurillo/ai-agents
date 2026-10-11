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

RUNS_PER_PAGE = 30
MAX_RUN_PAGES = 4
_ID = re.compile(r"[0-9]{1,20}")


def json_object(raw: bytes) -> dict[str, object]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("expected a JSON object")
    return parsed


def _runs_endpoint(page: int) -> str:
    return (
        f"repos/{CANONICAL_REPO}/actions/workflows/{WORKFLOW_FILE}/runs"
        f"?event=push&branch={MAIN_BRANCH}&per_page={RUNS_PER_PAGE}&page={page}"
    )


def _artifact_in_run(budget: Budget, run: dict[str, object], name: str) -> int | None:
    run_id = str(run["id"])
    if not _ID.fullmatch(run_id):
        return None
    listing = json_object(budget.get(f"repos/{CANONICAL_REPO}/actions/runs/{run_id}/artifacts"))
    return select_artifact_id(listing.get("artifacts"), name)


def find_artifact_id(
    budget: Budget, name: str, repo_root: Path, ancestor: Callable[[Path, str, float], bool]
) -> int | None:
    """Page through main push runs, newest first, until an accepted run has the artifact.

    Every candidate costs a git check and an API call, and all of them draw on
    the one shared ``budget``; when it runs out the lookup raises ``TimeoutError``
    and the caller falls back to the full run. A run without a seed still takes a
    slot, so one page is not enough when several recent seed jobs failed.
    """
    for page in range(1, MAX_RUN_PAGES + 1):
        runs = object_list(json_object(budget.get(_runs_endpoint(page))).get("workflow_runs"))
        for run in runs:
            # Trusted by the run object, then reachable from local origin/main: a
            # push to main whose commit is not in main's history is not accepted.
            if not run_is_trusted(run):
                continue
            if not ancestor(repo_root, str(run["head_sha"]), budget.remaining()):
                continue
            found = _artifact_in_run(budget, run, name)
            if found is not None:
                return found
        if len(runs) < RUNS_PER_PAGE:
            break
    return None
