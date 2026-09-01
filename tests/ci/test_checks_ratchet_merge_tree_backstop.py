"""``validate_count_ratchets`` folds the merge-tree backstop into one call.

Issue #5441: the five ratchets registered in
``scripts/ci/merge_tree_ratchet_registry.py`` used to run once through
``scripts/validation/checks_ratchet.py``'s ``RATCHETS`` (against the working
tree) and again inside a nested ``merge-tree-ratchet`` subprocess (against a
materialized copy), paying for the same five counts twice inside one 85s
deadline. They now run through ``scripts/ci/merge_tree_ratchet_check.py``
exactly once, which is what the tests below assert with a call counter.
Split out of ``test_pre_pr_runs_lefthook_ratchets.py`` to keep both files
under the taste-lints file-size ceiling.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))
import checks_ratchet  # noqa: E402


def _repo(tmp_path: Path) -> Path:
    from tests.ci.test_merge_tree_ratchet_check import _make_repo_with_baselines

    return _make_repo_with_baselines(tmp_path, ruff=10, taste=10, ignore=10, memory=10)


def _stub_standalone_ratchets(repo: Path) -> None:
    """Create the two non-shared ratchet scripts so the existence check passes.

    Their content never runs: neither remaining ``RATCHETS`` entry is invoked
    with a base ref that requires network access, and both exit 0 on an
    empty file, so an empty stub is enough to satisfy
    ``validate_count_ratchets``'s "does the script exist" gate.
    """
    for ratchet in checks_ratchet.RATCHETS:
        script = repo / ratchet.script
        script.parent.mkdir(parents=True, exist_ok=True)
        if not script.exists():
            script.write_text("", encoding="utf-8")


class TestMergeTreeBackstopDelegation:
    def test_each_shared_counter_runs_exactly_once_per_invocation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The happy-path regression guard for issue #5441's fix.

        A clean fast-forward branch (``base_ref == HEAD``) is the common case
        the issue's own reproduction hit. Each of the five merge-tree-backed
        counters must be measured exactly once for it, not twice.

        This mocks ``current_count`` in-process, so it cannot see a
        re-registration of one of these five scripts in ``checks_ratchet.
        RATCHETS``: a re-added entry dispatches through ``uv run --frozen`` as
        a separate interpreter (``build_command``), which this mock never
        touches, and the stub script written by ``_stub_standalone_ratchets``
        would exit 0 either way. ``test_no_ratchet_is_registered_in_both_
        tables`` in ``test_lefthook_ratchet_wiring.py`` is the guard against
        that specific mutation: it asserts the two script sets stay disjoint
        without running anything, so it catches what this test cannot
        (issue #5441 review).
        """
        repo = _repo(tmp_path)
        _stub_standalone_ratchets(repo)
        monkeypatch.setattr(checks_ratchet, "_resolve_default_base_ref", lambda _root: "HEAD")

        call_counts = {"ruff": 0, "taste": 0, "ignore": 0, "memory": 0, "cli_exit": 0}

        def _counter(key: str):
            def _count(_root: Path) -> int:
                call_counts[key] += 1
                return 0

            return _count

        with (
            patch(
                "scripts.ci.ruff_count_ratchet.current_count", side_effect=_counter("ruff")
            ),
            patch(
                "scripts.ci.taste_count_ratchet.current_count", side_effect=_counter("taste")
            ),
            patch(
                "scripts.ci.type_ignore_count_ratchet.current_count",
                side_effect=_counter("ignore"),
            ),
            patch(
                "scripts.ci.memory_index_count_ratchet.current_count",
                side_effect=_counter("memory"),
            ),
            patch(
                "scripts.ci.cli_exit_contract_ratchet.current_count",
                side_effect=_counter("cli_exit"),
            ),
        ):
            passed = checks_ratchet.validate_count_ratchets(repo)

        assert passed is True
        assert call_counts == {
            "ruff": 1,
            "taste": 1,
            "ignore": 1,
            "memory": 1,
            "cli_exit": 1,
        }

    def test_skip_merge_tree_never_calls_the_shared_counters(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ``count-ratchets`` Lefthook job's flag skips the backstop entirely."""
        repo = _repo(tmp_path)
        _stub_standalone_ratchets(repo)
        monkeypatch.setattr(checks_ratchet, "_resolve_default_base_ref", lambda _root: "HEAD")

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count") as ruff_counter,
            patch("scripts.ci.taste_count_ratchet.current_count") as taste_counter,
            patch("scripts.ci.type_ignore_count_ratchet.current_count") as ignore_counter,
            patch("scripts.ci.memory_index_count_ratchet.current_count") as memory_counter,
            patch("scripts.ci.cli_exit_contract_ratchet.current_count") as cli_counter,
        ):
            passed = checks_ratchet.validate_count_ratchets(repo, skip_merge_tree=True)

        assert passed is True
        ruff_counter.assert_not_called()
        taste_counter.assert_not_called()
        ignore_counter.assert_not_called()
        memory_counter.assert_not_called()
        cli_counter.assert_not_called()

    def test_merge_tree_regression_fails_the_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ratchet the backstop blocks fails the whole gate."""
        repo = _repo(tmp_path)
        _stub_standalone_ratchets(repo)
        monkeypatch.setattr(checks_ratchet, "_resolve_default_base_ref", lambda _root: "HEAD")

        with (
            patch("scripts.ci.ruff_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.taste_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.type_ignore_count_ratchet.current_count", return_value=0),
            patch("scripts.ci.memory_index_count_ratchet.current_count", return_value=0),
            patch(
                "scripts.ci.cli_exit_contract_ratchet.current_count", return_value=999
            ),
        ):
            passed = checks_ratchet.validate_count_ratchets(repo)

        assert passed is False

    def test_merge_tree_backstop_gets_its_own_deadline_not_the_60s_aggregate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Issue #5441 review (major finding): 60s < the ~64s materialize worst case.

        ``_AGGREGATE_TIMEOUT_SECONDS`` (60s) bounds only the two RATCHETS
        entries. Handing that same 60s down as the merge-tree backstop's own
        deadline caps a path measured at ~64s worst case under a tighter
        budget than its own worst case, a guaranteed failure rather than
        headroom. ``_evaluate_merge_tree_backstop`` must be called with no
        ``deadline`` override, so it falls back to its own internal 90s
        default instead.
        """
        repo = _repo(tmp_path)
        _stub_standalone_ratchets(repo)
        monkeypatch.setattr(checks_ratchet, "_resolve_default_base_ref", lambda _root: "HEAD")

        with patch.object(
            checks_ratchet, "_evaluate_merge_tree_backstop", return_value=0
        ) as backstop:
            checks_ratchet.validate_count_ratchets(repo)

        backstop.assert_called_once()
        assert "deadline" not in backstop.call_args.kwargs
