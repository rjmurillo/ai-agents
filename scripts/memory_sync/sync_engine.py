"""Core sync engine for Serena-to-Forgetful synchronization.

Handles creating, updating, and deleting memories in Forgetful
to mirror Serena's canonical .serena/memories/ files.

See: ADR-037, Issue #747
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from scripts.memory_sync.mcp_client import McpClient, McpError
from scripts.memory_sync.models import SyncOperation, SyncResult

_logger = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

STATE_FILE = Path(".memory_sync_state.json")
SOURCE_REPO = "rjmurillo/ai-agents"
ENCODING_AGENT = "memory-sync/0.1.0"


def compute_content_hash(content: str) -> str:
    """Compute SHA-256 hash of content for deduplication."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_state(project_root: Path) -> dict[str, Any]:
    """Load sync state from .memory_sync_state.json."""
    state_path = project_root / STATE_FILE
    if state_path.exists():
        result: dict[str, Any] = json.loads(state_path.read_text("utf-8"))
        return result
    return {}


def save_state(project_root: Path, state: dict[str, Any]) -> None:
    """Save sync state to .memory_sync_state.json."""
    state_path = project_root / STATE_FILE
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def detect_changes(
    staged_files: list[str],
) -> list[tuple[Path, SyncOperation]]:
    """Parse git staged file list into (path, operation) tuples.

    Only processes files under .serena/memories/.

    Args:
        staged_files: Lines from ``git diff --cached --name-status``.
            Each line has format: ``STATUS\\tFILENAME`` (e.g. ``A\\t.serena/memories/foo.md``).

    Returns:
        List of (path, operation) tuples for memory files.
    """
    changes: list[tuple[Path, SyncOperation]] = []
    for line in staged_files:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) < 2:
            continue
        status, filepath = parts[0], parts[1]
        path = Path(filepath)
        if not is_memory_file(path):
            continue
        operation = _status_to_operation(status)
        if operation is not None:
            changes.append((path, operation))
    return changes


def build_create_payload(memory: Any, path: Path) -> dict[str, Any]:
    """Build Forgetful create_memory payload from a parsed Memory.

    Args:
        memory: A Memory dataclass (from memory_enhancement.models).
        path: The source file path.

    Returns:
        Dict of arguments for Forgetful's create_memory tool.
    """
    importance = _confidence_to_importance(memory.confidence)
    keywords = memory.tags if memory.tags else [path.stem]
    return {
        "title": memory.id or path.stem,
        "content": memory.content,
        "context": f"Synced from Serena: {path}",
        "keywords": keywords,
        "tags": keywords,
        "importance": importance,
        "source_repo": SOURCE_REPO,
        "source_files": [str(path)],
        "encoding_agent": ENCODING_AGENT,
        "confidence": memory.confidence,
    }


def build_update_payload(
    memory: Any, path: Path, forgetful_id: str
) -> dict[str, Any]:
    """Build Forgetful update_memory payload.

    Args:
        memory: A Memory dataclass.
        path: The source file path.
        forgetful_id: Existing Forgetful memory ID.

    Returns:
        Dict of arguments for Forgetful's update_memory tool.
    """
    importance = _confidence_to_importance(memory.confidence)
    keywords = memory.tags if memory.tags else [path.stem]
    return {
        "memory_id": int(forgetful_id),
        "content": memory.content,
        "context": f"Synced from Serena: {path}",
        "keywords": keywords,
        "tags": keywords,
        "importance": importance,
        "source_files": [str(path)],
        "encoding_agent": ENCODING_AGENT,
        "confidence": memory.confidence,
    }


def sync_memory(
    client: McpClient,
    path: Path,
    operation: SyncOperation,
    project_root: Path,
    force: bool = False,
    dry_run: bool = False,
) -> SyncResult:
    """Sync a single memory to Forgetful.

    Delegates to operation-specific helpers for CREATE, UPDATE,
    DELETE, and SKIP operations.
    """
    start = time.monotonic()

    if operation == SyncOperation.SKIP:
        return _make_result(path, operation, True, start=start)

    if operation == SyncOperation.DELETE:
        return _sync_delete(client, path, project_root, dry_run, start)

    return _sync_create_or_update(
        client, path, operation, project_root, force, dry_run, start,
    )


