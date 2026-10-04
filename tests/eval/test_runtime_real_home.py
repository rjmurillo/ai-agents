"""Opt-in real Claude home for the runtime-parity harness (issue #5404).

The isolated profile has no login, so a keyless run answers "Not logged in".
`--real-home` hands Claude the operator's own HOME. The harness creates no
link to, copy of, or read of a credential file, and the report records that
`~/.claude` instructions load ambiently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import parity, runtime_harness

ENV = runtime_harness.REAL_HOME_ENV


@pytest.fixture
def operator_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "operator-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return home


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return workspace


def test_default_run_isolates_home_and_config(
    tmp_path: Path, operator_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV, raising=False)
    env = runtime_harness.runtime_env(_workspace(tmp_path), "claude")
    assert env["HOME"] != str(operator_home)
    assert "CLAUDE_CONFIG_DIR" in env


def test_opt_in_passes_the_real_home_and_leaves_config_unset(
    tmp_path: Path, operator_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV, "1")
    env = runtime_harness.runtime_env(_workspace(tmp_path), "claude")
    assert env["HOME"] == str(operator_home)
    assert "CLAUDE_CONFIG_DIR" not in env
    assert ENV not in env


def test_opt_in_creates_no_symlink_and_no_credential_file(
    tmp_path: Path, operator_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV, "1")
    workspace = _workspace(tmp_path)
    runtime_harness.runtime_env(workspace, "claude")
    tree = list(workspace.rglob("*"))
    assert [p for p in tree if p.is_symlink()] == []
    assert [p for p in tree if "credentials" in p.name or p.name == "auth.json"] == []


def test_opt_in_does_not_touch_other_harnesses(
    tmp_path: Path, operator_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV, "1")
    env = runtime_harness.runtime_env(_workspace(tmp_path), "codex")
    assert env["HOME"] != str(operator_home)


@pytest.mark.parametrize("value", ["", "0", "true", "yes"])
def test_only_the_exact_opt_in_value_enables_it(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV, value)
    assert runtime_harness.real_home_enabled() is False


def test_cli_flag_is_off_by_default() -> None:
    parser = parity._parser()
    assert parser.parse_args(["--real-home"]).real_home is True
    assert parser.parse_args([]).real_home is False


def test_report_records_the_ambient_home_confound(monkeypatch: pytest.MonkeyPatch) -> None:
    kwargs = {
        "model": "haiku",
        "output": Path("o.json"),
        "claude_bin": "claude",
        "copilot_bin": "copilot",
        "runner": lambda *args, **kwargs: None,
        "timeout": 1.0,
        "dry_run": True,
        "fixture_count": 0,
        "source_commit": "x",
        "instructions_ref": None,
        "instructions_ref_sha": None,
        "harnesses": "claude",
    }
    monkeypatch.setattr(parity, "_probe_versions", lambda *args, **kw: {})
    monkeypatch.delenv(ENV, raising=False)
    assert "ambient_home" not in parity._base_report(**kwargs)
    monkeypatch.setenv(ENV, "1")
    assert parity._base_report(**kwargs)["ambient_home"]["claude_home"] == "real"


def test_the_claude_cli_grader_uses_the_real_home_only_under_the_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib.util
    import sys

    eval_dir = str(Path(__file__).resolve().parents[2] / "scripts" / "eval")
    sys.path.insert(0, eval_dir)
    try:
        import _claude_cli as claude_cli
    finally:
        sys.path.remove(eval_dir)
    assert importlib.util.find_spec("_claude_cli") is not None
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    provider = claude_cli._ClaudeCLIProvider()
    isolated = provider._build_env(tmp_path / "profile")
    assert isolated["CLAUDE_CONFIG_DIR"] == str(tmp_path / "profile")
    with pytest.raises(RuntimeError, match="CLAUDE_CODE_OAUTH_TOKEN"):
        provider._require_subscription_credential(isolated)
    monkeypatch.setenv(ENV, "1")
    real = provider._build_env(tmp_path / "profile")
    assert real["HOME"] == str(tmp_path)
    assert "CLAUDE_CONFIG_DIR" not in real
    provider._require_subscription_credential(real)
