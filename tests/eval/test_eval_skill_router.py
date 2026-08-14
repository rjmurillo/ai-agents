"""Tests for eval_skill_router.py (issue #4304).

Covers:
- BEFORE_REF is an immutable SHA, not a moving branch name.
- check_identical_arms detects when both eval arms read the same bytes.
- main() exits 1 when all arms are identical (loud failure, not silent zero).
- main() exits 0 (dry-run) when arms differ.
- Partial identical coverage emits a warning but does not abort.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Ensure scripts/eval is importable.
_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
_SKILL_ROUTER_FIXTURES = Path(__file__).resolve().parents[2] / "evals" / "skill-router-spike" / "fixtures.json"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import eval_skill_router as router  # noqa: E402

# ---------------------------------------------------------------------------
# BEFORE_REF is a fixed SHA (not a branch name)
# ---------------------------------------------------------------------------

class TestBeforeRefIsImmutable:
    def test_before_ref_is_a_full_sha(self) -> None:
        """BEFORE_REF must be a 40-hex-char commit SHA, not a branch/tag name."""
        ref = router.BEFORE_REF
        assert len(ref) == 40, (
            f"BEFORE_REF={ref!r} is {len(ref)} chars; expected a 40-char SHA. "
            "A moving branch name makes both eval arms read identical bytes "
            "once the target commit lands on that branch (issue #4304)."
        )
        assert all(c in "0123456789abcdef" for c in ref.lower()), (
            f"BEFORE_REF={ref!r} contains non-hex characters; not a valid SHA."
        )

    def test_before_ref_is_not_origin_main(self) -> None:
        ref = router.BEFORE_REF
        assert ref != "origin/main", (
            "BEFORE_REF must be a pinned commit SHA. "
            "'origin/main' is a moving ref; after PR #2127 merged it points to "
            "post-#2127 content and makes both arms identical (issue #4304)."
        )

    def test_before_ref_does_not_contain_slash(self) -> None:
        """A SHA never contains a slash; a branch/remote ref always does."""
        assert "/" not in router.BEFORE_REF, (
            f"BEFORE_REF={router.BEFORE_REF!r} looks like a remote ref, not a SHA."
        )


# ---------------------------------------------------------------------------
# check_identical_arms
# ---------------------------------------------------------------------------

def _make_plan_item(
    fx_id: str,
    candidates: list[str],
    before_descs: dict[str, str],
    after_descs: dict[str, str],
) -> dict[str, Any]:
    return {
        "fixture": {"id": fx_id, "candidates": candidates, "query": "q", "correct": candidates[0]},
        "before_desc": before_descs,
        "after_desc": after_descs,
        "paths": {c: f".claude/skills/{c}/SKILL.md" for c in candidates},
        "prompts": {"before": "bp", "after": "ap"},
    }


class TestCheckIdenticalArms:
    def test_all_identical_returns_all_pairs(self) -> None:
        plan = [
            _make_plan_item("f1", ["a", "b"],
                            {"a": "desc-a", "b": "desc-b"},
                            {"a": "desc-a", "b": "desc-b"}),
        ]
        result = router.check_identical_arms(plan)
        assert set(result) == {"f1/a", "f1/b"}

    def test_all_differ_returns_empty(self) -> None:
        plan = [
            _make_plan_item("f1", ["a", "b"],
                            {"a": "old-a", "b": "old-b"},
                            {"a": "new-a", "b": "new-b"}),
        ]
        assert router.check_identical_arms(plan) == []

    def test_partial_identical_returns_only_identical(self) -> None:
        plan = [
            _make_plan_item("f1", ["a", "b"],
                            {"a": "same", "b": "old-b"},
                            {"a": "same", "b": "new-b"}),
        ]
        result = router.check_identical_arms(plan)
        assert result == ["f1/a"]
        assert "f1/b" not in result

    def test_multiple_fixtures_all_identical(self) -> None:
        plan = [
            _make_plan_item("f1", ["x"], {"x": "d"}, {"x": "d"}),
            _make_plan_item("f2", ["y"], {"y": "e"}, {"y": "e"}),
        ]
        result = router.check_identical_arms(plan)
        assert set(result) == {"f1/x", "f2/y"}

    def test_empty_plan_returns_empty(self) -> None:
        assert router.check_identical_arms([]) == []


# ---------------------------------------------------------------------------
# main() exits 1 when all arms are identical
# ---------------------------------------------------------------------------

def _write_fixture(tmp_path: Path, candidates: list[str]) -> str:
    fx = [{"id": "f1", "query": "what", "candidates": candidates, "correct": candidates[0]}]
    p = tmp_path / "fx.json"
    p.write_text(json.dumps(fx), encoding="utf-8")
    return str(p)


def _make_skill_files(repo: Path, names: list[str], content: str) -> None:
    """Create minimal SKILL.md files with the given description."""
    for name in names:
        d = repo / ".claude" / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\ndescription: {content}\n---\n# {name}\n"
        )


class TestMainIdenticalArmsExits1:
    def test_exits_1_when_all_arms_identical(self, tmp_path: Path) -> None:
        """main() must exit 1, not 0, when before==after for every candidate."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_skill_files(repo, ["skill-a", "skill-b"], "shared description")

        fx_path = _write_fixture(tmp_path, ["skill-a", "skill-b"])

        # Patch git show to return the same content as the working tree.
        def fake_git_show(cmd: list[str], **kwargs: Any) -> MagicMock:
            # cmd is: git -C <repo> show <ref>:<path>
            rel = cmd[-1].split(":", 1)[1]
            content = (repo / rel).read_text()
            m = MagicMock()
            m.stdout = content
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_git_show):
            with patch("sys.argv", ["eval_skill_router.py",
                                    "--fixtures", fx_path,
                                    "--repo-root", str(repo),
                                    "--dry-run"]):
                rc = router.main()

        assert rc == 1, f"Expected exit 1 (identical arms), got {rc}"

    def test_exits_0_dry_run_when_arms_differ(self, tmp_path: Path) -> None:
        """main() exits 0 on --dry-run when before and after differ."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_skill_files(repo, ["skill-a", "skill-b"], "new description")

        fx_path = _write_fixture(tmp_path, ["skill-a", "skill-b"])

        def fake_git_show(cmd: list[str], **kwargs: Any) -> MagicMock:
            m = MagicMock()
            m.stdout = "---\ndescription: old description\n---\n# skill\n"
            m.returncode = 0
            return m

        with patch("subprocess.run", side_effect=fake_git_show):
            with patch("sys.argv", ["eval_skill_router.py",
                                    "--fixtures", fx_path,
                                    "--repo-root", str(repo),
                                    "--dry-run"]):
                rc = router.main()

        assert rc == 0, f"Expected exit 0 (arms differ, dry-run), got {rc}"

    def test_partial_identical_does_not_abort(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Partial identical arms emit a warning but do not exit 1."""
        repo = tmp_path / "repo"
        repo.mkdir()
        # skill-a: same before/after; skill-b: differs
        _make_skill_files(repo, ["skill-a"], "same desc")
        _make_skill_files(repo, ["skill-b"], "new desc for b")

        fx_path = _write_fixture(tmp_path, ["skill-a", "skill-b"])

        call_count = [0]

        def fake_git_show(cmd: list[str], **kwargs: Any) -> MagicMock:
            rel = cmd[-1].split(":", 1)[1]
            m = MagicMock()
            if "skill-a" in rel:
                m.stdout = "---\ndescription: same desc\n---\n"
            else:
                m.stdout = "---\ndescription: old desc for b\n---\n"
            m.returncode = 0
            call_count[0] += 1
            return m

        with patch("subprocess.run", side_effect=fake_git_show):
            with patch("sys.argv", ["eval_skill_router.py",
                                    "--fixtures", fx_path,
                                    "--repo-root", str(repo),
                                    "--dry-run"]):
                rc = router.main()

        assert rc == 0, f"Partial identical should not abort; got rc={rc}"
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "skill-a" in captured.err


