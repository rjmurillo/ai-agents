"""Input validation shared by GitHub URL parsers."""

from __future__ import annotations

import re
from urllib.parse import unquote

SAFE_OWNER_REPO_RE = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_.]*$")
SAFE_REF_RE = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_./]*$")
SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9.][-a-zA-Z0-9_./%+@]*$")
SAFE_GIST_ID_RE = re.compile(r"(?:[0-9]+|[a-fA-F0-9]{20}|[a-fA-F0-9]{32})")
SAFE_GIST_REVISION_RE = re.compile(r"[a-fA-F0-9]{40}")
DANGEROUS_CHARS = set("\"'`$;&|><(){}[]!\\")


def is_safe_input(
    value: str | None,
    pattern: re.Pattern[str],
    allow_empty: bool = False,
    allow_triple_dot: bool = False,
    reject_path_traversal: bool = False,
) -> bool:
    """Validate input against command injection attacks."""
    if not value:
        return allow_empty
    if any(character in DANGEROUS_CHARS for character in value):
        return False

    if reject_path_traversal:
        for segment in value.split("/"):
            decoded = unquote(segment)
            if decoded in {".", ".."}:
                return False
            if "/" in decoded or "\\" in decoded:
                return False
    else:
        if allow_triple_dot:
            test_value = value.replace("...", "__TRIPLE__")
            if ".." in test_value:
                return False
        elif ".." in value:
            return False

    return bool(pattern.fullmatch(value))


def is_safe_raw_path(segments: list[str]) -> bool:
    """Reject path forms that gh or the remote server could reinterpret."""
    for segment in segments:
        decoded = unquote(segment)
        if decoded in {".", ".."}:
            return False
        if any(ord(character) < 32 or ord(character) == 127 for character in decoded):
            return False
        if any(character in DANGEROUS_CHARS for character in decoded):
            return False
        if "/" in decoded or "\\" in decoded:
            return False
    return True
