"""Both portability ratchets must refuse a baseline written from an empty scan.

The hazard is shared, so the tests live together rather than split across the
two checkers' own modules. A scan root can exist and still yield nothing to
read: a partial checkout, a sparse clone, a mistargeted repo root. The
offending-file mapping is empty in that case and equally empty for a genuinely
clean tree, so counts alone cannot separate them. Writing anyway replaces the
ratchet with an empty one, forgives every current violation, and exits 0.

Each checker is covered for the refusal itself, for leaving an existing
baseline untouched, for a root that holds files the scanner does not read, and
for the false-positive case that a clean tree still writes. That last one is
what keeps the guard from being a blanket refusal.
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
from scripts.validation.portability_common import refuse_empty_scan  # noqa: E402


class TestRefuseEmptyScanHelper:
    """The shared decision, tested directly rather than only through callers."""

    def test_zero_read_total_refuses(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        assert refuse_empty_scan(tmp_path, 0, "skill files") is True
        assert "read 0 skill files" in capsys.readouterr().err

    def test_positive_read_total_permits(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        assert refuse_empty_scan(tmp_path, 1, "skill files") is False
        assert capsys.readouterr().err == ""

    def test_refusal_names_the_root_it_scanned(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """The operator needs to see which root came back empty to fix the cause."""
        refuse_empty_scan(tmp_path, 0, "skill .md files")
        assert str(tmp_path) in capsys.readouterr().err


class TestMarkdownCheckerRefusal:
    def _required_roots(self, root: Path) -> None:
        for name in cmp.REQUIRED_SKILLS_ROOTS:
            (root / name / "skills").mkdir(parents=True, exist_ok=True)

    def _run(self, root: Path, baseline: Path) -> int:
        return cmp.main(
            ["--repo-root", str(root), "--baseline", str(baseline), "--update-baseline"]
        )

    def test_refuses_when_roots_present_but_empty(self, tmp_path: Path) -> None:
        self._required_roots(tmp_path)
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_refusal_leaves_an_existing_baseline_untouched(self, tmp_path: Path) -> None:
        self._required_roots(tmp_path)
        baseline = tmp_path / "baseline.json"
        original = json.dumps({"files": {"a/SKILL.md": 3}, "marker_files": {"b/SKILL.md": 1}})
        baseline.write_text(original, encoding="utf-8")
        assert self._run(tmp_path, baseline) == 2
        assert baseline.read_text(encoding="utf-8") == original

    def test_refuses_when_roots_hold_only_non_markdown(self, tmp_path: Path) -> None:
        self._required_roots(tmp_path)
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "run.py").write_text("x = 1\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_writes_when_a_single_clean_markdown_file_is_read(self, tmp_path: Path) -> None:
        """A clean repository must still write, or the guard is a false positive."""
        self._required_roots(tmp_path)
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "No upstream references here.\n", encoding="utf-8"
        )
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 0
        assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {}

    def test_read_total_counts_files_read_not_offenders(self, tmp_path: Path) -> None:
        self._required_roots(tmp_path)
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "SKILL.md").write_text(
            "Nothing upstream.\n", encoding="utf-8"
        )
        assert cmp.scan_plugin_roots(tmp_path) == {}
        assert cmp.scanned_markdown_total(tmp_path) == 1


class TestExecCheckerRefusal:
    def _run(self, root: Path, baseline: Path) -> int:
        return cep.main(
            ["--repo-root", str(root), "--baseline", str(baseline), "--update-baseline"]
        )

    def test_refuses_when_scan_root_present_but_empty(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_refusal_leaves_an_existing_baseline_untouched(self, tmp_path: Path) -> None:
        (tmp_path / ".claude" / "skills").mkdir(parents=True)
        baseline = tmp_path / "baseline.json"
        original = json.dumps({"files": {"keep/SKILL.md": 9}, "marker_files": {}})
        baseline.write_text(original, encoding="utf-8")
        assert self._run(tmp_path, baseline) == 2
        assert baseline.read_text(encoding="utf-8") == original

    def test_refuses_when_skill_dir_lacks_a_skill_file(self, tmp_path: Path) -> None:
        """A directory without SKILL.md yields no readable files."""
        (tmp_path / ".claude" / "skills" / "a").mkdir(parents=True)
        (tmp_path / ".claude" / "skills" / "a" / "notes.md").write_text(
            "python3 scripts/x.py\n", encoding="utf-8"
        )
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 2
        assert not baseline.exists()

    def test_writes_when_a_single_clean_skill_file_is_read(self, tmp_path: Path) -> None:
        """A clean repository must still write, or the guard is a false positive."""
        d = tmp_path / ".claude" / "skills" / "a"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("No bare invocations here.\n", encoding="utf-8")
        baseline = tmp_path / "baseline.json"
        assert self._run(tmp_path, baseline) == 0
        assert json.loads(baseline.read_text(encoding="utf-8"))["files"] == {}

    def test_read_total_counts_files_read_not_offenders(self, tmp_path: Path) -> None:
        d = tmp_path / ".claude" / "skills" / "a"
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text("No bare invocations here.\n", encoding="utf-8")
        assert cep.scan_skill_execs(tmp_path) == {}
        assert cep.scanned_file_total(tmp_path) == 1
