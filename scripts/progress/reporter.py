"""Progress reporter for session and skill-level operations.

This module provides utilities for emitting progress checkpoints during
long-running operations. All output respects quiet mode configuration
via the CLAUDE_PROGRESS_QUIET environment variable.

Session interruption analysis (Issue #670 evidence):
- 2 of 6 sessions (33%) were interrupted mid-execution
- Root cause hypothesis: lack of visibility into agent progress
- This module addresses the "unclear progress indicators" finding

Related: .agents/analysis/session-export-analysis-2025-12-30.md
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime


def is_quiet_mode() -> bool:
    """Check if progress output is suppressed.

    Quiet mode is enabled when CLAUDE_PROGRESS_QUIET=1 or
    CLAUDE_PROGRESS_QUIET=true (case-insensitive).

    Returns:
        True if progress output should be suppressed.
    """
    value = os.environ.get("CLAUDE_PROGRESS_QUIET", "").lower()
    return value in ("1", "true", "yes")


def emit_checkpoint(
    step_name: str,
    current: int | None = None,
    total: int | None = None,
    details: str | None = None,
) -> None:
    """Emit a checkpoint message for long-running operations.

    Skill authors SHOULD call this function for operations exceeding 30 seconds.
    The output format is consistent across all skills per Issue #670 requirements.

    Args:
        step_name: Name of the current step (e.g., "Processing files").
        current: Number of items processed so far.
        total: Total number of items to process.
        details: Optional additional context (e.g., current file name).

    Example:
        emit_checkpoint("Scanning files", current=5, total=20)
        # Output: [CHECKPOINT] Scanning files (5/20)

        emit_checkpoint("Validating", details="config.yaml")
        # Output: [CHECKPOINT] Validating: config.yaml
    """
    if is_quiet_mode():
        return

    parts = [f"[CHECKPOINT] {step_name}"]

    if current is not None and total is not None:
        parts.append(f"({current}/{total})")
    elif current is not None:
        parts.append(f"({current})")

    if details:
        parts.append(f": {details}")

    message = " ".join(parts)
    print(message, file=sys.stderr, flush=True)


@dataclass
class ProgressReporter:
    """Session-level progress reporter with phase tracking.

    Provides visibility into multi-step session operations by tracking
    current phase, step counts, and skill invocations.

    Attributes:
        total_steps: Expected number of steps in the session.
        completed_steps: Number of steps completed so far.
        current_phase: Name of the current phase/task.
        skills_invoked: List of skills invoked during the session.

    Example:
        reporter = ProgressReporter(total_steps=5)
        reporter.start_phase("Initialization")
        # ... do work ...
        reporter.complete_step()

        reporter.start_phase("Processing")
        reporter.invoke_skill("pr-review")
        # ... do work ...
        reporter.complete_step()

        reporter.report_summary()
    """

    total_steps: int = 0
    completed_steps: int = 0
    current_phase: str = ""
    skills_invoked: list[str] = field(default_factory=list)
    _start_time: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    def start_phase(self, phase_name: str) -> None:
        """Mark the start of a new phase.

        Args:
            phase_name: Human-readable name of the phase.
        """
        self.current_phase = phase_name
        if not is_quiet_mode():
            progress = self._format_progress()
            print(
                f"[PROGRESS] {progress} Starting: {phase_name}",
                file=sys.stderr,
                flush=True,
            )

    def complete_step(self, result: str | None = None) -> None:
        """Mark the current step as completed.

        Args:
            result: Optional result summary for the completed step.
        """
        self.completed_steps += 1
        if not is_quiet_mode():
            progress = self._format_progress()
            message = f"[PROGRESS] {progress} Completed: {self.current_phase}"
            if result:
                message += f" - {result}"
            print(message, file=sys.stderr, flush=True)

    def invoke_skill(self, skill_name: str) -> None:
        """Record a skill invocation.

        Args:
            skill_name: Name of the skill being invoked.
        """
        self.skills_invoked.append(skill_name)
        if not is_quiet_mode():
            print(
                f"[SKILL] Invoking: {skill_name}",
                file=sys.stderr,
                flush=True,
            )

    def report_summary(self) -> None:
        """Print a summary of the session progress."""
        if is_quiet_mode():
            return

        elapsed = datetime.now(tz=UTC) - self._start_time
        elapsed_str = str(elapsed).split(".")[0]  # Remove microseconds

        print("\n[SUMMARY]", file=sys.stderr)
        print(f"  Steps: {self.completed_steps}/{self.total_steps}", file=sys.stderr)
        print(f"  Duration: {elapsed_str}", file=sys.stderr)
        if self.skills_invoked:
            print(f"  Skills: {', '.join(self.skills_invoked)}", file=sys.stderr)
        sys.stderr.flush()

    def _format_progress(self) -> str:
        """Format the progress indicator string."""
        if self.total_steps > 0:
            percentage = int(self.completed_steps / self.total_steps * 100)
            return f"[{self.completed_steps}/{self.total_steps}] ({percentage}%)"
        return f"[{self.completed_steps}]"
