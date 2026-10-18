#!/usr/bin/env python3
"""session-start.sh exports AI_AGENTS_REMOTE_CONTAINER in the Claude web container.

Issue #5541: nothing set the marker, so ``_is_remote_container()`` depended on a
filesystem probe that was never measured in the Claude web container. The
SessionStart hook is gated on ``CLAUDE_CODE_REMOTE=true`` and persists env for
later Bash calls through ``$CLAUDE_ENV_FILE``, so it is the one setter this
repository ships.

Runs the real installed script (``.claude/hooks/session-start.sh``) against a
fake repo, as ``test_session_start_env_escaping.py`` does.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from tests.hooks.test_session_start_env_escaping import (
    INSTALLED_SCRIPT,
    REPO_ROOT,
    _materialize_fake_repo,
    _run_session_start,
    requires_bash,
)

MARKER_LINE = "export AI_AGENTS_REMOTE_CONTAINER=1"
IMAGE_FILE_NAMES = ("Dockerfile", "Containerfile")


def _source_and_read(env_file: Path, cwd: Path, name: str) -> str:
    proc = subprocess.run(
        ["bash", "-c", f'source "$1" && printf %s "${{{name}:-}}"', "bash", str(env_file)],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


@requires_bash
def test_marker_written_once_across_repeated_runs(tmp_path: Path) -> None:
    repo = _materialize_fake_repo(tmp_path, "plain-repo")
    env_file = tmp_path / "env.sh"
    env_file.write_text("", encoding="utf-8")

    first_proc = _run_session_start(repo, env_file)
    _run_session_start(repo, env_file)

    assert first_proc.returncode == 0, first_proc.stderr
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines.count(MARKER_LINE) == 1
    assert _source_and_read(env_file, tmp_path, "AI_AGENTS_REMOTE_CONTAINER") == "1"


@requires_bash
def test_marker_written_when_bootstrap_script_is_missing(tmp_path: Path) -> None:
    """The early exit on a missing bootstrap-vm.sh must not skip the marker."""
    repo = _materialize_fake_repo(tmp_path, "no-bootstrap")
    (repo / "scripts" / "bootstrap-vm.sh").unlink()
    env_file = tmp_path / "env.sh"
    env_file.write_text("", encoding="utf-8")

    proc = _run_session_start(repo, env_file)

    assert proc.returncode == 0, proc.stderr
    assert "not found or not executable" in proc.stderr
    assert MARKER_LINE in env_file.read_text(encoding="utf-8").splitlines()


@requires_bash
def test_stale_zero_assignment_is_overridden_by_later_one(tmp_path: Path) -> None:
    """A pre-existing `=0` must not suppress the marker; the later line wins."""
    repo = _materialize_fake_repo(tmp_path, "stale-zero")
    env_file = tmp_path / "env.sh"
    env_file.write_text("export AI_AGENTS_REMOTE_CONTAINER=0\n", encoding="utf-8")

    proc = _run_session_start(repo, env_file)

    assert proc.returncode == 0, proc.stderr
    assert _source_and_read(env_file, tmp_path, "AI_AGENTS_REMOTE_CONTAINER") == "1"


@requires_bash
def test_marker_not_written_outside_claude_web(tmp_path: Path) -> None:
    """A laptop (CLAUDE_CODE_REMOTE unset or not `true`) is never marked a container."""
    repo = _materialize_fake_repo(tmp_path, "laptop")
    for remote in (None, "", "false", "1"):
        env_file = tmp_path / f"env-{remote}.sh"
        env_file.write_text("", encoding="utf-8")
        env = dict(os.environ)
        env.pop("CLAUDE_CODE_REMOTE", None)
        if remote is not None:
            env["CLAUDE_CODE_REMOTE"] = remote
        env["CLAUDE_ENV_FILE"] = str(env_file)

        proc = subprocess.run(
            ["bash", str(repo / ".claude" / "hooks" / "session-start.sh")],
            cwd=repo,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        assert env_file.read_text(encoding="utf-8") == "", f"CLAUDE_CODE_REMOTE={remote!r}"


@requires_bash
def test_unset_env_file_reports_unpersisted_marker_and_exits_zero(tmp_path: Path) -> None:
    repo = _materialize_fake_repo(tmp_path, "no-env-file")
    env = dict(os.environ)
    env["CLAUDE_CODE_REMOTE"] = "true"
    env.pop("CLAUDE_ENV_FILE", None)

    proc = subprocess.run(
        ["bash", str(repo / ".claude" / "hooks" / "session-start.sh")],
        cwd=repo,
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert "AI_AGENTS_REMOTE_CONTAINER was not persisted" in proc.stderr


@requires_bash
def test_exported_marker_makes_is_remote_container_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The line the hook writes is the one `_is_remote_container()` reads."""
    from scripts.validation import run_workflow_local_test as rwlt

    repo = _materialize_fake_repo(tmp_path, "contract")
    env_file = tmp_path / "env.sh"
    env_file.write_text("", encoding="utf-8")
    _run_session_start(repo, env_file)
    value = _source_and_read(env_file, tmp_path, "AI_AGENTS_REMOTE_CONTAINER")

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("CODESPACES", raising=False)
    monkeypatch.setenv("AI_AGENTS_REMOTE_CONTAINER", value)
    monkeypatch.setattr(rwlt, "_has_container_filesystem_signal", lambda: False)

    assert rwlt._is_remote_container() is True


def _images_missing_marker(root: Path, tracked: list[str]) -> list[str]:
    """Tracked managed-image files that never mention the marker."""
    missing = []
    for rel in tracked:
        parts = Path(rel).parts
        name = parts[-1]
        is_image = (
            name in IMAGE_FILE_NAMES
            or name.startswith(("Dockerfile.", "Containerfile."))
            or ".devcontainer" in parts[:-1]
        )
        if not is_image:
            continue
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        if "AI_AGENTS_REMOTE_CONTAINER" not in text:
            missing.append(rel)
    return missing


def test_image_check_flags_image_without_marker(tmp_path: Path) -> None:
    (tmp_path / ".devcontainer").mkdir()
    (tmp_path / ".devcontainer" / "devcontainer.json").write_text("{}", encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("ENV AI_AGENTS_REMOTE_CONTAINER=1\n", encoding="utf-8")
    (tmp_path / "Containerfile.dev").write_text("FROM scratch\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("no marker\n", encoding="utf-8")
    tracked = [
        ".devcontainer/devcontainer.json",
        "Dockerfile",
        "Containerfile.dev",
        "README.md",
    ]

    assert _images_missing_marker(tmp_path, tracked) == [
        ".devcontainer/devcontainer.json",
        "Containerfile.dev",
    ]


def test_every_tracked_managed_image_sets_the_marker() -> None:
    """Fails when a Dockerfile, Containerfile, or .devcontainer file lacks the marker.

    ADR-104 rule 8 needs every managed image detected by
    ``_is_remote_container()``. A new image either carries the marker or adds
    its own measured filesystem signal and removes itself from this check.
    """
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip(f"git ls-files unavailable: {proc.stderr.strip()}")
    tracked = [p for p in proc.stdout.split("\0") if p and (REPO_ROOT / p).is_file()]

    assert _images_missing_marker(REPO_ROOT, tracked) == []


def test_installed_script_matches_template() -> None:
    """The rendered hook carries the marker export (build_all.py ran)."""
    text = INSTALLED_SCRIPT.read_text(encoding="utf-8")
    assert MARKER_LINE in text
