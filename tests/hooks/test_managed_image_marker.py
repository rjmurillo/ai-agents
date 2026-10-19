#!/usr/bin/env python3
"""Every tracked managed image must set AI_AGENTS_REMOTE_CONTAINER (Issue #5541, AC3).

ADR-104 rule 8 needs every managed environment detected by
``_is_remote_container()``. The Claude web container is marked by the
SessionStart hook (see ``test_session_start_remote_container_marker.py``); an
image definition tracked in this repository must carry the marker itself.
The parsers live in ``managed_image_marker_parsers.py``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.hooks.managed_image_marker_parsers import (
    images_missing_marker,
    is_managed_image_path,
    sets_marker,
)
from tests.hooks.test_session_start_env_escaping import REPO_ROOT


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

    assert images_missing_marker(tmp_path, tracked) == [
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
    assert is_managed_image_path(rel) is expected


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

    assert images_missing_marker(tmp_path, tracked) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ENV AI_AGENTS_REMOTE_CONTAINER=1\n", True),
        ("ENV AI_AGENTS_REMOTE_CONTAINER 1\n", True),
        ("env AI_AGENTS_REMOTE_CONTAINER=1\n", True),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=true\n", True),
        ('ENV AI_AGENTS_REMOTE_CONTAINER="1"\n', True),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=TRUE\n", True),
        ("ENV FOO=a AI_AGENTS_REMOTE_CONTAINER=1\n", True),
        ("ENV FOO=a \\\n    AI_AGENTS_REMOTE_CONTAINER=1\n", True),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=0\nENV AI_AGENTS_REMOTE_CONTAINER=1\n", True),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=1\n# ENV AI_AGENTS_REMOTE_CONTAINER=0\n", True),
        ("# sets AI_AGENTS_REMOTE_CONTAINER=1 someday\n", False),
        ("RUN echo AI_AGENTS_REMOTE_CONTAINER\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=0\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=false\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER 0\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER=1\nENV AI_AGENTS_REMOTE_CONTAINER=0\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER_OTHER=1\n", False),
        ("ENV AI_AGENTS_REMOTE_CONTAINER='unterminated\n", False),
        ("export AI_AGENTS_REMOTE_CONTAINER=1\n", False),
        ("ARG AI_AGENTS_REMOTE_CONTAINER=1\n", False),
        ("", False),
    ],
)
def test_dockerfile_marker_requires_a_truthy_env_instruction(text: str, expected: bool) -> None:
    assert sets_marker("Dockerfile", text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Set only in a builder stage: the final image does not inherit it.
        (
            "FROM base AS build\nENV AI_AGENTS_REMOTE_CONTAINER=1\nFROM base\nRUN true\n",
            False,
        ),
        # Set in the final stage: counts.
        (
            "FROM base AS build\nFROM base\nENV AI_AGENTS_REMOTE_CONTAINER=1\n",
            True,
        ),
        # Set in the builder stage and again in the final stage: counts.
        (
            "FROM a AS b\nENV AI_AGENTS_REMOTE_CONTAINER=1\nFROM a\n"
            "ENV AI_AGENTS_REMOTE_CONTAINER=true\n",
            True,
        ),
        # Final stage resets it: last wins.
        (
            "FROM a\nENV AI_AGENTS_REMOTE_CONTAINER=1\nENV AI_AGENTS_REMOTE_CONTAINER=0\n",
            False,
        ),
        # FROM keyword is case-insensitive.
        ("from a as b\nENV AI_AGENTS_REMOTE_CONTAINER=1\nfrom a\n", False),
        # FROM names an earlier stage: the final image inherits its ENV.
        ("FROM base AS build\nENV AI_AGENTS_REMOTE_CONTAINER=1\nFROM build\nRUN true\n", True),
        # Alias match is case-insensitive and ignores FROM flags.
        (
            "FROM base AS Build\nENV AI_AGENTS_REMOTE_CONTAINER=1\n"
            "FROM --platform=linux/arm64 build\n",
            True,
        ),
        # The inheriting stage can override the inherited value.
        (
            "FROM base AS build\nENV AI_AGENTS_REMOTE_CONTAINER=1\n"
            "FROM build\nENV AI_AGENTS_REMOTE_CONTAINER=0\n",
            False,
        ),
        # Inheritance chains through several stages.
        (
            "FROM base AS a\nENV AI_AGENTS_REMOTE_CONTAINER=1\nFROM a AS b\nRUN true\nFROM b\n",
            True,
        ),
        # An inherited stage that never set it leaves it unset.
        ("FROM base AS build\nRUN true\nFROM build\n", False),
        # A later stage that does not name the marking stage does not inherit.
        (
            "FROM base AS build\nENV AI_AGENTS_REMOTE_CONTAINER=1\nFROM other AS x\nFROM x\n",
            False,
        ),
    ],
    ids=[
        "builder-only",
        "final-stage",
        "both-stages",
        "final-resets",
        "lowercase-from",
        "inherits-from-named-stage",
        "inherits-case-and-flags",
        "inheriting-stage-overrides",
        "inheritance-chain",
        "inherited-unset",
        "unrelated-stage",
    ],
)
def test_dockerfile_marker_counts_only_the_final_stage(text: str, expected: bool) -> None:
    assert sets_marker("Dockerfile", text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # A RUN continuation line that starts with the assignment is part of RUN.
        ("FROM a\nRUN apt-get update && \\\n    AI_AGENTS_REMOTE_CONTAINER=1 make\n", False),
        ("FROM a\nRUN true && \\\nAI_AGENTS_REMOTE_CONTAINER=1 ./run\n", False),
        # A RUN line whose command is an ENV-looking continuation is still RUN.
        ("FROM a\nRUN export AI_AGENTS_REMOTE_CONTAINER=1\n", False),
        # An ENV continued over lines is one ENV instruction.
        ("FROM a\nENV FOO=bar \\\n    AI_AGENTS_REMOTE_CONTAINER=1\n", True),
        # A comment inside a continuation does not break the join.
        ("FROM a\nENV FOO=bar \\\n# note\n    AI_AGENTS_REMOTE_CONTAINER=1\n", True),
        # A trailing backslash on the last line does not crash.
        ("FROM a\nENV FOO=bar \\\n", False),
    ],
    ids=[
        "run-continuation",
        "run-continuation-flush-left",
        "run-export",
        "env-continuation",
        "env-continuation-with-comment",
        "dangling-continuation",
    ],
)
def test_dockerfile_marker_ignores_run_lines_and_joins_continuations(
    text: str, expected: bool
) -> None:
    assert sets_marker("Dockerfile", text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"containerEnv": {"AI_AGENTS_REMOTE_CONTAINER": "1"}}', True),
        ('{"containerEnv": {"AI_AGENTS_REMOTE_CONTAINER": "true"}}', True),
        ('{"remoteEnv": {"AI_AGENTS_REMOTE_CONTAINER": "1"}}', True),
        ('{"containerEnv": {"AI_AGENTS_REMOTE_CONTAINER": "0"}}', False),
        ('{"containerEnv": {"AI_AGENTS_REMOTE_CONTAINER": ""}}', False),
        # remoteEnv overrides containerEnv.
        (
            '{"containerEnv": {"AI_AGENTS_REMOTE_CONTAINER": "1"},'
            ' "remoteEnv": {"AI_AGENTS_REMOTE_CONTAINER": "0"}}',
            False,
        ),
        (
            '{"containerEnv": {"AI_AGENTS_REMOTE_CONTAINER": "0"},'
            ' "remoteEnv": {"AI_AGENTS_REMOTE_CONTAINER": "1"}}',
            True,
        ),
        # Build args are build time only, never runtime env.
        ('{"build": {"args": {"AI_AGENTS_REMOTE_CONTAINER": "1"}}}', False),
        (
            '{"build": {"args": {"AI_AGENTS_REMOTE_CONTAINER": "1"}},'
            ' "containerEnv": {"AI_AGENTS_REMOTE_CONTAINER": "0"}}',
            False,
        ),
        # Other places the name can appear.
        ('{"name": "AI_AGENTS_REMOTE_CONTAINER=1"}', False),
        ('{"features": {"AI_AGENTS_REMOTE_CONTAINER": "1"}}', False),
        ('{"containerEnv": {"AI_AGENTS_REMOTE_CONTAINER_OTHER": "1"}}', False),
        # JSON null and non-string values are not a truthy string.
        ('{"remoteEnv": {"AI_AGENTS_REMOTE_CONTAINER": null}}', False),
        ('{"containerEnv": {"AI_AGENTS_REMOTE_CONTAINER": 1}}', False),
        # JSONC: comments and trailing commas are valid in devcontainer.json.
        (
            '{\n  // managed image marker\n  "containerEnv": {\n'
            '    /* ADR-104 rule 8 */\n    "AI_AGENTS_REMOTE_CONTAINER": "1",\n  },\n}\n',
            True,
        ),
        ('{"containerEnv": {"URL": "http://x//y,", "AI_AGENTS_REMOTE_CONTAINER": "1"}}', True),
        # An escaped quote does not end the string, so the `//` stays text.
        (
            '{"containerEnv": {"X": "a\\"//b,", "AI_AGENTS_REMOTE_CONTAINER": "1"}}',
            True,
        ),
        # An unterminated block comment swallows the rest, so nothing is set.
        ('{"containerEnv": {}} /* AI_AGENTS_REMOTE_CONTAINER', False),
        # A commented-out entry does not count.
        ('{"containerEnv": {\n  // "AI_AGENTS_REMOTE_CONTAINER": "1"\n}}', False),
        # Malformed or non-object JSON is reported as missing, not guessed at.
        ("{not json", False),
        ("[]", False),
        ("", False),
        ("{}", False),
    ],
    ids=[
        "container-env-1",
        "container-env-true",
        "remote-env-1",
        "container-env-0",
        "container-env-empty",
        "remote-overrides-container-to-0",
        "remote-overrides-container-to-1",
        "build-args-only",
        "build-args-and-container-0",
        "name-in-other-field",
        "name-in-features",
        "prefix-name",
        "null-value",
        "int-value",
        "jsonc-comments-trailing-commas",
        "string-with-slashes-and-comma",
        "escaped-quote-in-string",
        "unterminated-block-comment",
        "commented-out-entry",
        "malformed",
        "non-object",
        "empty",
        "empty-object",
    ],
)
def test_devcontainer_marker_reads_only_runtime_env(text: str, expected: bool) -> None:
    assert sets_marker(".devcontainer/devcontainer.json", text) is expected
    assert sets_marker(".devcontainer.json", text) is expected


def _tracked_files(root: Path) -> list[str]:
    """Tracked files under ``root``. Fails in a git checkout when listing fails.

    A checkout whose ``git ls-files`` breaks must not pass the image check
    silently. Only a tree with no ``.git`` entry (such as an exported source
    archive) skips.
    """
    proc = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        if (root / ".git").exists():
            pytest.fail(f"git ls-files failed in a git checkout: {proc.stderr.strip()}")
        pytest.skip(f"not a git checkout: {proc.stderr.strip()}")
    return [p for p in proc.stdout.split("\0") if p and (root / p).is_file()]


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
    assert images_missing_marker(REPO_ROOT, _tracked_files(REPO_ROOT)) == []


def _fake_ls_files(returncode: int):
    def run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr="boom")

    return run


def test_tracked_files_fails_when_git_breaks_in_a_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(subprocess, "run", _fake_ls_files(128))

    with pytest.raises(pytest.fail.Exception, match="git ls-files failed"):
        _tracked_files(tmp_path)


def test_tracked_files_skips_when_the_tree_is_not_a_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", _fake_ls_files(128))

    with pytest.raises(pytest.skip.Exception, match="not a git checkout"):
        _tracked_files(tmp_path)


def test_tracked_files_returns_existing_files_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    def run(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, stdout="Dockerfile\0gone\0", stderr="")

    monkeypatch.setattr(subprocess, "run", run)

    assert _tracked_files(tmp_path) == ["Dockerfile"]


def test_devcontainer_takes_the_marker_from_its_build_dockerfile(tmp_path: Path) -> None:
    dev = tmp_path / ".devcontainer"
    dev.mkdir()
    (dev / "devcontainer.json").write_text(
        '{"build": {"dockerfile": "Dockerfile"}}', encoding="utf-8"
    )
    (dev / "Dockerfile").write_text(
        "FROM base AS build\nENV AI_AGENTS_REMOTE_CONTAINER=1\nFROM build\n", encoding="utf-8"
    )

    assert images_missing_marker(tmp_path, [".devcontainer/devcontainer.json"]) == []


@pytest.mark.parametrize(
    ("config", "dockerfile"),
    [
        ('{"build": {"dockerfile": "Dockerfile"}}', "FROM base\n"),
        ('{"build": {"dockerfile": "missing.Dockerfile"}}', None),
        ('{"build": {"dockerfile": 7}}', None),
        ('{"build": {"dockerfile": ""}}', None),
        ('{"build": "Dockerfile"}', None),
        ('{"image": "registry.example/base:1"}', None),
        ("{not json", None),
    ],
    ids=[
        "dockerfile-lacks-marker",
        "dockerfile-missing",
        "non-string-path",
        "empty-path",
        "build-not-object",
        "registry-image",
        "malformed",
    ],
)
def test_devcontainer_without_a_marker_source_is_reported(
    tmp_path: Path, config: str, dockerfile: str | None
) -> None:
    dev = tmp_path / ".devcontainer"
    dev.mkdir()
    (dev / "devcontainer.json").write_text(config, encoding="utf-8")
    if dockerfile is not None:
        (dev / "Dockerfile").write_text(dockerfile, encoding="utf-8")

    assert images_missing_marker(tmp_path, [".devcontainer/devcontainer.json"]) == [
        ".devcontainer/devcontainer.json"
    ]


def test_devcontainer_env_still_wins_over_its_build_dockerfile(tmp_path: Path) -> None:
    dev = tmp_path / ".devcontainer"
    dev.mkdir()
    (dev / "devcontainer.json").write_text(
        '{"build": {"dockerfile": "Dockerfile"},'
        ' "containerEnv": {"AI_AGENTS_REMOTE_CONTAINER": "1"}}',
        encoding="utf-8",
    )
    (dev / "Dockerfile").write_text("FROM base\n", encoding="utf-8")

    assert images_missing_marker(tmp_path, [".devcontainer/devcontainer.json"]) == []


def test_devcontainer_build_dockerfile_outside_the_repo_is_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / ".devcontainer").mkdir(parents=True)
    (root / ".devcontainer" / "devcontainer.json").write_text(
        '{"build": {"dockerfile": "../../outside/Dockerfile"}}', encoding="utf-8"
    )
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "Dockerfile").write_text(
        "ENV AI_AGENTS_REMOTE_CONTAINER=1\n", encoding="utf-8"
    )

    assert images_missing_marker(root, [".devcontainer/devcontainer.json"]) == [
        ".devcontainer/devcontainer.json"
    ]


@pytest.mark.parametrize(
    "env_section",
    [
        '"containerEnv": {"AI_AGENTS_REMOTE_CONTAINER": "0"}',
        '"remoteEnv": {"AI_AGENTS_REMOTE_CONTAINER": null}',
        '"remoteEnv": {"AI_AGENTS_REMOTE_CONTAINER": ""}',
    ],
    ids=["container-env-0", "remote-env-null-unsets", "remote-env-empty"],
)
def test_devcontainer_env_that_names_the_marker_overrides_its_build_dockerfile(
    tmp_path: Path, env_section: str
) -> None:
    """The definition's env applies at runtime, so a Dockerfile `=1` cannot rescue a `0`."""
    dev = tmp_path / ".devcontainer"
    dev.mkdir()
    (dev / "devcontainer.json").write_text(
        '{"build": {"dockerfile": "Dockerfile"}, ' + env_section + "}", encoding="utf-8"
    )
    (dev / "Dockerfile").write_text(
        "FROM base\nENV AI_AGENTS_REMOTE_CONTAINER=1\n", encoding="utf-8"
    )

    assert images_missing_marker(tmp_path, [".devcontainer/devcontainer.json"]) == [
        ".devcontainer/devcontainer.json"
    ]
