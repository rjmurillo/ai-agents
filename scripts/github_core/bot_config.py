"""Bot authors configuration: loading, caching, and lookup."""

from __future__ import annotations

import logging
import os
import warnings
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot configuration
# ---------------------------------------------------------------------------

_DEFAULT_BOTS: dict[str, list[str]] = {
    "reviewer": [
        "coderabbitai[bot]",
        "github-copilot[bot]",
        "gemini-code-assist[bot]",
        "cursor[bot]",
    ],
    "automation": [
        "github-actions[bot]",
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
    """Walk up from *start* to find the directory containing .git."""
    search = start or os.getcwd()
    while search and search != os.path.dirname(search):
        if os.path.isdir(os.path.join(search, ".git")):
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
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

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

    except (OSError, yaml.YAMLError) as exc:
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
