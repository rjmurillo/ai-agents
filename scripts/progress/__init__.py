"""Progress reporting module for session and skill operations.

Provides utilities for emitting checkpoints and progress indicators during
long-running operations to improve visibility and reduce user interruptions.

Usage:
    from scripts.progress import ProgressReporter, emit_checkpoint

    # Session-level progress
    reporter = ProgressReporter(total_steps=5)
    reporter.start_phase("Initialization")
    reporter.complete_step()

    # Skill-level checkpoints
    emit_checkpoint("Processing files", current=5, total=20)
"""

from scripts.progress.reporter import (
    ProgressReporter,
    emit_checkpoint,
    is_quiet_mode,
)

__all__ = ["ProgressReporter", "emit_checkpoint", "is_quiet_mode"]
