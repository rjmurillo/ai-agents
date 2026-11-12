"""Helpers for the Muse Code agent load test (issue #7226, ADR-115 Decision 8 amendment).

Muse Code starts when an agent definition is invalid, but the lead cannot spawn
that agent (https://dev.meta.ai/docs/muse-code/agents). The live test in
``test_muse_agents_load.py`` needs a Muse login. The always-on tests in
``test_muse_agents_load_helpers.py`` cover these helpers without the CLI.

Event shape, read from a real Muse Code 1.4.15 run (``exec --json``): one JSON
record per line with ``payload_type`` and ``payload``. A ``tool.result`` record
whose ``payload.correlation_facts.tool_name`` is ``subagent_spawn`` carries the
spawn outcome in ``payload.text`` (JSON: ``status``, ``subagent_id``,
``agent_path`` such as ``main/00 architect/1``). The matching ``subagent_wait``
record carries ``status: ready``, the same ``subagent_id``, and the child's reply
as ``summary``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MUSE_AGENTS = REPO_ROOT / "src" / "muse" / "agents"
CONTROL_NAME = "zz-extra-key-control"
NOT_VERIFIED = "MUSE_NOT_VERIFIED:"
USAGE_TIMEOUT_SECONDS = 30
EXEC_TIMEOUT_SECONDS = 1500
PYTEST_MARGIN_SECONDS = 60
DRAIN_TIMEOUT_SECONDS = 10
RUN = os.environ.get("RUN_CLI_E2E") == "1"
_ENV_ALLOW = frozenset(
    {"PATH", "HOME", "LANG", "TERM", "TMPDIR", "TZ", "USER", "LOGNAME", "SHELL", "NO_COLOR"}
)
_ENV_ALLOW_PREFIXES = ("LC_", "XDG_", "MUSE_")
CODE_BASE = 1000
CODE_STEP = 17
_REPLY_TOOLS = frozenset({"subagent_wait", "subagent_read_result"})


def cli_budget(*subprocess_timeouts: int) -> pytest.MarkDecorator:
    """pytest-timeout marker that outlasts every subprocess timeout in a test."""
    return pytest.mark.timeout(sum(subprocess_timeouts) + PYTEST_MARGIN_SECONDS)


def shipped_agent_names() -> list[str]:
    return sorted(p.stem for p in MUSE_AGENTS.glob("*.md"))


SKILL_NAME = "github"
SKILL_SCRIPT_REL = "skills/github/scripts/pr/get_pr_checks.py"
SKILL_USAGE = "usage: get_pr_checks.py"
LIB_MISSING = "Plugin lib directory not found"


def build_skill_prompt() -> str:
    """Return the instruction to load one installed skill with the skill tool."""
    return f"Then load the `{SKILL_NAME}` skill with your `read_skill` tool and tell me its name."


def skill_script_found_lib(output: str) -> bool:
    """True when the output shows the script's usage line and no missing-lib message."""
    return SKILL_USAGE in output and LIB_MISSING not in output


def skill_loaded(events: Sequence[Mapping[str, object]], name: str, root: Path) -> bool:
    """True when a successful ``read_skill`` result loaded skill ``name`` from ``root``.

    The result text must name the skill's folder under ``root``: Muse Code loaded
    179 skills in the owner's run, so another root could shadow the same name.
    """
    marker = f'name="{name}" status="ok"'
    folder = str(root / "skills" / name)
    for event in events:
        if event.get("payload_type") != "tool.result":
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        facts = payload.get("correlation_facts")
        text = payload.get("text")
        if (
            isinstance(facts, Mapping)
            and facts.get("tool_name") == "read_skill"
            and facts.get("outcome") == "success"
            and isinstance(text, str)
            and marker in text
            and folder in text
        ):
            return True
    return False


def run_installed_script(script: str) -> str:
    """Run the installed skill script with ``--help`` outside Muse; return its output.

    Muse Code's default sandbox hides the user root from the model's shell
    (``Permission denied``, observed on 1.4.15), so the model cannot run this
    script. A normal shell shows only that the skill folder and ``lib/`` arrive
    together, which is what a script needs. It does not show that Muse Code runs it.
    """
    done = subprocess.run(
        ["python3", "-I", script, "--help"],
        capture_output=True,
        text=True,
        timeout=USAGE_TIMEOUT_SECONDS,
        env=allowlisted_env(os.environ),
        check=False,
    )
    return done.stdout + done.stderr


def build_prompt(names: list[str]) -> str:
    """Return the prompt: spawn each named agent once, then load one skill."""
    return build_agents_prompt(names) + "\n" + build_skill_prompt()


def spawn_code(index: int) -> str:
    """Return the reply code the child at ``index`` gives: ``code-`` plus 1000 + 17 * index."""
    return f"code-{CODE_BASE + CODE_STEP * index}"


