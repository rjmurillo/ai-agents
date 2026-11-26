"""Tests for the Claude CLI cell's inherited environment and its gateway step.

The child inherits the parent environment minus a deny list, so a local hub
exported as `ANTHROPIC_BASE_URL` plus `ANTHROPIC_AUTH_TOKEN` works with no key.
These tests pin what keeps that honest:

- the deny list still removes the metered key, the cloud switches, and the
  parent session's `CLAUDE*` plumbing;
- the auth token reaches the child only on the `gateway` step, because it
  outranks the OAuth token the other steps record;
- isolation (relocated config, no settings, MCP, or tools) holds on every step;
- the run records the endpoint host, never the token or the URL path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tests.eval._cli_transport_test_support import (
    MESSAGES,
    Recorder,
    _claude_cli,
    claude_payload,
    install_runner,
)
from tests.eval._credential_test_support import _cli_credentials as creds
from tests.eval._credential_test_support import set_sources
from tests.eval._gateway_test_support import (
    GATEWAY_TOKEN,
    GATEWAY_URL,
    MODEL,
    OAUTH_TOKEN,
    clear_claude_env,
    export_gateway,
    run_once,
)

gateway = sys.modules["_claude_gateway"]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    return clear_claude_env(monkeypatch)


@pytest.fixture
def gateway_env(clean_env: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    return export_gateway(clean_env)


# --- endpoint_host and gateway_configured ------------------------------------


@pytest.mark.parametrize(
    ("url", "host"),
    [
        ("", "api.anthropic.com"),
        ("   ", "api.anthropic.com"),
        ("http://127.0.0.1:8319", "127.0.0.1:8319"),
        ("http://127.0.0.1:8319/v1/messages?x=1", "127.0.0.1:8319"),
        ("https://gateway.example.com", "gateway.example.com"),
        ("https://user:secret@gateway.example.com/v1", "gateway.example.com"),
        ("http://[::1]:8319", "[::1]:8319"),
        ("http://LOCALHOST:8319", "localhost:8319"),
    ],
)
def test_endpoint_host_names_the_host_and_port_only(url: str, host: str) -> None:
    assert gateway.endpoint_host({"ANTHROPIC_BASE_URL": url}) == host


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:notaport", "http://127.0.0.1:99999", "not a url"]
)
def test_endpoint_host_never_falls_back_to_the_default_on_a_bad_url(url: str) -> None:
    assert gateway.endpoint_host({"ANTHROPIC_BASE_URL": url}) == "unparseable"


def test_endpoint_host_drops_userinfo() -> None:
    host = gateway.endpoint_host({"ANTHROPIC_BASE_URL": "https://u:pw@gw.example.com"})

    assert "pw" not in host and "u:" not in host


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({"ANTHROPIC_BASE_URL": GATEWAY_URL, "ANTHROPIC_AUTH_TOKEN": GATEWAY_TOKEN}, True),
        ({"ANTHROPIC_BASE_URL": GATEWAY_URL}, False),
        ({"ANTHROPIC_AUTH_TOKEN": GATEWAY_TOKEN}, False),
        ({"ANTHROPIC_BASE_URL": " ", "ANTHROPIC_AUTH_TOKEN": GATEWAY_TOKEN}, False),
        ({"ANTHROPIC_BASE_URL": GATEWAY_URL, "ANTHROPIC_AUTH_TOKEN": "  "}, False),
        ({}, False),
    ],
)
def test_gateway_needs_both_halves_of_the_pair(environ: dict[str, str], expected: bool) -> None:
    assert gateway.gateway_configured(environ) is expected


# --- resolution order ---------------------------------------------------------


def _resolve(environ: dict[str, str], *, disk: str | None = None, probe: bool = False):
    import dataclasses

    spec = dataclasses.replace(
        _claude_cli.CREDENTIAL_SPEC,
        read_disk=lambda env: disk,
        login_probe=lambda executable, env: probe,
    )
    environ = {"EVAL_DOTENV_FILES": "/nonexistent/ai-agents-eval.env", **environ}
    return creds.resolve_credential(spec, executable="claude", environ=environ, stdin_is_tty=False)


def _pair() -> dict[str, str]:
    return {"ANTHROPIC_BASE_URL": GATEWAY_URL, "ANTHROPIC_AUTH_TOKEN": GATEWAY_TOKEN}


def test_the_gateway_pair_resolves_first_and_carries_no_secret() -> None:
    resolved = _resolve(_pair())

    assert resolved.step == creds.STEP_GATEWAY
    assert resolved.secret is None


def test_the_gateway_beats_an_exported_oauth_token_as_the_cli_does() -> None:
    """Claude Code ranks ANTHROPIC_AUTH_TOKEN above CLAUDE_CODE_OAUTH_TOKEN."""
    resolved = _resolve({**_pair(), "CLAUDE_CODE_OAUTH_TOKEN": OAUTH_TOKEN})

    assert resolved.step == creds.STEP_GATEWAY


def test_the_gateway_beats_a_stored_login() -> None:
    assert _resolve(_pair(), disk="stored").step == creds.STEP_GATEWAY
    assert _resolve(_pair(), probe=True).step == creds.STEP_GATEWAY


def test_half_a_pair_falls_through_to_the_normal_order() -> None:
    token_only = {"ANTHROPIC_AUTH_TOKEN": GATEWAY_TOKEN, "CLAUDE_CODE_OAUTH_TOKEN": OAUTH_TOKEN}
    url_only = {"ANTHROPIC_BASE_URL": GATEWAY_URL}

    assert _resolve(token_only).step == creds.STEP_ENV
    assert _resolve(url_only, disk="stored").step == creds.STEP_DISK
    with pytest.raises(creds.CredentialNotFoundError, match="gateway"):
        _resolve(url_only)


def test_the_gateway_step_has_a_report_label() -> None:
    assert creds.step_label(creds.STEP_GATEWAY) == creds.GATEWAY_NOTE


# --- the child process --------------------------------------------------------


def test_a_gateway_run_inherits_the_pair_under_an_isolated_profile(
    gateway_env: pytest.MonkeyPatch,
) -> None:
    env, argv, provider = run_once(gateway_env)

    assert env["ANTHROPIC_BASE_URL"] == GATEWAY_URL
    assert env["ANTHROPIC_AUTH_TOKEN"] == GATEWAY_TOKEN
    assert Path(env["CLAUDE_CONFIG_DIR"]).name.startswith("eval-claude-cli-")
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert provider.credential_step == creds.STEP_GATEWAY
    assert gateway.endpoint_host(os.environ) == "127.0.0.1:8319"
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert "mcp__*" in argv[argv.index("--disallowed-tools") + 1]
    assert not any(GATEWAY_TOKEN in part for part in argv)


def test_a_gateway_run_never_injects_an_exported_oauth_token(
    gateway_env: pytest.MonkeyPatch,
) -> None:
    gateway_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)

    env, _, provider = run_once(gateway_env)

    assert "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert provider.credential_step == creds.STEP_GATEWAY


def test_the_child_inherits_unrelated_parent_variables(gateway_env: pytest.MonkeyPatch) -> None:
    gateway_env.setenv("HTTPS_PROXY", "http://proxy.internal:3128")
    gateway_env.setenv("NODE_EXTRA_CA_CERTS", "/etc/ssl/corp.pem")
    gateway_env.setenv("OPENAI_API_KEY", "sk-other-vendor")

    env, _, _ = run_once(gateway_env)

    assert env["HTTPS_PROXY"] == "http://proxy.internal:3128"
    assert env["NODE_EXTRA_CA_CERTS"] == "/etc/ssl/corp.pem"
    assert env["OPENAI_API_KEY"] == "sk-other-vendor"


def test_the_deny_list_still_holds_under_the_gateway(gateway_env: pytest.MonkeyPatch) -> None:
    gateway_env.setenv("ANTHROPIC_API_KEY", "sk-ant-metered")
    gateway_env.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    gateway_env.setenv("CLAUDE_CODE_USE_VERTEX", "1")
    gateway_env.setenv("CLAUDE_CODE_USE_FOUNDRY", "1")
    gateway_env.setenv("CLAUDECODE", "1")
    gateway_env.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
    gateway_env.setenv("CLAUDE_CODE_SSE_PORT", "4242")
    gateway_env.setenv("CLAUDE_PROJECT_DIR", "/operator/repo")

    env, _, _ = run_once(gateway_env)

    assert "ANTHROPIC_API_KEY" not in env
    leaked = sorted(
        name for name in env if name.startswith("CLAUDE") and name != "CLAUDE_CONFIG_DIR"
    )
    assert leaked == []


def test_the_operator_config_dir_never_reaches_a_gateway_run(
    gateway_env: pytest.MonkeyPatch,
) -> None:
    gateway_env.setenv("CLAUDE_CONFIG_DIR", "/operator/claude-hub")

    env, _, _ = run_once(gateway_env)

    assert env["CLAUDE_CONFIG_DIR"] != "/operator/claude-hub"


def test_an_auth_token_without_a_base_url_never_reaches_the_child(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Alone it is a metered api.anthropic.com bearer that outranks the OAuth token."""
    clean_env.setenv("ANTHROPIC_AUTH_TOKEN", GATEWAY_TOKEN)
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)

    env, _, provider = run_once(clean_env)

    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == OAUTH_TOKEN
    assert provider.credential_step == creds.STEP_ENV
    assert gateway.endpoint_host(os.environ) == "api.anthropic.com"


