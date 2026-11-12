"""Always-on tests for ``muse_load_probe.py``, the helpers the Muse Code load test uses.

They need no ``muse`` CLI and no login. They cover the reply-code rule, the
prompt, the install checks, the stub-driven timeouts, and the loud failures, so
the live test in ``test_muse_agents_load.py`` is not the only check on them.
"""

from __future__ import annotations

import json
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
    SKILL_NAME,
    allowlisted_env,
    build_prompt,
    check_prerequisites,
    child_ran_definition,
    child_replies,
    parse_events,
    require_user_install,
    run_installed_script,
    run_muse,
    shipped_agent_names,
    skill_loaded,
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
    prompt = build_prompt(names)
    assert "- 00: a-one" in prompt and "- 01: b-two" in prompt
    assert not any(spawn_code(i) in prompt for i in range(len(names)))


def test_codes_are_distinct_and_never_prefix_each_other() -> None:
    codes = [spawn_code(i) for i in range(40)]
    assert len(set(codes)) == 40
    assert not any(a != b and a in b for a in codes for b in codes)


def _result(tool: str, body: dict[str, object]) -> dict[str, object]:
    """A `tool.result` record shaped like the Muse Code 1.4.15 sample."""
    return {
        "payload_type": "tool.result",
        "payload": {
            "correlation_facts": {"outcome": "success", "tool_name": tool},
            "kind": "tool_result",
            "text": json.dumps(body),
        },
    }


def _spawn(child: str, index: int, role: str, status: str = "accepted") -> dict[str, object]:
    path = f"main/{index:02d} {role}/{index + 1}"
    return _result("subagent_spawn", {"status": status, "subagent_id": child, "agent_path": path})


def _wait(child: str, summary: str, status: str = "ready") -> dict[str, object]:
    return _result("subagent_wait", {"status": status, "subagent_id": child, "summary": summary})


NAMES = ["architect", "critic", "debug"]


def test_parse_events_keeps_only_records_with_a_payload_type() -> None:
    out = (
        '{"payload_type": "x", "payload": {}}\nnot json\n[1, 2]\n\n'
        '{"usage": "get_pr_checks.py"}\n{"payload_type": "y"}\n{"payload_type": 3}\n'
    )
    assert [e["payload_type"] for e in parse_events(out)] == ["x", "y"]


def test_spawned_agents_counts_a_child_that_replied_with_its_code() -> None:
    events = [_spawn("c1", 1, "critic"), _wait("c1", spawn_code(1))]
    assert spawned_agents(events, NAMES) == {"critic"}


def test_spawned_agents_matches_the_real_run_shape_for_every_role() -> None:
    events = []
    for i, name in enumerate(NAMES):
        events += [_spawn(f"c{i}", i, name), _wait(f"c{i}", f"{spawn_code(i)}.")]
    assert spawned_agents(events, NAMES) == set(NAMES)


def test_spawned_agents_ignores_a_code_the_lead_wrote_into_plain_text() -> None:
    lead_text = {"payload_type": "run.output.delta", "payload": {"text": spawn_code(1)}}
    assert spawned_agents([lead_text], NAMES) == set()


def test_spawned_agents_ignores_a_code_in_a_tool_result_of_another_tool() -> None:
    events = [_spawn("c1", 1, "critic"), _result("bash", {"summary": spawn_code(1)})]
    assert spawned_agents(events, NAMES) == set()


def test_spawned_agents_ignores_a_rejected_spawn() -> None:
    rejected = _result(
        "subagent_spawn", {"status": "rejected", "cause": "agent_definition_invalid"}
    )
    assert spawned_agents([rejected, _wait("c1", spawn_code(1))], NAMES) == set()


def test_spawned_agents_ignores_a_spawn_request_with_no_wait_result() -> None:
    assert spawned_agents([_spawn("c1", 1, "critic")], NAMES) == set()


def test_spawned_agents_ignores_a_wait_that_is_not_ready() -> None:
    events = [_spawn("c1", 1, "critic"), _wait("c1", spawn_code(1), status="failed")]
    assert spawned_agents(events, NAMES) == set()


def test_spawned_agents_ignores_a_wait_for_a_child_that_was_never_spawned() -> None:
    assert spawned_agents([_wait("ghost", spawn_code(1))], NAMES) == set()


def test_the_code_not_the_label_decides_which_role_a_child_answered_for() -> None:
    events = [_spawn("c1", 1, "critic"), _wait("c1", spawn_code(2))]
    assert spawned_agents(events, NAMES) == {"debug"}


def test_child_replies_ignores_the_label_the_lead_chose() -> None:
    for path in ("main/architect/1", "main/lead-01-critic/2", "main/anything at all/9", "x"):
        spawn = _result(
            "subagent_spawn", {"status": "accepted", "subagent_id": "c1", "agent_path": path}
        )
        assert child_replies([spawn, _wait("c1", spawn_code(1))], NAMES) == {"critic": []}


def test_child_replies_ignores_a_summary_with_two_codes() -> None:
    both = f"{spawn_code(0)} and {spawn_code(1)}"
    assert child_replies([_spawn("c1", 0, "architect"), _wait("c1", both)], NAMES) == {}


def test_child_replies_ignores_unparseable_wait_text() -> None:
    bad = {
        "payload_type": "tool.result",
        "payload": {"correlation_facts": {"tool_name": "subagent_wait"}, "text": "not json"},
    }
    assert (
        child_replies([_spawn("c1", 1, "critic"), bad, {"payload_type": "tool.result"}], NAMES)
        == {}
    )


