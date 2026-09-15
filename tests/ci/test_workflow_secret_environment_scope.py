"""Every stored-secret consumer must declare a GitHub environment.

ADR-101 Phase 0 item 1 (issue #5244). The exit condition there is not "the
named consumers are contained" but that no repository-level secret remains
which a pushed branch could reference. Environment-scoped secrets reach only
jobs that name their environment, so a job reading a stored secret without an
``environment:`` key loses access the moment the repository-level copy is
deleted, and silently keeps working until then.

The secret set is DERIVED from the workflows rather than hard-coded. A
hand-written inventory is what failed during this migration: the first pass
enumerated ``BOT_PAT`` consumers and missed ``COPILOT_GITHUB_TOKEN``, leaving
the nightly smoke job about to run unauthenticated. Deriving the set means a
newly introduced secret is covered the day it appears.

``GITHUB_TOKEN`` is excluded because it is minted per run by Actions rather
than stored on the repository, so it has nothing to migrate and no
environment to declare.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

SECRET_REF = re.compile(r"secrets\.([A-Z_][A-Z0-9_]*)")

# Minted per run by Actions, not stored on the repository.
NOT_STORED: frozenset[str] = frozenset({"GITHUB_TOKEN"})


def workflow_paths() -> list[Path]:
    return sorted(WORKFLOW_DIR.glob("*.yml"))


def stored_secrets() -> set[str]:
    """Every secret named by any workflow, minus the per-run token."""
    found: set[str] = set()
    for path in workflow_paths():
        found.update(SECRET_REF.findall(path.read_text(encoding="utf-8")))
    return found - set(NOT_STORED)


def jobs_reaching(path: Path, secret: str) -> dict[str, str | None]:
    """Jobs that can read ``secret``, mapped to their declared environment.

    A workflow-level ``env:`` block puts the secret in scope for every job in
    the file, so reachability is not answerable from the job body alone. That
    is how three of this repository's jobs reach their token.
    """
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    jobs = {j: b for j, b in (data.get("jobs") or {}).items() if isinstance(b, dict)}
    preamble = text.split("\njobs:")[0]
    workflow_level = f"secrets.{secret}" in preamble
    reaching: dict[str, str | None] = {}
    for job_id, body in jobs.items():
        if workflow_level or f"secrets.{secret}" in yaml.safe_dump(body):
            reaching[job_id] = body.get("environment")
    return reaching


def unscoped_consumers() -> list[str]:
    """Every ``workflow:job`` reading a stored secret with no environment."""
    offenders: list[str] = []
    for secret in sorted(stored_secrets()):
        for path in workflow_paths():
            if f"secrets.{secret}" not in path.read_text(encoding="utf-8"):
                continue
            for job_id, environment in jobs_reaching(path, secret).items():
                if not environment:
                    offenders.append(f"{path.name}:{job_id} reads {secret}")
    return sorted(set(offenders))


def test_every_stored_secret_consumer_declares_an_environment() -> None:
    """Positive: no job reads a stored secret without an environment."""
    offenders = unscoped_consumers()
    assert not offenders, "unscoped stored-secret consumers:\n" + "\n".join(offenders)


def test_the_derived_secret_set_is_not_empty() -> None:
    """Guard: an empty set would make the check above vacuously pass.

    Distinguishes "zero violations across a real corpus" from "zero violations
    because nothing was examined".
    """
    secrets = stored_secrets()
    assert secrets, "derived no stored secrets; the scan found nothing to check"
    assert "GITHUB_TOKEN" not in secrets


def test_workflow_level_env_counts_as_reaching(tmp_path: Path) -> None:
    """Edge: a workflow-level env block puts the secret in every job's scope."""
    wf = tmp_path / "w.yml"
    wf.write_text(
        "name: x\non: push\nenv:\n  TOKEN: ${{ secrets.EXAMPLE_TOKEN }}\n"
        "jobs:\n  a:\n    runs-on: ubuntu-latest\n    steps: []\n",
        encoding="utf-8",
    )
    assert jobs_reaching(wf, "EXAMPLE_TOKEN") == {"a": None}


def test_a_job_body_reference_counts_as_reaching(tmp_path: Path) -> None:
    """Positive: a step-level reference is detected and its environment read."""
    wf = tmp_path / "w.yml"
    wf.write_text(
        "name: x\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        "    environment: bot-secrets\n    steps:\n"
        "      - run: echo\n        env:\n          T: ${{ secrets.EXAMPLE_TOKEN }}\n",
        encoding="utf-8",
    )
    assert jobs_reaching(wf, "EXAMPLE_TOKEN") == {"a": "bot-secrets"}


def test_a_job_that_does_not_read_the_secret_is_not_reported(tmp_path: Path) -> None:
    """Negative: an unrelated job in the same file is not a consumer."""
    wf = tmp_path / "w.yml"
    wf.write_text(
        "name: x\non: push\njobs:\n"
        "  a:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo\n        env:\n          T: ${{ secrets.EXAMPLE_TOKEN }}\n"
        "  b:\n    runs-on: ubuntu-latest\n    steps: []\n",
        encoding="utf-8",
    )
    assert set(jobs_reaching(wf, "EXAMPLE_TOKEN")) == {"a"}
