"""Always-on tests for ``muse_load_probe.py``, the helpers the Muse Code load test uses.

They need no ``muse`` CLI and no login. They cover the spawn-record rule, the
prompt, the scratch install, and the loud failures, so the live test in
``test_muse_agents_load.py`` is not the only check on them.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

_E2E_DIR = Path(__file__).resolve().parent
if str(_E2E_DIR) not in sys.path:
    sys.path.insert(0, str(_E2E_DIR))

from muse_load_probe import (  # noqa: E402
    CONTROL_NAME,
    allowlisted_env,
    build_prompt,
    check_prerequisites,
    install_agents,
    parse_events,
    require_user_skill_install,
    skill_script_found_lib,
    spawn_token,
    spawned_agents,
)


def test_prompt_numbers_every_agent_and_never_prints_a_whole_token() -> None:
    names = ["a-one", "b-two"]
    prompt = build_prompt(names, "/x/s.py")
    assert "- 00: a-one" in prompt and "- 01: b-two" in prompt
    assert not any(spawn_token(i) in prompt for i in range(len(names)))


def test_parse_events_ignores_non_json_and_non_objects() -> None:
    out = '{"type": "x"}\nnot json\n[1, 2]\n\n{"type": "y"}\n'
    assert [e["type"] for e in parse_events(out)] == ["x", "y"]


def test_spawned_agents_counts_an_agent_whose_child_replied_with_its_token() -> None:
    events = [{"type": "result", "text": f"reply {spawn_token(1)}"}]
    assert spawned_agents(events, ["architect", "critic"]) == {"critic"}


def test_spawned_agents_ignores_a_spawn_request_with_no_reply() -> None:
    events = [{"type": "subagent_spawn", "agent": "architect"}]
    assert spawned_agents(events, ["architect"]) == set()


def test_spawned_agents_ignores_a_request_followed_by_a_failed_result() -> None:
    events = [
        {"type": "subagent_spawn", "agent": "architect"},
        {"type": "subagent_result", "resultStatus": "failed", "agentPath": "architect"},
    ]
    assert spawned_agents(events, ["architect"]) == set()


def test_spawned_agents_ignores_a_roster_event_that_lists_the_names() -> None:
    events = [{"type": "init", "subagents": ["architect", "critic"]}]
    assert spawned_agents(events, ["architect", "critic"]) == set()


def test_spawned_agents_does_not_confuse_token_numbers() -> None:
    events = [{"text": spawn_token(10)}]
    assert spawned_agents(events, [f"a{i}" for i in range(12)]) == {"a10"}


def test_control_reply_is_counted_so_its_assertion_can_fail() -> None:
    events = [{"text": spawn_token(1)}]
    assert spawned_agents(events, ["architect", CONTROL_NAME]) == {CONTROL_NAME}


def test_skill_script_check_needs_usage_and_no_missing_lib() -> None:
    assert skill_script_found_lib("usage: get_pr_checks.py [-h]")
    assert not skill_script_found_lib("Plugin lib directory not found: /x")
    assert not skill_script_found_lib("usage: get_pr_checks.py ... Plugin lib directory not found")
    assert not skill_script_found_lib("nothing relevant")


def test_prompt_asks_for_the_skill_script() -> None:
    assert "/x/get_pr_checks.py --help" in build_prompt(["a"], "/x/get_pr_checks.py")


def test_missing_user_skill_install_fails_clearly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: no installed skills"):
        require_user_skill_install()


def test_install_agents_adds_the_control_and_every_shipped_agent(tmp_path: Path) -> None:
    names = install_agents(tmp_path / "agents")
    files = sorted(p.stem for p in (tmp_path / "agents").glob("*.md"))
    assert files == sorted([*names, CONTROL_NAME])
    assert "readonly: true" in (tmp_path / "agents" / f"{CONTROL_NAME}.md").read_text("utf-8")


def test_env_allowlist_keeps_only_what_muse_needs() -> None:
    env = allowlisted_env(
        {
            "HOME": "/h",
            "PATH": "/p",
            "XDG_CONFIG_HOME": "/x",
            "MUSE_LOG": "1",
            "LC_ALL": "C",
            "GH_TOKEN": "a",
            "AWS_SECRET_ACCESS_KEY": "b",
            "AWS_ACCESS_KEY_ID": "c",
            "SSH_AUTH_SOCK": "d",
            "DATABASE_URL": "e",
        }
    )
    assert env == {
        "HOME": "/h",
        "PATH": "/p",
        "XDG_CONFIG_HOME": "/x",
        "MUSE_LOG": "1",
        "LC_ALL": "C",
    }


def test_missing_muse_fails_with_a_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: .*not on PATH"):
        check_prerequisites()


def test_not_logged_in_fails_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = tmp_path / "muse"
    fake.write_text("#!/bin/sh\necho 'muse usage: not logged in' >&2\nexit 1\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))
    with pytest.raises(
        pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: Muse Code is not logged in"
    ):
        check_prerequisites()


def test_no_allowance_account_fails_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`muse usage` exits 0 and prints no_allowance when signed in without an allowance."""
    fake = tmp_path / "muse"
    fake.write_text("#!/bin/sh\necho 'No subscription allowance (no_allowance)'\nexit 0\n", "utf-8")
    fake.chmod(0o755)
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))
    with pytest.raises(
        pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: .*no subscription allowance"
    ):
        check_prerequisites()