# ---------------------------------------------------------------------------
# Negative control: the old BEFORE_REF="origin/main" would trigger exit 1
# ---------------------------------------------------------------------------

class TestOldBehaviorWouldFail:
    def test_origin_main_triggers_identical_arms_detection(self, tmp_path: Path) -> None:
        """Regression proof: if BEFORE_REF were 'origin/main', check_identical_arms
        would detect identical descriptions and force exit 1. This test patches
        BEFORE_REF to the old value and verifies the guard catches it."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _make_skill_files(repo, ["skill-x", "skill-y"], "some description")

        fx_path = _write_fixture(tmp_path, ["skill-x", "skill-y"])

        def fake_git_show_same(cmd: list[str], **kwargs: Any) -> MagicMock:
            rel = cmd[-1].split(":", 1)[1]
            content = (repo / rel).read_text()
            m = MagicMock()
            m.stdout = content
            m.returncode = 0
            return m

        with patch.object(router, "BEFORE_REF", "origin/main"):
            with patch("subprocess.run", side_effect=fake_git_show_same):
                with patch("sys.argv", ["eval_skill_router.py",
                                        "--fixtures", fx_path,
                                        "--repo-root", str(repo),
                                        "--dry-run"]):
                    rc = router.main()

        assert rc == 1, (
            "With BEFORE_REF='origin/main' and working-tree==origin/main content, "
            "main() must exit 1 (identical arms). The guard is not firing."
        )


class TestReviewRoutingCoverage:
    def test_review_routing_cases_are_present(self) -> None:
        fixtures = {fx["id"]: fx for fx in json.loads(_SKILL_ROUTER_FIXTURES.read_text(encoding="utf-8"))}

        expected = {
            "review-05-low-risk-review": "review",
            "review-06-security-routing": "security",
            "review-07-dependency-routing": "architect",
            "review-08-ci-routing": "devops",
            "review-09-type-routing": "architect",
            "review-10-test-routing": "qa",
            "review-11-error-routing": "qa",
            "review-12-fail-closed-additive": "review",
        }

        for fixture_id, correct in expected.items():
            assert fixture_id in fixtures
            assert fixtures[fixture_id]["correct"] == correct
            assert correct in fixtures[fixture_id]["candidates"]
