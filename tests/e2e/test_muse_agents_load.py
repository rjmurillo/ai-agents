"""Muse Code agent load test (issue #7226, ADR-115 Decision 8 amendment).

Muse Code starts when an agent definition is invalid, but the lead cannot spawn
that agent (https://dev.meta.ai/docs/muse-code/agents). No run without a login
shows whether an agent loads, so this test needs one.

The live test (markers ``smoke`` and ``muse``) reads the install the guide ships:
skills, ``lib/``, and every shipped agent under ``${XDG_CONFIG_HOME:-$HOME/.config}/muse/``.
It puts one control agent with an extra frontmatter key into a scratch
workspace's ``.agents/agents/``, runs ``muse exec --json --trust-workspace`` with
a prompt that asks the lead to spawn each agent once and load one skill, and asserts from the JSONL
events that every shipped agent's child replied with its code and the control's
did not. The owner still reads the saved output before the merge gate. The test
writes nothing to the user's Muse folder. It runs under the user's login with
the web tools off.

Run the guide's Muse Code install step first. The test fails with
``MUSE_NOT_VERIFIED`` when an agent file is missing from the user root.

  - Without ``RUN_CLI_E2E=1`` it skips with a reason that starts with
    ``MUSE_NOT_VERIFIED:``.
  - With ``RUN_CLI_E2E=1`` it fails, never skips, when ``muse`` is not on PATH or
    ``muse usage`` exits non-zero. A ``no_allowance`` message does not fail it,
    because a login that prints it still ran a model call.

A spawned child counts only when the runtime's ``subagent_spawn`` result accepted
it and its ``subagent_wait`` result for the same child id holds the role's code
(see ``child_replies``). The child's session log, named in that
result, must also hold the shipped agent body (see ``child_ran_definition``).

The raw stdout is saved on every outcome that has output, including a timeout,
and the failure message names the file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_E2E_DIR = Path(__file__).resolve().parent
if str(_E2E_DIR) not in sys.path:
    sys.path.insert(0, str(_E2E_DIR))

from muse_load_probe import (  # noqa: E402
    CONTROL_NAME,
    EXEC_TIMEOUT_SECONDS,
    NOT_VERIFIED,
    RUN,
    SKILL_NAME,
    SKILL_USAGE,
    USAGE_TIMEOUT_SECONDS,
    allowlisted_env,
    build_prompt,
    check_prerequisites,
    child_ran_definition,
    child_replies,
    cli_budget,
    parse_events,
    require_user_install,
    run_installed_script,
    run_muse,
    shipped_agent_names,
    skill_loaded,
    skill_script_found_lib,
    spawned_agents,
    user_muse_root,
    write_control_agent,
)

# The one test runs `muse usage`, `muse exec`, then the installed script (three timeouts).
pytestmark = cli_budget(USAGE_TIMEOUT_SECONDS, EXEC_TIMEOUT_SECONDS, USAGE_TIMEOUT_SECONDS)


@pytest.mark.smoke
@pytest.mark.muse
def test_lead_spawns_every_shipped_agent_and_not_the_control(tmp_path: Path) -> None:
    if not RUN:
        pytest.skip(f"{NOT_VERIFIED} set RUN_CLI_E2E=1 with muse on PATH and a Muse login")
    muse = check_prerequisites()
    script = require_user_install()
    workspace = tmp_path / "work"
    write_control_agent(workspace / ".agents" / "agents")
    names = [*shipped_agent_names(), CONTROL_NAME]
    saved = tmp_path / "muse-exec.jsonl"
    result = run_muse(
        [muse, "exec", "--json", "--trust-workspace", "--disable-web-tools",
         "--workspace", str(workspace), build_prompt(names)],
        cwd=workspace,
        env=allowlisted_env(os.environ),
        timeout=EXEC_TIMEOUT_SECONDS,
        save_to=saved,
    )  # fmt: skip
    saved.write_text(result.stdout + "\n--- stderr ---\n" + result.stderr, encoding="utf-8")
    assert result.returncode == 0, (
        f"{NOT_VERIFIED} muse exec exit {result.returncode}. Raw output: {saved}. "
        f"stderr: {result.stderr[-500:]}"
    )
    events = parse_events(result.stdout)
    assert events, (
        f"{NOT_VERIFIED} no JSONL events on stdout. Raw output: {saved}. "
        f"stdout: {result.stdout[-500:]} stderr: {result.stderr[-300:]}"
    )
    replies = child_replies(events, names)
    spawned = spawned_agents(events, names)
    missing = sorted(set(shipped_agent_names()) - spawned)
    assert skill_loaded(events, SKILL_NAME, user_muse_root()), (
        f"the lead did not load the {SKILL_NAME!r} skill from the user root. "
        f"Install the skills first (Install on Muse Code). Raw output: {saved}"
    )
    assert skill_script_found_lib(run_installed_script(script)), (
        f"{script} did not print {SKILL_USAGE!r}, or lib/ was missing. "
        "Install the skills and lib first (Install on Muse Code)."
    )
    assert not missing, f"agents not spawned: {missing}. Raw output: {saved}"
    wrong = sorted(n for n in shipped_agent_names() if not child_ran_definition(replies[n], n))
    assert not wrong, (
        f"the child session did not hold the shipped body for: {wrong}. Raw output: {saved}"
    )
    assert CONTROL_NAME not in spawned, f"the control agent was spawned. Raw output: {saved}"
