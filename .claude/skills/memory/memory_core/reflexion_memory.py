#!/usr/bin/env python3
"""Reflexion Memory module for episodic replay.

Implements the episodic portion of the ADR-038 Reflexion Memory Schema:
- Episodic memory storage and retrieval

Tier Architecture:
- Tier 0: Working memory (context window, managed by Claude)
- Tier 1: Semantic memory (Serena, ADR-037)
- Tier 2: Episodic memory (this module)

Tier 3 causal memory was removed; the graph was a derived cache with no runtime
reader. Episodes remain the source of truth. No code reads them today either:
the query API below has no caller outside this module, its tests, and
documentation examples. See ADR-089 and issue 3630.

Exit codes (ADR-035):
    0 - Success
    1 - Logic error (validation failure)
    2 - Config error (schema/path not found)
    3 - External error (I/O failure)
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

# A graph that has drifted produces thousands of errors; a message that long is
# unreadable in a hook's stderr and truncated by most log sinks.
_MAX_REPORTED_SCHEMA_ERRORS = 20

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MODULE_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _MODULE_DIR.parent
_AGENTS_ROOT = _SKILL_ROOT.parent.parent.parent / ".agents"

EPISODES_PATH = _AGENTS_ROOT / "memory" / "episodes"

SCHEMAS_PATH = _SKILL_ROOT / "resources" / "schemas"
EPISODE_SCHEMA_FILE = SCHEMAS_PATH / "episode.schema.json"


# ---------------------------------------------------------------------------
# Private functions
# ---------------------------------------------------------------------------


def _validate_schema(
    data: dict[str, Any],
    schema_file: Path,
    data_type: str,
) -> None:
    """Validate data against a JSON Schema.

    Every constraint the schema states is checked, including the ones inside
    array items. The hand-rolled predecessor checked only top-level ``required``
    presence and top-level property types, so it passed data carrying thousands
    of real violations inside array items while reporting success (#3356). A
    validator that reports success over data it never descended into is worse
    than none, because it gets cited as evidence the data is well formed.

    ``jsonschema`` is already a project dependency, so there was never a cost
    argument for the shorter path.

    Args:
        data: The data dict to validate.
        schema_file: Path to the JSON Schema file.
        data_type: Human-readable name for error messages.

    Raises:
        FileNotFoundError: If schema file is missing.
        ValueError: If data does not conform to the schema.
    """
    if not schema_file.is_file():
        msg = (
            f"Required schema file not found: {schema_file}. "
            f"Cannot validate {data_type}. "
            f"Ensure schema files exist at {SCHEMAS_PATH}"
        )
        raise FileNotFoundError(msg)

    try:
        # Round-tripping normalizes values the schema cannot describe (datetimes
        # become strings) so validation sees what a later reader would read back
        # off disk rather than the in-memory objects.
        parsed = json.loads(json.dumps(data, default=str))
    except (TypeError, ValueError) as exc:
        msg = f"Failed to serialize {data_type} to JSON: {exc}"
        raise ValueError(msg) from exc

    try:
        schema = json.loads(schema_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"Failed to read schema file '{schema_file}': {exc}"
        raise ValueError(msg) from exc

    validator = jsonschema.Draft7Validator(schema)
    raw_errors = sorted(validator.iter_errors(parsed), key=str)
    if raw_errors:
        shown = [
            f"{'/'.join(str(part) for part in e.absolute_path) or '<root>'}: "
            f"{e.message}"
            for e in raw_errors[:_MAX_REPORTED_SCHEMA_ERRORS]
        ]
        suffix = (
            f"; and {len(raw_errors) - len(shown)} more"
            if len(raw_errors) > len(shown)
            else ""
        )
        msg = (
            f"Invalid {data_type} - JSON Schema validation failed: "
            + "; ".join(shown)
            + suffix
        )
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# Episode functions
# ---------------------------------------------------------------------------


def get_episode(session_id: str) -> dict[str, Any] | None:
    """Retrieve an episode by session ID.

    Args:
        session_id: The session identifier (e.g., "2026-01-01-session-126").

    Returns:
        Episode dict or None if not found.

    Raises:
        ValueError: If episode file is corrupted.
    """
    episode_file = (EPISODES_PATH / f"episode-{session_id}.json").resolve()
    if not episode_file.is_relative_to(EPISODES_PATH.resolve()):
        raise ValueError("Path traversal attempt detected in session_id")

    if not episode_file.is_file():
        return None

    try:
        content = episode_file.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(content)
        return data
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"Episode file corrupted at '{episode_file}': {exc}"
        raise ValueError(msg) from exc


def get_episodes(
    outcome: str | None = None,
    task: str | None = None,
    since: datetime | None = None,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """Retrieve episodes matching criteria.

    Args:
        outcome: Filter by outcome: success, partial, failure.
        task: Filter by task name (substring match, case-insensitive).
        since: Filter episodes since this datetime.
        max_results: Maximum number of episodes to return (1-100).

    Returns:
        List of episode dicts sorted by timestamp descending.
    """
    if outcome is not None and outcome not in ("success", "partial", "failure"):
        msg = f"Invalid outcome: {outcome}. Must be success, partial, or failure."
        raise ValueError(msg)
    if max_results < 1 or max_results > 100:
        msg = "max_results must be between 1 and 100"
        raise ValueError(msg)

    episodes: list[dict[str, Any]] = []
    skipped_count = 0

    if not EPISODES_PATH.is_dir():
        return episodes

    try:
        files = sorted(EPISODES_PATH.glob("episode-*.json"))
    except PermissionError as exc:
        logger.error(
            "Permission denied reading episodes from '%s': %s",
            EPISODES_PATH,
            exc,
        )
        return episodes
    except OSError as exc:
        logger.error("Failed to enumerate episodes: %s", exc)
        return episodes

    for episode_file in files:
        try:
            content = episode_file.read_text(encoding="utf-8")
            episode = json.loads(content)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Skipping corrupted episode file '%s': %s", episode_file, exc
            )
            skipped_count += 1
            continue

        # Apply filters
        if outcome and episode.get("outcome") != outcome:
            continue

        if task and task.lower() not in (episode.get("task") or "").lower():
            continue

        if since:
            try:
                ep_timestamp = episode.get("timestamp", "")
                episode_date = datetime.fromisoformat(ep_timestamp)
                if episode_date < since:
                    continue
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "Episode '%s' has invalid timestamp '%s': %s",
                    episode_file.name,
                    episode.get("timestamp"),
                    exc,
                )
                skipped_count += 1
                continue

        episodes.append(episode)

        if len(episodes) >= max_results:
            break

    if skipped_count > 0:
        logger.warning(
            "Skipped %d corrupted or invalid episode file(s)", skipped_count
        )

    # Sort by timestamp descending
    episodes.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    return episodes


def new_episode(
    session_id: str,
    task: str,
    outcome: str,
    decisions: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
    lessons: list[str] | None = None,
    metrics: dict[str, Any] | None = None,
    skip_validation: bool = False,
) -> dict[str, Any]:
    """Create a new episode from structured data.

    Args:
        session_id: The source session identifier.
        task: High-level task description.
        outcome: Episode outcome: success, partial, failure.
        decisions: Array of decision objects.
        events: Array of event objects.
        lessons: Array of lesson strings.
        metrics: Metrics dict.
        skip_validation: Skip JSON Schema validation (for tests only).

    Returns:
        Episode dict.

    Raises:
        ValueError: If outcome is invalid or validation fails.
        OSError: If file write fails.
    """
    if outcome not in ("success", "partial", "failure"):
        msg = f"Invalid outcome: {outcome}. Must be success, partial, or failure."
        raise ValueError(msg)

    episode: dict[str, Any] = {
        "id": f"episode-{session_id}",
        "session": session_id,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "outcome": outcome,
        "task": task,
        "decisions": decisions or [],
        "events": events or [],
        "metrics": metrics or {},
        "lessons": lessons or [],
    }

    if not skip_validation:
        _validate_schema(episode, EPISODE_SCHEMA_FILE, "episode")

    EPISODES_PATH.mkdir(parents=True, exist_ok=True)

    episode_file = (EPISODES_PATH / f"episode-{session_id}.json").resolve()
    if not episode_file.is_relative_to(EPISODES_PATH.resolve()):
        raise ValueError("Path traversal attempt detected in session_id")
    try:
        json_str = json.dumps(episode, indent=2, default=str)
        episode_file.write_text(json_str, encoding="utf-8")
    except OSError as exc:
        msg = f"Failed to save episode to '{episode_file}': {exc}"
        raise OSError(msg) from exc

    return episode


def get_decision_sequence(episode_id: str) -> list[dict[str, Any]]:
    """Retrieve the decision sequence from an episode.

    Args:
        episode_id: The episode identifier (e.g., "episode-2026-01-01-126").

    Returns:
        List of decision dicts sorted by timestamp. Empty list if not found.
    """
    session_id = episode_id.removeprefix("episode-")
    episode = get_episode(session_id)

    if not episode:
        return []

    decisions = episode.get("decisions") or []
    return sorted(decisions, key=lambda d: d.get("timestamp", ""))


# ---------------------------------------------------------------------------
# Status functions
# ---------------------------------------------------------------------------


def get_reflexion_memory_status() -> dict[str, Any]:
    """Get the status of the reflexion memory system.

    Returns:
        Dict with Episodes and Configuration status.
    """
    episode_count = 0
    if EPISODES_PATH.is_dir():
        try:
            episode_count = len(list(EPISODES_PATH.glob("episode-*.json")))
        except OSError as exc:
            logger.warning("Failed to count episode files: %s", exc)

    return {
        "Episodes": {
            "Path": str(EPISODES_PATH),
            "Count": episode_count,
        },
        "Configuration": {
            "EpisodesPath": str(EPISODES_PATH),
        },
    }
