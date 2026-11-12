"""Muse Code agent load test (issue #7226, ADR-115 Decision 8 amendment).

Muse Code starts when an agent definition is invalid, but the lead cannot spawn
that agent (https://dev.meta.ai/docs/muse-code/agents). No run without a login
shows whether an agent loads, so this test needs one.

The live test (markers ``smoke`` and ``muse``) puts ``src/muse/agents`` plus a
control agent with an extra frontmatter key into a scratch workspace's
``.agents/agents/``, runs ``muse exec --json --trust-workspace`` with a prompt
that asks the lead to spawn each named agent once, and asserts from the JSONL
events that every shipped agent was spawned and the control was not. The user's
own Muse folder and login are not touched.

  - Without ``RUN_CLI_E2E=1`` it skips with a reason that starts with
    ``MUSE_NOT_VERIFIED:``.
  - With ``RUN_CLI_E2E=1`` it fails, never skips, when ``muse`` is not on PATH or
    ``muse usage`` exits non-zero.

Not verified: the shape of the JSONL events. Nothing here has run with a login,
so ``spawned_agents`` reads spawn records by a loose rule (see its docstring).
The owner's run, recorded in the pull request, settles whether that rule fits
Muse Code's real events. ``test_muse_agents_load_helpers.py`` covers the rule,
not the CLI. On failure the raw stdout is saved beside the test workspace so the
owner can attach it.
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
    SKILL_USAGE,
    allowlisted_env,
    build_prompt,
    check_prerequisites,
    install_agents,
    parse_events,
    require_user_skill_install,
    run_muse,
    skill_script_found_lib,
    spawned_agents,
)


@pytest.mark.smoke
@pytest.mark.muse
def test_lead_spawns_every_shipped_agent_and_not_the_control(tmp_path: Path) -> None:
    if not RUN:
        pytest.skip(f"{NOT_VERIFIED} set RUN_CLI_E2E=1 with muse on PATH and a Muse login")
    muse = check_prerequisites()
    script = require_user_skill_install()
    workspace = tmp_path / "work"
    names = install_agents(workspace / ".agents" / "agents")
    result = run_muse(
        [muse, "exec", "--json", "--trust-workspace", "--workspace", str(workspace),
         build_prompt([*names, CONTROL_NAME], script)],
        cwd=workspace,
        env=allowlisted_env(os.environ),
        timeout=EXEC_TIMEOUT_SECONDS,
    )  # fmt: skip
    saved = tmp_path / "muse-exec.jsonl"
    saved.write_text(result.stdout, encoding="utf-8")
    assert result.returncode == 0, (
        f"{NOT_VERIFIED} muse exec exit {result.returncode}. Raw stdout: {saved}. "
        f"stderr: {result.stderr[-500:]}"
    )
    events = parse_events(result.stdout)
    assert events, f"{NOT_VERIFIED} no JSONL events on stdout: {result.stdout[-500:]}"
    spawned = spawned_agents(events, [*names, CONTROL_NAME])
    missing = sorted(set(names) - spawned)
    assert skill_script_found_lib(result.stdout), (
        f"the lead did not show {SKILL_USAGE!r} from {script}, or lib/ was missing. "
        f"Install the skills and lib first (Install on Muse Code). Raw stdout: {saved}"
    )
    assert not missing, f"agents not spawned: {missing}. Raw stdout: {saved}"
    assert CONTROL_NAME not in spawned, f"the control agent was spawned. Raw stdout: {saved}"
