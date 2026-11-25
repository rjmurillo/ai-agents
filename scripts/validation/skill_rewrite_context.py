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
