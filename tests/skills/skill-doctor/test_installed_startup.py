"""Execute startup examples outside Git with no plugin environment variables."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / "src" / "claude" / "skills" / "skill-doctor"
TEMPLATE = REPO / "templates" / "skills" / "skill-doctor.SKILL.md.tmpl"


@pytest.mark.parametrize("shell", ["bash", "powershell"])
def test_loaded_skill_location_works_from_unrelated_directory(tmp_path, shell):
    executable = shutil.which("bash" if shell == "bash" else "pwsh")
    if executable is None or (shell == "bash" and os.name == "nt"):
        pytest.skip(f"Native {shell} runtime is not available on this test host.")
    content = TEMPLATE.read_text(encoding="utf-8")
    block = re.search(rf"```{shell}\n(.*?)\n```", content, re.DOTALL).group(1)
    env = dict(os.environ)
    for key in ("COPILOT_PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "SKILL_ROOT"):
        env.pop(key, None)
    if shell == "bash":
        env["SKILL_ROOT"] = str(SKILL)
        command = [
            executable,
            "-c",
            block + '\npython3 "$SKILL_ROOT/scripts/collect_sessions.py" --help',
        ]
    else:
        escaped_skill = str(SKILL).replace("'", "''")
        escaped_python = sys.executable.replace("'", "''")
        command = [
            executable,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            f"$SKILL_ROOT = '{escaped_skill}'\n{block}\n"
            f"& '{escaped_python}' (Join-Path $SKILL_ROOT 'scripts\\collect_sessions.py') --help",
        ]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--harness" in result.stdout
