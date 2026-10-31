"""Real Lefthook binary tests for the failed-hook report (issue #6734, item 5).

Each test runs `lefthook_runner.py` against a temporary repository with a real
Lefthook binary, then runs the rerun command the report printed.

Coverage:

- integration: stage, path, and a rerun command that fails the same way.
- integration: a pre-push rerun replays the pushed ref lines.
- integration: failure text streams while a slower job runs, and a job killed at
  its timeout still names the hung gate.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.support.lefthook_binary import resolve_lefthook

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh")
_LEFTHOOK = resolve_lefthook()
FIGHT = "\U0001f94a"


def _hook_repo(tmp_path: Path, hook: str, jobs: str) -> tuple[Path, dict[str, str]]:
    assert _LEFTHOOK is not None
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    # A pre-push job runs only when files are pushed, so HEAD needs one tracked file.
    (repo / "pushed.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "pushed.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "r"],
        cwd=repo,
        check=True,
    )
    (repo / "lefthook.yml").write_text(
        f"output:\n  - failure\nno_auto_install: true\n{hook}:\n  jobs:\n{jobs}", encoding="utf-8"
    )
    # A printed pre-push rerun calls the runner from the repository root (issue #6884).
    validation = repo / "scripts" / "validation"
    validation.mkdir(parents=True)
    for module in ("lefthook_runner.py", "lefthook_failure_report.py", "push_file_list.py"):
        shutil.copy2(PROJECT_ROOT / "scripts" / "validation" / module, validation / module)
    tools = tmp_path / "tools"
    tools.mkdir()
    # `uv` cannot resolve Lefthook here, so the runner falls back to this binary.
    stub = tools / "uv"
    stub.write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
    stub.chmod(0o755)
    (tools / "lefthook").symlink_to(_LEFTHOOK)
    env = {
        "PATH": f"{tools}{os.pathsep}/usr/bin{os.pathsep}/bin",
        "HOME": str(tmp_path),
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    return repo, env


def _run_runner(
    repo: Path, env: dict[str, str], args: list[str], stdin: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts/validation/lefthook_runner.py"), *args],
        cwd=repo,
        env=env,
        input=stdin,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _rerun_line(stderr: str) -> str:
    return next(line.split("rerun: ", 1)[1] for line in stderr.splitlines() if "rerun: " in line)


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_real_pre_commit_failure_names_stage_path_and_a_rerun_that_fails_the_same_way(
    tmp_path: Path,
) -> None:
    jobs = (
        "    - name: quiet-pass\n      run: echo success noise\n"
        "    - name: format-check\n"
        "      run: echo 'src/widget.py:7:3 expected two blank lines'; exit 1\n"
    )
    repo, env = _hook_repo(tmp_path, "pre-commit", jobs)

    first = _run_runner(repo, env, ["run", "pre-commit", "--force"])

    combined = first.stdout + first.stderr
    assert first.returncode == 1, combined
    assert "src/widget.py:7:3 expected two blank lines" in first.stdout
    assert "success noise" not in combined
    assert "pre-commit FAILED (exit 1)" in first.stderr
    assert "job: format-check" in first.stderr
    assert FIGHT not in combined

    rerun = subprocess.run(
        ["sh", "-c", _rerun_line(first.stderr) + " --force"],
        cwd=repo,
        env=env,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert rerun.returncode == 1, rerun.stdout + rerun.stderr
    assert "src/widget.py:7:3 expected two blank lines" in rerun.stdout + rerun.stderr


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_real_pre_push_failure_rerun_replays_the_pushed_refs(tmp_path: Path) -> None:
    jobs = (
        "    - name: range-check\n      use_stdin: true\n"
        "      run: sh -c 'while read a b c d; do echo \"range $b\"; done; exit 1'\n"
    )
    repo, env = _hook_repo(tmp_path, "pre-push", jobs)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    ).stdout.strip()
    ref_line = f"refs/heads/topic {head} refs/heads/topic {'0' * 40}\n"

    first = _run_runner(repo, env, ["run", "pre-push", "origin", "file:///x"], stdin=ref_line)

    assert first.returncode == 1, first.stdout + first.stderr
    assert f"range {head}" in first.stdout
    assert "pre-push FAILED (exit 1)" in first.stderr
    assert "job: range-check" in first.stderr
    rerun_command = _rerun_line(first.stderr)
    assert rerun_command.startswith("printf ")
    assert "run pre-push --job range-check origin file:///x" in rerun_command

    rerun = subprocess.run(
        ["sh", "-c", rerun_command],
        cwd=repo,
        env=env,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    assert rerun.returncode == 1
    assert f"range {head}" in rerun.stdout + rerun.stderr


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_real_passing_hook_prints_nothing(tmp_path: Path) -> None:
    repo, env = _hook_repo(tmp_path, "pre-commit", "    - name: ok\n      run: echo fine\n")

    result = _run_runner(repo, env, ["run", "pre-commit", "--force"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_real_failure_text_appears_while_a_slower_job_is_still_running(tmp_path: Path) -> None:
    jobs = (
        "    - name: fast-fail\n      run: echo FASTFAIL; exit 1\n"
        "    - name: slow-job\n      run: sleep 6\n"
    )
    repo, env = _hook_repo(tmp_path, "pre-commit", jobs)
    config = repo / "lefthook.yml"
    config.write_text(
        config.read_text(encoding="utf-8").replace(
            "pre-commit:\n", "pre-commit:\n  parallel: true\n"
        ),
        encoding="utf-8",
    )
    runner_script = PROJECT_ROOT / "scripts/validation/lefthook_runner.py"
    start = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, str(runner_script), "run", "pre-commit", "--force"],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    first_line = process.stdout.readline()
    seen_after = time.monotonic() - start
    process.communicate()

    assert first_line.strip() == "FASTFAIL"
    assert seen_after < 4, f"failure text arrived after {seen_after:.1f}s, with the slow job at 6s"


@POSIX_ONLY
@pytest.mark.skipif(_LEFTHOOK is None, reason="lefthook not installed")
def test_real_job_killed_at_its_timeout_still_names_the_hung_gate(tmp_path: Path) -> None:
    validation_dir = PROJECT_ROOT / "scripts" / "validation"
    jobs = (
        "    - name: hung-gate\n      timeout: 3s\n      run: |\n"
        f"        {sys.executable} -c \"import sys; sys.path.insert(0, '{validation_dir}'); "
        "import pre_pr_held_output as c, time; c.SLOW_AFTER_SECONDS = 0.3; "
        "h = c.HeldOutput(True, 'Hung Gate'); h.__enter__(); print('held text'); "
        'time.sleep(30)"\n'
    )
    repo, env = _hook_repo(tmp_path, "pre-commit", jobs)

    result = _run_runner(repo, env, ["run", "pre-commit", "--force"])

    combined = result.stdout + result.stderr
    assert result.returncode == 1, combined
    assert "[SLOW] Hung Gate still running after 0.3s" in result.stdout
    assert "held text" not in combined
    assert "job: hung-gate" in result.stderr
