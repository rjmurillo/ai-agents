#!/usr/bin/env python3
# taste-lint: ignore naming -- a library imported by the drift-check hook, its
# model, and its report; registered as a hook nowhere. The `invoke_` prefix
# marks a registered entry point, so using it here would assert the opposite of
# what is true. Same reasoning as `plugin_hook_drift_model.py`.
"""The shapes a drift scan produces, and the bounds it runs under.

Held apart from both the parser and the scanner because all three layers need
them: the hook fills them in, the model reads the bounds, and the report
renders them. Keeping them here is what lets the parsing and rendering layers
stay independent of each other.

The one idea worth stating: an incomplete scan is a first-class outcome, not a
missing result. `ScanBudget` records why a walk stopped being exhaustive, and
`ScanOutcome.incomplete` carries that to the message, because zero reports on
its own reads as "nothing is installed", which is a claim the check has not
earned.

Refs: issue #5085.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Bounds on the on-disk scan. Session start is not the place for an unbounded
# walk: a marketplace clone can carry a full node_modules tree. Depth 5 reaches
# `plugins/marketplaces/<marketplace>/src/copilot-cli`, the deepest plugin root
# this repository publishes.
MAX_SCAN_DEPTH = 5
MAX_SCAN_DIRS = 4000
PRUNED_DIR_NAMES = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv"})


# Why a walk stopped being exhaustive. Rendered verbatim into the inconclusive
# block, so each one reads as a cause a human can act on.
DIRECTORY_BUDGET_SPENT = f"stopped at the {MAX_SCAN_DIRS}-directory scan bound"
ENTRY_CEILING_REACHED = "a directory held more entries than the per-directory ceiling"
DIRECTORY_UNREADABLE = "a directory could not be listed"
PLUGIN_MANIFEST_UNREADABLE = "a candidate plugin manifest could not be read"


@dataclass(slots=True)
class ScanBudget:
    """Directory-visit budget for one bounded walk, and whether it ran out.

    Exhausting the budget has to reach the reader. A walk that stopped early
    may never have visited the stale install this hook exists to name, and
    reporting that as "matches" or "no installed copy found" is precisely the
    false-clean verdict the check is meant to prevent. Truncation is therefore
    an outcome the caller reads, not an early ``return`` the caller cannot see.
    """

    # Read at construction, not at class creation, so the bound stays one
    # number that tests and callers can lower.
    remaining: int = field(default_factory=lambda: MAX_SCAN_DIRS)
    truncated: bool = False
    reasons: set[str] = field(default_factory=set)

    def stop(self, reason: str) -> None:
        """Record that the walk is no longer exhaustive, and why.

        Four different things cut a scan short and they call for different
        responses, so they are not collapsed into one flag. Reporting an
        unreadable directory as "hit the directory bound" sends the reader off
        to raise a limit that had nothing to do with it.
        """
        self.truncated = True
        self.reasons.add(reason)

    def spend(self) -> bool:
        """Consume one directory visit; False once the budget is exhausted."""
        if self.remaining <= 0:
            self.stop(DIRECTORY_BUDGET_SPENT)
            return False
        self.remaining -= 1
        return True


@dataclass(frozen=True, slots=True)
class InstallReport:
    """Comparison of one installed copy against its source manifest."""

    surface: str
    install_path: Path
    only_in_install: tuple[str, ...]
    only_in_source: tuple[str, ...]
    error: str | None

    @property
    def has_drift(self) -> bool:
        return bool(self.only_in_install or self.only_in_source or self.error)


@dataclass(frozen=True, slots=True)
class ScanOutcome:
    """Everything one pass over the install trees established, and did not.

    ``incomplete`` names each search root whose walk hit ``MAX_SCAN_DIRS``.
    While it is non-empty, no verdict in ``reports`` is a statement about the
    whole tree.
    """

    reports: list[InstallReport] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    incomplete: list[str] = field(default_factory=list)
