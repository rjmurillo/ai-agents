"""Validate Pi responses, isolated environments, and command discovery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.e2e.pi_package_runtime_cases import (
    _PLUGIN_ROOT_ENV_KEYS,
    get_commands_line,
    package_skill_paths,
    pi_binary,
    pi_env,
    skill_script_env,
)


def _response(
    *commands: dict[str, object], success: bool = True, command: str = "get_commands"
) -> str:
    return json.dumps(
        {
            "id": "1",
            "type": "response",
            "command": command,
            "success": success,
            "data": {"commands": list(commands)},
        }
    )


def _skill(name: str, path: Path, origin: str = "package") -> dict[str, object]:
    return {
        "name": f"skill:{name}",
        "source": "skill",
        "sourceInfo": {"path": str(path), "origin": origin},
    }


def test_package_skill_paths_keeps_package_skills_under_the_repo(tmp_path: Path) -> None:
    line = _response(_skill("a", tmp_path / "a" / "SKILL.md"))

    assert package_skill_paths(line, tmp_path) == {"a": tmp_path / "a" / "SKILL.md"}


@pytest.mark.parametrize(
    "command",
    [
        lambda root: _skill("a", Path("/elsewhere/a/SKILL.md")),
        lambda root: _skill("a", root / "a" / "SKILL.md", origin="top-level"),
        lambda root: {
            "name": "a",
            "source": "skill",
            "sourceInfo": {"path": "x", "origin": "package"},
        },
        lambda root: {"name": "skill:a", "source": "extension", "sourceInfo": {"path": "x"}},
        lambda root: {"name": "skill:a", "source": "skill"},
    ],
    ids=["outside-repo", "not-package", "no-prefix", "not-a-skill", "no-source-info"],
)
def test_package_skill_paths_ignores_skills_not_from_this_package(tmp_path: Path, command) -> None:
    assert package_skill_paths(_response(command(tmp_path)), tmp_path) == {}


@pytest.mark.parametrize(
    "line",
    [
        _response(success=False),
        _response(command="other"),
        "{}",
    ],
)
def test_package_skill_paths_rejects_an_unexpected_response(line: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unexpected Pi response"):
        package_skill_paths(line, tmp_path)


def test_package_skill_paths_rejects_non_json(tmp_path: Path) -> None:
    with pytest.raises(json.JSONDecodeError):
        package_skill_paths("not json", tmp_path)


def test_pi_env_isolates_config_home_and_drops_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("PI_CODING_AGENT_DIR", "/real/config")

    env = pi_env(tmp_path / "c", tmp_path / "h")

    assert env["PI_CODING_AGENT_DIR"] == str(tmp_path / "c")
    assert env["HOME"] == str(tmp_path / "h")
    assert env["PI_OFFLINE"] == "1"
    assert "OPENAI_API_KEY" not in env


def test_skill_script_env_drops_plugin_root_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _PLUGIN_ROOT_ENV_KEYS:
        monkeypatch.setenv(key, "/somewhere")

    env = skill_script_env()

    assert not set(_PLUGIN_ROOT_ENV_KEYS) & set(env)


def test_pi_binary_prefers_pi_bin_and_returns_none_when_it_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "fake-pi"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PI_BIN", str(fake))
    assert pi_binary() == str(fake)

    monkeypatch.setenv("PI_BIN", str(tmp_path / "absent"))
    assert pi_binary() is None


def test_pi_binary_finds_pi_on_path_when_pi_bin_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "pi"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.delenv("PI_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert pi_binary() == str(fake)


def test_pi_binary_returns_none_when_pi_bin_is_unset_and_path_has_no_pi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PI_BIN", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert pi_binary() is None


def test_get_commands_line_skips_a_banner_before_the_response() -> None:
    response = _response()

    assert get_commands_line(f"pi 1.2.0 ready\n{{not json\n{response}\n") == response


@pytest.mark.parametrize(
    "stdout",
    ["", "banner only\n", _response(command="other"), "[1, 2]\n"],
    ids=["empty", "banner-only", "other-command", "non-object-json"],
)
def test_get_commands_line_fails_clearly_when_no_response_is_present(stdout: str) -> None:
    with pytest.raises(ValueError, match="no get_commands response in Pi stdout, tail:"):
        get_commands_line(stdout)
