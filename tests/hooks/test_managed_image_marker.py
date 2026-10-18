#!/usr/bin/env python3
"""Every tracked managed image must set AI_AGENTS_REMOTE_CONTAINER (Issue #5541, AC3).

ADR-104 rule 8 needs every managed environment detected by
``_is_remote_container()``. The Claude web container is marked by the
SessionStart hook (see ``test_session_start_remote_container_marker.py``); an
image definition tracked in this repository must carry the marker itself.
"""

from __future__ import annotations

import json
import shlex
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


def _logical_dockerfile_lines(text: str) -> list[str]:
    """Dockerfile instructions with comment lines dropped and `\\` continuations joined.

    Docker removes a comment line even inside a continuation, so comments go
    first. A `RUN a && \\` continuation therefore stays part of its RUN line and
    never reads as a standalone `ENV` or assignment.
    """
    logical: list[str] = []
    pending = ""
    for raw in text.splitlines():
        if raw.strip().startswith("#"):
            continue
        line = raw.rstrip()
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        logical.append(pending + line)
        pending = ""
    if pending:
        logical.append(pending)
    return [line.strip() for line in logical if line.strip()]


def _env_instruction_pairs(rest: str) -> list[tuple[str, str]]:
    """(name, value) pairs of an `ENV` instruction body, in order.

    Handles `ENV NAME=1 OTHER=2` and the legacy `ENV NAME 1`. A body that does
    not tokenize (unbalanced quote) yields no pairs.
    """
    try:
        tokens = shlex.split(rest, posix=True)
    except ValueError:
        return []
    if not tokens:
        return []
    if "=" not in tokens[0]:
        return [(tokens[0], " ".join(tokens[1:]))]
    pairs = []
    for token in tokens:
        name, sep, value = token.partition("=")
        if sep:
            pairs.append((name, value))
    return pairs


def _from_instruction(rest: str) -> tuple[str, str | None]:
    """(base reference, stage alias) of a `FROM` body, both lowercased.

    Skips `--platform=...` style flags. The alias is None when there is no
    `AS name` clause. A body with no base reference yields an empty base.
    """
    tokens = [t for t in rest.split() if not t.startswith("--")]
    base = tokens[0].lower() if tokens else ""
    alias = tokens[2].lower() if len(tokens) >= 3 and tokens[1].lower() == "as" else None
    return base, alias


def _dockerfile_effective_value(text: str) -> str | None:
    """Value the FINAL stage's image config carries for the marker, or None.

    A stage starts empty when it builds on an external image, and inherits the
    value of an earlier stage when `FROM` names that stage's alias. Only the
    final stage counts, and a `RUN` line that names the variable never
    persists into the image config.
    """
    effective: str | None = None
    alias: str | None = None
    stage_values: dict[str, str | None] = {}
    for line in _logical_dockerfile_lines(text):
        keyword, _, rest = line.partition(" ")
        word = keyword.upper()
        if word == "FROM":
            if alias is not None:
                stage_values[alias] = effective
            base, alias = _from_instruction(rest)
            effective = stage_values.get(base)
        elif word == "ENV":
            for name, value in _env_instruction_pairs(rest.strip()):
                if name == MARKER_NAME:
                    effective = value
    return effective


def _skip_string_char(chars: str, i: int) -> int:
    """Index of the last character of the string-literal char starting at ``i``.

    A backslash escapes the next character, so an escaped quote does not end
    the literal.
    """
    return i + 1 if chars[i] == "\\" and i + 1 < len(chars) else i


def _drop_jsonc_comments(text: str) -> str:
    """Remove `//` and `/* */` comments that sit outside string literals."""
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        if in_string:
            end = _skip_string_char(text, i)
            out.append(text[i : end + 1])
            in_string = text[end] != '"' or end != i
            i = end + 1
        elif text.startswith("//", i):
            newline = text.find("\n", i)
            i = n if newline == -1 else newline
        elif text.startswith("/*", i):
            close = text.find("*/", i + 2)
            i = n if close == -1 else close + 2
        else:
            in_string = text[i] == '"'
            out.append(text[i])
            i += 1
    return "".join(out)


