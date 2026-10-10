"""Which GitHub Actions runs and artifacts may seed the testmon database (issue #6239).

The artifact is an SQLite file testmon trusts, so it must come from a `push` run
on `main` of the canonical repository, never from a pull request or a fork.
`scripts/validation/testmon_seed.py` documents the whole trust model.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

GIT_TIMEOUT_SECONDS = 10.0
_FULL_SHA = re.compile(r"[0-9a-f]{40}")
ORIGIN_MAIN_REF = "refs/remotes/origin/main"
WORKFLOW_PATH = ".github/workflows/pytest.yml"
CANONICAL_REPO = "rjmurillo/ai-agents"
WORKFLOW_FILE = "pytest.yml"
MAIN_BRANCH = "main"


def object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def run_is_trusted(run: dict[str, object]) -> bool:
    """True only for a successful push to ``main`` of the canonical repository.

    Checks the run object itself, not the query that found it, so a changed or
    ignored query parameter cannot admit a pull request run. The run must also
    be this workflow file (`path`), have concluded `success`, and carry a full
    lowercase `head_sha` so the caller can check it against local history.
    """
    head_repo = run.get("head_repository")
    repo_name = head_repo.get("full_name") if isinstance(head_repo, dict) else None
    sha = run.get("head_sha")
    return (
        run.get("event") == "push"
        and run.get("head_branch") == MAIN_BRANCH
        and repo_name == CANONICAL_REPO
        and run.get("conclusion") == "success"
        and run.get("path") == WORKFLOW_PATH
        and isinstance(sha, str)
        and _FULL_SHA.fullmatch(sha) is not None
        and isinstance(run.get("id"), int)
    )


def _git_succeeds(repo_root: Path, *args: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def origin_main_present(repo_root: Path) -> bool:
    """True when the local clone has an ``origin/main`` to check ancestry against."""
    return _git_succeeds(repo_root, "rev-parse", "--verify", "--quiet", ORIGIN_MAIN_REF)


def is_main_ancestor(repo_root: Path, sha: str) -> bool:
    """True when ``sha`` is an ancestor of local ``origin/main``.

    An unknown commit (not fetched yet) and a malformed value are both False, so
    the caller skips that run and tries an older one rather than trusting it.
    """
    if _FULL_SHA.fullmatch(sha) is None:
        return False
    return _git_succeeds(repo_root, "merge-base", "--is-ancestor", sha, ORIGIN_MAIN_REF)


def select_artifact_id(artifacts: object, name: str) -> int | None:
    """Return the id of the unexpired artifact called exactly ``name``, or None."""
    for artifact in object_list(artifacts):
        artifact_id = artifact.get("id")
        if (
            artifact.get("name") == name
            and artifact.get("expired") is False
            and isinstance(artifact_id, int)
        ):
            return artifact_id
    return None
