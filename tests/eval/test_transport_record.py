"""Tests for the run's transport record: cell, payer, credential step, host.

`eval-prompt-change.py` writes this record into `result.json` and prints it on
stderr, on success and on failure, so a gateway run is never read back as a
direct run. The record names the host, never the token.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.eval._cli_transport_test_support import _claude_cli
from tests.eval._credential_test_support import _cli_credentials as creds
from tests.eval._gateway_test_support import (
    GATEWAY_TOKEN,
    GATEWAY_URL,
    MODEL,
    OAUTH_TOKEN,
    clear_claude_env,
    export_gateway,
    load_prompt_change,
    run_once,
)

prompt_change = load_prompt_change()
transport = sys.modules["_transport_record"]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    return clear_claude_env(monkeypatch)


@pytest.fixture
def gateway_env(clean_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    return export_gateway(clean_env)


# --- the runner's transport record ------------------------------------------


def test_transport_record_for_a_gateway_run_names_the_host_not_the_token(
    gateway_env: pytest.MonkeyPatch,
) -> None:
    gateway_env.setenv("EVAL_PROVIDER", "claude-subscription")
    run_once(gateway_env)

    record = transport.transport_record()

    assert record == {
        "provider": "claude-cli",
        "harness": "claude",
        "payer": "gateway",
        "credential_steps": [creds.STEP_GATEWAY],
        "endpoint_host": "127.0.0.1:8319",
    }
    assert GATEWAY_TOKEN not in json.dumps(record)
    assert "gateway" in transport.transport_line(record)


def test_transport_record_for_a_subscription_run_keeps_the_cell_payer(
    clean_env: pytest.MonkeyPatch,
) -> None:
    clean_env.setenv("EVAL_PROVIDER", "claude-subscription")
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)
    run_once(clean_env)

    record = transport.transport_record()

    assert record["payer"] == "subscription"
    assert record["credential_steps"] == [creds.STEP_ENV]
    assert record["endpoint_host"] == "api.anthropic.com"


def test_transport_record_for_the_default_api_cell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", GATEWAY_URL)

    record = transport.transport_record()

    assert record["provider"] == "anthropic"
    assert record["payer"] == "api"
    # The urllib transport ignores ANTHROPIC_BASE_URL, so the record must too.
    assert record["endpoint_host"] == "api.anthropic.com"


def test_transport_record_does_not_guess_a_host_it_cannot_see(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVAL_PROVIDER", "codex-cli")

    assert transport.transport_record()["endpoint_host"] is None


def test_transport_record_under_real_home_still_says_gateway(
    gateway_env: pytest.MonkeyPatch,
) -> None:
    """The real-HOME path skips the shared cache; the report must not go blank."""
    gateway_env.setenv(_claude_cli.REAL_HOME_ENV, "1")
    gateway_env.setenv("EVAL_PROVIDER", "claude-subscription")
    run_once(gateway_env)

    record = transport.transport_record()

    assert record["payer"] == "gateway"
    assert record["credential_steps"] == [creds.STEP_GATEWAY]
    assert record["endpoint_host"] == "127.0.0.1:8319"


def test_real_home_records_an_oauth_step_too(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv(_claude_cli.REAL_HOME_ENV, "1")
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)
    run_once(clean_env)

    assert creds.recorded_steps() == [creds.STEP_ENV]


def test_transport_record_for_a_lone_base_url_names_the_host_the_run_reached(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """The child never sees half a pair, so the run went to the default host."""
    clean_env.setenv("EVAL_PROVIDER", "claude-subscription")
    clean_env.setenv("ANTHROPIC_BASE_URL", "https://proxy.example.com")
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)
    run_once(clean_env)

    record = transport.transport_record()

    assert record["payer"] == "subscription"
    assert record["credential_steps"] == [creds.STEP_ENV]
    assert record["endpoint_host"] == "api.anthropic.com"


# --- the runner writes the record ---------------------------------------------


def _report_args(tmp_path: Path):
    import argparse

    return argparse.Namespace(
        runs=3,
        model=MODEL,
        security_critical=False,
        base_resamples=0,
        max_tokens=256,
        output=str(tmp_path / "result.json"),
    )


def _fake_comparison() -> dict[str, object]:
    return {
        "before_score": 1.0,
        "after_score": 1.0,
        "delta": 0.0,
        "scenario_count": 1,
        "scored_scenario_count": 1,
        "api_calls": 6,
        "est_tokens": 100,
        "before_results": [],
        "after_results": [],
    }


def test_result_json_and_stderr_carry_the_transport_and_no_token(
    gateway_env: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    gateway_env.setenv("EVAL_PROVIDER", "claude-subscription")
    run_once(gateway_env)
    gateway_env.setattr(prompt_change, "run_comparison", lambda *a, **k: _fake_comparison())
    gateway_env.setattr(prompt_change, "acceptance_gate", lambda *a, **k: {"passed": True})
    gateway_env.setattr(prompt_change, "_print_gate_summary", lambda gate: None)
    args = _report_args(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        prompt_change._run_and_report("", "b", "a", [], args, "explicit")

    written = (tmp_path / "result.json").read_text(encoding="utf-8")
    stderr = capsys.readouterr().err
    assert excinfo.value.code == 0
    assert json.loads(written)["transport"]["payer"] == "gateway"
    assert json.loads(written)["transport"]["endpoint_host"] == "127.0.0.1:8319"
    assert "Transport: claude-cli via 127.0.0.1:8319 (credential: gateway)" in stderr
    assert GATEWAY_TOKEN not in written and GATEWAY_TOKEN not in stderr


def test_a_failed_run_still_names_the_transport(
    gateway_env: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    gateway_env.setenv("EVAL_PROVIDER", "claude-subscription")
    run_once(gateway_env)

    def _hub_rejects(*args: object, **kwargs: object) -> dict[str, object]:
        raise RuntimeError("API Error: 400 unknown provider for model claude-sonnet-5")

    gateway_env.setattr(prompt_change, "run_comparison", _hub_rejects)

    with pytest.raises(SystemExit):
        prompt_change._run_or_exit("", "b", "a", [], _report_args(tmp_path), "explicit")

    stderr = capsys.readouterr().err
    assert "Transport: claude-cli via 127.0.0.1:8319 (credential: gateway)" in stderr
    assert GATEWAY_TOKEN not in stderr


def test_a_malformed_metadata_failure_still_names_the_transport(
    gateway_env: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    gateway_env.setenv("EVAL_PROVIDER", "claude-subscription")
    run_once(gateway_env)
    error_type = prompt_change.MalformedProviderMetadataError

    def _bad_envelope(*args: object, **kwargs: object) -> dict[str, object]:
        raise error_type("provider metadata field is not a string")

    gateway_env.setattr(prompt_change, "run_comparison", _bad_envelope)

    with pytest.raises(error_type):
        prompt_change._run_or_exit("", "b", "a", [], _report_args(tmp_path), "explicit")

    assert "Transport: claude-cli via 127.0.0.1:8319" in capsys.readouterr().err


@pytest.mark.parametrize(
    "url", ["https://api.anthropic.com:443", "https://api.anthropic.com:8443", "not a url"]
)
def test_any_lone_base_url_records_the_default_host_and_cell_payer(
    clean_env: pytest.MonkeyPatch, url: str
) -> None:
    clean_env.setenv("EVAL_PROVIDER", "claude-subscription")
    clean_env.setenv("ANTHROPIC_BASE_URL", url)
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)
    run_once(clean_env)

    record = transport.transport_record()

    assert record["payer"] == "subscription"
    assert record["endpoint_host"] == "api.anthropic.com"


@pytest.mark.parametrize("name", ["anthropic-sdk", "Anthropic-SDK", " ANTHROPIC-SDK "])
def test_the_sdk_alias_records_no_host_in_any_case(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """The SDK may follow ANTHROPIC_BASE_URL, so the record must not guess."""
    monkeypatch.setenv("EVAL_PROVIDER", name)

    assert transport.transport_record()["endpoint_host"] is None


def test_real_home_with_no_credential_records_the_existing_login(
    clean_env: pytest.MonkeyPatch,
) -> None:
    clean_env.setenv(_claude_cli.REAL_HOME_ENV, "1")
    run_once(clean_env)

    assert creds.recorded_steps() == [creds.STEP_EXISTING_LOGIN]


def test_a_pair_exported_before_any_call_still_reads_gateway(
    gateway_env: pytest.MonkeyPatch,
) -> None:
    """A run that fails before resolution must not read as a direct run for a hub."""
    gateway_env.setenv("EVAL_PROVIDER", "claude-subscription")

    record = transport.transport_record()

    assert record["credential_steps"] == []
    assert record["payer"] == "gateway"


# --- the code-review catch-rate runner's cost note ---------------------------


def _catch_rate_cli():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from code_review_catch_rate_helpers import cli
    finally:
        sys.path.pop(0)
    return cli


def test_the_catch_rate_cost_note_names_a_gateway_run(gateway_env: pytest.MonkeyPatch) -> None:
    """Before the env was inherited this note was always true; now it must check."""
    gateway_env.setenv("EVAL_PROVIDER", "claude-cli")
    run_once(gateway_env)

    note = _catch_rate_cli()._cost_note("claude-cli")

    assert note.startswith("gateway at 127.0.0.1:8319")
    assert "no metered spend" not in note
    assert GATEWAY_TOKEN not in note


def test_the_catch_rate_cost_note_keeps_the_seat_wording_for_a_direct_run(
    clean_env: pytest.MonkeyPatch,
) -> None:
    clean_env.setenv("EVAL_PROVIDER", "claude-cli")
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)
    run_once(clean_env)

    assert _catch_rate_cli()._cost_note("claude-cli") == (
        "subscription CLI, no metered spend; dollars not reported"
    )
