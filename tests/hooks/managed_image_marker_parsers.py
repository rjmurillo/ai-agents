#!/usr/bin/env python3
"""Parsers behind the managed-image marker check (Issue #5541, AC3).

Reads a Dockerfile, Containerfile, or devcontainer definition and reports
whether its runtime environment carries ``AI_AGENTS_REMOTE_CONTAINER`` with a
value ``_env_truthy()`` accepts. The tests live in
``test_managed_image_marker.py``.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

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


def sets_marker(rel: str, text: str) -> bool:
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


def is_managed_image_path(rel: str) -> bool:
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
    return sets_marker(dockerfile_rel, target.read_text(encoding="utf-8", errors="replace"))


def images_missing_marker(root: Path, tracked: list[str]) -> list[str]:
    """Tracked managed-image files that never assign the marker."""
    missing = []
    for rel in tracked:
        if not is_managed_image_path(rel):
            continue
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        if not sets_marker(rel, text) and not _build_dockerfile_sets_marker(root, rel, text):
            missing.append(rel)
    return missing