def build_agents_prompt(names: list[str]) -> str:
    """Return the spawn instruction: each named agent once, with a code to compute.

    The prompt prints the number before each role and the formula, never the
    code. A spawn request carries the formula, so the request cannot show the
    code. A child that ran replies with the computed code, and ``spawned_agents``
    reads that reply from the runtime's wait result for the child.
    """
    listing = "\n".join(f"- {i:02d}: {name}" for i, name in enumerate(names))
    return (
        "For each agent role below, spawn that exact agent once. Give it this "
        f"objective: reply with the single word code-N, where N is {CODE_BASE} plus "
        f"{CODE_STEP} times the number printed before its role. Do not compute N "
        "yourself and do not repeat it. Spawn one at a time: after each spawn, call "
        "subagent_wait for that child and read its reply before the next spawn. If a "
        "role cannot be spawned, say so and go on to the next. Do not use any other "
        "role and do not edit files. When done, list which roles you spawned.\n"
        f"{listing}"
    )


def parse_events(stdout: str) -> list[dict[str, object]]:
    """Return the Muse event records among the lines of ``stdout``.

    A record is a JSON object with a string ``payload_type``. Other lines, and
    JSON that is not a record (a skill script's own output), are ignored.
    """
    events: list[dict[str, object]] = []
    for line in stdout.splitlines():
        try:
            loaded = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict) and isinstance(loaded.get("payload_type"), str):
            events.append(loaded)
    return events


def _tool_result(event: Mapping[str, object]) -> tuple[str, dict[str, object]] | None:
    """Return ``(tool_name, body)`` for a ``tool.result`` record whose text is a JSON object."""
    if event.get("payload_type") != "tool.result":
        return None
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return None
    facts = payload.get("correlation_facts")
    text = payload.get("text")
    if not isinstance(facts, Mapping) or not isinstance(text, str):
        return None
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    return str(facts.get("tool_name")), body


def child_replies(events: Sequence[Mapping[str, object]], names: list[str]) -> dict[str, list[str]]:
    """Return ``{name: evidence_refs}`` for each name whose spawned child replied with its code.

    Name ``names[i]`` counts when two runtime records agree:

    1. a ``subagent_spawn`` result with ``status: accepted`` and a ``subagent_id``, and
    2. a ``subagent_wait`` or ``subagent_read_result`` result (a wait that times
       out at 60s is followed by a read) with ``status: ready`` for that same
       ``subagent_id`` whose ``summary`` holds ``spawn_code(i)`` and no other code.

    The runtime writes both records. A lead cannot forge them by working out the
    formula and echoing a code: its text is not a ``tool.result`` for a wait on a
    child id. A rejected spawn, a roster, or a wait on another child does not
    count. The ``agent_path`` label is ignored: the lead picks it, and three
    spellings occurred. Identity comes from ``child_ran_definition``, which reads
    the child's own session log (the value lists its ``evidence_refs``).
    """
    accepted: set[str] = set()
    for event in events:
        parsed = _tool_result(event)
        if parsed is None or parsed[0] != "subagent_spawn":
            continue
        child = parsed[1].get("subagent_id")
        if parsed[1].get("status") == "accepted" and isinstance(child, str):
            accepted.add(child)
    replied: dict[str, list[str]] = {}
    for event in events:
        parsed = _tool_result(event)
        if parsed is None or parsed[0] not in _REPLY_TOOLS:
            continue
        body = parsed[1]
        child, summary = body.get("subagent_id"), body.get("summary")
        if body.get("status") != "ready" or child not in accepted or not isinstance(summary, str):
            continue
        hits = [i for i in range(len(names)) if spawn_code(i) in summary]
        if len(hits) != 1:
            continue
        refs = body.get("evidence_refs")
        replied[names[hits[0]]] = (
            [r for r in refs if isinstance(r, str)] if isinstance(refs, list) else []
        )
    return replied


def spawned_agents(events: Sequence[Mapping[str, object]], names: list[str]) -> set[str]:
    """Return the names of ``names`` whose spawned child replied with its own code."""
    return set(child_replies(events, names))


def _squash(text: str) -> str:
    """Collapse JSON escapes and whitespace so a body matches inside a nested log line."""
    unescaped = re.sub(r'\\+"', '"', re.sub(r"\\+n", " ", text))
    return re.sub(r"\s+", " ", unescaped).strip()


def child_ran_definition(evidence_refs: Sequence[str], name: str) -> bool:
    """True when a child session file holds the shipped body of agent ``name``.

    Muse Code writes each child's session log to disk and names it in the wait
    result's ``evidence_refs``. Its ``agent_definition_prompt`` block carries the
    agent file's body, so a match shows the runtime started the child from the
    shipped definition and not from a label the lead chose. A missing or
    unreadable file is False.
    """
    shipped = (MUSE_AGENTS / f"{name}.md").read_text("utf-8").split("---", 2)[-1]
    snippet = _squash(shipped)[:160]
    if not snippet:
        return False
    for ref in evidence_refs:
        try:
            if snippet in _squash(Path(ref).read_text("utf-8", errors="replace")):
                return True
        except OSError:
            continue
    return False


