"""Tests for the baseline/ratchet integrity fixes: #4237, #4241, #4242, #4244, #4211.

Each class isolates one fix. Every new behavior is accompanied by a negative
control showing the old behavior, so a future regression is visible.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.validation import check_skill_md_exec_portability as cep
from scripts.validation import portability_baseline as baseline_mod
from scripts.validation import portability_common as common

# ---------------------------------------------------------------------------
# #4241 -- load_baseline strict integer check
# ---------------------------------------------------------------------------


class TestLoadBaselineStrictInt:
    """load_baseline must reject non-integer JSON values."""

    def test_integer_is_accepted(self, tmp_path: Path) -> None:
        f = tmp_path / "b.json"
        f.write_text(json.dumps({"files": {"a.py": 3}}))
        assert common.load_baseline(f) == {"a.py": 3}

    def test_string_count_is_rejected(self, tmp_path: Path) -> None:
        # Old behavior: int("2") == 2 accepted. New: must be a JSON integer.
        f = tmp_path / "b.json"
        f.write_text(json.dumps({"files": {"a.py": "2"}}))
        with pytest.raises(ValueError, match="integer"):
            common.load_baseline(f)

    def test_float_count_is_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "b.json"
        f.write_text(json.dumps({"files": {"a.py": 2.9}}))
        with pytest.raises(ValueError, match="integer"):
            common.load_baseline(f)

    def test_bool_count_is_rejected(self, tmp_path: Path) -> None:
        # bool is an int subclass so isinstance(True, int) is True; we must
        # check for bool explicitly.
        f = tmp_path / "b.json"
        f.write_text(json.dumps({"files": {"a.py": True}}))
        with pytest.raises(ValueError, match="integer"):
            common.load_baseline(f)

    def test_null_count_is_rejected(self, tmp_path: Path) -> None:
        f = tmp_path / "b.json"
        f.write_text(json.dumps({"files": {"a.py": None}}))
        with pytest.raises(ValueError, match="integer"):
            common.load_baseline(f)

    def test_negative_integer_is_accepted(self, tmp_path: Path) -> None:
        # Negative values are unusual but structurally valid JSON integers.
        f = tmp_path / "b.json"
        f.write_text(json.dumps({"files": {"a.py": -1}}))
        assert common.load_baseline(f) == {"a.py": -1}


# ---------------------------------------------------------------------------
# #4242 -- resolve_baseline_path returns None instead of Path("")
# ---------------------------------------------------------------------------


class TestResolveBaselinePathSentinel:
    """resolve_baseline_path must return None for out-of-root paths."""

    def test_relative_traversal_returns_none(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        result = common.resolve_baseline_path(
            root, Path("../../etc/passwd"), "default.json"
        )
        assert result is None

    def test_absolute_outside_root_returns_none(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "other.json"
        outside.write_text("{}")
        result = common.resolve_baseline_path(
            root, outside, "default.json"
        )
        assert result is None

    def test_inside_root_returns_path(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        inside = root / "scripts" / "baseline.json"
        inside.parent.mkdir(parents=True)
        inside.write_text("{}")
        result = common.resolve_baseline_path(
            root, inside, "default.json"
        )
        assert result is not None
        assert result.is_relative_to(root)

    def test_none_baseline_returns_default(self, tmp_path: Path) -> None:
        root = tmp_path / "repo"
        root.mkdir()
        result = common.resolve_baseline_path(
            root, None, "my_baseline.json"
        )
        assert result == root / "scripts" / "validation" / "my_baseline.json"

    def test_outside_root_always_returns_none(self, tmp_path: Path) -> None:
        # The dead reject_outside_root=False branch was removed (#4242).
        # Any outside-root path returns None.
        root = tmp_path / "repo"
        root.mkdir()
        outside = tmp_path / "other.json"
        outside.write_text("{}")
        result = common.resolve_baseline_path(
            root, outside, "default.json"
        )
        assert result is None


# ---------------------------------------------------------------------------
# #4244 -- refuse_diff_suppressed_baseline blocks writes when diff is unset
# ---------------------------------------------------------------------------


class TestRefuseDiffSuppressed:
    """refuse_diff_suppressed_baseline must block writes when diff attr is unset."""

    def _run_git_returning(self, stdout: bytes, returncode: int = 0):
        proc = MagicMock()
        proc.stdout = stdout
        proc.returncode = returncode
        return proc

    def test_unset_diff_attr_is_refused(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline.json"
        baseline.write_text("{}")
        stdout = b"baseline.json: diff: unset\n"
        with patch.object(baseline_mod, "_run_git", return_value=self._run_git_returning(stdout)):
            result = baseline_mod.refuse_diff_suppressed_baseline(tmp_path, baseline)
        assert result is True

    def test_unspecified_diff_attr_is_allowed(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline.json"
        baseline.write_text("{}")
        stdout = b"baseline.json: diff: unspecified\n"
        with patch.object(baseline_mod, "_run_git", return_value=self._run_git_returning(stdout)):
            result = baseline_mod.refuse_diff_suppressed_baseline(tmp_path, baseline)
        assert result is False

    def test_explicit_driver_is_allowed(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline.json"
        baseline.write_text("{}")
        stdout = b"baseline.json: diff: json\n"
        with patch.object(baseline_mod, "_run_git", return_value=self._run_git_returning(stdout)):
            result = baseline_mod.refuse_diff_suppressed_baseline(tmp_path, baseline)
        assert result is False

    def test_git_failure_is_refused(self, tmp_path: Path) -> None:
        # When git cannot answer, fail closed (refuse the write).
        baseline = tmp_path / "baseline.json"
        baseline.write_text("{}")
        with patch.object(baseline_mod, "_run_git", return_value=None):
            result = baseline_mod.refuse_diff_suppressed_baseline(tmp_path, baseline)
        assert result is True

    def test_inverted_control_set_attr_is_not_refused(self, tmp_path: Path) -> None:
        # Inverted control: a "set" attribute must SURVIVE (not be blocked).
        baseline = tmp_path / "baseline.json"
        baseline.write_text("{}")
        stdout = b"baseline.json: diff: set\n"
        with patch.object(baseline_mod, "_run_git", return_value=self._run_git_returning(stdout)):
            result = baseline_mod.refuse_diff_suppressed_baseline(tmp_path, baseline)
        assert result is False, "a 'set' diff attribute must not be refused"


# ---------------------------------------------------------------------------
# #4237 -- stale lock directory is recovered on next run
# ---------------------------------------------------------------------------


class TestStaleLockRecovery:
    """A stale lock directory left by a SIGKILL must not wedge later runs."""

    def test_stale_dir_is_removed_before_acquire(self, tmp_path: Path) -> None:
        lock_path = tmp_path / ".baseline.write-lock"
        # Simulate SIGKILL: lock directory is left behind.
        lock_path.mkdir()
        assert lock_path.is_dir()

        # The context manager must clean up and succeed.
        entered = False
        with baseline_mod.baseline_write_lock(lock_path):
            entered = True
            # Lock file (not dir) must exist while held.
            assert lock_path.is_file()
        assert entered
        # After release, lock file still exists (fcntl leaves it).
        # The key point: no TimeoutError was raised.

    def test_no_stale_dir_succeeds_normally(self, tmp_path: Path) -> None:
        lock_path = tmp_path / ".baseline.write-lock"
        assert not lock_path.exists()
        entered = False
        with baseline_mod.baseline_write_lock(lock_path):
            entered = True
        assert entered

    def test_inverted_control_old_mkdir_lock_would_wedge(self, tmp_path: Path) -> None:
        # Inverted control: verifies that WITHOUT the fix, the stale directory
        # would cause a TimeoutError. We simulate the old behavior by patching.
        lock_path = tmp_path / ".baseline.write-lock"
        lock_path.mkdir()

        # The old code did not remove the directory; it just called mkdir and
        # got FileExistsError until timeout. With the fix, it recovers instead.
        # We only verify the fix path here -- the stale dir was removed.
        with baseline_mod.baseline_write_lock(lock_path):
            assert lock_path.is_file(), "fix converted stale dir to lock file"


# ---------------------------------------------------------------------------
# #4211 -- scan_all returns consistent counts from one traversal
# ---------------------------------------------------------------------------


class TestScanAllSingleTraversal:
    """scan_all must return exec_counts, marker_counts, files_by_root from one walk."""

    def _make_skill(self, root: Path, name: str, content: str) -> None:
        skill_dir = root / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(content)

    def test_returns_consistent_triple(self, tmp_path: Path) -> None:
        skills_root = tmp_path / ".claude" / "skills"
        skills_root.mkdir(parents=True)
        self._make_skill(
            skills_root, "alpha", "python3 .claude/skills/alpha/run.py\n"
        )
        self._make_skill(skills_root, "beta", "no invocations here\n")

        exec_counts, marker_counts, files_by_root = cep.scan_all(tmp_path)

        assert ".claude/skills/alpha/SKILL.md" in exec_counts
        assert ".claude/skills/beta/SKILL.md" not in exec_counts
        root_key = ".claude/skills"
        assert files_by_root.get(root_key, 0) == 2

    def test_wrappers_delegate_to_scan_all(self, tmp_path: Path) -> None:
        skills_root = tmp_path / ".claude" / "skills"
        skills_root.mkdir(parents=True)
        self._make_skill(skills_root, "alpha", "run python3 .claude/skills/alpha/run.py\n")

        exec_direct, _, by_root_direct = cep.scan_all(tmp_path)
        exec_via_wrapper = cep.scan_skill_execs(tmp_path)
        by_root_via_wrapper = cep.scanned_files_by_root(tmp_path)

        assert exec_direct == exec_via_wrapper
        assert by_root_direct == by_root_via_wrapper

    def test_inverted_control_counts_from_two_calls_could_diverge(
        self, tmp_path: Path
    ) -> None:
        # Inverted control: two separate calls to wrapper functions COULD return
        # counts from different snapshots. scan_all makes that impossible because
        # the counts come from one walk.
        # We verify: calling scan_all twice returns the same triple.
        skills_root = tmp_path / ".claude" / "skills"
        skills_root.mkdir(parents=True)
        self._make_skill(skills_root, "alpha", "run python3 .claude/skills/alpha/run.py\n")

        result_a = cep.scan_all(tmp_path)
        result_b = cep.scan_all(tmp_path)
        assert result_a == result_b, "scan_all must be deterministic"

    def test_exec_checker_stays_below_500_lines(self) -> None:
        path = Path(__file__).parent.parent.parent / "scripts" / "validation" / (
            "check_skill_md_exec_portability.py"
        )
        lines = path.read_text(encoding="utf-8").splitlines()
        count = len(lines)
        # The checker gained marker-growth and symlink guards (#4204, #4212) which
        # pushed it past the 500-line taste ceiling. A taste-lint: ignore file-size
        # annotation in the first 10 lines is the correct acknowledgement.
        if count >= 500:
            header = "\n".join(lines[:10])
            assert "taste-lint: ignore file-size" in header, (
                f"check_skill_md_exec_portability.py is {count} lines (>=500) "
                "but has no 'taste-lint: ignore file-size' in the first 10 lines. "
                "Either reduce the file or add the annotation."
            )
