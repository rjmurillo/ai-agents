"""Which GitHub Actions runs and artifacts may seed the testmon database (issue #6239).

The artifact is an SQLite file testmon trusts, so it must come from a `push` run
on `main` of the canonical repository, never from a pull request or a fork.
`scripts/validation/testmon_seed.py` documents the whole trust model.
"""

from __future__ import annotations

CANONICAL_REPO = "rjmurillo/ai-agents"
WORKFLOW_FILE = "pytest.yml"
MAIN_BRANCH = "main"


def object_list(value: object) -> list[dict[str, object]]:
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
    for artifact in object_list(artifacts):
        artifact_id = artifact.get("id")
        if (
            artifact.get("name") == name
            and artifact.get("expired") is False
            and isinstance(artifact_id, int)
        ):
            return artifact_id
    return None
