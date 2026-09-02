"""The one-directional baseline guard survives inside the merge-tree gate.

Issue #5441 review finding (blocking): removing the five merge-tree-backed
ratchets from ``scripts/validation/checks_ratchet.py``'s ``RATCHETS`` also
removed the only local caller of ``count_ratchet._base_ref_verdict`` for
those five, because ``_check_one`` in ``merge_tree_ratchet_check.py`` compares
the measured count against ``min(base baseline, merged baseline)`` and never
checks whether the baseline itself moved. A branch that raises its own
baseline without adding a violation still measures under that lower ceiling
and passes silently, even though the standalone ratchet script still blocks
it with ``--base-ref`` (``count_ratchet.py``'s own docstring: "Neither
subsumes the other.").

Reproduces the finding's repro exactly: raise
``scripts/ci/cli_exit_contract_baseline.txt`` on a branch with the measured
count unchanged, and assert the merge-tree gate now blocks it, both through
the fast-forward-clean path (the common case the issue's own repro hit) and
the materialize-and-recount path.

Split into its own file, not appended to ``test_merge_tree_ratchet_check.py``,
to keep that file under the taste-lints 500-line ceiling (see
``test_checks_ratchet_merge_tree_backstop.py``'s docstring for the same
reasoning).
"""

from __future__ import annotations

import shutil
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.ci import merge_tree_ratchet_check as _m
from tests.ci.test_merge_tree_ratchet_check import _commit_all, _git, _make_repo_with_baselines

# Both classes below drive git through _make_repo_with_baselines and _git, so
# without git they would fail rather than skip (same pattern as
# tests/ci/test_merge_tree_materialization.py:138).
_REQUIRES_GIT = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed"
)


def _zero_five_counters():
    return (
        patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
        patch("scripts.ci.cli_exit_contract_ratchet.current_count", return_value=0),
    )


@_REQUIRES_GIT
@pytest.mark.usefixtures("_zero_non_target_aggregate_counts")
class TestOneDirectionalBaselineGuard:
    def test_raised_baseline_blocks_on_the_fast_forward_path(self, tmp_path: Path) -> None:
        """A branch that widens a ceiling with no new violations still fails.

        ``main`` never moves; the branch itself raises the baseline from 10 to
        20 and commits it. HEAD is a clean fast-forward ahead of ``main``, so
        this exercises ``is_fast_forward_clean``'s early-return path, the same
        one the finding's own reproduction hit.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "scripts" / "ci" / "cli_exit_contract_baseline.txt").write_text(
            "20\n", encoding="utf-8"
        )
        _commit_all(repo, "widen cli exit contract baseline for no reason")

        counters = _zero_five_counters()
        with counters[0], counters[1], counters[2], counters[3], counters[4]:
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_REGRESSION

    def test_raised_baseline_blocks_on_the_materialize_path(
        self, tmp_path: Path
    ) -> None:
        """Same guard, forced through the non-fast-forward materialize path.

        ``main`` also commits (an unrelated file) after the branch forks, so
        the branch is no longer a fast-forward ancestor and
        ``_evaluate_merged_tree`` must fall back to
        ``_materialize_tree``/``_init_scratch_repo`` before the loop runs.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "scripts" / "ci" / "cli_exit_contract_baseline.txt").write_text(
            "20\n", encoding="utf-8"
        )
        _commit_all(repo, "widen cli exit contract baseline for no reason")

        _git(repo, "checkout", "main")
        (repo / "unrelated.py").write_text("# unrelated change on main\n", encoding="utf-8")
        _commit_all(repo, "main moves ahead")
        _git(repo, "checkout", "pr-branch")

        counters = _zero_five_counters()
        with counters[0], counters[1], counters[2], counters[3], counters[4]:
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_REGRESSION

    def test_unraised_baseline_still_passes(self, tmp_path: Path) -> None:
        """Negative control: a branch that never touches its baseline passes.

        Without this, the two assertions above could pass against a build
        that always returns EXIT_REGRESSION for a merge-tree-backed ratchet.
        """
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "pr_change.py").write_text("# unrelated PR content\n", encoding="utf-8")
        _commit_all(repo, "PR change, baseline untouched")

        counters = _zero_five_counters()
        with counters[0], counters[1], counters[2], counters[3], counters[4]:
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_OK

    def test_raised_baseline_message_names_the_restore_value(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The diagnostic tells the contributor what value to restore."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        _git(repo, "checkout", "-b", "pr-branch")
        (repo / "scripts" / "ci" / "cli_exit_contract_baseline.txt").write_text(
            "20\n", encoding="utf-8"
        )
        _commit_all(repo, "widen cli exit contract baseline for no reason")

        counters = _zero_five_counters()
        with counters[0], counters[1], counters[2], counters[3], counters[4]:
            rc = _m.main(["--repo-root", str(repo), "--base-ref", "main"])

        assert rc == _m.EXIT_REGRESSION
        error = capsys.readouterr().err
        assert "BASELINE ABOVE BASE" in error
        assert "restore 10 and fix the violations" in error


@_REQUIRES_GIT
class TestDirectionVerdictExitCodes:
    """The guard's exit code reaches the caller instead of collapsing to 1.

    Issue #5441 review: ``raised_baseline`` returned a bool, so
    ``_evaluate_registered_ratchets`` raised the result to EXIT_REGRESSION for
    every non-None verdict. ``_base_ref_verdict`` distinguishes 1 (a baseline
    move), 2 (a fork point recording no baseline) and 3 (git or a fork baseline
    that could not be read), and those three share no remedy, so a config or
    external failure printed its own exit-2 or exit-3 diagnostic and then made
    the process exit 1.
    """

    @staticmethod
    def _evaluate(repo: Path, base_oid: str, verdict: int | None, base_ref: str = "HEAD"):
        with ExitStack() as stack:
            for counter in _zero_five_counters():
                stack.enter_context(counter)
            guard = stack.enter_context(
                patch.object(
                    _m, "_one_directional_baseline_failure", return_value=verdict
                )
            )
            code = _m._evaluate_registered_ratchets(
                repo, base_oid, repo, base_ref=base_ref
            )
        return code, guard

    @pytest.mark.parametrize(
        ("verdict", "expected"),
        [
            (1, _m.EXIT_REGRESSION),
            (2, _m.EXIT_CONFIG),
            (3, _m.EXIT_EXTERNAL),
        ],
    )
    def test_the_verdict_code_is_propagated(
        self, tmp_path: Path, verdict: int, expected: int
    ) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        base_oid = _git(repo, "rev-parse", "HEAD").stdout.strip()

        code, _ = self._evaluate(repo, base_oid, verdict)

        assert code == expected

    def test_a_passing_verdict_leaves_the_run_ok(self, tmp_path: Path) -> None:
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        base_oid = _git(repo, "rev-parse", "HEAD").stdout.strip()

        code, _ = self._evaluate(repo, base_oid, None)

        assert code == _m.EXIT_OK

    def test_the_guard_is_pinned_to_the_oid_not_the_ref(self, tmp_path: Path) -> None:
        """A concurrent fetch must not move what the count is judged against."""
        repo = _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10)
        base_oid = _git(repo, "rev-parse", "HEAD").stdout.strip()

        _, guard = self._evaluate(
            repo, base_oid, None, base_ref="refs/remotes/origin/main"
        )

        assert guard.call_args_list, "the guard must run for each ratchet"
        for call in guard.call_args_list:
            assert call.args[1] == base_oid
