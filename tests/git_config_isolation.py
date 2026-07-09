"""Hermetic git-config isolation helpers for the test suite (issue #2996).

``git -c core.hooksPath=/abs <cmd>`` re-exports the override to child processes
via ``GIT_CONFIG_PARAMETERS`` (and, for the indexed form, ``GIT_CONFIG_COUNT`` +
``GIT_CONFIG_KEY_n`` / ``GIT_CONFIG_VALUE_n``). When the pre-push hook is invoked
that way with an *absolute* hooks path (which happens when a push is launched
from a linked worktree, where ``-c core.hooksPath=.githooks`` relative would not
resolve), the absolute path resolves inside every ``tmp_path`` git repo the
suite creates. Each fixture ``git commit`` then runs the *real* pre-commit hook,
which fails outside the repo, producing dozens of
``subprocess.CalledProcessError: git commit ... exit status 1`` failures that
have nothing to do with the code under test.

Stripping ``core.hooksPath`` from the inherited git-config env makes the suite
hermetic regardless of how the launcher configured hooks. This module holds the
pure, unit-tested string manipulation; ``conftest.py`` wires it into a
session-scoped autouse fixture.
"""

from __future__ import annotations

import re
from collections.abc import MutableMapping

# Git normalizes config keys case-insensitively; core.hooksPath compares equal to
# CORE.HOOKSPATH. Store the comparison target in canonical lowercase.
_HOOKS_PATH_KEY = "core.hookspath"

# One single-quoted run in GIT_CONFIG_PARAMETERS. Git escapes an embedded single
# quote as '\'' (close quote, literal backslash-quote, reopen quote), so a run is
# any mix of non-quote characters and that escape sequence, wrapped in quotes.
_QUOTED_RUN = r"'(?:[^']|'\\'')*'"


def _unquote_git_param_key(token: str) -> str:
    """Return the lowercased config key from a GIT_CONFIG_PARAMETERS token.

    A token is ``'section.key'`` or ``'section.key'='value'``. The key is the
    first single-quoted run. Embedded ``'\\''`` escapes collapse to a single
    quote.
    """
    match = re.match(_QUOTED_RUN, token)
    if match is None:
        return token.lower()
    inner = match.group(0)[1:-1]
    return inner.replace("'\\''", "'").lower()


def _split_git_config_parameters(raw: str) -> list[str]:
    """Split GIT_CONFIG_PARAMETERS into its space-separated tokens.

    Spaces inside single-quoted runs do not separate tokens.
    """
    tokens: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        while i < n and raw[i] == " ":
            i += 1
        if i >= n:
            break
        start = i
        in_quote = False
        while i < n:
            char = raw[i]
            if char == "'":
                in_quote = not in_quote
            elif char == " " and not in_quote:
                break
            i += 1
        tokens.append(raw[start:i])
    return tokens


def _strip_from_parameters(environ: MutableMapping[str, str]) -> None:
    """Drop core.hooksPath tokens from GIT_CONFIG_PARAMETERS in place."""
    raw = environ.get("GIT_CONFIG_PARAMETERS")
    if not raw:
        return
    kept = [
        token
        for token in _split_git_config_parameters(raw)
        if _unquote_git_param_key(token) != _HOOKS_PATH_KEY
    ]
    if kept:
        environ["GIT_CONFIG_PARAMETERS"] = " ".join(kept)
    else:
        environ.pop("GIT_CONFIG_PARAMETERS", None)


def _strip_from_indexed(environ: MutableMapping[str, str]) -> None:
    """Drop core.hooksPath entries from the GIT_CONFIG_COUNT family in place.

    Surviving entries are renumbered contiguously so git still reads them.
    """
    raw_count = environ.get("GIT_CONFIG_COUNT")
    if raw_count is None:
        return
    try:
        count = int(raw_count)
    except ValueError:
        return

    kept: list[tuple[str | None, str | None]] = []
    for idx in range(count):
        key = environ.get(f"GIT_CONFIG_KEY_{idx}")
        value = environ.get(f"GIT_CONFIG_VALUE_{idx}")
        if key is not None and key.lower() == _HOOKS_PATH_KEY:
            continue
        kept.append((key, value))

    for idx in range(count):
        environ.pop(f"GIT_CONFIG_KEY_{idx}", None)
        environ.pop(f"GIT_CONFIG_VALUE_{idx}", None)

    if not kept:
        environ.pop("GIT_CONFIG_COUNT", None)
        return

    environ["GIT_CONFIG_COUNT"] = str(len(kept))
    for new_idx, (key, value) in enumerate(kept):
        if key is not None:
            environ[f"GIT_CONFIG_KEY_{new_idx}"] = key
        if value is not None:
            environ[f"GIT_CONFIG_VALUE_{new_idx}"] = value


def strip_git_config_hooks_path(environ: MutableMapping[str, str]) -> None:
    """Remove any inherited ``core.hooksPath`` from git-config env injection.

    Mutates ``environ`` in place, handling both the ``GIT_CONFIG_PARAMETERS``
    token form (used by ``git -c``) and the ``GIT_CONFIG_COUNT`` indexed form.
    Leaves every other git-config entry intact. Idempotent.
    """
    _strip_from_parameters(environ)
    _strip_from_indexed(environ)


def snapshot_git_config_env(environ: MutableMapping[str, str]) -> dict[str, str]:
    """Capture the current ``GIT_CONFIG*`` namespace for later restoration."""
    return {k: v for k, v in environ.items() if k.startswith("GIT_CONFIG")}


def restore_git_config_env(
    environ: MutableMapping[str, str], snapshot: dict[str, str]
) -> None:
    """Restore the ``GIT_CONFIG*`` namespace from a prior snapshot in place."""
    for key in [k for k in environ if k.startswith("GIT_CONFIG")]:
        del environ[key]
    environ.update(snapshot)
