"""Branch history shared by the ADR-127 evidence check and its scenario rules.

``check_skill_rewrite_evidence.py`` builds one :class:`Context` per run. The
scenario rules in ``skill_rewrite_scenarios.py`` take it too, so it lives
here: the checker imports the scenario module, and a second import back
would be circular.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import ModuleType

from skill_rewrite_skills import Git

EVIDENCE_ROOT = "evals/skill-rewrites"
RETIRED_FILE = "retired.json"


@dataclass
class Context:
    git: Git
    base_ref: str
    head: str
    merge_base: str
    commits: list[str]
    runner: ModuleType
    _changes: dict[str, dict[str, str]] = field(default_factory=dict)

    def changes(self, commit: str) -> dict[str, str]:
        """Path to status for one commit. ``--cc`` keeps a merge's own edits."""
        if commit in self._changes:
            return self._changes[commit]
        raw = self.git.text(
            "diff-tree",
            "--no-commit-id",
            "-r",
            "-z",
            "--cc",
            "--name-status",
            "--no-renames",
            commit,
        )
        parts = [p for p in raw.split("\0") if p]
        self._changes[commit] = {parts[i + 1]: parts[i] for i in range(0, len(parts) - 1, 2)}
        return self._changes[commit]

    def merge_edits(self, commit: str, prefix: str) -> dict[str, str]:
        """Paths under *prefix* that a merge deletes or changes against its first parent.

        ``changes`` uses ``--cc``, which lists only a path that differs from
        every parent. A merge that takes the other parent's tree for a path,
        by deleting a file the first parent holds, never shows there. An add
        is left out: a file from the other parent is inherited, and a file both
        parents add is already an ``AA`` in ``changes``. A non-merge commit has
        no first-parent comparison to make.
        """
        parents = self.git.text("rev-list", "--parents", "-n", "1", commit).split()[1:]
        if len(parents) < 2:
            return {}
        raw = self.git.text(
            "diff-tree",
            "-r",
            "-z",
            "--name-status",
            "--no-renames",
            parents[0],
            commit,
            "--",
            prefix,
        )
        parts = [p for p in raw.split("\0") if p]
        return {parts[i + 1]: parts[i] for i in range(0, len(parts) - 1, 2) if parts[i] != "A"}
