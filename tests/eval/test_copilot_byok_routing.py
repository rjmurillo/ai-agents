"""Copilot BYOK provider env passthrough and routing provenance (issue #5404).

GitHub-routed Copilot CLI quota exhausts (HTTP 402, observed 2026-09-24, see
`scripts/eval/README.md` "Copilot: the client-label finding and BYOK"), so
`eval_runtime_parity.py --harnesses copilot` needs the documented BYOK
provider env (`copilot help environment`, Copilot CLI 1.0.89) to keep
running at all. These tests cover the two new units: the `copilot`
`runtime_env` allowlist entries in `_runtime_harness.py`, and the pure
`copilot_routing` helper that records how a run was routed in `report.json`
without ever writing a credential into it.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import FIXTURES, parity, runtime_harness

BYOK_VARS = (
    "COPILOT_PROVIDER_TYPE",
    "COPILOT_PROVIDER_BASE_URL",
    "COPILOT_PROVIDER_API_KEY",
    "COPILOT_PROVIDER_BEARER_TOKEN",
    "COPILOT_PROVIDER_MODEL_ID",
    "COPILOT_PROVIDER_WIRE_MODEL",
)

SECRET_SENTINEL = "sk-parity-5404-do-not-leak"


def _clear_byok_vars(monkeypatch) -> None:
    for key in (*BYOK_VARS, "COPILOT_PROVIDER_API_KEY_COMMAND", "COPILOT_PROVIDER_HEADERS"):
        monkeypatch.delenv(key, raising=False)


def _version_runner(argv, **_kwargs):
    args = [str(value) for value in argv]
    executable = Path(args[0]).name.lower()
    return subprocess.CompletedProcess(args, 0, f"{executable} test-version\n", "")


def _single_fixture_corpus(tmp_path: Path) -> Path:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    payload["fixtures"] = payload["fixtures"][:1]
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --- runtime_env: positive -----------------------------------------------


def test_runtime_env_passes_copilot_byok_vars_through(tmp_path: Path, monkeypatch) -> None:
    _clear_byok_vars(monkeypatch)
    values = {name: f"value-{name.lower()}" for name in BYOK_VARS}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    workspace = tmp_path / "copilot"
    workspace.mkdir()

    env = runtime_harness.runtime_env(workspace, "copilot")

    for key, value in values.items():
        assert env[key] == value


# --- runtime_env: negative -------------------------------------------------


def test_runtime_env_drops_api_key_command_and_headers(tmp_path: Path, monkeypatch) -> None:
    _clear_byok_vars(monkeypatch)
    monkeypatch.setenv("COPILOT_PROVIDER_API_KEY_COMMAND", "cat ~/.secret-key")
    monkeypatch.setenv("COPILOT_PROVIDER_HEADERS", "X-Api-Key: leaked")
    workspace = tmp_path / "copilot"
    workspace.mkdir()

    env = runtime_harness.runtime_env(workspace, "copilot")

    assert "COPILOT_PROVIDER_API_KEY_COMMAND" not in env
    assert "COPILOT_PROVIDER_HEADERS" not in env


def test_claude_and_codex_envs_exclude_copilot_provider_vars(tmp_path: Path, monkeypatch) -> None:
    _clear_byok_vars(monkeypatch)
    for key in BYOK_VARS:
        monkeypatch.setenv(key, "leaked-if-present")
    claude_workspace = tmp_path / "claude"
    codex_workspace = tmp_path / "codex"
    claude_workspace.mkdir()
    codex_workspace.mkdir()

    claude_env = runtime_harness.runtime_env(claude_workspace, "claude")
    codex_env = runtime_harness.runtime_env(codex_workspace, "codex")

    for key in BYOK_VARS:
        assert key not in claude_env
        assert key not in codex_env


# --- copilot_routing: positive ---------------------------------------------


def test_copilot_routing_byok_records_type_and_base_url() -> None:
    env = {
        "COPILOT_PROVIDER_TYPE": "anthropic",
        "COPILOT_PROVIDER_BASE_URL": "https://api.anthropic.com",
        "COPILOT_PROVIDER_API_KEY": SECRET_SENTINEL,
    }

    routing = runtime_harness.copilot_routing(env)

    assert routing == {
        "routing": "byok",
        "provider_type": "anthropic",
        "base_url": "https://api.anthropic.com",
    }


# --- copilot_routing: negative ---------------------------------------------


def test_copilot_routing_never_includes_secret_values() -> None:
    env = {
        "COPILOT_PROVIDER_TYPE": "openai",
        "COPILOT_PROVIDER_BASE_URL": "https://byok.example.com",
        "COPILOT_PROVIDER_API_KEY": SECRET_SENTINEL,
        "COPILOT_PROVIDER_BEARER_TOKEN": SECRET_SENTINEL,
        "COPILOT_PROVIDER_MODEL_ID": SECRET_SENTINEL,
        "COPILOT_PROVIDER_WIRE_MODEL": SECRET_SENTINEL,
    }

    routing = runtime_harness.copilot_routing(env)

    assert SECRET_SENTINEL not in json.dumps(routing)
    assert set(routing) == {"routing", "provider_type", "base_url"}


# --- copilot_routing: edge --------------------------------------------------


def test_copilot_routing_empty_base_url_is_github() -> None:
    env = {"COPILOT_PROVIDER_TYPE": "anthropic", "COPILOT_PROVIDER_BASE_URL": ""}

    assert runtime_harness.copilot_routing(env) == {"routing": "github"}


def test_copilot_routing_absent_base_url_is_github() -> None:
    assert runtime_harness.copilot_routing({}) == {"routing": "github"}


def test_copilot_routing_defaults_provider_type_to_openai_when_unset() -> None:
    env = {"COPILOT_PROVIDER_BASE_URL": "https://byok.example.com"}

    routing = runtime_harness.copilot_routing(env)

    assert routing["provider_type"] == "openai"


# --- report.json integration -----------------------------------------------


def test_report_records_copilot_routing_for_copilot_harness(tmp_path: Path, monkeypatch) -> None:
    _clear_byok_vars(monkeypatch)
    monkeypatch.setenv("COPILOT_PROVIDER_TYPE", "anthropic")
    monkeypatch.setenv("COPILOT_PROVIDER_BASE_URL", "https://api.anthropic.com")
    monkeypatch.setenv("COPILOT_PROVIDER_API_KEY", SECRET_SENTINEL)
    fixtures_path = _single_fixture_corpus(tmp_path)

    report, code = parity.run_evaluation(
        fixtures_path=fixtures_path,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
        runner=_version_runner,
        harnesses="copilot",
    )

    assert code == parity.EXIT_OK
    assert report["copilot_routing"] == {
        "routing": "byok",
        "provider_type": "anthropic",
        "base_url": "https://api.anthropic.com",
    }
    assert SECRET_SENTINEL not in json.dumps(report)


def test_report_omits_copilot_routing_for_claude_only_harness(tmp_path: Path, monkeypatch) -> None:
    _clear_byok_vars(monkeypatch)
    monkeypatch.setenv("COPILOT_PROVIDER_BASE_URL", "https://api.anthropic.com")
    fixtures_path = _single_fixture_corpus(tmp_path)

    report, code = parity.run_evaluation(
        fixtures_path=fixtures_path,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
        runner=_version_runner,
        harnesses="claude",
    )

    assert code == parity.EXIT_OK
    assert "copilot_routing" not in report


def test_report_records_github_routing_when_no_byok_vars_set(tmp_path: Path, monkeypatch) -> None:
    _clear_byok_vars(monkeypatch)
    fixtures_path = _single_fixture_corpus(tmp_path)

    report, code = parity.run_evaluation(
        fixtures_path=fixtures_path,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
        runner=_version_runner,
        harnesses="both",
    )

    assert code == parity.EXIT_OK
    assert report["copilot_routing"] == {"routing": "github"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://user:s3cret@gw.example:8443/v1?key=s3cret#s3cret", "https://gw.example:8443"),
        ("https://gw.example/token/s3cret", "https://gw.example"),
        ("https://api.anthropic.com", "https://api.anthropic.com"),
        ("http://[::1]:11434/v1", "http://[::1]:11434"),
        ("https://[2001:db8::1]/v1", "https://[2001:db8::1]"),
        ("https://gw.example:abc/v1", "https://gw.example:abc"),
        ("gw.example", ""),
    ],
)
def test_copilot_routing_redacts_base_url_credentials(raw: str, expected: str) -> None:
    routing = runtime_harness.copilot_routing({"COPILOT_PROVIDER_BASE_URL": raw})
    assert routing["base_url"] == expected
    assert "s3cret" not in json.dumps(routing)
