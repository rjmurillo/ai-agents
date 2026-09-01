"""The repo-health failure report names a repair that can actually clear it.

Split from ``test_check_repo_health.py``, which pins detection, to keep both
files under the 500-line taste ceiling. These cases drive
``_report_corruption`` directly against a constructed verdict, so they need no
scratch repository: the config scopes git can report are enumerable, and
constructing them is the only way to reach the global, system, and command
scopes without writing to the host's real configuration.

Issue #4698: the repair GOTCHAS names, ``git config core.bare false``, writes
to the local config. Pointed at a worktree-scoped, global, or system value it
reports success and changes nothing, so the reader repairs the wrong file and
the checkout stays broken.

Coverage:

- positive: each of git's five config scopes, and an unrecognized one, maps to
  a command that can clear a value held in it; two poisoned scopes get two
  repairs.
- negative: the worktree-scoped immunization line is withheld when
  ``extensions.worktreeConfig`` is absent (``git config --worktree`` exits 128
  there) and when the worktree scope is itself the offender, where immunizing
  with the value that is already wrong is not a repair.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Import the way production imports (issue #2223): prepend ``scripts/validation``
# to ``sys.path`` and import by bare name.
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import check_repo_health


def _report(
    work_tree: Path,
    bare_scopes: tuple[tuple[str, str], ...],
    *,
    worktree_config: bool = False,
) -> None:
    """Print the failure report for one constructed verdict."""
    check_repo_health.report_corruption(
        check_repo_health.RepoHealth(
            "corrupted",
            work_tree=work_tree,
            bare_scopes=bare_scopes,
            worktree_config=worktree_config,
        )
    )


class TestRepairNamesEveryScopeThatCarriesTheValue:
    """A repair aimed at the wrong config file leaves the checkout broken."""

    @pytest.mark.parametrize(
        ("scope", "expected"),
        [
            ("local", "git config --replace-all core.bare false"),
            ("worktree", "git config --worktree --replace-all core.bare false"),
            ("global", "git config --global --unset-all core.bare"),
            ("system", "git config --system --unset-all core.bare"),
            ("command", "remove the command-scoped core.bare override"),
            ("unheard-of", "git config --replace-all core.bare false"),
        ],
    )
    def test_every_scope_maps_to_a_command_that_can_clear_it(
        self,
        scope: str,
        expected: str,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _report(tmp_path, ((scope, "true"),))

        assert f"Fix: {expected}" in capsys.readouterr().err

    def test_two_poisoned_scopes_get_two_repairs(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _report(tmp_path, (("local", "true"), ("worktree", "true")))

        err = capsys.readouterr().err
        assert "Fix: git config --replace-all core.bare false" in err
        assert "Fix: git config --worktree --replace-all core.bare false" in err

    def test_the_work_tree_and_every_poisoned_scope_are_named(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A diagnosis the reader cannot act on is why this incident cost hours.

        Both scopes read ``true`` because ``_scoped_core_bare`` asks git for
        ``--type=bool`` and git normalizes every spelling it accepts, so
        ``yes``, ``on`` and ``42`` never reach the report as themselves.
        """
        _report(tmp_path, (("local", "true"), ("global", "true")))

        err = capsys.readouterr().err
        assert str(tmp_path) in err
        assert "local=true" in err
        assert "global=true" in err


class TestImmunizationHintTracksTheWorktreeConfigExtension:
    """``git config --worktree`` exits 128 without the extension enabled."""

    def test_the_hint_appears_when_the_extension_is_enabled(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _report(tmp_path, (("local", "true"),), worktree_config=True)

        assert "in every worktree" in capsys.readouterr().err

    def test_the_hint_is_withheld_when_the_extension_is_absent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _report(tmp_path, (("local", "true"),), worktree_config=False)

        assert "in every worktree" not in capsys.readouterr().err

    def test_the_hint_is_withheld_when_the_worktree_scope_is_the_offender(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Immunizing with the value that is already wrong is not a repair."""
        _report(tmp_path, (("worktree", "true"),), worktree_config=True)

        assert "in every worktree" not in capsys.readouterr().err
