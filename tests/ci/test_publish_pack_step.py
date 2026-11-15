"""publish.yml: the pack step makes its folder before npm writes into it.

npm pack does not create its ``--pack-destination`` folder. The first dispatch
of the workflow, run 43679280035 on 2026-11-15 UTC, failed with ENOENT because
nothing had made ``$RUNNER_TEMP/pack`` (issue #7365). This test runs the step's
own script against a stand-in npm that, like npm, does not make the folder.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PUBLISH = ROOT / ".github" / "workflows" / "publish.yml"
STEP_NAME = "Pack the tarball once"
BEFORE_THE_FIX = 'npm pack --pack-destination "$RUNNER_TEMP/pack"'

pytestmark = pytest.mark.skipif(
    "sys.platform == 'win32'", reason="the workflow step is a bash script"
)


def _pack_script() -> str:
    document = yaml.safe_load(PUBLISH.read_text(encoding="utf-8"))
    steps = document["jobs"]["build"]["steps"]
    (step,) = [s for s in steps if s.get("name") == STEP_NAME]
    return str(step["run"])


def _run(script: str, tmp_path: Path) -> tuple[int, Path]:
    """Run ``script`` under ``bash -e`` with the stand-in npm first on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    npm.write_text('#!/bin/sh\n: > "$3/package.tgz"\n', encoding="utf-8")
    npm.chmod(0o755)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    done = subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=tmp_path,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "RUNNER_TEMP": str(runner_temp)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return done.returncode, runner_temp


def test_the_pack_step_writes_the_tarball_into_a_folder_it_made(tmp_path: Path) -> None:
    script = _pack_script()
    assert "--pack-destination" in script

    code, runner_temp = _run(script, tmp_path)

    assert code == 0
    assert (runner_temp / "pack" / "package.tgz").is_file()


def test_the_command_from_before_the_fix_fails_in_the_same_harness(tmp_path: Path) -> None:
    code, runner_temp = _run(BEFORE_THE_FIX, tmp_path)

    assert code != 0
    assert not (runner_temp / "pack").exists()