@pytest.mark.parametrize(
    "url", ["https://proxy.example.com/anthropic", "http://127.0.0.1:8319", "not a url"]
)
def test_a_base_url_alone_never_reaches_an_oauth_child(
    clean_env: pytest.MonkeyPatch, url: str
) -> None:
    """Half a pair is stripped: the seat token must not leave for another host."""
    clean_env.setenv("ANTHROPIC_BASE_URL", url)
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)

    env, _, provider = run_once(clean_env)

    assert "ANTHROPIC_BASE_URL" not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == OAUTH_TOKEN
    assert provider.credential_step == creds.STEP_ENV


def test_a_base_url_alone_never_reaches_a_stored_login_child(
    clean_env: pytest.MonkeyPatch,
) -> None:
    clean_env.setenv("ANTHROPIC_BASE_URL", "https://proxy.example.com")
    set_sources(clean_env, "_claude_cli", disk=lambda environ: "stored-oauth", probe=False)

    env, _, provider = run_once(clean_env)

    assert "ANTHROPIC_BASE_URL" not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "stored-oauth"
    assert provider.credential_step == creds.STEP_DISK


def test_a_base_url_alone_never_reaches_a_real_home_child(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """Real HOME uses the CLI's own login; a lone base URL would redirect it too."""
    clean_env.setenv(_claude_cli.REAL_HOME_ENV, "1")
    clean_env.setenv("ANTHROPIC_BASE_URL", "https://proxy.example.com")

    env, _, provider = run_once(clean_env)

    assert "ANTHROPIC_BASE_URL" not in env
    assert provider.credential_step == creds.STEP_EXISTING_LOGIN


def test_a_pair_removed_after_resolution_fails_closed(gateway_env: pytest.MonkeyPatch) -> None:
    recorder = Recorder(stdout=claude_payload(model=MODEL))
    install_runner(gateway_env, recorder)
    provider = _claude_cli._ClaudeCLIProvider()
    provider.complete(messages=MESSAGES, model=MODEL)
    gateway_env.delenv("ANTHROPIC_BASE_URL")

    with pytest.raises(RuntimeError, match="no longer set") as excinfo:
        provider.complete(messages=MESSAGES, model=MODEL)

    assert len(recorder.calls) == 1
    assert GATEWAY_TOKEN not in str(excinfo.value)


def test_a_missing_credential_error_names_the_pair_and_no_value(
    clean_env: pytest.MonkeyPatch,
) -> None:
    clean_env.setenv("ANTHROPIC_AUTH_TOKEN", GATEWAY_TOKEN)
    recorder = Recorder(stdout=claude_payload(model=MODEL))
    install_runner(clean_env, recorder)

    with pytest.raises(RuntimeError, match="ANTHROPIC_BASE_URL") as excinfo:
        _claude_cli._ClaudeCLIProvider().complete(messages=MESSAGES, model=MODEL)

    assert recorder.calls == []
    assert GATEWAY_TOKEN not in str(excinfo.value)


def test_real_home_records_the_gateway_and_sets_no_config_dir(
    gateway_env: pytest.MonkeyPatch,
) -> None:
    gateway_env.setenv(_claude_cli.REAL_HOME_ENV, "1")

    env, _, provider = run_once(gateway_env)

    assert provider.credential_step == creds.STEP_GATEWAY
    assert env["ANTHROPIC_AUTH_TOKEN"] == GATEWAY_TOKEN
    assert "CLAUDE_CONFIG_DIR" not in env


# --- custom headers ---------------------------------------------------------


def test_custom_headers_reach_only_a_gateway_run(gateway_env: pytest.MonkeyPatch) -> None:
    gateway_env.setenv("ANTHROPIC_CUSTOM_HEADERS", "x-hub-route: eval")

    env, _, _ = run_once(gateway_env)

    assert env["ANTHROPIC_CUSTOM_HEADERS"] == "x-hub-route: eval"


def test_custom_headers_never_ride_along_with_an_oauth_run(
    clean_env: pytest.MonkeyPatch,
) -> None:
    """A header can carry x-api-key or Authorization and bill another credential."""
    clean_env.setenv("ANTHROPIC_CUSTOM_HEADERS", "x-api-key: sk-ant-metered")
    clean_env.setenv("CLAUDE_CODE_OAUTH_TOKEN", OAUTH_TOKEN)

    env, _, _ = run_once(clean_env)

    assert "ANTHROPIC_CUSTOM_HEADERS" not in env
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == OAUTH_TOKEN


# --- isolated runners (parity, control ablation) ------------------------------


def test_isolated_runners_skip_the_gateway_and_inject_the_stored_token(
    gateway_env: pytest.MonkeyPatch,
) -> None:
    """They build their own env, so a token-free gateway step would strand them."""
    login = sys.modules["_isolated_claude_login"]
    gateway_env.setattr(login, "resolve_cached", creds.resolve_cached)
    set_sources(gateway_env, "_claude_cli", disk=lambda environ: "stored-oauth", probe=False)
    env: dict[str, str] = {}

    login.add_claude_login(env, "claude")

    assert env == {"CLAUDE_CODE_OAUTH_TOKEN": "stored-oauth"}


def test_isolated_runners_with_only_a_gateway_name_the_missing_token(
    gateway_env: pytest.MonkeyPatch,
) -> None:
    """A hub-only operator must not be told to export the pair they already have."""
    login = sys.modules["_isolated_claude_login"]
    gateway_env.setattr(login, "resolve_cached", creds.resolve_cached)

    with pytest.raises(login.IsolatedLoginError) as excinfo:
        login.add_claude_login({}, "claude")

    message = str(excinfo.value)
    assert "does not use a gateway" in message
    assert "Export the gateway pair" not in message
    assert GATEWAY_TOKEN not in message