def _sync_create_or_update(
    client: McpClient,
    path: Path,
    operation: SyncOperation,
    project_root: Path,
    force: bool,
    dry_run: bool,
    start: float,
) -> SyncResult:
    """Handle CREATE or UPDATE: parse, dedup check, and dispatch."""
    abs_path = project_root / path

    try:
        memory = _parse_memory(abs_path)
    except Exception as exc:
        _logger.warning("Failed to parse %s: %s", path, exc)
        return _make_result(path, operation, False, error=f"Parse error: {exc}", start=start)

    content_hash = compute_content_hash(abs_path.read_text("utf-8"))
    state = load_state(project_root)
    skip_result = _check_dedup(path, operation, force, content_hash, state, start)
    if skip_result is not None:
        return skip_result

    if dry_run:
        _logger.info("[DRY RUN] Would %s: %s", operation.value, path)
        return _make_result(path, operation, True, start=start)

    try:
        if operation == SyncOperation.CREATE:
            result = _sync_create(client, memory, path, content_hash, state, project_root)
        else:
            result = _sync_update(client, memory, path, content_hash, state, project_root)
        return _make_result(
            result.path, result.operation, result.success,
            error=result.error, forgetful_id=result.forgetful_id, start=start,
        )
    except McpError as exc:
        return _make_result(path, operation, False, error=str(exc), start=start)


def _check_dedup(
    path: Path,
    operation: SyncOperation,
    force: bool,
    content_hash: str,
    state: dict[str, Any],
    start: float,
) -> SyncResult | None:
    """Return a SKIP result if content is unchanged, else None."""
    if force or operation != SyncOperation.UPDATE:
        return None
    existing = state.get(path.stem, {})
    if existing.get("hash") != content_hash:
        return None
    _logger.info("Skipping %s: content unchanged", path)
    return _make_result(
        path, SyncOperation.SKIP, True,
        forgetful_id=existing.get("forgetful_id"), start=start,
    )


def _make_result(
    path: Path,
    operation: SyncOperation,
    success: bool,
    *,
    error: str | None = None,
    forgetful_id: str | None = None,
    start: float = 0.0,
) -> SyncResult:
    """Build a SyncResult with elapsed time."""
    return SyncResult(
        path=path,
        operation=operation,
        success=success,
        error=error,
        forgetful_id=forgetful_id,
        duration_ms=_elapsed_ms(start),
    )


def sync_batch(
    client: McpClient,
    changes: list[tuple[Path, SyncOperation]],
    project_root: Path,
    force: bool = False,
    dry_run: bool = False,
) -> list[SyncResult]:
    """Sync a batch of memory changes in one MCP session.

    Args:
        client: Active MCP client connection.
        changes: List of (path, operation) tuples.
        project_root: Absolute path to the project root.
        force: Skip hash-based deduplication.
        dry_run: Log what would happen without making changes.

    Returns:
        List of SyncResult for each change.
    """
    results: list[SyncResult] = []
    for path, operation in changes:
        result = sync_memory(client, path, operation, project_root, force, dry_run)
        results.append(result)
    return results


def is_memory_file(path: Path) -> bool:
    """Check if a path is a Serena memory file."""
    parts = path.parts
    return (
        len(parts) >= 3
        and parts[0] == ".serena"
        and parts[1] == "memories"
        and path.suffix == ".md"
    )


def _status_to_operation(git_status: str) -> SyncOperation | None:
    """Map git status letter to SyncOperation."""
    status_char = git_status[0].upper()
    if status_char == "A":
        return SyncOperation.CREATE
    if status_char in ("M", "R"):
        return SyncOperation.UPDATE
    if status_char == "D":
        return SyncOperation.DELETE
    return None