def test_child_replies_returns_the_evidence_refs_of_the_wait_result() -> None:
    wait = _result(
        "subagent_wait",
        {
            "status": "ready",
            "subagent_id": "c1",
            "summary": spawn_code(1),
            "evidence_refs": ["/x/s.jsonl", 3],
        },
    )
    assert child_replies([_spawn("c1", 1, "critic"), wait], NAMES) == {"critic": ["/x/s.jsonl"]}


def _session_with(tmp_path: Path, body: str) -> str:
    """Write a session file that holds ``body`` as a doubly-encoded log line would."""
    inner = json.dumps({"text": body})
    outer = json.dumps({"record_json": inner})
    path = tmp_path / "session.jsonl"
    path.write_text(outer + "\n", encoding="utf-8")
    return str(path)


def _shipped_body(name: str) -> str:
    return (MUSE_AGENTS / f"{name}.md").read_text("utf-8").split("---", 2)[-1]


def test_child_ran_definition_finds_the_shipped_body_in_a_nested_log_line(tmp_path: Path) -> None:
    ref = _session_with(tmp_path, "intro\n" + _shipped_body("critic") + "\ntail")
    assert child_ran_definition([ref], "critic")


def test_child_ran_definition_rejects_another_agents_body(tmp_path: Path) -> None:
    ref = _session_with(tmp_path, _shipped_body("architect"))
    assert not child_ran_definition([ref], "critic")


def test_child_ran_definition_is_false_for_missing_files_and_no_refs(tmp_path: Path) -> None:
    assert not child_ran_definition([str(tmp_path / "gone.jsonl")], "critic")
    assert not child_ran_definition([], "critic")


def test_child_ran_definition_accepts_every_shipped_agent(tmp_path: Path) -> None:
    for name in shipped_agent_names():
        assert child_ran_definition([_session_with(tmp_path, _shipped_body(name))], name), name


def test_spawned_agents_does_not_confuse_code_numbers() -> None:
    names = [f"a{i}" for i in range(12)]
    events = [_spawn("c10", 10, "a10"), _wait("c10", spawn_code(10))]
    assert spawned_agents(events, names) == {"a10"}


def test_control_reply_is_counted_so_its_assertion_can_fail() -> None:
    events = [_spawn("c1", 1, CONTROL_NAME), _wait("c1", spawn_code(1))]
    assert spawned_agents(events, ["architect", CONTROL_NAME]) == {CONTROL_NAME}


def test_skill_script_check_needs_usage_and_no_missing_lib() -> None:
    assert skill_script_found_lib("usage: get_pr_checks.py [-h]")
    assert not skill_script_found_lib("Plugin lib directory not found: /x")
    assert not skill_script_found_lib("usage: get_pr_checks.py ... Plugin lib directory not found")
    assert not skill_script_found_lib("nothing relevant")


def test_prompt_asks_for_the_skill_by_name_and_never_for_a_script() -> None:
    prompt = build_prompt(["a"])
    assert f"load the `{SKILL_NAME}` skill with your `read_skill` tool" in prompt
    assert "python3" not in prompt


def _read_skill(text: str, outcome: str = "success") -> dict[str, object]:
    return _result_raw("read_skill", text, outcome)


def _result_raw(tool: str, text: str, outcome: str = "success") -> dict[str, object]:
    return {
        "payload_type": "tool.result",
        "payload": {"correlation_facts": {"outcome": outcome, "tool_name": tool}, "text": text},
    }


def test_skill_loaded_needs_a_successful_read_skill_result_from_the_user_root() -> None:
    root = Path("/u/muse")
    ok = '<read-skill-result name="github" status="ok"> path: /u/muse/skills/github/SKILL.md'
    assert skill_loaded([_read_skill(ok)], "github", root)
    assert not skill_loaded([_read_skill(ok, outcome="failure")], "github", root)
    other = '<read-skill-result name="github" status="ok"> path: /elsewhere/skills/github/SKILL.md'
    assert not skill_loaded([_read_skill(other)], "github", root)
    memory = '<read-skill-result name="memory" status="ok"> path: /u/muse/skills/memory/SKILL.md'
    assert not skill_loaded([_read_skill(memory)], "github", root)
    missing = '<read-skill-result name="github" status="missing"> path: /u/muse/skills/github'
    assert not skill_loaded([_read_skill(missing)], "github", root)
    assert not skill_loaded([_result_raw("bash", ok)], "github", root)
    assert not skill_loaded([{"payload_type": "tool.result", "payload": "x"}, {}], "github", root)


def test_run_installed_script_returns_stdout_and_stderr(tmp_path: Path) -> None:
    script = tmp_path / "s.py"
    script.write_text(
        "import sys\nprint('usage: get_pr_checks.py')\nsys.stderr.write('e')\n", "utf-8"
    )
    assert run_installed_script(str(script)).startswith("usage: get_pr_checks.py")


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


def test_no_allowance_account_still_passes_the_prerequisite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`muse usage` exits 0 and prints no_allowance, yet that login ran a model call."""
    fake = _stub(tmp_path / "muse", "echo 'No subscription allowance (no_allowance)'")
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))
    assert check_prerequisites() == str(fake)


def test_a_failing_usage_call_that_mentions_no_allowance_is_still_not_logged_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _stub(tmp_path / "muse", "echo 'No subscription allowance (no_allowance)' >&2; exit 1")
    monkeypatch.setattr(shutil, "which", lambda _name: str(fake))
    with pytest.raises(
        pytest.fail.Exception, match=r"MUSE_NOT_VERIFIED: Muse Code is not logged in"
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
