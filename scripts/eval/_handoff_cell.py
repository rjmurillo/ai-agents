"""Cell bookkeeping for the strategy comparison (issue #7350): launches, spend, retries."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import _control_ablation as ablation
import _control_ablation_claude as claude_run
import _control_ablation_grade as grade
import _handoff_strategy as hs
from _run_changes import path_safe


def cell_dir(workspace_root: Path, task_id: str, repeat: int) -> Path:
    """Arm-neutral cell path: the reproduction's traceback prints it, so it must not name the arm.

    Cells run one at a time and each is deleted after grading, so both arms reuse it.
    """
    return Path(workspace_root, path_safe(f"{task_id}-r{repeat}"))


def file_state(workspace: Path) -> dict[str, str]:
    """Non-incidental changed paths mapped to content hashes, to detect an investigator write."""
    state: dict[str, str] = {}
    for path in grade.changed_paths(workspace):
        if ablation._is_incidental_path(path):
            continue
        target = workspace / path
        state[path] = (
            hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else "deleted"
        )
    return state


def argv_summary(argv: Sequence[str]) -> list[str]:
    """The argv with the prompt and role text replaced by hashes, so a report stays small."""
    out: list[str] = []
    hide = False
    for item in argv:
        out.append(f"<sha256 {hs.sha256_text(item)}>" if hide else item)
        hide = item in ("--print", "--append-system-prompt")
    return out


class Cell:
    """Accumulates one cell's launches, spend, and time."""

    def __init__(
        self,
        model: str,
        timeout: float,
        runner: claude_run.Runner,
        workspace: Path,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model, self.timeout, self.runner, self.workspace = model, timeout, runner, workspace
        self.sleep = sleep
        self.transient_retries = 0
        self.cost = 0.0
        self.wall = 0.0
        self.failures = 0
        self.launches: list[dict[str, Any]] = []

    def launch(self, role: str, prompt: str, markers: Sequence[str], **kwargs: object) -> str:
        for attempt in range(hs.TRANSIENT_RETRIES + 1):
            try:
                events, reply, cost, wall, argv = claude_run.invoke_launch(
                    self.workspace, prompt, self.model, self.timeout, self.runner, **kwargs
                )
                break
            except claude_run.HarnessFailureError as exc:
                prior = self.cost
                self.cost += exc.cost_usd
                self.wall += exc.wall_seconds
                if not exc.transient or attempt == hs.TRANSIENT_RETRIES:
                    # The failing launch keeps its own cost, so an unmeasured one still fails
                    # the spend guard closed. Earlier spend rides separately.
                    exc.prior_cost_usd = prior
                    raise
                self.transient_retries += 1
                self.sleep(hs.TRANSIENT_WAITS[attempt])
        self.cost += cost
        self.wall += wall
        self.failures += claude_run.tool_failures(events)
        trajectory = claude_run.trajectory(events, markers)
        self.launches.append(
            {
                "role": role,
                "argv": argv_summary(argv),
                "cost_usd": cost,
                "wall_seconds": round(wall, 2),
                "reply": reply,
                "trajectory": trajectory,
            }
        )
        return str(reply)
