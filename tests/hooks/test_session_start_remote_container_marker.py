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
import re
import stat
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
MARKER_NAME = "AI_AGENTS_REMOTE_CONTAINER"
# An actual assignment, not a mention: `ENV NAME=1`, `ENV NAME 1`, `export NAME=1`,
# `NAME=1`, or the JSON form `"NAME": "1"`. A comment line never matches. The value
# is captured so the check can require one `_env_truthy()` accepts: `=0` or
# `=false` declares the marker false and must not satisfy the image check.
_ASSIGNMENT = re.compile(
    rf"^\s*(?:(?:ENV|export)\s+)?{MARKER_NAME}(?:\s*=\s*|\s+)(?P<bare>\S+)"
    rf"|^\s*\"{MARKER_NAME}\"\s*:\s*\"(?P<json>[^\"]+)\""
)
_COMMENT_PREFIXES = ("#", "//", "*", "/*")


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


def _source_and_read_exported(env_file: Path, cwd: Path, name: str) -> str:
    """Value a child process inherits after sourcing, which is what os.environ sees."""
    proc = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1" && printf %s "$(printenv "$2" || true)"',
            "bash",
            str(env_file),
            name,
        ],
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
def test_later_zero_after_one_is_overridden_by_new_one(tmp_path: Path) -> None:
    """`=1` followed by a later `=0` leaves 0 in effect, so the hook re-appends `=1`."""
    repo = _materialize_fake_repo(tmp_path, "one-then-zero")
    env_file = tmp_path / "env.sh"
    env_file.write_text(f"{MARKER_LINE}\nexport AI_AGENTS_REMOTE_CONTAINER=0\n", encoding="utf-8")

    proc = _run_session_start(repo, env_file)

    assert proc.returncode == 0, proc.stderr
    assert _source_and_read(env_file, tmp_path, MARKER_NAME) == "1"


@requires_bash
@pytest.mark.parametrize(
    "trailer",
    [
        "unset AI_AGENTS_REMOTE_CONTAINER",
        "unset -v AI_AGENTS_REMOTE_CONTAINER",
        "export -n AI_AGENTS_REMOTE_CONTAINER",
        "declare AI_AGENTS_REMOTE_CONTAINER=0",
        "declare -x AI_AGENTS_REMOTE_CONTAINER=0",
        "  unset AI_AGENTS_REMOTE_CONTAINER",
        "AI_AGENTS_REMOTE_CONTAINER=0",
    ],
    ids=["unset", "unset-v", "export-n", "declare", "declare-x", "indented-unset", "bare-zero"],
)
def test_later_unset_or_redeclare_after_marker_is_overridden(tmp_path: Path, trailer: str) -> None:
    """`=1` followed by an `unset` or redeclare leaves the marker empty or 0, so re-append."""
    repo = _materialize_fake_repo(tmp_path, "one-then-unset")
    env_file = tmp_path / "env.sh"
    env_file.write_text(f"{MARKER_LINE}\n{trailer}\n", encoding="utf-8")
    # Precondition: the pre-hook file leaves no exported 1 for a child process.
    assert _source_and_read_exported(env_file, tmp_path, MARKER_NAME) != "1"

    proc = _run_session_start(repo, env_file)

    assert proc.returncode == 0, proc.stderr
    assert _source_and_read_exported(env_file, tmp_path, MARKER_NAME) == "1"


@requires_bash
def test_unrelated_unset_after_marker_does_not_reappend(tmp_path: Path) -> None:
    """An `unset` of another variable, or of a name that merely shares the prefix, is ignored."""
    repo = _materialize_fake_repo(tmp_path, "unrelated-unset")
    env_file = tmp_path / "env.sh"
    env_file.write_text(
        f"{MARKER_LINE}\nunset FOO\nunset AI_AGENTS_REMOTE_CONTAINER_OTHER\n", encoding="utf-8"
    )

    proc = _run_session_start(repo, env_file)

    assert proc.returncode == 0, proc.stderr
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines.count(MARKER_LINE) == 1
    assert _source_and_read(env_file, tmp_path, MARKER_NAME) == "1"


