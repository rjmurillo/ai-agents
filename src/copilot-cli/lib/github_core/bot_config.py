"""Bot authors configuration: loading, caching, and lookup."""

from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Errors raised while loading the config. ``yaml.YAMLError`` is only
# referenceable when PyYAML is installed; when it is absent the vendored
# parser raises only OSError on read failure. Build the except-tuple to
# match whichever loader path get_bot_authors_config uses (issue #1844).
_CONFIG_LOAD_ERRORS: tuple[type[Exception], ...] = (
    (OSError, yaml.YAMLError) if yaml is not None else (OSError,)
)

# ---------------------------------------------------------------------------
# Bot configuration
# ---------------------------------------------------------------------------

_DEFAULT_BOTS: dict[str, list[str]] = {
    "reviewer": [
        "coderabbitai[bot]",
        "github-copilot[bot]",
        "gemini-code-assist[bot]",
        "cursor[bot]",
        "Copilot",
    ],
    "automation": [
        "github-actions[bot]",
        "github-actions",
        "dependabot[bot]",
    ],
    "repository": [
        "rjmurillo-bot",
        "copilot-swe-agent[bot]",
    ],
}

_bot_authors_cache: dict[str, list[str]] | None = None
_bot_authors_cache_path: str | None = None


def _find_repo_root(start: str | None = None) -> str | None:
    """Walk up from *start* to find the directory containing .git.

    Handles both regular repos (.git is a directory) and worktrees
    (.git is a file containing 'gitdir: ...').
    """
    search = start or os.getcwd()
    while search and search != os.path.dirname(search):
        git_path = os.path.join(search, ".git")
        if os.path.isdir(git_path) or os.path.isfile(git_path):
            return search
        search = os.path.dirname(search)
    return None


