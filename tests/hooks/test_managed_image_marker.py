#!/usr/bin/env python3
"""Every tracked managed image must set AI_AGENTS_REMOTE_CONTAINER (Issue #5541, AC3).

ADR-104 rule 8 needs every managed environment detected by
``_is_remote_container()``. The Claude web container is marked by the
SessionStart hook (see ``test_session_start_remote_container_marker.py``); an
image definition tracked in this repository must carry the marker itself.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.hooks.test_session_start_env_escaping import REPO_ROOT

MARKER_NAME = "AI_AGENTS_REMOTE_CONTAINER"
IMAGE_FILE_NAMES = ("Dockerfile", "Containerfile")
# Only the devcontainer definition files count as a managed image. A sibling
# script, README, or features file under `.devcontainer/` is not an image.
DEVCONTAINER_FILE_NAMES = ("devcontainer.json", ".devcontainer.json")
# Fixtures and CI action images are not agent environments. A path with one of
# these parts, or under `.github/actions/`, is outside the image check.
NON_IMAGE_PATH_PARTS = ("tests", "test", "fixtures", "testdata")
NON_IMAGE_PATH_PREFIXES = (".github/actions/",)
# An actual assignment, not a mention: `ENV NAME=1`, `ENV NAME 1`, `export NAME=1`,
# `NAME=1`, or the JSON form `"NAME": "1"`. A comment line never matches. The value
# is captured so the check can require one `_env_truthy()` accepts: `=0` or
# `=false` declares the marker false and must not satisfy the image check.
_ASSIGNMENT = re.compile(
    rf"^\s*(?:(?:ENV|export)\s+)?{MARKER_NAME}(?:\s*=\s*|\s+)(?P<bare>\S+)"
    rf"|^\s*\"{MARKER_NAME}\"\s*:\s*\"(?P<json>[^\"]+)\""
)
_COMMENT_PREFIXES = ("#", "//", "*", "/*")


def _sets_marker(text: str) -> bool:
    """True when the LAST non-comment assignment of the marker is a value ``_env_truthy()`` accepts.

    Last wins, as in the hook guard: ``ENV NAME=1`` then ``ENV NAME=0`` leaves 0.
    """
    from scripts.validation import run_workflow_local_test as rwlt

    effective: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(_COMMENT_PREFIXES):
            continue
        match = _ASSIGNMENT.match(line)
        if match is None:
            continue
        effective = (match.group("bare") or match.group("json") or "").strip("\"'").lower()
    return effective is not None and effective in rwlt._TRUTHY


def _is_managed_image_path(rel: str) -> bool:
    """True for a Dockerfile, Containerfile, or devcontainer definition outside fixtures."""
    if rel.startswith(NON_IMAGE_PATH_PREFIXES):
        return False
    parts = Path(rel).parts
    if any(part in NON_IMAGE_PATH_PARTS for part in parts[:-1]):
        return False
    name = parts[-1]
    if name.endswith(".md"):
        return False
    return (
        name in IMAGE_FILE_NAMES
        or name.startswith(("Dockerfile.", "Containerfile."))
        or name in DEVCONTAINER_FILE_NAMES
    )


def _images_missing_marker(root: Path, tracked: list[str]) -> list[str]:
    """Tracked managed-image files that never assign the marker."""
    missing = []
    for rel in tracked:
        if not _is_managed_image_path(rel):
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
    ("rel", "expected"),
    [
        ("Dockerfile", True),
        ("docker/Dockerfile", True),
        ("Dockerfile.dev", True),
        ("Containerfile", True),
        ("Containerfile.ci", True),
        (".devcontainer/devcontainer.json", True),
        (".devcontainer/web/devcontainer.json", True),
        (".devcontainer.json", True),
        (".devcontainer/post-create.sh", False),
        (".devcontainer/README.md", False),
        (".devcontainer/features/feature.json", False),
        ("tests/fixtures/Dockerfile", False),
        ("tests/devcontainer.json", False),
        ("scripts/testdata/Containerfile", False),
        (".github/actions/build/Dockerfile", False),
        ("README.md", False),
        ("docs/Dockerfile.md", False),
    ],
)
def test_managed_image_path_is_limited_to_image_definitions(rel: str, expected: bool) -> None:
    assert _is_managed_image_path(rel) is expected


def test_image_check_ignores_non_image_files_and_fixtures(tmp_path: Path) -> None:
    """A `.devcontainer` script, a fixture Dockerfile, and an action image are not flagged."""
    for rel in (
        ".devcontainer/post-create.sh",
        "tests/fixtures/Dockerfile",
        ".github/actions/x/Dockerfile",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("FROM scratch\n", encoding="utf-8")

    tracked = [
        ".devcontainer/post-create.sh",
        "tests/fixtures/Dockerfile",
        ".github/actions/x/Dockerfile",
    ]

    assert _images_missing_marker(tmp_path, tracked) == []


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
        ("ENV AI_AGENTS_REMOTE_CONTAINER=1\nENV AI_AGENTS_REMOTE_CONTAINER=0\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=1\n# AI_AGENTS_REMOTE_CONTAINER=0\n", True),
        ("", False),
    ],
)
def test_sets_marker_requires_a_truthy_assignment_not_a_mention(text: str, expected: bool) -> None:
    assert _sets_marker(text) is expected


def test_every_tracked_managed_image_sets_the_marker() -> None:
    """Fails when a Dockerfile, Containerfile, or devcontainer.json lacks the marker.

    ADR-104 rule 8 needs every managed image detected by
    ``_is_remote_container()``. A new image either carries the marker or adds
    its own measured filesystem signal and removes itself from this check.

    Limit: AC3 covers image definitions tracked in this repository only. No
    Dockerfile, Containerfile, or devcontainer.json path is tracked today, so this
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
