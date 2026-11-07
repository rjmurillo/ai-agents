"""An isolated Claude fixture run gets the stored login as a token (issue #5410)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.eval._credential_test_support import set_sources
from tests.eval._runtime_parity_test_support import parity, runtime_harness

parity_module = sys.modules["_runtime_parity"]

TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
DISK_TOKEN = "disk-token-for-test"


@pytest.fixture(autouse=True)
def _parity_runs_have_a_token() -> None:
    """Override the conftest stub: these tests exercise real resolution."""


def _disk_login(monkeypatch: pytest.MonkeyPatch) -> None:
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: DISK_TOKEN)


def test_isolated_claude_run_receives_the_stored_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _disk_login(monkeypatch)

    env = parity._fixture_env(tmp_path, "claude", "claude")

    assert env[TOKEN_ENV] == DISK_TOKEN
    assert env["CLAUDE_CONFIG_DIR"] == str(tmp_path / ".parity-profile" / "claude")


def test_runtime_env_itself_stays_login_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    _disk_login(monkeypatch)

    assert TOKEN_ENV not in parity.runtime_env(tmp_path, "claude")


def test_real_home_run_uses_the_cli_login_and_gets_no_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.setenv(parity.REAL_HOME_ENV, "1")
    _disk_login(monkeypatch)

    assert TOKEN_ENV not in parity._fixture_env(tmp_path, "claude", "claude")


def test_copilot_run_gets_no_claude_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    _disk_login(monkeypatch)

    assert TOKEN_ENV not in parity._fixture_env(tmp_path, "copilot", "copilot")


@pytest.mark.parametrize(
    ("name", "value"),
    [("ANTHROPIC_API_KEY", "operator-key"), (TOKEN_ENV, "operator-token")],
)
def test_an_exported_credential_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.setenv(name, value)
    _disk_login(monkeypatch)

    env = parity._fixture_env(tmp_path, "claude", "claude")

    assert env[name] == value
    assert env.get(TOKEN_ENV) != DISK_TOKEN


def test_existing_login_step_stops_the_run_with_an_auth_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: None, probe=True)

    with pytest.raises(parity.IsolatedLoginError, match="needs a token"):
        parity._fixture_env(tmp_path, "claude", "claude")


def test_missing_credential_stops_the_run_with_an_auth_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: None, probe=False)

    with pytest.raises(parity.IsolatedLoginError):
        parity._fixture_env(tmp_path, "claude", "claude")


@pytest.mark.parametrize("blank", ["", "   "])
@pytest.mark.parametrize("name", ["ANTHROPIC_API_KEY", TOKEN_ENV])
def test_blank_credentials_do_not_block_the_stored_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, blank: str
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.setenv(name, blank)
    _disk_login(monkeypatch)

    env = parity._fixture_env(tmp_path, "claude", "claude")

    assert env[TOKEN_ENV] == DISK_TOKEN
    assert "ANTHROPIC_API_KEY" not in env


def test_main_exits_4_before_any_workspace_when_no_login_is_reachable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: None, probe=True)
    monkeypatch.setattr(parity, "verify_worktree_identity", lambda: None)
    started: list[bool] = []
    monkeypatch.setattr(parity, "run_evaluation", lambda **_kwargs: started.append(True))

    assert parity.main([]) == parity.EXIT_AUTH
    assert started == []
    assert "needs a token" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("harnesses", "dry_run", "real_home"),
    [("copilot", False, False), ("claude", True, False), ("claude", False, True)],
)
def test_preflight_skips_runs_that_need_no_isolated_login(
    monkeypatch: pytest.MonkeyPatch, harnesses: str, dry_run: bool, real_home: bool
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    if real_home:
        monkeypatch.setenv(parity.REAL_HOME_ENV, "1")
    set_sources(monkeypatch, "_claude_cli", disk=lambda _env: None, probe=True)

    parity._require_isolated_login(harnesses, "claude", dry_run=dry_run)


def _echoing_run(text: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["claude"], 0, stdout=text, stderr=text)


def _invoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    harness: str,
    printed: str,
) -> tuple[subprocess.CompletedProcess[str], dict[str, str]]:
    """Run `_invoke_runtime` with a child that prints `printed`; return the run and its env."""
    monkeypatch.setattr(parity, "prepare_workspace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(parity, "resolve_cwd", lambda workspace, _cwd: workspace)
    monkeypatch.setattr(parity, "build_argv", lambda *_args: [harness])
    seen: dict[str, str] = {}

    def runner(
        _argv: list[str], *, env: dict[str, str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        seen.update(env)
        return _echoing_run(printed)

    fixture = type("FixtureStub", (), {"cwd": ".", "instructions": {}, "path_local": {}})()
    run, _argv, failure, _listing = parity._invoke_runtime(
        fixture, harness, harness, "model", tmp_path, runner, 1.0, {}, {}
    )
    assert failure is None
    assert run is not None
    return run, seen


def test_invoke_runtime_masks_a_token_the_child_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _disk_login(monkeypatch)

    run, seen = _invoke(tmp_path, monkeypatch, "claude", f"leaked {DISK_TOKEN} here")

    assert seen[TOKEN_ENV] == DISK_TOKEN
    assert DISK_TOKEN not in run.stdout
    assert DISK_TOKEN not in run.stderr
    assert runtime_harness.TOKEN_MASK in run.stdout


def test_invoke_runtime_masks_an_exported_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-operator-key")

    run, seen = _invoke(tmp_path, monkeypatch, "claude", "key=sk-ant-operator-key")

    assert seen["ANTHROPIC_API_KEY"] == "sk-ant-operator-key"
    assert "sk-ant-operator-key" not in run.stdout + run.stderr


@pytest.mark.parametrize(
    "name",
    [
        "COPILOT_GITHUB_TOKEN",
        "GH_TOKEN",
        "GITHUB_TOKEN",
        "COPILOT_PROVIDER_API_KEY",
        "COPILOT_PROVIDER_BEARER_TOKEN",
    ],
)
def test_invoke_runtime_masks_each_copilot_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "copilot-secret-value")

    run, seen = _invoke(tmp_path, monkeypatch, "copilot", "echo copilot-secret-value")

    assert seen[name] == "copilot-secret-value"
    assert "copilot-secret-value" not in run.stdout + run.stderr
    assert runtime_harness.TOKEN_MASK in run.stdout


@pytest.mark.parametrize(
    "name",
    [
        "COPILOT_PROVIDER_TYPE",
        "COPILOT_PROVIDER_BASE_URL",
        "COPILOT_PROVIDER_MODEL_ID",
        "COPILOT_PROVIDER_WIRE_MODEL",
    ],
)
def test_invoke_runtime_leaves_routing_values_readable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "routing-value")

    run, _seen = _invoke(tmp_path, monkeypatch, "copilot", "route routing-value")

    assert run.stdout == "route routing-value"


def test_blank_credentials_do_not_corrupt_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "")
    monkeypatch.setenv("GITHUB_TOKEN", "   ")

    run, _seen = _invoke(tmp_path, monkeypatch, "copilot", "a b c")

    assert run.stdout == "a b c"
    assert run.stderr == "a b c"


def test_a_padded_credential_is_masked_by_its_trimmed_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "  padded-secret\n")

    run, _seen = _invoke(tmp_path, monkeypatch, "copilot", "printed padded-secret ok")

    assert "padded-secret" not in run.stdout
    assert run.stdout == f"printed {runtime_harness.TOKEN_MASK} ok"


def test_a_credential_that_contains_another_is_masked_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "abcdefgh")
    monkeypatch.setenv("GITHUB_TOKEN", "abcdefgh-extended")

    run, _seen = _invoke(tmp_path, monkeypatch, "copilot", "abcdefgh-extended")

    assert run.stdout == runtime_harness.TOKEN_MASK


def test_instruction_listing_failure_record_masks_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "listing-secret")
    monkeypatch.setenv("COPILOT_PROVIDER_TYPE", "anthropic")
    monkeypatch.setattr(parity, "prepare_workspace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(parity, "resolve_cwd", lambda workspace, _cwd: workspace)
    monkeypatch.setattr(parity, "build_argv", lambda *_args: ["copilot"])

    def runner(_argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            ["copilot"], 2, stdout="out listing-secret", stderr="err listing-secret"
        )

    fixture = type("FixtureStub", (), {"cwd": ".", "instructions": {"a": b"x"}, "path_local": {}})()
    run, _argv, failure, _listing = parity._invoke_runtime(
        fixture, "copilot", "copilot", "model", tmp_path, runner, 1.0, {"a": b"x"}, {}
    )

    assert run is None
    assert failure is not None
    recorded = json.dumps(failure)
    assert "listing-secret" not in recorded
    assert runtime_harness.TOKEN_MASK in recorded


def test_output_is_untouched_when_no_credential_was_passed() -> None:
    run = _echoing_run("plain output")

    assert runtime_harness.mask_credentials(run, []) is run
    assert runtime_harness.credential_values("claude", {"PATH": "/bin"}) == []


@pytest.mark.parametrize(
    "path",
    [
        ".claude/settings.json",
        ".claude/hooks/run.py",
        "sub/.claude/settings.local.json",
        ".CLAUDE/settings.json",
        ".git/config",
    ],
)
def test_setup_files_may_not_plant_claude_config(path: str) -> None:
    with pytest.raises(parity_module.ParityConfigError, match="must not write under"):
        parity_module._load_setup_files({path: "{}"}, "fixtures[0].setup_files")


def test_setup_files_accept_ordinary_workspace_paths() -> None:
    files = {"dates.py": "x = 1", "tests/test_dates.py": "", "claude/notes.md": ""}

    assert parity_module._load_setup_files(files, "fixtures[0].setup_files") == files
