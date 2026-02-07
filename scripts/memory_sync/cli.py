"""CLI for memory synchronization.

Subcommands:
    sync       - Sync a single memory file
    sync-batch - Batch sync from staged git changes or queue file
    validate   - Generate freshness report

Exit codes per ADR-035:
    0 - Success
    1 - Sync failure
    2 - Invalid arguments
    3 - I/O error

See: ADR-037, Issue #747
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

from scripts.memory_sync.freshness import check_freshness
from scripts.memory_sync.mcp_client import McpClient, McpError
from scripts.memory_sync.models import FreshnessStatus, SyncOperation
from scripts.memory_sync.sync_engine import detect_changes, sync_batch, sync_memory

_logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_SYNC_FAILURE = 1
EXIT_INVALID_ARGS = 2
EXIT_IO_ERROR = 3

QUEUE_FILE = Path(".memory_sync_queue.json")


def main(argv: list[str] | None = None) -> int:
    """Entry point for the CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    _setup_logging(getattr(args, "verbose", False))

    if not hasattr(args, "func"):
        parser.print_help()
        return EXIT_INVALID_ARGS

    try:
        result: int = args.func(args)
        return result
    except KeyboardInterrupt:
        _logger.info("Interrupted")
        return EXIT_SYNC_FAILURE


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory_sync",
        description="Sync Serena memories to Forgetful.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    subparsers = parser.add_subparsers(dest="command")

    # sync
    sync_parser = subparsers.add_parser("sync", help="Sync a single memory file")
    sync_parser.add_argument("path", type=Path, help="Path to memory file")
    sync_parser.add_argument(
        "--force", action="store_true", help="Skip deduplication check"
    )
    sync_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would happen"
    )
    sync_parser.set_defaults(func=_cmd_sync)

    # sync-batch
    batch_parser = subparsers.add_parser(
        "sync-batch", help="Batch sync from staged changes or queue"
    )
    batch_parser.add_argument(
        "--staged", action="store_true", help="Detect from git staged files"
    )
    batch_parser.add_argument(
        "--from-queue", action="store_true", help="Read from queue file"
    )
    batch_parser.add_argument(
        "--force", action="store_true", help="Skip deduplication check"
    )
    batch_parser.add_argument(
        "--dry-run", action="store_true", help="Show what would happen"
    )
    batch_parser.set_defaults(func=_cmd_sync_batch)

    # validate
    validate_parser = subparsers.add_parser(
        "validate", help="Check memory freshness"
    )
    validate_parser.add_argument(
        "--json", action="store_true", dest="output_json", help="Output as JSON"
    )
    validate_parser.set_defaults(func=_cmd_validate)

    # hook
    hook_parser = subparsers.add_parser(
        "hook", help="Pre-commit hook entry point"
    )
    hook_parser.add_argument(
        "--immediate", action="store_true", help="Sync immediately via MCP"
    )
    hook_parser.set_defaults(func=_cmd_hook)

    return parser


def _cmd_sync(args: argparse.Namespace) -> int:
    """Handle the sync subcommand."""
    project_root = _find_project_root()
    path = args.path

    if not (project_root / path).exists():
        _logger.error("File not found: %s", path)
        return EXIT_INVALID_ARGS

    if not McpClient.is_available():
        _logger.error("Forgetful is not available (database not found)")
        return EXIT_INVALID_ARGS

    # Determine operation: if file exists, check if we have state
    from scripts.memory_sync.sync_engine import load_state

    state = load_state(project_root)
    operation = (
        SyncOperation.UPDATE if path.stem in state else SyncOperation.CREATE
    )

    try:
        with McpClient.create() as client:
            result = sync_memory(
                client, path, operation, project_root,
                force=args.force, dry_run=args.dry_run,
            )
    except McpError as exc:
        _logger.error("MCP error: %s", exc)
        return EXIT_IO_ERROR

    if result.success:
        _logger.info(
            "%s %s -> %s",
            result.operation.value.upper(),
            result.path,
            result.forgetful_id or "(dry-run)",
        )
        return EXIT_SUCCESS
    _logger.error("Sync failed for %s: %s", result.path, result.error)
    return EXIT_SYNC_FAILURE


