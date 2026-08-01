"""Both portability ratchets must refuse a baseline written from a partial scan.

The hazard is shared, so the tests live together rather than split across the
two checkers' own modules. A scan root can exist and still yield nothing to
read: a partial checkout, a sparse clone, a mistargeted repo root. The
offending-file mapping is empty in that case and equally empty for a genuinely
clean tree, so counts alone cannot separate them.

Coverage is per root, never a sum. Both checkers ship two roots, so a total
stays positive while one of them reads nothing. Emptying only
``src/copilot-cli/skills`` on a real checkout drove the markdown baseline from
73 files to 34 and the exec baseline from 170 to 84, both at exit 0. Every
refusal test below therefore populates one root and starves the other, and the
false-positive control populates every root with several files so that it
cannot be mistaken for the partial checkout it has to stay distinct from.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validation import check_skill_md_exec_portability as cep  # noqa: E402
from scripts.validation import check_skill_md_portability as cmp  # noqa: E402
from scripts.validation.portability_common import refuse_uncovered_scan  # noqa: E402


class TestRefuseUncoveredScanHelper:
    """The shared decision, tested directly rather than only through callers."""

    def test_every_root_read_permits(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        assert refuse_uncovered_scan(tmp_path, {"a": 3, "b": 4}, "skill files") is False
        assert capsys.readouterr().err == ""

    def test_one_unread_root_among_several_refuses(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """A sum would stay positive here. Coverage is what has to fail."""
        assert refuse_uncovered_scan(tmp_path, {"a": 84, "b": 0}, "skill files") is True
        assert "read 0 skill files under: b" in capsys.readouterr().err

    def test_all_roots_unread_refuses(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        assert refuse_uncovered_scan(tmp_path, {"a": 0, "b": 0}, "skill files") is True
        assert "none" in capsys.readouterr().err

    def test_no_roots_at_all_refuses(self, tmp_path: Path) -> None:
        """An empty mapping means nothing was enumerated, which is not coverage."""
        assert refuse_uncovered_scan(tmp_path, {}, "skill files") is True

    def test_refusal_names_the_roots_that_were_read(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Naming both sides is what tells an operator it was partial, not empty."""
        refuse_uncovered_scan(tmp_path, {"kept": 12, "lost": 0}, "skill .md files")
        err = capsys.readouterr().err
        assert "under: lost" in err
        assert "kept (12)" in err


