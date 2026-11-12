"""Login-free Muse Code check: every shipped Muse skill validates as compatible (issue #7226).

``muse skills validate`` needs no Muse login. It runs only under ``RUN_CLI_E2E=1``
and fails, never skips, when ``muse`` is missing in that mode. The agent load
test is in ``test_muse_agents_load.py``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

_E2E_DIR = Path(__file__).resolve().parent
if str(_E2E_DIR) not in sys.path:
    sys.path.insert(0, str(_E2E_DIR))

from muse_load_probe import (  # noqa: E402
    NOT_VERIFIED,
    REPO_ROOT,
    RUN,
    USAGE_TIMEOUT_SECONDS,
    allowlisted_env,
    cli_budget,
    run_muse,
)

SKILLS_DIR = REPO_ROOT / "src" / "muse" / "skills"

# One `muse skills validate` per skill directory, each capped at the usage timeout.
pytestmark = cli_budget(len(list(SKILLS_DIR.iterdir())) * USAGE_TIMEOUT_SECONDS)


def _run_validate(muse: str, skill_dir: Path, cwd: Path) -> tuple[int, str, str]:
    result = run_muse(
        [muse, "skills", "validate", str(skill_dir), "--json"],
        cwd=cwd,
        env=allowlisted_env(os.environ),
        timeout=USAGE_TIMEOUT_SECONDS,
    )
    return result.returncode, result.stdout, result.stderr


def _validate_skill(muse: str, skill_dir: Path, cwd: Path) -> str:
    """Return a failure message for ``skill_dir``, or an empty string when it is compatible."""
    returncode, stdout, _stderr = _run_validate(muse, skill_dir, cwd)
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        return f"{skill_dir.name}: unparseable output (exit {returncode}): {stdout[-200:]}"
    if not isinstance(report, dict):
        return f"{skill_dir.name}: output is not a JSON object"
    compat = report.get("compatibility")
    result_word = compat.get("result") if isinstance(compat, dict) else None
    if returncode != 0 or report.get("valid") is not True or result_word != "compatible":
        return f"{skill_dir.name}: valid={report.get('valid')!r} result={result_word!r}"
    return ""


@pytest.mark.smoke
@pytest.mark.muse
def test_muse_code_validates_every_shipped_skill_as_compatible(tmp_path: Path) -> None:
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
    returncode, stdout, stderr = _run_validate(muse, rejected, tmp_path)
    assert returncode != 0, "a SKILL.md without a description was accepted"
    assert "description" in stdout + stderr
