"""Always-on tests for ``muse_load_probe.py``, the helpers the Muse Code load test uses.

They need no ``muse`` CLI and no login. They cover the reply-code rule, the
prompt, the install checks, the stub-driven timeouts, and the loud failures, so
the live test in ``test_muse_agents_load.py`` is not the only check on them.
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
    MUSE_AGENTS,
    allowlisted_env,
    build_prompt,
    check_prerequisites,
    parse_events,
    require_user_install,
    run_muse,
    shipped_agent_names,
    skill_script_found_lib,
    spawn_code,
    spawned_agents,
    write_control_agent,
)


def _stub(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_prompt_numbers_every_agent_and_never_prints_a_code() -> None:
    names = ["a-one", "b-two"]
    prompt = build_prompt(names, "/x/s.py")
    assert "- 00: a-one" in prompt and "- 01: b-two" in prompt
    assert not any(spawn_code(i) in prompt for i in range(len(names)))


def test_codes_are_distinct_and_never_prefix_each_other() -> None:
    codes = [spawn_code(i) for i in range(40)]
    assert len(set(codes)) == 40
    assert not any(a != b and a in b for a in codes for b in codes)


def test_parse_events_ignores_non_json_and_non_objects() -> None:
    out = '{"type": "x"}\nnot json\n[1, 2]\n\n{"type": "y"}\n'
    assert [e["type"] for e in parse_events(out)] == ["x", "y"]


def test_spawned_agents_counts_an_agent_whose_child_replied_with_its_code() -> None:
    events = [{"type": "result", "text": f"reply {spawn_code(1)}"}]
    assert spawned_agents(events, ["architect", "critic"]) == {"critic"}


def test_spawned_agents_ignores_a_spawn_request_that_holds_only_the_formula() -> None:
    objective = "reply with the single word code-N, where N is 1000 plus 17 times 03"
    events = [{"type": "subagent_spawn", "role": "architect", "objective": objective}]
    assert spawned_agents(events, ["architect"]) == set()


def test_spawned_agents_ignores_a_request_followed_by_a_failed_result() -> None:
    events = [
        {"type": "subagent_spawn", "agent": "architect", "objective": "reply with code-N"},
        {"type": "subagent_result", "resultStatus": "failed", "agentPath": "architect"},
    ]
    assert spawned_agents(events, ["architect"]) == set()


def test_spawned_agents_ignores_a_roster_event_that_lists_the_names() -> None:
    events = [{"type": "init", "subagents": ["architect", "critic"]}]
    assert spawned_agents(events, ["architect", "critic"]) == set()


def test_spawned_agents_does_not_confuse_code_numbers() -> None:
    events = [{"text": spawn_code(10)}]
    assert spawned_agents(events, [f"a{i}" for i in range(12)]) == {"a10"}


def test_control_reply_is_counted_so_its_assertion_can_fail() -> None:
    events = [{"text": spawn_code(1)}]
    assert spawned_agents(events, ["architect", CONTROL_NAME]) == {CONTROL_NAME}


def test_skill_script_check_needs_usage_and_no_missing_lib() -> None:
    assert skill_script_found_lib("usage: get_pr_checks.py [-h]")
    assert not skill_script_found_lib("Plugin lib directory not found: /x")
    assert not skill_script_found_lib("usage: get_pr_checks.py ... Plugin lib directory not found")
    assert not skill_script_found_lib("nothing relevant")


def test_prompt_asks_for_the_skill_script() -> None:
    assert "/x/get_pr_checks.py --help" in build_prompt(["a"], "/x/get_pr_checks.py")


def test_control_agent_has_the_extra_key(tmp_path: Path) -> None:
    path = write_control_agent(tmp_path / "agents")
    assert "readonly: true" in path.read_text("utf-8")
    assert path.name == f"{CONTROL_NAME}.md"


def _install_user_root(root: Path, *, agents: bool = True, lib: bool = True) -> None:
    script = root / "skills" / "github" / "scripts" / "pr" / "get_pr_checks.py"
    script.parent.mkdir(parents=True)
    script.write_text("# stub\n", encoding="utf-8")
    if lib:
        (root / "lib" / "github_core").mkdir(parents=True)
    if agents:
        (root / "agents").mkdir(parents=True)
        for name in shipped_agent_names():
            shutil.copyfile(MUSE_AGENTS / f"{name}.md", root / "agents" / f"{name}.md")


def test_a_complete_user_install_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _install_user_root(tmp_path / "muse")
    assert require_user_install().endswith("get_pr_checks.py")


def test_missing_user_skill_install_fails_clearly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: no installed skills"):
        require_user_install()


def test_missing_user_lib_fails_clearly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _install_user_root(tmp_path / "muse", lib=False)
    with pytest.raises(pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: no installed lib"):
        require_user_install()


def test_a_missing_shipped_agent_fails_clearly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _install_user_root(tmp_path / "muse")
    (tmp_path / "muse" / "agents" / "critic.md").unlink()
    with pytest.raises(
        pytest.fail.Exception, match=r"1 shipped agents are missing or differ.*critic"
    ):
        require_user_install()


def test_a_stale_same_name_agent_fails_clearly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _install_user_root(tmp_path / "muse")
    (tmp_path / "muse" / "agents" / "critic.md").write_text("an older critic\n", encoding="utf-8")
    with pytest.raises(
        pytest.fail.Exception, match=r"1 shipped agents are missing or differ.*critic"
    ):
        require_user_install()


def test_the_script_path_is_quoted_in_the_prompt() -> None:
    prompt = build_prompt(["a"], "/home/Jane Doe/.config/muse/skills/x.py")
    assert "python3 -I '/home/Jane Doe/.config/muse/skills/x.py' --help" in prompt


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


def test_run_muse_returns_the_output_of_a_finished_run(tmp_path: Path) -> None:
    fake = _stub(tmp_path / "muse", "echo out; echo err >&2; exit 3")
    result = run_muse([str(fake)], cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, timeout=10)
    assert (result.returncode, result.stdout.strip(), result.stderr.strip()) == (3, "out", "err")


def test_run_muse_timeout_saves_the_partial_output_and_names_the_file(tmp_path: Path) -> None:
    fake = _stub(tmp_path / "muse", "echo partial-line; sleep 30")
    saved = tmp_path / "partial.txt"
    with pytest.raises(
        pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: .*exceeded 1s.*partial.txt"
    ):
        run_muse(
            [str(fake)],
            cwd=tmp_path,
            env={"PATH": "/usr/bin:/bin"},
            timeout=1,
            save_to=saved,
        )
    assert "partial-line" in saved.read_text("utf-8")


def test_missing_muse_fails_with_a_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: .*not on PATH"):
        check_prerequisites()


def test_not_logged_in_fails_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _stub(tmp_path / "muse", "echo 'muse usage: not logged in' >&2; exit 1")
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))
    with pytest.raises(
        pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: Muse Code is not logged in"
    ):
        check_prerequisites()


def test_no_allowance_account_fails_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`muse usage` exits 0 and prints no_allowance when signed in without an allowance."""
    fake = _stub(tmp_path / "muse", "echo 'No subscription allowance (no_allowance)'")
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))
    with pytest.raises(
        pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: .*no subscription allowance"
    ):
        check_prerequisites()


def test_a_logged_in_account_with_allowance_passes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _stub(tmp_path / "muse", "echo 'Plan: pro, 90 percent left'")
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))
    assert check_prerequisites() == str(fake)


@pytest.mark.skipif(shutil.which("setsid") is None, reason="setsid is required")
def test_run_muse_gives_up_on_a_descendant_that_left_the_group(tmp_path: Path) -> None:
    """A child in its own session keeps the pipes open; the drain must not hang."""
    fake = _stub(tmp_path / "muse", "echo partial-line\nsetsid sleep 30 &\nsleep 30")
    saved = tmp_path / "partial.txt"
    with pytest.raises(pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: .*exceeded 1s"):
        run_muse([str(fake)], cwd=tmp_path, env={"PATH": "/usr/bin:/bin"}, timeout=1, save_to=saved)
    assert "partial-line" in saved.read_text("utf-8")
