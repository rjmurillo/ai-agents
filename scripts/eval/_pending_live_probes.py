"""Live probes a harness still owes, recorded next to the cells they would move.

A cell that stays `UNVERIFIED` because a call cannot be made today (quota,
paid spend, a missing CLI) says so in prose. Prose cannot be read by #5424 or
#5426. Each entry here is the machine-readable form: what is unproven, the
exact blocker, and the command to run once the blocker clears. An entry is a
promise about the future, never an observation, so it carries no status.

Observation only. Nothing here runs a command.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class PendingProbeError(ValueError):
    """A pending-probe entry is malformed. Raised, never defaulted."""


@dataclass(frozen=True, slots=True)
class PendingLiveProbe:
    """One unproven claim: its scope, why it is blocked, and how to unblock it."""

    scope: str
    blocker: str
    command: str

    def as_dict(self) -> dict[str, str]:
        """Return the JSON form used in the matrix and the report."""
        return {"scope": self.scope, "blocker": self.blocker, "command": self.command}


def _field(raw: Mapping[str, object], key: str, index: int) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PendingProbeError(f"pending_live_probes[{index}].{key} must be a non-empty string")
    return value


def load_pending_probes(value: object) -> tuple[PendingLiveProbe, ...]:
    """Parse the `pending_live_probes` array; absent means none are owed."""
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise PendingProbeError("pending_live_probes must be an array")
    entries: list[PendingLiveProbe] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise PendingProbeError(f"pending_live_probes[{index}] must be an object")
        entries.append(
            PendingLiveProbe(
                scope=_field(raw, "scope", index),
                blocker=_field(raw, "blocker", index),
                command=_field(raw, "command", index),
            )
        )
    scopes = [entry.scope for entry in entries]
    if len(set(scopes)) != len(scopes):
        raise PendingProbeError("pending_live_probes scopes must be unique")
    return tuple(entries)