def _drop_trailing_commas(text: str) -> str:
    """Remove a comma that is followed only by whitespace and a closing bracket."""
    out: list[str] = []
    last_comma = -1
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            end = _skip_string_char(text, i)
            out.append(text[i : end + 1])
            in_string = text[end] != '"' or end != i
            i = end + 1
            continue
        if ch in "}]" and last_comma != -1:
            out[last_comma] = ""
        if ch == ",":
            last_comma = len(out)
        elif not ch.isspace():
            last_comma = -1
        in_string = ch == '"'
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_jsonc(text: str) -> str:
    """Make devcontainer.json JSONC (comments, trailing commas) parseable as JSON."""
    return _drop_trailing_commas(_drop_jsonc_comments(text))


def _devcontainer_effective_value(text: str) -> str | None:
    """Runtime value from `remoteEnv` (wins) or `containerEnv`, or None.

    `build.args` is build-time only and never reaches a running container, so
    it is not read. Unparseable JSON yields None: the image is reported as
    missing the marker rather than guessed at.
    """
    try:
        data = json.loads(_strip_jsonc(text))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    for section in ("remoteEnv", "containerEnv"):
        env = data.get(section)
        if isinstance(env, dict) and MARKER_NAME in env:
            value = env[MARKER_NAME]
            return value if isinstance(value, str) else None
    return None


def _devcontainer_dockerfile(text: str) -> str | None:
    """`build.dockerfile` from a devcontainer definition, or None.

    The path is relative to the devcontainer file. A bare `image` reference
    names a registry image that this repository cannot read, so it is not
    followed.
    """
    try:
        data = json.loads(_strip_jsonc(text))
    except ValueError:
        return None
    build = data.get("build") if isinstance(data, dict) else None
    dockerfile = build.get("dockerfile") if isinstance(build, dict) else None
    return dockerfile if isinstance(dockerfile, str) and dockerfile else None


def _sets_marker(rel: str, text: str) -> bool:
    """True when the image's runtime environment holds a value ``_env_truthy()`` accepts.

    ``rel`` picks the parser: a devcontainer definition reads `containerEnv` and
    `remoteEnv`; a Dockerfile or Containerfile reads `ENV` lines in its final
    stage. Last wins, as in the hook guard: ``ENV NAME=1`` then ``ENV NAME=0``
    leaves 0.
    """
    from scripts.validation import run_workflow_local_test as rwlt

    if Path(rel).name in DEVCONTAINER_FILE_NAMES:
        effective = _devcontainer_effective_value(text)
    else:
        effective = _dockerfile_effective_value(text)
    return effective is not None and effective.strip().lower() in rwlt._TRUTHY


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


def _build_dockerfile_sets_marker(root: Path, rel: str, text: str) -> bool:
    """True when a devcontainer's `build.dockerfile` sets the marker in its final stage.

    ``containerEnv`` and ``remoteEnv`` are checked first by the caller; this is
    the fallback for a definition that takes the marker from its Dockerfile.
    A missing or unreadable Dockerfile counts as no marker.
    """
    if Path(rel).name not in DEVCONTAINER_FILE_NAMES:
        return False
    dockerfile = _devcontainer_dockerfile(text)
    if dockerfile is None:
        return False
    resolved_root = root.resolve()
    target = ((root / rel).parent / dockerfile).resolve()
    if not target.is_relative_to(resolved_root) or not target.is_file():
        return False
    dockerfile_rel = target.relative_to(resolved_root).as_posix()
    return _sets_marker(dockerfile_rel, target.read_text(encoding="utf-8", errors="replace"))


def _images_missing_marker(root: Path, tracked: list[str]) -> list[str]:
    """Tracked managed-image files that never assign the marker."""
    missing = []
    for rel in tracked:
        if not _is_managed_image_path(rel):
            continue
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        if not _sets_marker(rel, text) and not _build_dockerfile_sets_marker(root, rel, text):
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
    assert _sets_marker("Dockerfile", text) is expected


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
    assert _sets_marker("Dockerfile", text) is expected


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
    assert _sets_marker("Dockerfile", text) is expected


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
    assert _sets_marker(".devcontainer/devcontainer.json", text) is expected
    assert _sets_marker(".devcontainer.json", text) is expected


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
    assert _images_missing_marker(REPO_ROOT, _tracked_files(REPO_ROOT)) == []


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

    assert _images_missing_marker(tmp_path, [".devcontainer/devcontainer.json"]) == []


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

    assert _images_missing_marker(tmp_path, [".devcontainer/devcontainer.json"]) == [
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

    assert _images_missing_marker(tmp_path, [".devcontainer/devcontainer.json"]) == []


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

    assert _images_missing_marker(root, [".devcontainer/devcontainer.json"]) == [
        ".devcontainer/devcontainer.json"
    ]