class TestMarkdownCheckerCoverage:
    def _roots(self, root: Path, populated: tuple[str, ...] = ()) -> None:
        """Create every required root, then seed only the named ones."""
        for name in sorted(cmp.REQUIRED_SKILLS_ROOTS):
            skills = root / name / "skills"
            skills.mkdir(parents=True, exist_ok=True)
            if name not in populated:
                continue
            for slug in ("alpha", "beta"):
                (skills / slug).mkdir()
                (skills / slug / "SKILL.md").write_text("Nothing upstream.\n", encoding="utf-8")

    def _run(self, root: Path, baseline: Path) -> int:
        return cmp.main(
            ["--repo-root", str(root), "--baseline", str(baseline), "--update-baseline"]
        )

    def test_refuses_when_every_root_is_empty(self, tmp_path: Path) -> None:
        self._roots(tmp_path)
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_refuses_when_only_the_claude_root_is_populated(self, tmp_path: Path) -> None:
        """The reported failure: one root full, one empty, previously exit 0."""
        self._roots(tmp_path, populated=(".claude",))
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_refuses_when_only_the_copilot_root_is_populated(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=("src/copilot-cli",))
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_partial_scan_leaves_a_populated_baseline_untouched(self, tmp_path: Path) -> None:
        """The wipe this guards against: shrinking a real baseline, not creating one."""
        self._roots(tmp_path, populated=(".claude",))
        baseline = tmp_path / "baseline.json"
        original = json.dumps({"files": {"a/SKILL.md": 3}, "marker_files": {"b/SKILL.md": 1}})
        baseline.write_text(original, encoding="utf-8")
        assert self._run(tmp_path, baseline) == 2
        assert baseline.read_text(encoding="utf-8") == original

    def test_refuses_when_roots_hold_only_non_markdown(self, tmp_path: Path) -> None:
        self._roots(tmp_path)
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "run.py").write_text("x = 1\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_writes_when_every_root_is_populated(self, tmp_path: Path) -> None:
        """The false-positive control. Multi-root by design, so a partial checkout
        cannot satisfy it and the guard cannot degrade into a blanket refusal."""
        self._roots(tmp_path, populated=tuple(sorted(cmp.REQUIRED_SKILLS_ROOTS)))
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 0
        assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {}

    def test_coverage_counts_files_read_not_offenders(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=tuple(sorted(cmp.REQUIRED_SKILLS_ROOTS)))
        assert cmp.scan_plugin_roots(tmp_path) == {}
        assert cmp.scanned_markdown_by_root(tmp_path) == {
            ".claude/skills": 2,
            "src/copilot-cli/skills": 2,
        }

    def test_coverage_reports_a_starved_root_as_zero(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=(".claude",))
        assert cmp.scanned_markdown_by_root(tmp_path) == {
            ".claude/skills": 2,
            "src/copilot-cli/skills": 0,
        }


class TestExecCheckerCoverage:
    def _roots(self, root: Path, populated: tuple[str, ...] = ()) -> None:
        for parts in cep.SCAN_ROOTS:
            skills = root.joinpath(*parts)
            skills.mkdir(parents=True, exist_ok=True)
            if "/".join(parts) not in populated:
                continue
            for slug in ("alpha", "beta"):
                (skills / slug).mkdir()
                (skills / slug / "SKILL.md").write_text("No bare invocations.\n", encoding="utf-8")

    def _run(self, root: Path, baseline: Path) -> int:
        return cep.main(
            ["--repo-root", str(root), "--baseline", str(baseline), "--update-baseline"]
        )

    def test_refuses_when_every_root_is_empty(self, tmp_path: Path) -> None:
        self._roots(tmp_path)
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_refuses_when_only_the_claude_root_is_populated(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=(".claude/skills",))
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_refuses_when_the_copilot_root_is_absent_entirely(self, tmp_path: Path) -> None:
        """A sparse checkout omits the directory rather than emptying it."""
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text("ok\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_partial_scan_leaves_a_populated_baseline_untouched(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=(".claude/skills",))
        baseline = tmp_path / "baseline.json"
        original = json.dumps({"files": {"keep/SKILL.md": 9}, "marker_files": {}})
        baseline.write_text(original, encoding="utf-8")
        assert self._run(tmp_path, baseline) == 2
        assert baseline.read_text(encoding="utf-8") == original

    def test_refuses_when_skill_dir_lacks_a_skill_file(self, tmp_path: Path) -> None:
        """A directory without SKILL.md yields no readable files."""
        self._roots(tmp_path)
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "notes.md").write_text(
            "python3 scripts/x.py\n", encoding="utf-8"
        )
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_writes_when_every_root_is_populated(self, tmp_path: Path) -> None:
        """The false-positive control, built multi-root so it stays distinct."""
        self._roots(tmp_path, populated=tuple("/".join(p) for p in cep.SCAN_ROOTS))
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 0
        assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {}

    def test_coverage_counts_files_read_not_offenders(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=tuple("/".join(p) for p in cep.SCAN_ROOTS))
        assert cep.scan_skill_execs(tmp_path) == {}
        assert cep.scanned_files_by_root(tmp_path) == {
            ".claude/skills": 2,
            "src/copilot-cli/skills": 2,
        }

    def test_coverage_reports_an_absent_root_as_zero(self, tmp_path: Path) -> None:
        self._roots(tmp_path, populated=(".claude/skills",))
        assert cep.scanned_files_by_root(tmp_path)["src/copilot-cli/skills"] == 0