def _confidence_to_importance(confidence: float) -> int:
    """Map Serena confidence (0.0-1.0) to Forgetful importance (1-10)."""
    return max(1, min(10, int(confidence * 10)))


def _parse_memory(abs_path: Path) -> Any:
    """Parse a Serena memory file using Memory.from_file."""
    # Import here to avoid circular dependency at module level
    from memory_enhancement.models import Memory

    return Memory.from_file(abs_path)


def _sync_create(
    client: McpClient,
    memory: Any,
    path: Path,
    content_hash: str,
    state: dict[str, Any],
    project_root: Path,
) -> SyncResult:
    """Create a new memory in Forgetful."""
    payload = build_create_payload(memory, path)
    result = client.call_tool("create_memory", payload)
    forgetful_id = _extract_id(result)
    state[path.stem] = {"forgetful_id": forgetful_id, "hash": content_hash}
    save_state(project_root, state)
    _logger.info("Created %s -> forgetful:%s", path, forgetful_id)
    return SyncResult(
        path=path,
        operation=SyncOperation.CREATE,
        success=True,
        forgetful_id=forgetful_id,
    )


def _sync_update(
    client: McpClient,
    memory: Any,
    path: Path,
    content_hash: str,
    state: dict[str, Any],
    project_root: Path,
) -> SyncResult:
    """Update an existing memory in Forgetful."""
    memory_key = path.stem
    existing = state.get(memory_key, {})
    forgetful_id = existing.get("forgetful_id")

    if not forgetful_id:
        _logger.info("No existing ID for %s, creating instead", path)
        return _sync_create(client, memory, path, content_hash, state, project_root)

    payload = build_update_payload(memory, path, forgetful_id)
    client.call_tool("update_memory", payload)
    state[memory_key] = {"forgetful_id": forgetful_id, "hash": content_hash}
    save_state(project_root, state)
    _logger.info("Updated %s (forgetful:%s)", path, forgetful_id)
    return SyncResult(
        path=path,
        operation=SyncOperation.UPDATE,
        success=True,
        forgetful_id=forgetful_id,
    )


def _sync_delete(
    client: McpClient,
    path: Path,
    project_root: Path,
    dry_run: bool,
    start: float,
) -> SyncResult:
    """Mark a memory as obsolete in Forgetful."""
    state = load_state(project_root)
    memory_key = path.stem
    existing = state.get(memory_key, {})
    forgetful_id = existing.get("forgetful_id")

    if not forgetful_id:
        _logger.info("No Forgetful ID for deleted memory %s, skipping", path)
        return SyncResult(
            path=path,
            operation=SyncOperation.SKIP,
            success=True,
            duration_ms=_elapsed_ms(start),
        )

    if dry_run:
        _logger.info("[DRY RUN] Would delete: %s (forgetful:%s)", path, forgetful_id)
        return SyncResult(
            path=path,
            operation=SyncOperation.DELETE,
            success=True,
            forgetful_id=forgetful_id,
            duration_ms=_elapsed_ms(start),
        )

    client.call_tool("mark_memory_obsolete", {
        "memory_id": int(forgetful_id),
        "reason": f"Deleted from Serena: {path}",
    })
    del state[memory_key]
    save_state(project_root, state)
    _logger.info("Deleted %s (forgetful:%s)", path, forgetful_id)
    return SyncResult(
        path=path,
        operation=SyncOperation.DELETE,
        success=True,
        forgetful_id=forgetful_id,
        duration_ms=_elapsed_ms(start),
    )


def _extract_id(result: dict[str, Any]) -> str:
    """Extract the memory ID from a Forgetful create response."""
    content = result.get("content", [])
    if content:
        text = content[0].get("text", "")
        try:
            data = json.loads(text)
            if "id" in data:
                return str(data["id"])
        except (json.JSONDecodeError, TypeError):
            pass
    # Fallback: try result directly
    if "id" in result:
        return str(result["id"])
    raise McpError(f"Could not extract memory ID from response: {result}")


def _elapsed_ms(start: float) -> float:
    """Compute elapsed milliseconds."""
    return (time.monotonic() - start) * 1000
