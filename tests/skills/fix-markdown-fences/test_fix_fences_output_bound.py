"""Text output of fix_fences.py is bounded by --max-lines; the total is not."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/fix-markdown-fences/scripts/fix_fences.py")
main = mod.main

DEFECTIVE = "```py\nx\n```py\ny\n```\n"


@pytest.fixture
def three_defective_files(tmp_path: Path) -> Path:
    for index in range(3):
        (tmp_path / f"d{index}.md").write_text(DEFECTIVE, encoding="utf-8")
    return tmp_path


class TestMaxLines:
    def test_cuts_the_listing_names_the_rest_and_keeps_the_exit_code(
        self, three_defective_files: Path, capsys
    ) -> None:
        rc = main([str(three_defective_files), "--max-lines", "1"])

        out = capsys.readouterr().out
        assert rc == 1
        assert "more defect line(s) not shown" in out
        assert "3 defect(s) in 3 file(s)" in out
        assert out.count(": ") >= 1

    def test_zero_lists_every_defect(self, three_defective_files: Path, capsys) -> None:
        main([str(three_defective_files), "--max-lines", "0"])

        out = capsys.readouterr().out
        assert "not shown" not in out
        assert out.count(".md:") == 3

    def test_default_leaves_a_small_report_whole(self, three_defective_files: Path, capsys) -> None:
        main([str(three_defective_files)])

        assert "not shown" not in capsys.readouterr().out

    def test_json_is_never_cut(self, three_defective_files: Path, capsys) -> None:
        main([str(three_defective_files), "--json", "--max-lines", "1"])

        payload = json.loads(capsys.readouterr().out)
        assert payload["defect_count"] == 3
        assert len(payload["files"]) == 3

    def test_negative_value_is_a_usage_error(self, tmp_path: Path, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            main([str(tmp_path), "--max-lines", "-1"])

        assert exc.value.code == 2
        assert "--max-lines must be 0 or greater, got -1" in capsys.readouterr().err


class TestRefusalLinesAreBounded:
    @staticmethod
    def _refuse_everything(monkeypatch) -> None:
        monkeypatch.setattr(mod, "refusal_reason", lambda *args, **kwargs: "forced refusal")

    def test_refusals_are_cut_at_the_limit_and_the_rest_is_counted(
        self, three_defective_files: Path, capsys, monkeypatch
    ) -> None:
        self._refuse_everything(monkeypatch)

        rc = main([str(three_defective_files), "--write", "--max-lines", "1"])

        out = capsys.readouterr().out
        assert rc == 1
        assert out.count("Refused ") == 1
        assert "2 more refusal(s) not shown" in out

    def test_zero_lists_every_refusal(
        self, three_defective_files: Path, capsys, monkeypatch
    ) -> None:
        self._refuse_everything(monkeypatch)

        main([str(three_defective_files), "--write", "--max-lines", "0"])

        out = capsys.readouterr().out
        assert out.count("Refused ") == 3
        assert "not shown" not in out
