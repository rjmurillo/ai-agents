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


def reads_secret(text: str, secret: str) -> bool:
    """True when ``text`` names ``secret`` in dotted or bracket form."""
    return re.search(rf"secrets(?:\.{secret}\b|\[\s*['\"]{secret}['\"]\s*\])", text) is not None


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
    workflow_level = reads_secret(preamble, secret)
    reaching: dict[str, str | None] = {}
    for job_id, body in jobs.items():
        if workflow_level or reads_secret(yaml.safe_dump(body), secret):
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


RETIRED_ENVIRONMENT = "bot-secrets"


def _environment_name(environment: object) -> str:
    """Return the environment name from a string or a ``name:`` mapping."""
    if isinstance(environment, dict):
        environment = environment.get("name")
    return environment if isinstance(environment, str) else ""


def bot_pat_readers(paths: list[Path]) -> list[str]:
    """Every ``workflow:job`` that can read BOT_PAT, in any environment.

    Issue #4607: BOT_PAT is retired. Jobs use the per-run ``github.token``.
    """
    offenders: list[str] = []
    for path in paths:
        for job_id, environment in jobs_reaching(path, "BOT_PAT").items():
            offenders.append(f"{path.name}:{job_id} environment={_environment_name(environment)!r}")
    return sorted(offenders)


def jobs_in_retired_environment(paths: list[Path]) -> list[str]:
    """Every ``workflow:job`` that declares ``environment: bot-secrets``."""
    offenders: list[str] = []
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_id, body in (data.get("jobs") or {}).items():
            if not isinstance(body, dict):
                continue
            if _environment_name(body.get("environment")) == RETIRED_ENVIRONMENT:
                offenders.append(f"{path.name}:{job_id}")
    return sorted(offenders)


def test_no_job_reads_the_retired_bot_pat() -> None:
    """Positive: no real workflow job can read BOT_PAT (issue #4607)."""
    offenders = bot_pat_readers(workflow_paths())
    assert not offenders, "BOT_PAT is retired, use github.token:\n" + "\n".join(offenders)


def test_bot_pat_scan_flags_a_job_with_no_environment(tmp_path: Path) -> None:
    """Control: a job reading BOT_PAT with no environment is reported."""
    wf = tmp_path / "w.yml"
    wf.write_text(
        "name: x\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo\n        env:\n          T: ${{ secrets.BOT_PAT }}\n",
        encoding="utf-8",
    )
    assert bot_pat_readers([wf]) == ["w.yml:a environment=''"]


def test_bot_pat_scan_flags_an_agent_environment(tmp_path: Path) -> None:
    """Control: an agent-* environment no longer excuses a BOT_PAT read."""
    wf = tmp_path / "w.yml"
    wf.write_text(
        "name: x\non: push\njobs:\n"
        "  a:\n    runs-on: ubuntu-latest\n    environment: agent-claude\n    steps:\n"
        "      - run: echo\n        env:\n          T: ${{ secrets.BOT_PAT }}\n"
        "  b:\n    runs-on: ubuntu-latest\n    environment:\n      name: agent-copilot\n"
        "    steps:\n      - run: echo\n        env:\n          T: ${{ secrets['BOT_PAT'] }}\n",
        encoding="utf-8",
    )
    assert bot_pat_readers([wf]) == [
        "w.yml:a environment='agent-claude'",
        "w.yml:b environment='agent-copilot'",
    ]


def test_bot_pat_scan_accepts_github_token(tmp_path: Path) -> None:
    """Negative control: a job on github.token is not a BOT_PAT reader."""
    wf = tmp_path / "w.yml"
    wf.write_text(
        "name: x\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo\n        env:\n          T: ${{ github.token }}\n",
        encoding="utf-8",
    )
    assert bot_pat_readers([wf]) == []


def test_no_job_declares_the_retired_bot_secrets_environment() -> None:
    """Positive: no real workflow job declares environment: bot-secrets."""
    offenders = jobs_in_retired_environment(workflow_paths())
    assert not offenders, "jobs still in bot-secrets:\n" + "\n".join(offenders)


def test_retired_environment_scan_flags_a_bot_secrets_job(tmp_path: Path) -> None:
    """Control: a job declaring bot-secrets, in either form, is reported."""
    wf = tmp_path / "w.yml"
    wf.write_text(
        "name: x\non: push\njobs:\n"
        "  a:\n    runs-on: ubuntu-latest\n    environment: bot-secrets\n    steps: []\n"
        "  b:\n    runs-on: ubuntu-latest\n    environment:\n      name: bot-secrets\n"
        "    steps: []\n"
        "  c:\n    runs-on: ubuntu-latest\n    steps: []\n",
        encoding="utf-8",
    )
    assert jobs_in_retired_environment([wf]) == ["w.yml:a", "w.yml:b"]