def _cmd_sync_batch(args: argparse.Namespace) -> int:
    """Handle the sync-batch subcommand."""
    project_root = _find_project_root()

    if not McpClient.is_available():
        _logger.error("Forgetful is not available (database not found)")
        return EXIT_INVALID_ARGS

    changes: list[tuple[Path, SyncOperation]] = []

    if args.staged:
        staged_output = _get_staged_files()
        changes = detect_changes(staged_output)
    elif args.from_queue:
        changes = _read_queue(project_root)
    else:
        _logger.error("Specify --staged or --from-queue")
        return EXIT_INVALID_ARGS

    if not changes:
        _logger.info("No memory changes to sync")
        return EXIT_SUCCESS

    try:
        with McpClient.create() as client:
            results = sync_batch(
                client, changes, project_root,
                force=args.force, dry_run=args.dry_run,
            )
    except McpError as exc:
        _logger.error("MCP error: %s", exc)
        return EXIT_IO_ERROR

    failures = [r for r in results if not r.success]
    for r in results:
        status = "OK" if r.success else "FAIL"
        _logger.info(
            "[%s] %s %s %s",
            status,
            r.operation.value,
            r.path,
            r.error or "",
        )

    if args.from_queue and not args.dry_run:
        _clear_queue(project_root)

    if failures:
        return EXIT_SYNC_FAILURE
    return EXIT_SUCCESS


def _cmd_validate(args: argparse.Namespace) -> int:
    """Handle the validate subcommand."""
    project_root = _find_project_root()
    report = check_freshness(project_root)

    if args.output_json:
        output = {
            "total": report.total,
            "in_sync": report.in_sync,
            "stale": report.stale,
            "missing": report.missing,
            "orphaned": report.orphaned,
            "duration_ms": round(report.duration_ms, 2),
            "details": [
                {
                    "name": d.name,
                    "status": d.status.value,
                    "serena_hash": d.serena_hash,
                    "forgetful_id": d.forgetful_id,
                }
                for d in report.details
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Memory Freshness Report ({report.duration_ms:.1f}ms)")
        print(f"  Total:    {report.total}")
        print(f"  In-sync:  {report.in_sync}")
        print(f"  Stale:    {report.stale}")
        print(f"  Missing:  {report.missing}")
        print(f"  Orphaned: {report.orphaned}")
        if report.stale or report.missing or report.orphaned:
            print()
            for d in report.details:
                if d.status != FreshnessStatus.IN_SYNC:
                    print(f"  [{d.status.value}] {d.name}")

    return EXIT_SUCCESS


def _cmd_hook(args: argparse.Namespace) -> int:
    """Handle the hook subcommand (called from pre-commit).

    Never blocks commits. Always returns 0.
    """
    project_root = _find_project_root()
    staged_output = _get_staged_files()
    changes = detect_changes(staged_output)

    if not changes:
        return EXIT_SUCCESS

    if not McpClient.is_available():
        _logger.info("Forgetful not available, queuing changes")
        _write_queue(project_root, changes)
        return EXIT_SUCCESS

    if args.immediate:
        try:
            with McpClient.create() as client:
                results = sync_batch(client, changes, project_root)
            failures = [r for r in results if not r.success]
            if failures:
                _logger.warning(
                    "Memory sync: %d/%d failed (non-blocking)",
                    len(failures),
                    len(results),
                )
            else:
                _logger.info("Memory sync: %d synced", len(results))
        except Exception as exc:
            _logger.warning("Memory sync failed (non-blocking): %s", exc)
    else:
        _write_queue(project_root, changes)
        _logger.info(
            "Memory sync: %d changes queued to %s",
            len(changes),
            QUEUE_FILE,
        )

    return EXIT_SUCCESS


def _find_project_root() -> Path:
    """Find the project root by looking for .git directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    return Path.cwd()


def _get_staged_files() -> list[str]:
    """Get staged files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-status"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip().splitlines()
    except subprocess.CalledProcessError:
        _logger.warning("Failed to get staged files from git")
        return []


def _read_queue(project_root: Path) -> list[tuple[Path, SyncOperation]]:
    """Read changes from the queue file."""
    queue_path = project_root / QUEUE_FILE
    if not queue_path.exists():
        return []
    try:
        data = json.loads(queue_path.read_text("utf-8"))
        changes: list[tuple[Path, SyncOperation]] = []
        for entry in data:
            path = Path(entry["path"])
            operation = SyncOperation(entry["operation"])
            changes.append((path, operation))
        return changes
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        _logger.warning("Failed to read queue file: %s", exc)
        return []


def _write_queue(
    project_root: Path, changes: list[tuple[Path, SyncOperation]]
) -> None:
    """Write changes to the queue file."""
    queue_path = project_root / QUEUE_FILE
    data = [
        {"path": str(path), "operation": op.value}
        for path, op in changes
    ]
    queue_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _clear_queue(project_root: Path) -> None:
    """Remove the queue file after processing."""
    queue_path = project_root / QUEUE_FILE
    if queue_path.exists():
        queue_path.unlink()


def _setup_logging(verbose: bool) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )



if __name__ == "__main__":
    sys.exit(main())