@requires_bash
@pytest.mark.parametrize(
    ("existing", "name", "expected"),
    [
        ("FOO=bar", "FOO", "bar"),
        ("export FOO=bar", "FOO", "bar"),
        ("FOO=bar\n", "FOO", "bar"),
        ("export FOO=bar\nexport BAZ=qux", "BAZ", "qux"),
        (f"{MARKER_LINE}", "FOO", ""),
    ],
    ids=["bare-no-lf", "export-no-lf", "with-lf", "two-lines-no-lf", "marker-last-no-lf"],
)
def test_unterminated_last_line_keeps_both_existing_var_and_marker(
    tmp_path: Path, existing: str, name: str, expected: str
) -> None:
    """An env file whose last line lacks LF must not fuse with the appended marker."""
    repo = _materialize_fake_repo(tmp_path, "no-lf")
    env_file = tmp_path / "env.sh"
    env_file.write_text(existing, encoding="utf-8")

    proc = _run_session_start(repo, env_file)

    assert proc.returncode == 0, proc.stderr
    assert _source_and_read(env_file, tmp_path, name) == expected
    assert _source_and_read(env_file, tmp_path, MARKER_NAME) == "1"
    assert MARKER_LINE in env_file.read_text(encoding="utf-8").splitlines()


@requires_bash
def test_unterminated_last_line_does_not_fuse_with_later_path_append(tmp_path: Path) -> None:
    """The newline guard covers the PATH and PYENV appends, not only the marker."""
    repo = _materialize_fake_repo(tmp_path, "no-lf-path")
    env_file = tmp_path / "env.sh"
    env_file.write_text(MARKER_LINE, encoding="utf-8")

    proc = _run_session_start(repo, env_file)

    assert proc.returncode == 0, proc.stderr
    lines = env_file.read_text(encoding="utf-8").splitlines()
    assert lines[0] == MARKER_LINE
    assert any(line.startswith("export PATH=") for line in lines)
    assert any(line.startswith("export PYENV_ROOT=") for line in lines)


@requires_bash
def test_empty_env_file_gets_no_leading_blank_line(tmp_path: Path) -> None:
    repo = _materialize_fake_repo(tmp_path, "empty-env")
    env_file = tmp_path / "env.sh"
    env_file.write_text("", encoding="utf-8")

    _run_session_start(repo, env_file)

    assert env_file.read_text(encoding="utf-8").splitlines()[0] == MARKER_LINE


@requires_bash
def test_unwritable_env_file_does_not_skip_bootstrap(tmp_path: Path) -> None:
    """An env file under a missing directory must not stop bootstrap-vm.sh from running."""
    repo = _materialize_fake_repo(tmp_path, "bad-env-file")
    bootstrap = repo / "scripts" / "bootstrap-vm.sh"
    sentinel = tmp_path / "BOOTSTRAP_RAN"
    bootstrap.write_text(f"#!/bin/sh\ntouch '{sentinel}'\nexit 0\n", encoding="utf-8")
    bootstrap.chmod(bootstrap.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    env_file = tmp_path / "missing-dir" / "env.sh"

    proc = _run_session_start(repo, env_file)

    assert sentinel.exists(), proc.stderr
    assert "could not write AI_AGENTS_REMOTE_CONTAINER" in proc.stderr
    assert not env_file.exists()


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
    """Accepted limit: with no env file the marker cannot persist, so the bound lapses.

    The hook logs one stderr line and exits 0 so bootstrap is not blocked.
    `_is_remote_container()` then falls back to the filesystem probe. This test
    documents that behavior; it does not claim the bound holds in this case.
    """
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


def _sets_marker(text: str) -> bool:
    """True when a non-comment line assigns the marker a value ``_env_truthy()`` accepts."""
    from scripts.validation import run_workflow_local_test as rwlt

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_COMMENT_PREFIXES):
            continue
        match = _ASSIGNMENT.match(line)
        if match is None:
            continue
        value = (match.group("bare") or match.group("json") or "").strip("\"'").lower()
        if value in rwlt._TRUTHY:
            return True
    return False


