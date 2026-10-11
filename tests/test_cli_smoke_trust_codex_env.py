"""Codex job environment tests for the CLI smoke workflow (REQ-047 AC11).

The Codex leg needs no credential. These tests pin that no step or job env can
carry an OpenAI or Codex key, and that the job joins no environment.
"""

from __future__ import annotations

from typing import Any

import yaml

pytest_plugins = ["tests.lib.cli_smoke_fixtures"]

_FORBIDDEN_ENV = {"OPENAI_API_KEY", "CODEX_API_KEY"}


def test_codex_job_declares_no_environment(codex_job: dict[str, Any]) -> None:
    assert "environment" not in codex_job


def test_codex_job_and_step_env_carry_no_credential(codex_job: dict[str, Any]) -> None:
    """Negative, per scope: no job or step env names an OpenAI or Codex key."""
    scopes = [codex_job.get("env") or {}, *[step.get("env") or {} for step in codex_job["steps"]]]

    for env in scopes:
        assert not _FORBIDDEN_ENV & set(env)
        assert "secrets." not in str(env)


def test_no_codex_step_references_a_secret(codex_job: dict[str, Any]) -> None:
    for step in codex_job["steps"]:
        assert "secrets." not in yaml.safe_dump(step), step.get("name")
