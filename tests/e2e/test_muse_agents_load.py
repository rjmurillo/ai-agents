"""Muse Code agent load test (issue #7226, ADR-115 Decision 8 amendment).

Muse Code starts when an agent definition is invalid, but the lead cannot spawn
that agent (https://dev.meta.ai/docs/muse-code/agents). No run without a login
shows whether an agent loads, so this test needs one.

The live test (markers ``smoke`` and ``muse``) installs ``src/muse/agents`` plus
a control agent with an unknown key into a scratch ``XDG_CONFIG_HOME/muse/agents``,
runs ``muse exec --json --trust-workspace`` with a prompt that asks the lead to
spawn each named agent once, and asserts from the JSONL events that every
shipped agent was spawned and the control was not.

  - Without ``RUN_CLI_E2E=1`` it skips with a reason that starts with
    ``MUSE_NOT_VERIFIED:``.
  - With ``RUN_CLI_E2E=1`` it fails, never skips, when ``muse`` is not on PATH or
    ``muse usage`` reports no login.

Not verified: the shape of the JSONL events. Nothing here has run with a login,
so ``spawned_agents`` reads spawn records by a loose rule (see its docstring).
The owner's run, recorded in the pull request, settles whether that rule fits
Muse Code's real events. The helper tests below cover the rule, not the CLI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MUSE_AGENTS = REPO_ROOT / "src" / "muse" / "agents"
CONTROL_NAME = "zz-unknown-key-control"
NOT_VERIFIED = "MUSE_NOT_VERIFIED:"
_USAGE_TIMEOUT_SECONDS = 30
_EXEC_TIMEOUT_SECONDS = 600
_RUN = os.environ.get("RUN_CLI_E2E") == "1"
_REFUSAL_WORDS = ("error", "unknown", "invalid", "not found", "unavailable", "refus")
_SECRET_SUFFIXES = ("_TOKEN", "_API_KEY", "_SECRET", "_PASSWORD", "_PAT", "_CREDENTIALS")


def shipped_agent_names() -> list[str]:
    return sorted(p.stem for p in MUSE_AGENTS.glob("*.md"))


def build_prompt(names: list[str]) -> str:
    """Return the prompt: spawn each named agent once with a one-word objective."""
    listing = "\n".join(f"- {name}" for name in names)
    return (
        "For each agent role below, spawn that exact agent once. Give it this "
        "objective: reply with the single word ok. Spawn one at a time. If a role "
        "cannot be spawned, say so and go on to the next. Do not use any other "
        "role and do not edit files. When done, list which roles you spawned.\n"
        f"{listing}"
    )


def parse_events(stdout: str) -> list[dict[str, object]]:
    """Return the JSON objects among the lines of ``stdout``; non-JSON lines are ignored."""
    events: list[dict[str, object]] = []
    for line in stdout.splitlines():
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            events.append(loaded)
    return events


def spawned_agents(events: list[dict[str, object]], names: list[str]) -> set[str]:
    """Return the names of ``names`` that a spawn record shows as spawned.

    A spawn record is an event whose serialized text mentions ``spawn`` or
    ``subagent`` (case-insensitive) and the agent name as a whole JSON string
    value. A record that also carries an error word (``error``, ``unknown``,
    ``invalid``, ``not found``, ``unavailable``, ``refus``) is a refusal, not a
    spawn. Looser than a schema because Muse Code publishes no event schema.
    """
    spawned: set[str] = set()
    for event in events:
        text = json.dumps(event).lower()
        if "spawn" not in text and "subagent" not in text:
            continue
        if any(word in text for word in _REFUSAL_WORDS):
            continue
        for name in names:
            if f'"{name}"' in text:
                spawned.add(name)
    return spawned


def write_control_agent(agents_dir: Path) -> Path:
    path = agents_dir / f"{CONTROL_NAME}.md"
    path.write_text(
        f"---\nname: {CONTROL_NAME}\ndescription: Control agent with an unknown key\n"
        "readonly: true\n---\nReply ok.\n",
        encoding="utf-8",
    )
    return path


def install_agents(agents_dir: Path) -> list[str]:
    agents_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(MUSE_AGENTS.glob("*.md")):
        shutil.copyfile(src, agents_dir / src.name)
    write_control_agent(agents_dir)
    return shipped_agent_names()


def _scrub(env: dict[str, str]) -> dict[str, str]:
    """Drop tokens and keys: the run uses ``--trust-workspace`` and the lead can run shell."""
    return {
        k: v
        for k, v in env.items()
        if not k.upper().endswith(_SECRET_SUFFIXES)
        and k.upper() not in {"GH_TOKEN", "GITHUB_TOKEN"}
    }


def check_prerequisites() -> str:
    """Return the path of ``muse``; fail with a clear message when it or a login is missing."""
    muse = shutil.which("muse")
    if muse is None:
        pytest.fail(
            f"{NOT_VERIFIED} RUN_CLI_E2E=1 but `muse` is not on PATH. Install Muse Code "
            "(https://dev.meta.ai/docs/muse-code) and put it on PATH."
        )
    try:
        usage = subprocess.run(
            [muse, "usage"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_USAGE_TIMEOUT_SECONDS,
            check=False,
            env=_scrub(dict(os.environ)),
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{NOT_VERIFIED} `muse usage` exceeded {_USAGE_TIMEOUT_SECONDS}s")
    if usage.returncode != 0:
        detail = (usage.stdout + usage.stderr).strip()[-300:]
        pytest.fail(
            f"{NOT_VERIFIED} Muse Code is not logged in (`muse usage` exit {usage.returncode}: "
            f"{detail}). Run `muse login`, then rerun this test."
        )
    return muse


# Helper tests (always run, no CLI) -------------------------------------------


def test_prompt_names_every_agent_once() -> None:
    prompt = build_prompt(["a-one", "b-two"])
    assert prompt.count("- a-one") == 1 and prompt.count("- b-two") == 1


def test_parse_events_ignores_non_json_and_non_objects() -> None:
    out = '{"type": "x"}\nnot json\n[1, 2]\n\n{"type": "y"}\n'
    assert [e["type"] for e in parse_events(out)] == ["x", "y"]


def test_spawned_agents_counts_a_spawn_record() -> None:
    events = [{"type": "subagent_spawn", "agent": "architect"}]
    assert spawned_agents(events, ["architect", "critic"]) == {"architect"}


def test_spawned_agents_ignores_a_refused_spawn() -> None:
    events = [{"type": "subagent_spawn", "agent": CONTROL_NAME, "error": "unknown agent"}]
    assert spawned_agents(events, [CONTROL_NAME]) == set()


def test_spawned_agents_ignores_events_that_are_not_spawns() -> None:
    events = [{"type": "message", "text": "architect"}]
    assert spawned_agents(events, ["architect"]) == set()


def test_spawned_agents_needs_the_whole_name() -> None:
    events = [{"type": "subagent_spawn", "agent": "architect-extra"}]
    assert spawned_agents(events, ["architect"]) == set()


def test_install_agents_adds_the_control_and_every_shipped_agent(tmp_path: Path) -> None:
    names = install_agents(tmp_path / "agents")
    files = sorted(p.stem for p in (tmp_path / "agents").glob("*.md"))
    assert files == sorted([*names, CONTROL_NAME])
    assert "readonly: true" in (tmp_path / "agents" / f"{CONTROL_NAME}.md").read_text("utf-8")


def test_scrub_drops_secrets_and_keeps_home() -> None:
    env = _scrub({"HOME": "/h", "GH_TOKEN": "x", "OPENAI_API_KEY": "y", "PATH": "/p"})
    assert env == {"HOME": "/h", "PATH": "/p"}


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


# Live test -------------------------------------------------------------------


@pytest.mark.smoke
@pytest.mark.muse
def test_lead_spawns_every_shipped_agent_and_not_the_control(tmp_path: Path) -> None:
    if not _RUN:
        pytest.skip(f"{NOT_VERIFIED} set RUN_CLI_E2E=1 with muse on PATH and a Muse login")
    muse = check_prerequisites()
    xdg = tmp_path / "xdg"
    names = install_agents(xdg / "muse" / "agents")
    workspace = tmp_path / "work"
    workspace.mkdir()
    env = _scrub(dict(os.environ))
    env["XDG_CONFIG_HOME"] = str(xdg)
    result = subprocess.run(
        [muse, "exec", "--json", "--trust-workspace", "--workspace", str(workspace),
         build_prompt([*names, CONTROL_NAME])],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_EXEC_TIMEOUT_SECONDS,
        check=False,
    )  # fmt: skip
    assert result.returncode == 0, (
        f"{NOT_VERIFIED} muse exec exit {result.returncode}. If the login lives under "
        f"XDG_CONFIG_HOME it was hidden by the scratch value. stderr: {result.stderr[-500:]}"
    )
    events = parse_events(result.stdout)
    assert events, f"{NOT_VERIFIED} no JSONL events on stdout: {result.stdout[-500:]}"
    spawned = spawned_agents(events, [*names, CONTROL_NAME])
    missing = sorted(set(names) - spawned)
    assert not missing, f"agents not spawned: {missing}. stdout tail: {result.stdout[-800:]}"
    assert CONTROL_NAME not in spawned, "the control agent with an unknown key was spawned"