def _cache_bot_config(
    config_path: str | None,
    bots: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Store *bots* in module-level cache keyed by *config_path*."""
    global _bot_authors_cache, _bot_authors_cache_path  # noqa: PLW0603
    _bot_authors_cache = bots
    _bot_authors_cache_path = config_path
    return bots


def _strip_inline_comment(value: str) -> str:
    """Drop a YAML inline comment from *value*.

    A ``#`` at index 0, or one preceded by a space or tab, starts a comment. A
    ``#`` with a non-space character before it is part of the value:
    ``foo # note`` becomes ``foo``; ``foo#bar`` stays ``foo#bar``. A ``#``
    inside a quoted span (single or double quotes) is literal content, not a
    comment. The returned value is stripped of surrounding whitespace.
    """
    quote_char: str | None = None
    for i, char in enumerate(value):
        if quote_char is None and char in ("'", '"'):
            quote_char = char
        elif char == quote_char:
            quote_char = None
        elif quote_char is None and char == "#" and (i == 0 or value[i - 1] in (" ", "\t")):
            return value[:i].strip()
    return value.strip()


def _strip_quotes(value: str) -> str:
    """Remove one matching pair of surrounding quotes from *value*.

    When *value* is at least two characters long and starts and ends with the
    same single- or double-quote character, return the inner slice. Otherwise
    return *value* unchanged.
    """
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _parse_mapping_line(raw: str) -> tuple[str, str] | None:
    """Split a top-level mapping line into (key, inline_value), or None.

    A line is a mapping entry only when a colon is followed by whitespace
    (``key: value``) or the colon is the last character before any inline
    comment (``key:``). A colon with a non-space character after it is part of
    a plain scalar, not a separator: yaml.safe_load("name:value") returns the
    string "name:value", not a dict. Returns None for such non-mapping lines.

    The inline value has its inline comment stripped but quotes left intact;
    the caller decides whether to unwrap quotes. For a bare ``key:`` the inline
    value is the empty string, signalling a block list follows.
    """
    line = _strip_inline_comment(raw)
    for i, char in enumerate(line):
        if char != ":":
            continue
        after = line[i + 1 :]
        if after == "" or after[0] in (" ", "\t"):
            return line[:i].strip(), after.strip()
    return None


def _parse_simple_yaml(text: str) -> dict:
    """Parse the small YAML subset used by bot-authors.yml without PyYAML.

    Supports top-level scalar keys (``key: value``) and top-level list keys
    (``key:`` followed by ``- item`` lines). A colon is a key separator only
    when followed by whitespace or at end of line; ``name:value`` (no space) is
    a plain scalar, matching yaml.safe_load, and contributes nothing to the
    mapping. Blank lines and full-line comments are skipped. Inline comments and
    one matching pair of surrounding quotes are stripped from values and list
    items. This is the fallback used when PyYAML is not importable; for the
    bot-authors.yml subset its output equals ``yaml.safe_load`` (issue #1844).
    """
    result: dict = {}
    current_key: str | None = None
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("-"):
            item = _strip_quotes(_strip_inline_comment(stripped[1:]))
            if current_key is not None and isinstance(result.get(current_key), list):
                result[current_key].append(item)
            continue
        if not raw[0].isspace():
            parsed = _parse_mapping_line(raw)
            if parsed is None:
                continue
            key, inline = parsed
            if inline:
                result[key] = _strip_quotes(inline)
                current_key = None
            else:
                result[key] = []
                current_key = key
    return result


def get_bot_authors_config(
    config_path: str | None = None,
    force: bool = False,
) -> dict[str, list[str]]:
    """Load bot authors configuration from .github/bot-authors.yml.

    Results are cached at module level for performance.

    Args:
        config_path: Explicit path to config file. Defaults to repo-root/.github/bot-authors.yml.
        force: Bypass cache and reload from disk.

    Returns:
        Dict with 'reviewer', 'automation', 'repository' keys mapping to username lists.
    """
    if config_path is None:
        repo_root = _find_repo_root()
        if repo_root:
            config_path = os.path.join(repo_root, ".github", "bot-authors.yml")

    if not force and _bot_authors_cache is not None and _bot_authors_cache_path == config_path:
        return _bot_authors_cache

    if not config_path or not os.path.isfile(config_path):
        logger.debug("Bot authors config not found at %s, using defaults", config_path)
        return _cache_bot_config(config_path, dict(_DEFAULT_BOTS))

    # CWE-22: validate config path stays within repo root
    repo_root = _find_repo_root()
    if repo_root:
        resolved_config = str(Path(config_path).resolve())
        resolved_root = str(Path(repo_root).resolve())
        if not resolved_config.startswith(resolved_root + os.sep):
            warnings.warn(
                f"Config path '{config_path}' is outside repository root, using defaults",
                stacklevel=2,
            )
            return _cache_bot_config(config_path, dict(_DEFAULT_BOTS))

    try:
        text = Path(config_path).read_text(encoding="utf-8")
        data = yaml.safe_load(text) if yaml is not None else _parse_simple_yaml(text)

        if not isinstance(data, dict):
            logger.debug("Bot authors config was not a dict, using defaults")
            return _cache_bot_config(config_path, dict(_DEFAULT_BOTS))

        bots: dict[str, list[str]] = {
            "reviewer": list(data.get("reviewer", [])),
            "automation": list(data.get("automation", [])),
            "repository": list(data.get("repository", [])),
        }

        if sum(len(v) for v in bots.values()) == 0:
            logger.debug("Bot authors config was empty, using defaults")
            return _cache_bot_config(config_path, dict(_DEFAULT_BOTS))

        return _cache_bot_config(config_path, bots)

    except _CONFIG_LOAD_ERRORS as exc:
        warnings.warn(
            f"Failed to parse bot authors config: {exc}, using defaults",
            stacklevel=2,
        )
        return _cache_bot_config(config_path, dict(_DEFAULT_BOTS))


def get_bot_authors(category: str = "all") -> list[str]:
    """Return bot author login names, optionally filtered by category.

    Args:
        category: 'reviewer', 'automation', 'repository', or 'all' (default).

    Returns:
        Sorted list of unique bot author names.
    """
    bots = get_bot_authors_config()

    if category == "all":
        combined: set[str] = set()
        for names in bots.values():
            combined.update(names)
        return sorted(combined)

    return list(bots.get(category, []))


_BOT_SUFFIXES = ("[bot]", "-bot")


def is_bot(login: str, user_type: str | None = None) -> bool:
    """Determine if a GitHub login belongs to a bot account.

    Uses multiple detection strategies:
    1. API-provided user_type field (most reliable when available)
    2. Configured bot authors from bot-authors.yml
    3. Naming convention suffixes ([bot] and -bot)

    Args:
        login: GitHub username to check.
        user_type: Optional GitHub API user type field (e.g., "Bot", "User").

    Returns:
        True if the login appears to be a bot account.
    """
    if user_type == "Bot":
        return True

    lower = login.lower()
    if any(lower.endswith(s) for s in _BOT_SUFFIXES):
        return True

    configured_bots = {b.lower() for b in get_bot_authors()}
    return lower in configured_bots
