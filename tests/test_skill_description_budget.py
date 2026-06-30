"""Tests for scripts/skill_description_budget.py (issue #2794)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import skill_description_budget as budget  # noqa: E402


def _write_skill(root: Path, name: str, description: str | None, *, extra: str = "") -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm = ["---", f"name: {name}", "version: 1.0.0"]
    if description is not None:
        fm.append(f"description: {description}")
    fm.append("---")
    body = "\n".join(fm) + f"\n\n# {name}\n{extra}\n"
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


# --- estimate_tokens ---------------------------------------------------------


def test_estimate_tokens_rounds_up():
    assert budget.estimate_tokens(0) == 0
    assert budget.estimate_tokens(4) == 1
    assert budget.estimate_tokens(5) == 2  # ceil(5/4)
    assert budget.estimate_tokens(17109) == 4278  # ceil(17109/4)


# --- extract_frontmatter -----------------------------------------------------


def test_extract_frontmatter_parses_mapping():
    text = "---\nname: foo\ndescription: bar\n---\n# body\n"
    fm = budget.extract_frontmatter(text)
    assert fm == {"name": "foo", "description": "bar"}


def test_extract_frontmatter_none_when_no_fence():
    assert budget.extract_frontmatter("# just a heading\n") is None


def test_extract_frontmatter_none_when_unterminated():
    assert budget.extract_frontmatter("---\nname: foo\n# never closed\n") is None


def test_extract_frontmatter_none_on_malformed_yaml():
    assert budget.extract_frontmatter("---\n: : :\n bad\n---\n") is None


# --- measure_skill -----------------------------------------------------------


def test_measure_skill_counts_chars(tmp_path: Path):
    _write_skill(tmp_path, "alpha", "hello")  # 5 chars
    measured = budget.measure_skill(tmp_path / "alpha" / "SKILL.md")
    assert measured is not None
    assert measured.name == "alpha"
    assert measured.chars == 5
    assert measured.tokens == 2


def test_measure_skill_none_without_description(tmp_path: Path):
    _write_skill(tmp_path, "beta", None)
    assert budget.measure_skill(tmp_path / "beta" / "SKILL.md") is None


def test_measure_skill_falls_back_to_dir_name(tmp_path: Path):
    # name omitted from frontmatter -> use directory name.
    skill_dir = tmp_path / "gamma"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nversion: 1.0.0\ndescription: hi there\n---\n", encoding="utf-8"
    )
    measured = budget.measure_skill(skill_dir / "SKILL.md")
    assert measured is not None
    assert measured.name == "gamma"


# --- measure_corpus ----------------------------------------------------------


def test_measure_corpus_aggregates(tmp_path: Path):
    _write_skill(tmp_path, "alpha", "aaaa")  # 4
    _write_skill(tmp_path, "beta", "bbbbbbbb")  # 8
    _write_skill(tmp_path, "nodesc", None)
    report = budget.measure_corpus(tmp_path)
    assert report.count == 2
    assert report.skills_without_description == 1
    assert report.total_chars == 12
    assert report.total_tokens == 3


def test_top_orders_by_length_desc(tmp_path: Path):
    _write_skill(tmp_path, "small", "ab")
    _write_skill(tmp_path, "big", "abcdefghij")
    _write_skill(tmp_path, "mid", "abcde")
    report = budget.measure_corpus(tmp_path)
    assert [s.name for s in report.top(2)] == ["big", "mid"]


# --- renderers ---------------------------------------------------------------


def test_to_json_shape(tmp_path: Path):
    _write_skill(tmp_path, "alpha", "aaaa")
    payload = budget.to_json(budget.measure_corpus(tmp_path), top=5)
    assert payload["skills"] == 1
    assert payload["total_chars"] == 4
    assert payload["total_tokens_est"] == 1
    assert payload["top"][0]["name"] == "alpha"


def test_to_human_has_totals(tmp_path: Path):
    _write_skill(tmp_path, "alpha", "aaaa")
    text = budget.to_human(budget.measure_corpus(tmp_path), top=5)
    assert "Skill description budget" in text
    assert "alpha" in text


# --- CLI / budget gate -------------------------------------------------------


def test_main_bad_root_exits_config(tmp_path: Path, capsys):
    code = budget.main(["--root", str(tmp_path / "missing")])
    assert code == budget.EXIT_CONFIG
    assert "not a directory" in capsys.readouterr().err


def test_main_no_skills_exits_config(tmp_path: Path, capsys):
    code = budget.main(["--root", str(tmp_path)])
    assert code == budget.EXIT_CONFIG
    assert "no skills" in capsys.readouterr().err


def test_main_negative_top_exits_config(tmp_path: Path, capsys):
    _write_skill(tmp_path, "alpha", "aaaa")
    code = budget.main(["--root", str(tmp_path), "--top", "-1"])
    assert code == budget.EXIT_CONFIG


def test_main_within_budget_ok(tmp_path: Path, capsys):
    _write_skill(tmp_path, "alpha", "aaaa")  # 4 chars
    code = budget.main(["--root", str(tmp_path), "--max-total-chars", "100"])
    assert code == budget.EXIT_OK


def test_main_over_char_budget_exits_one(tmp_path: Path, capsys):
    _write_skill(tmp_path, "alpha", "a" * 50)
    code = budget.main(["--root", str(tmp_path), "--max-total-chars", "10"])
    assert code == budget.EXIT_OVER_BUDGET
    assert "OVER BUDGET" in capsys.readouterr().err


def test_main_over_token_budget_exits_one(tmp_path: Path, capsys):
    _write_skill(tmp_path, "alpha", "a" * 40)  # ~10 tokens
    code = budget.main(["--root", str(tmp_path), "--max-total-tokens", "5"])
    assert code == budget.EXIT_OVER_BUDGET


def test_main_json_output_ok(tmp_path: Path, capsys):
    _write_skill(tmp_path, "alpha", "aaaa")
    code = budget.main(["--root", str(tmp_path), "--output-format", "json"])
    assert code == budget.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["skills"] == 1


def test_main_runs_on_real_corpus(capsys):
    """The instrument must run on the live .claude/skills corpus."""
    real = Path(__file__).resolve().parents[1] / ".claude" / "skills"
    code = budget.main(["--root", str(real), "--output-format", "json"])
    assert code == budget.EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["skills"] > 40
    assert payload["total_chars"] > 0
