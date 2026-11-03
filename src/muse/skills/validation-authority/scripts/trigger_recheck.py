"""Trigger recomputation for ``validation_record.py`` (issue #6506, review-gates-04).

A record carries the trigger output the agent saved. With ``--changed-path``,
the validator reruns the sibling trigger's ``decide`` on the real changed paths
so a record cannot claim ``skip`` for a change the trigger would activate.
The trigger module is passed in, so this module loads nothing on its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from relocation_evidence import is_text_list


class TriggerRecheckError(Exception):
    """The trigger could not run, so the CLI must report a config error, not a defect."""


def recomputed_trigger_defects(
    trigger: object,
    changed_paths: Sequence[str],
    repo_root: Path | None,
    trigger_module: ModuleType | None,
) -> list[str]:
    """Rerun the trigger on the real changed paths and catch a record that skipped too early."""
    if trigger_module is None or not changed_paths or not isinstance(trigger, dict):
        return []
    effects = trigger.get("effects")
    declared = effects if is_text_list(effects) else []
    try:
        fresh = trigger_module.decide(list(changed_paths), declared, repo_root or Path.cwd())
    except ValueError as exc:
        return [f"trigger recomputed from the changed paths was refused: {exc}"]
    except OSError as exc:
        raise TriggerRecheckError(f"trigger could not read its inputs: {exc}") from exc
    if fresh.get("decision") == "activate" and trigger.get("decision") != "activate":
        return [
            "trigger.decision is `skip` but the trigger recomputed from the changed paths "
            f"activates: {fresh.get('reason')}"
        ]
    return []
