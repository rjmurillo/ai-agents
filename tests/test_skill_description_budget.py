"""Tests for scripts/skill_description_budget.py (issue #2794)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

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


def test_extract_frontmatter_parses_closing_fence_at_end_of_file():
    assert budget.extract_frontmatter("---\nname: foo\ndescription: bar\n---") == {
        "name": "foo",
        "description": "bar",
    }


def test_extract_frontmatter_parses_crlf_fences():
    text = "---\r\nname: foo\r\ndescription: bar\r\n---\r\n# body\r\n"
    assert budget.extract_frontmatter(text) == {"name": "foo", "description": "bar"}


def test_extract_frontmatter_parses_padded_closing_fence():
    assert budget.extract_frontmatter("---\nname: foo\n   ---\n# body\n") == {"name": "foo"}


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
    assert payload["skills"] >= 1
    assert payload["total_chars"] > 0


# --- budget file mode (issue #5762) -------------------------------------------

_REPO = Path(__file__).resolve().parents[1]
_ROOT_CLAUDE = ".claude/skills"
_ROOT_COPILOT = "src/copilot-cli/skills"


def _budget_repo(tmp_path: Path, monkeypatch, limits: dict[str, int]) -> Path:
    """Fake repo root with one 10-char skill in each root, plus a budget file."""
    monkeypatch.setattr(budget, "_REPO_ROOT", tmp_path)
    for root in limits:
        _write_skill(tmp_path / root, "alpha", "x" * 10)
    path = tmp_path / "budget.json"
    path.write_text(
        json.dumps({"roots": {r: {"max_total_chars": n} for r, n in limits.items()}}),
        encoding="utf-8",
    )
    return path


def test_budget_file_within_budget_for_every_root(tmp_path, monkeypatch, capsys):
    path = _budget_repo(tmp_path, monkeypatch, {_ROOT_CLAUDE: 10, _ROOT_COPILOT: 10})

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_OK
    out = capsys.readouterr().out
    assert f"[OK] {_ROOT_CLAUDE}" in out
    assert f"[OK] {_ROOT_COPILOT}" in out


def test_budget_file_over_budget_in_claude_root_fails(tmp_path, monkeypatch, capsys):
    path = _budget_repo(tmp_path, monkeypatch, {_ROOT_CLAUDE: 9, _ROOT_COPILOT: 10})

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_OVER_BUDGET
    err = capsys.readouterr().err
    assert f"[OVER BUDGET] {_ROOT_CLAUDE}" in err
    assert "budget 9 chars" in err
    assert "over by 1 chars" in err
    assert "alpha" in err


def test_copilot_only_description_growth_cannot_bypass_the_gate(tmp_path, monkeypatch, capsys):
    """A description added only to the Copilot tree must fail the Copilot root."""
    path = _budget_repo(tmp_path, monkeypatch, {_ROOT_CLAUDE: 10, _ROOT_COPILOT: 10})
    _write_skill(tmp_path / _ROOT_COPILOT, "beta", "y" * 5)

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_OVER_BUDGET
    captured = capsys.readouterr()
    assert f"[OK] {_ROOT_CLAUDE}" in captured.out
    assert f"[OVER BUDGET] {_ROOT_COPILOT}" in captured.err
    assert "beta" in captured.err


def test_budget_file_reports_every_failing_root(tmp_path, monkeypatch, capsys):
    path = _budget_repo(tmp_path, monkeypatch, {_ROOT_CLAUDE: 1, _ROOT_COPILOT: 1})

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_OVER_BUDGET
    err = capsys.readouterr().err
    assert _ROOT_CLAUDE in err
    assert _ROOT_COPILOT in err


def test_budget_file_missing_root_is_config_error(tmp_path, monkeypatch, capsys):
    path = _budget_repo(tmp_path, monkeypatch, {_ROOT_CLAUDE: 10})
    path.write_text(
        json.dumps({"roots": {_ROOT_COPILOT: {"max_total_chars": 10}}}), encoding="utf-8"
    )

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_CONFIG
    assert "is not a directory" in capsys.readouterr().err


def test_budget_file_unreadable_is_config_error(tmp_path, capsys):
    assert budget.main(["--budget-file", str(tmp_path / "nope.json")]) == budget.EXIT_CONFIG
    assert "cannot read budget file" in capsys.readouterr().err


def test_budget_file_invalid_json_is_config_error(tmp_path, capsys):
    path = tmp_path / "budget.json"
    path.write_text("{not json", encoding="utf-8")

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_CONFIG


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"roots": {}},
        {"roots": {"a": 5}},
        {"roots": {"a": {}}},
        {"roots": {"a": {"max_total_chars": "10"}}},
        {"roots": {"a": {"max_total_chars": True}}},
        {"roots": {"a": {"max_total_chars": 0}}},
    ],
)
def test_budget_file_invalid_shape_is_config_error(tmp_path, capsys, payload):
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_CONFIG
    assert "error:" in capsys.readouterr().err


def test_budget_file_negative_top_is_config_error(tmp_path, monkeypatch, capsys):
    path = _budget_repo(tmp_path, monkeypatch, {_ROOT_CLAUDE: 10})

    assert budget.main(["--budget-file", str(path), "--top", "-1"]) == budget.EXIT_CONFIG


def test_repository_budget_file_passes_on_the_live_tree(capsys):
    """The checked-in budgets must cover both shipped roots as they stand."""
    code = budget.main(["--budget-file", str(_REPO / "scripts" / "skill_description_budget.json")])

    assert code == budget.EXIT_OK, capsys.readouterr().err
    budgets = budget.load_root_budgets(_REPO / "scripts" / "skill_description_budget.json")
    assert set(budgets) == {_ROOT_CLAUDE, _ROOT_COPILOT}


def test_workflow_blocks_and_covers_both_roots():
    text = (_REPO / ".github" / "workflows" / "skill-passive-compliance.yml").read_text(
        encoding="utf-8"
    )
    step = text.split("- name: Run skill description budget", 1)[1].split("- name:", 1)[0]

    assert "continue-on-error" not in step
    assert "--budget-file scripts/skill_description_budget.json" in step
    for glob in (
        "'.claude/skills/**/SKILL.md'",
        "'src/copilot-cli/skills/**/SKILL.md'",
        "'scripts/skill_description_budget.json'",
    ):
        assert glob in text


def test_budget_file_root_without_described_skills_is_config_error(tmp_path, monkeypatch, capsys):
    path = _budget_repo(tmp_path, monkeypatch, {_ROOT_CLAUDE: 10})
    _write_skill(tmp_path / _ROOT_COPILOT, "bare", None)
    path.write_text(
        json.dumps({"roots": {_ROOT_COPILOT: {"max_total_chars": 10}}}), encoding="utf-8"
    )

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_CONFIG
    assert "has no skills with a description" in capsys.readouterr().err


def test_budget_file_json_output_lists_every_root(tmp_path, monkeypatch, capsys):
    path = _budget_repo(tmp_path, monkeypatch, {_ROOT_CLAUDE: 10, _ROOT_COPILOT: 5})

    code = budget.main(["--budget-file", str(path), "--output-format", "json"])

    assert code == budget.EXIT_OVER_BUDGET
    payload = json.loads(capsys.readouterr().out)
    by_root = {entry["root"]: entry for entry in payload}
    assert by_root[_ROOT_CLAUDE]["within_budget"] is True
    assert by_root[_ROOT_COPILOT]["within_budget"] is False
    assert by_root[_ROOT_COPILOT]["budget_chars"] == 5
    assert by_root[_ROOT_COPILOT]["total_chars"] == 10
    assert by_root[_ROOT_COPILOT]["budget_tokens_est"] == 2