def write_control_agent(agents_dir: Path) -> Path:
    agents_dir.mkdir(parents=True, exist_ok=True)
    path = agents_dir / f"{CONTROL_NAME}.md"
    path.write_text(
        f"---\nname: {CONTROL_NAME}\ndescription: Control agent with an extra frontmatter key\n"
        "readonly: true\n---\nReply ok.\n",
        encoding="utf-8",
    )
    return path


def allowlisted_env(env: Mapping[str, str]) -> dict[str, str]:
    """Return only the variables ``muse`` needs: the run uses ``--trust-workspace``.

    The lead can run shell, so a denylist of secret-looking names is not enough.
    Anything not named here (cloud keys, agent sockets, database URLs) is dropped
    from the environment. Files under ``HOME`` stay reachable, because the login
    lives there.
    """
    return {k: v for k, v in env.items() if k in _ENV_ALLOW or k.startswith(_ENV_ALLOW_PREFIXES)}


def _text(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def run_muse(
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    save_to: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``muse`` in its own process group; a timeout kills the group and fails.

    On a timeout the partial stdout and stderr go to ``save_to`` when given, and
    the failure message names that file. The lead can start children, so the
    whole group is killed, not only ``muse``.
    """
    use_group = hasattr(os, "killpg")
    proc = subprocess.Popen(
        list(args),
        cwd=cwd,
        env=dict(env),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=use_group,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as first:
        if use_group:
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=DRAIN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as drain:
            # A descendant that left the group still holds the pipes. Keep what was
            # read so far, then give up on the pipes.
            stdout = _text(drain.stdout) or _text(first.stdout)
            stderr = _text(drain.stderr) or _text(first.stderr)
            for pipe in (proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()
        where = ""
        if save_to is not None:
            save_to.write_text(_text(stdout) + "\n--- stderr ---\n" + _text(stderr), "utf-8")
            where = f" Partial output: {save_to}."
        pytest.fail(
            f"{NOT_VERIFIED} `muse {' '.join(args[1:3])}` exceeded {timeout}s.{where} "
            f"Tail: {_text(stdout)[-500:]}"
        )
    return subprocess.CompletedProcess(list(args), proc.returncode, stdout, stderr)


def check_prerequisites() -> str:
    """Return the path of ``muse``; fail with a clear message when it or a login is missing.

    ``muse usage`` must exit 0. Its text is not read: a login that prints
    ``no_allowance`` still ran a model call on Muse Code 1.4.15, so only the live
    run shows whether a call can run.
    """
    muse = shutil.which("muse")
    if muse is None:
        pytest.fail(
            f"{NOT_VERIFIED} RUN_CLI_E2E=1 but `muse` is not on PATH. Install Muse Code "
            "(https://dev.meta.ai/docs/muse-code) and put it on PATH."
        )
    usage = run_muse(
        [muse, "usage"],
        cwd=Path.cwd(),
        env=allowlisted_env(os.environ),
        timeout=USAGE_TIMEOUT_SECONDS,
    )
    if usage.returncode != 0:
        detail = (usage.stdout + usage.stderr).strip()[-300:]
        pytest.fail(
            f"{NOT_VERIFIED} Muse Code is not logged in (`muse usage` exit {usage.returncode}: "
            f"{detail}). Run `muse login`, then rerun this test."
        )
    # `muse usage` printed `no_allowance` under a login where `muse exec` made a
    # model call (Muse Code 1.4.15, run.usage calls=1). So an allowance message is
    # not a failure. A run that cannot call a model fails on its own exit code.
    return muse


def user_muse_root() -> Path:
    """Return the real Muse user root, ``$XDG_CONFIG_HOME/muse`` or ``~/.config/muse``."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "muse"


def _same_as_shipped(agents_dir: Path, name: str) -> bool:
    installed = agents_dir / f"{name}.md"
    return (
        installed.is_file() and installed.read_bytes() == (MUSE_AGENTS / f"{name}.md").read_bytes()
    )


def require_user_install() -> str:
    """Return the installed ``get_pr_checks.py`` path; fail unless the guide install ran.

    The guide's Muse Code step copies skills, ``lib/``, and every shipped agent
    into the user root. The test reads that copy, so it checks the route the
    guide ships and never installs the shipped agents itself.
    """
    root = user_muse_root()
    script = root / SKILL_SCRIPT_REL
    if not script.is_file():
        pytest.fail(
            f"{NOT_VERIFIED} no installed skills under {root}/skills; run the install first"
        )
    if not (root / "lib" / "github_core").is_dir():
        pytest.fail(f"{NOT_VERIFIED} no installed lib under {root}/lib; run the install first")
    stale = [n for n in shipped_agent_names() if not _same_as_shipped(root / "agents", n)]
    if stale:
        pytest.fail(
            f"{NOT_VERIFIED} {len(stale)} shipped agents are missing or differ from "
            f"src/muse/agents under {root}/agents (first: {stale[0]}); run the install first"
        )
    return str(script)
