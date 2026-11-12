"""Helpers for the Muse Code agent load test (issue #7226, ADR-115 Decision 8 amendment).

Muse Code starts when an agent definition is invalid, but the lead cannot spawn
that agent (https://dev.meta.ai/docs/muse-code/agents). The live test in
``test_muse_agents_load.py`` needs a Muse login. The always-on tests in
``test_muse_agents_load_helpers.py`` cover these helpers without the CLI.

Not verified: the shape of the JSONL events. Nothing here has run with a login,
so ``spawned_agents`` looks for each child's reply code in any event (see its
docstring). The owner's run, recorded in the pull request, shows whether the
codes appear.
"""

from __future__ import annotations

import json
import os
import shlex
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
EXEC_TIMEOUT_SECONDS = 600
PYTEST_MARGIN_SECONDS = 60
DRAIN_TIMEOUT_SECONDS = 10
RUN = os.environ.get("RUN_CLI_E2E") == "1"
_ENV_ALLOW = frozenset(
    {"PATH", "HOME", "LANG", "TERM", "TMPDIR", "TZ", "USER", "LOGNAME", "SHELL", "NO_COLOR"}
)
_ENV_ALLOW_PREFIXES = ("LC_", "XDG_", "MUSE_")
CODE_BASE = 1000
CODE_STEP = 17


def cli_budget(*subprocess_timeouts: int) -> pytest.MarkDecorator:
    """pytest-timeout marker that outlasts every subprocess timeout in a test."""
    return pytest.mark.timeout(sum(subprocess_timeouts) + PYTEST_MARGIN_SECONDS)


def shipped_agent_names() -> list[str]:
    return sorted(p.stem for p in MUSE_AGENTS.glob("*.md"))


SKILL_SCRIPT_REL = "skills/github/scripts/pr/get_pr_checks.py"
SKILL_USAGE = "usage: get_pr_checks.py"
LIB_MISSING = "Plugin lib directory not found"


def build_script_prompt(script: str) -> str:
    """Return the instruction to run one script-backed skill and quote its output."""
    command = f"python3 -I {shlex.quote(script)} --help"
    return f"Then run `{command}` in a shell and quote its first output line exactly."


def skill_script_found_lib(output: str) -> bool:
    """True when the run shows the script's usage line and no missing-lib message."""
    return SKILL_USAGE in output and LIB_MISSING not in output


def build_prompt(names: list[str], script: str) -> str:
    """Return the prompt: spawn each named agent once, then run one skill script."""
    return build_agents_prompt(names) + "\n" + build_script_prompt(script)


def spawn_code(index: int) -> str:
    """Return the reply code the child at ``index`` gives: ``code-`` plus 1000 + 17 * index."""
    return f"code-{CODE_BASE + CODE_STEP * index}"


def build_agents_prompt(names: list[str]) -> str:
    """Return the spawn instruction: each named agent once, with a code to compute.

    The prompt prints the number before each role and the formula, never the
    code. A spawn request carries the formula, so the request cannot show the
    code. A child that ran replies with the computed code. A lead that works the
    formula out and writes it into a request or a reply could still fake it,
    which only the owner's read of the saved stdout can rule out.
    """
    listing = "\n".join(f"- {i:02d}: {name}" for i, name in enumerate(names))
    return (
        "For each agent role below, spawn that exact agent once. Give it this "
        f"objective: reply with the single word code-N, where N is {CODE_BASE} plus "
        f"{CODE_STEP} times the number printed before its role. Do not compute N "
        "yourself and do not repeat it. Spawn one at a time. If a role cannot be "
        "spawned, say so and go on to the next. Do not use any other role and do "
        "not edit files. When done, list which roles you spawned.\n"
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


def spawned_agents(events: Sequence[Mapping[str, object]], names: list[str]) -> set[str]:
    """Return the names of ``names`` whose child replied with its own code.

    A name at position ``i`` counts as spawned when ``spawn_code(i)`` appears in
    the serialized text of any event. Muse Code publishes no event schema for
    ``exec --json``, so the rule does not read event types or fields. A spawn
    request holds only the formula, and a roster or a refusal holds neither, so
    none of them carries the code. Only a child that ran, or a lead that worked
    the formula out against instructions, does.
    """
    text = "\n".join(json.dumps(event) for event in events)
    return {name for i, name in enumerate(names) if spawn_code(i) in text}


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
    except subprocess.TimeoutExpired:
        if use_group:
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=DRAIN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            # A descendant that left the group still holds the pipes. Give up on them.
            stdout, stderr = "", ""
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
    """Return the path of ``muse``; fail with a clear message when it or a login is missing."""
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
    combined = (usage.stdout + usage.stderr).lower()
    if "no_allowance" in combined or "no subscription allowance" in combined:
        pytest.fail(
            f"{NOT_VERIFIED} Muse Code is signed in but has no subscription allowance, "
            f"so a model call cannot run (`muse usage`: {combined.strip()[-200:]})."
        )
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
