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
Muse Code's real events. ``test_muse_agents_load_helpers.py`` covers the rule, not the CLI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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
    REPO_ROOT,
    RUN,
    SKILL_USAGE,
    USAGE_TIMEOUT_SECONDS,
    build_prompt,
    check_prerequisites,
    install_agents,
    parse_events,
    require_user_skill_install,
    scrub,
    skill_script_found_lib,
    spawned_agents,
)

# Live test -------------------------------------------------------------------


@pytest.mark.smoke
@pytest.mark.muse
def test_lead_spawns_every_shipped_agent_and_not_the_control(tmp_path: Path) -> None:
    if not RUN:
        pytest.skip(f"{NOT_VERIFIED} set RUN_CLI_E2E=1 with muse on PATH and a Muse login")
    muse = check_prerequisites()
    script = require_user_skill_install()
    xdg = tmp_path / "xdg"
    names = install_agents(xdg / "muse" / "agents")
    workspace = tmp_path / "work"
    workspace.mkdir()
    env = scrub(dict(os.environ))
    env["XDG_CONFIG_HOME"] = str(xdg)
    result = subprocess.run(
        [muse, "exec", "--json", "--trust-workspace", "--workspace", str(workspace),
         build_prompt([*names, CONTROL_NAME], script)],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=EXEC_TIMEOUT_SECONDS,
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
    assert skill_script_found_lib(result.stdout), (
        f"the lead did not show {SKILL_USAGE!r} from {script}, or lib/ was missing. "
        "Install the skills and lib with README 'Install into Muse Code' first. "
        f"stdout tail: {result.stdout[-800:]}"
    )
    assert not missing, f"agents not spawned: {missing}. stdout tail: {result.stdout[-800:]}"
    assert CONTROL_NAME not in spawned, "the control agent with an unknown key was spawned"


SKILLS_DIR = REPO_ROOT / "src" / "muse" / "skills"


def _run_validate(muse: str, skill_dir: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [muse, "skills", "validate", str(skill_dir), "--json"],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=USAGE_TIMEOUT_SECONDS,
        check=False,
    )


def _validate_skill(muse: str, skill_dir: Path, cwd: Path) -> str:
    """Return a failure message for ``skill_dir``, or an empty string when it is compatible."""
    result = _run_validate(muse, skill_dir, cwd)
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        tail = result.stdout[-200:]
        return f"{skill_dir.name}: unparseable output (exit {result.returncode}): {tail}"
    if not isinstance(report, dict):
        return f"{skill_dir.name}: output is not a JSON object"
    compat = report.get("compatibility")
    result_word = compat.get("result") if isinstance(compat, dict) else None
    if result.returncode != 0 or report.get("valid") is not True or result_word != "compatible":
        return f"{skill_dir.name}: valid={report.get('valid')!r} result={result_word!r}"
    return ""


@pytest.mark.smoke
@pytest.mark.muse
def test_muse_code_validates_every_shipped_skill_as_compatible(tmp_path: Path) -> None:
    """`muse skills validate` needs no login: every src/muse/skills dir must pass."""
    if not RUN:
        pytest.skip(f"{NOT_VERIFIED} set RUN_CLI_E2E=1 with muse on PATH")
    muse = shutil.which("muse")
    if muse is None:
        pytest.fail(f"{NOT_VERIFIED} RUN_CLI_E2E=1 but `muse` is not on PATH (Muse Code CLI)")
    dirs = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
    assert dirs, "no skill directories under src/muse/skills"
    failures = [msg for d in dirs if (msg := _validate_skill(muse, d, tmp_path))]
    assert failures == []
    rejected = tmp_path / "no-description"
    rejected.mkdir()
    (rejected / "SKILL.md").write_text("---\nname: no-description\n---\nBody.\n", "utf-8")
    result = _run_validate(muse, rejected, tmp_path)
    assert result.returncode != 0, "a SKILL.md without a description was accepted"
    assert "description" in result.stdout + result.stderr
