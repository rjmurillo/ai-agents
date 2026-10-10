"""Which runs and artifacts may seed the database (issue #6239)."""

from __future__ import annotations

import pytest

from scripts.validation.testmon_seed_trust import run_is_trusted, select_artifact_id
from tests.validation.testmon_seed_helpers import make_run

_NO_REPO = {k: v for k, v in make_run(1).items() if k != "head_repository"}
_NO_ID = {k: v for k, v in make_run(1).items() if k != "id"}


def test_a_successful_push_to_main_of_the_canonical_repo_is_trusted() -> None:
    assert run_is_trusted(make_run(1))


@pytest.mark.parametrize(
    "run",
    [
        make_run(1, event="pull_request"),
        make_run(1, event="merge_group"),
        make_run(1, event="workflow_dispatch"),
        make_run(1, head_branch="feature/x"),
        make_run(1, head_branch="main-evil"),
        make_run(1, head_repository={"full_name": "attacker/ai-agents"}),
        make_run(1, conclusion="failure"),
        make_run(1, conclusion="cancelled"),
        make_run(1, conclusion=None),
        make_run(1, path=".github/workflows/evil.yml"),
        make_run(1, path=".github/workflows/pytest.yml@refs/heads/x"),
        make_run(1, head_sha="abc"),
        make_run(1, head_sha="A" * 40),
        make_run(1, head_sha=None),
        make_run(1, id="1"),
        _NO_REPO,
        _NO_ID,
    ],
)
def test_everything_else_is_refused(run: dict) -> None:
    assert not run_is_trusted(run)


def test_exact_name_match_wins() -> None:
    artifacts = [
        {"id": 1, "name": "testmon-db-other", "expired": False},
        {"id": 2, "name": "testmon-db-key", "expired": False},
    ]
    assert select_artifact_id(artifacts, "testmon-db-key") == 2


@pytest.mark.parametrize(
    "artifacts",
    [
        [{"id": 1, "name": "testmon-db-key-extra", "expired": False}],
        [{"id": 2, "name": "x-testmon-db-key", "expired": False}],
        [{"id": 3, "name": "testmon-db-key", "expired": True}],
        [{"id": 4, "name": "testmon-db-key", "expired": None}],
        [{"id": 5, "name": "testmon-db-key", "expired": "false"}],
        None,
        "x",
        3,
        [{"id": 6}],
        [None, "x"],
    ],
)
def test_prefix_expired_or_malformed_entries_select_nothing(artifacts: object) -> None:
    assert select_artifact_id(artifacts, "testmon-db-key") is None