def _images_missing_marker(root: Path, tracked: list[str]) -> list[str]:
    """Tracked managed-image files that never assign the marker."""
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
        if not _sets_marker(text):
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ENV AI_AGENTS_REMOTE_CONTAINER=1\n", True),
        ("ENV AI_AGENTS_REMOTE_CONTAINER 1\n", True),
        ("export AI_AGENTS_REMOTE_CONTAINER=1\n", True),
        ('{"containerEnv": {\n  "AI_AGENTS_REMOTE_CONTAINER": "1"\n}}\n', True),
        ("# sets AI_AGENTS_REMOTE_CONTAINER=1 someday\n", False),
        ("// AI_AGENTS_REMOTE_CONTAINER=1\n", False),
        ("RUN echo AI_AGENTS_REMOTE_CONTAINER\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=true\n", True),
        ('ENV AI_AGENTS_REMOTE_CONTAINER="1"\n', True),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=TRUE\n", True),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=0\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=false\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER 0\n", False),
        ("export AI_AGENTS_REMOTE_CONTAINER=0\n", False),
        ('{"containerEnv": {\n  "AI_AGENTS_REMOTE_CONTAINER": "0"\n}}\n', False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=0\nENV AI_AGENTS_REMOTE_CONTAINER=1\n", True),
        ("", False),
    ],
)
def test_sets_marker_requires_a_truthy_assignment_not_a_mention(text: str, expected: bool) -> None:
    assert _sets_marker(text) is expected


def test_every_tracked_managed_image_sets_the_marker() -> None:
    """Fails when a Dockerfile, Containerfile, or .devcontainer file lacks the marker.

    ADR-104 rule 8 needs every managed image detected by
    ``_is_remote_container()``. A new image either carries the marker or adds
    its own measured filesystem signal and removes itself from this check.

    Limit: AC3 covers image definitions tracked in this repository only. No
    Dockerfile, Containerfile, or .devcontainer path is tracked today, so this
    test scans zero files and passes vacuously until one lands. An image
    provisioned outside the repo (such as the Claude web image) has no check
    here; the SessionStart hook is its setter.
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
    """The rendered hook copies are byte-identical to the template (build_all.py ran)."""
    template = (REPO_ROOT / "templates" / "hooks" / "session-start.sh").read_bytes()
    shipped = (REPO_ROOT / "src" / "claude" / "hooks" / "session-start.sh").read_bytes()

    assert INSTALLED_SCRIPT.read_bytes() == template
    assert shipped == template
    assert MARKER_LINE.encode() in template


def test_known_managed_environments_each_have_a_setter() -> None:
    """Pin the two setters this repository relies on today.

    Claude web is marked by the SessionStart hook; Codespaces is marked by the
    platform's own variable. The expected dict is hand-written, so this guards
    against removing either setter. It does not detect a new managed
    environment that nobody adds a row for; that gap is not covered.
    """
    from scripts.validation import run_workflow_local_test as rwlt

    template = (REPO_ROOT / "templates" / "hooks" / "session-start.sh").read_text(encoding="utf-8")
    setters = {
        "claude-web": any(
            line.strip().startswith(f"echo '{MARKER_LINE}'") for line in template.splitlines()
        ),
        "codespaces": "CODESPACES" in rwlt._REMOTE_CONTAINER_ENV_MARKERS,
    }

    assert setters == {"claude-web": True, "codespaces": True}
    assert MARKER_NAME in rwlt._REMOTE_CONTAINER_ENV_MARKERS
