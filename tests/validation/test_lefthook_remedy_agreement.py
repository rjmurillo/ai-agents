"""Two adjacent pre-PR gates must not prescribe repairs that fight each other.

``pre_pr_sequence.py`` runs ``Git Hook Health (core.hooksPath)`` immediately
before ``Lefthook Installed``. The first prints a repair command; the second
reads every declared hook file and rejects one carrying a machine-bound
absolute path. ``lefthook install --reset-hooks-path`` writes exactly such a
shim, probing the installing checkout's ``.venv``, so an operator who followed
the first gate's on-screen remedy repaired it and reddened the next gate in the
same run (issue #4789).

Lives apart from ``test_check_git_hook_health.py`` because the contract is not
that module's: it is an agreement between two modules that cannot import each
other. ``check_git_hook_health`` is imported by bare name with
``scripts/validation`` on ``sys.path`` and is also run directly as a script, so
neither invocation can resolve ``scripts.maintenance``. The constant is
therefore duplicated by hand, and this file is what stops the two copies
drifting.

Coverage:

- positive: the remedy names the worktree-safe installer and equals the
  installer's own ``REPAIR_COMMAND``.
- negative: no remedy, scoped or unscoped, runs a bare ``lefthook install``.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way production imports (issue #2223): prepend ``scripts/validation``
# to ``sys.path`` and import by bare name.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_git_hook_health

from scripts.maintenance.install_lefthook_worktree_safe import REPAIR_COMMAND


class TestRemedyAgreesWithTheAdjacentGate:
    """The remedy this gate prints must leave the gate after it passing."""

    def test_the_remedy_names_the_worktree_safe_installer(self) -> None:
        assert "install_lefthook_worktree_safe.py" in check_git_hook_health.REMEDY

    def test_the_remedy_is_the_installers_own_repair_command(self) -> None:
        assert check_git_hook_health.REMEDY == REPAIR_COMMAND

    def test_no_remedy_runs_a_bare_lefthook_install(self) -> None:
        """The three scoped variants interpolate REMEDY, so none may reintroduce it."""
        remedies = (
            check_git_hook_health.REMEDY,
            check_git_hook_health.WORKTREE_REMEDY,
            check_git_hook_health.GLOBAL_REMEDY,
            check_git_hook_health.SYSTEM_REMEDY,
        )

        for remedy in remedies:
            assert "lefthook install" not in remedy, remedy

    def test_every_scoped_remedy_still_clears_its_hooks_path_override(self) -> None:
        """Control: repointing the command must not drop the unset it prefixes."""
        scoped = {
            "--worktree": check_git_hook_health.WORKTREE_REMEDY,
            "--global": check_git_hook_health.GLOBAL_REMEDY,
            "--system": check_git_hook_health.SYSTEM_REMEDY,
        }

        for scope, remedy in scoped.items():
            assert f"git config {scope} --unset-all core.hooksPath" in remedy
            assert remedy.endswith(REPAIR_COMMAND), remedy
