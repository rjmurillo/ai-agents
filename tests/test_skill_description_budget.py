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


def test_extract_frontmatter_parses_trailing_padded_closing_fence():
    assert budget.extract_frontmatter("---\nname: foo\n---   \n# body\n") == {"name": "foo"}


def test_extract_frontmatter_rejects_indented_closing_fence():
    # The shared fence rule (FM_BOUNDARY, ^-{3,}\\s*$) anchors at column 0.
    assert budget.extract_frontmatter("---\nname: foo\n   ---\n# body\n") is None


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
_ROOT_SRC_CLAUDE = "src/claude/skills"


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
    """The checked-in budgets must cover every shipped root as they stand."""
    code = budget.main(["--budget-file", str(_REPO / "scripts" / "skill_description_budget.json")])

    assert code == budget.EXIT_OK, capsys.readouterr().err
    budgets = budget.load_root_budgets(_REPO / "scripts" / "skill_description_budget.json")
    assert set(budgets) == {_ROOT_CLAUDE, _ROOT_SRC_CLAUDE, _ROOT_COPILOT}
    config = budget.load_budget_config(_REPO / "scripts" / "skill_description_budget.json")
    assert all(b.max_listing_chars is not None for b in config.roots.values())


def test_workflow_blocks_and_covers_both_roots():
    text = (_REPO / ".github" / "workflows" / "skill-passive-compliance.yml").read_text(
        encoding="utf-8"
    )
    step = text.split("- name: Run skill description budget", 1)[1].split("- name:", 1)[0]

    assert "continue-on-error" not in step
    assert "--budget-file scripts/skill_description_budget.json" in step
    for glob in (
        "'.claude/skills/**/SKILL.md'",
        "'src/claude/skills/**/SKILL.md'",
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


# --- listing chars and host fit (PR #7871) -------------------------------------


def _config_repo(tmp_path: Path, monkeypatch, root_entry: dict, hosts=None) -> Path:
    """Fake repo with one skill 'alpha' (10-char description) and a custom budget entry."""
    monkeypatch.setattr(budget, "_REPO_ROOT", tmp_path)
    _write_skill(tmp_path / _ROOT_CLAUDE, "alpha", "x" * 10)
    data: dict = {"roots": {_ROOT_CLAUDE: root_entry}}
    if hosts is not None:
        data["host_budgets"] = hosts
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _host(**overrides) -> dict:
    entry = {
        "host": "copilot-cli",
        "chars": 1000,
        "state": "INFERRED",
        "source": "test source",
        "date": "2026-11-28",
    }
    entry.update(overrides)
    return entry


_ALPHA_LISTING = 93 + len("alpha") + 10  # 108


def test_listing_chars_arithmetic(tmp_path: Path):
    _write_skill(tmp_path, "alpha", "x" * 10)
    _write_skill(tmp_path, "bb", "y" * 3)
    measured = budget.measure_skill(tmp_path / "alpha" / "SKILL.md")
    assert measured is not None
    assert measured.listing_chars == _ALPHA_LISTING
    assert budget.measure_corpus(tmp_path).listing_chars == _ALPHA_LISTING + 93 + 2 + 3


def test_listing_chars_skips_skills_without_description(tmp_path: Path):
    _write_skill(tmp_path, "alpha", "x" * 10)
    _write_skill(tmp_path, "nodesc", None)
    assert budget.measure_corpus(tmp_path).listing_chars == _ALPHA_LISTING


def test_listing_chars_uses_dir_name_when_name_missing(tmp_path: Path):
    skill_dir = tmp_path / "gamma"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\ndescription: hello\n---\n", encoding="utf-8")
    assert budget.measure_corpus(tmp_path).listing_chars == 93 + len("gamma") + 5


def test_listing_ceiling_exceeded_exits_one_and_names_root(tmp_path, monkeypatch, capsys):
    path = _config_repo(
        tmp_path, monkeypatch, {"max_total_chars": 10, "max_listing_chars": _ALPHA_LISTING - 1}
    )

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_OVER_BUDGET
    err = capsys.readouterr().err
    assert f"[OVER BUDGET] {_ROOT_CLAUDE}" in err
    assert "listing over ceiling by 1 chars" in err


def test_listing_ceiling_equal_passes(tmp_path, monkeypatch, capsys):
    path = _config_repo(
        tmp_path, monkeypatch, {"max_total_chars": 10, "max_listing_chars": _ALPHA_LISTING}
    )

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_OK
    out = capsys.readouterr().out
    assert f"listing: {_ALPHA_LISTING} chars, ceiling {_ALPHA_LISTING}" in out


def test_missing_listing_ceiling_still_works(tmp_path, monkeypatch, capsys):
    path = _config_repo(tmp_path, monkeypatch, {"max_total_chars": 10})

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_OK
    assert "ceiling none" in capsys.readouterr().out


def test_every_failing_listing_root_is_reported(tmp_path, monkeypatch, capsys):
    path = _budget_repo(tmp_path, monkeypatch, {_ROOT_CLAUDE: 10, _ROOT_COPILOT: 10})
    path.write_text(
        json.dumps(
            {
                "roots": {
                    _ROOT_CLAUDE: {"max_total_chars": 10, "max_listing_chars": 1},
                    _ROOT_COPILOT: {"max_total_chars": 10, "max_listing_chars": 1},
                }
            }
        ),
        encoding="utf-8",
    )

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_OVER_BUDGET
    err = capsys.readouterr().err
    assert f"[OVER BUDGET] {_ROOT_CLAUDE}" in err
    assert f"[OVER BUDGET] {_ROOT_COPILOT}" in err


@pytest.mark.parametrize("bad", [0, -5, True, "100", 1.5, None])
def test_invalid_listing_ceiling_is_config_error(tmp_path, monkeypatch, capsys, bad):
    path = _config_repo(tmp_path, monkeypatch, {"max_total_chars": 10, "max_listing_chars": bad})

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_CONFIG
    assert "max_listing_chars" in capsys.readouterr().err


@pytest.mark.parametrize(
    "hosts",
    [
        {"host": "x"},
        ["not an object"],
        [_host(host="")],
        [_host(host=5)],
        [_host(chars=0)],
        [_host(chars=True)],
        [_host(chars="15000")],
        [_host(state="")],
        [_host(source=" ")],
        [_host(date="28/11/2026")],
        [_host(date=20261128)],
        [{k: v for k, v in _host().items() if k != "source"}],
    ],
)
def test_bad_host_budgets_shape_is_config_error(tmp_path, monkeypatch, capsys, hosts):
    path = _config_repo(tmp_path, monkeypatch, {"max_total_chars": 10}, hosts)

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_CONFIG
    assert "host_budgets" in capsys.readouterr().err


def test_empty_host_budgets_list_is_accepted(tmp_path, monkeypatch, capsys):
    path = _config_repo(tmp_path, monkeypatch, {"max_total_chars": 10}, [])

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_OK
    assert "fit [" not in capsys.readouterr().out


def _fit_corpus(tmp_path: Path) -> budget.BudgetReport:
    # Listing sizes: a=93+1+10=104, b=93+1+200=294, c=93+1+10=104.
    _write_skill(tmp_path, "a", "x" * 10)
    _write_skill(tmp_path, "b", "y" * 200)
    _write_skill(tmp_path, "c", "z" * 10)
    return budget.measure_corpus(tmp_path)


def test_fit_count_exact_fit_boundary(tmp_path: Path):
    report = _fit_corpus(tmp_path)

    assert report.fit_count(104) == 1  # a lands exactly on the budget
    assert report.fit_count(103) == 0  # one char short of a
    assert report.fit_count(104 + 294) == 2  # a + b exact
    assert report.fit_count(104 + 294 + 104) == 3  # all three exact


def test_fit_count_stops_at_first_miss_and_skips_later_smaller_entries(tmp_path: Path):
    report = _fit_corpus(tmp_path)

    # a fits, b misses (104 + 294 > 400 - 1), c (104) would fit the remainder but is not counted.
    assert report.fit_count(104 + 294 - 1) == 1
    assert report.fit_count(104 + 294 + 103) == 2


def test_fit_count_orders_by_name_not_size(tmp_path: Path):
    _write_skill(tmp_path, "zeta", "x" * 5)
    _write_skill(tmp_path, "alpha", "x" * 400)
    report = budget.measure_corpus(tmp_path)

    # alpha (498) sorts first and misses, so tiny zeta is never counted.
    assert report.fit_count(300) == 0


def test_fit_count_zero_for_empty_corpus():
    assert budget.BudgetReport(skills=[], skills_without_description=0).fit_count(1000) == 0


def test_human_output_has_one_fit_line_per_host_budget(tmp_path, monkeypatch, capsys):
    hosts = [_host(chars=108), _host(chars=107, state="DISPUTED")]
    path = _config_repo(tmp_path, monkeypatch, {"max_total_chars": 10}, hosts)

    assert budget.main(["--budget-file", str(path)]) == budget.EXIT_OK
    out = capsys.readouterr().out
    assert "fit [INFERRED] copilot-cli 108: 1 of 1 skills keep a full entry" in out
    assert "fit [DISPUTED] copilot-cli 107: 0 of 1 skills keep a full entry" in out
    assert f"model: {budget.FIT_MODEL}" in out


def test_json_output_has_listing_and_host_fit_keys(tmp_path, monkeypatch, capsys):
    path = _config_repo(
        tmp_path,
        monkeypatch,
        {"max_total_chars": 10, "max_listing_chars": _ALPHA_LISTING},
        [_host(chars=_ALPHA_LISTING)],
    )

    assert budget.main(["--budget-file", str(path), "--output-format", "json"]) == budget.EXIT_OK
    (entry,) = json.loads(capsys.readouterr().out)
    assert entry["listing_chars"] == _ALPHA_LISTING
    assert entry["max_listing_chars"] == _ALPHA_LISTING
    assert entry["within_listing_ceiling"] is True
    assert entry["within_budget"] is True  # existing keys stay
    (fit,) = entry["host_fit"]
    assert fit["host"] == "copilot-cli"
    assert fit["fit_count"] == 1
    assert fit["skills"] == 1
    assert fit["state"] == "INFERRED"
    assert fit["source"] == "test source"
    assert fit["date"] == "2026-11-28"
    assert fit["fit_model"] == budget.FIT_MODEL


def test_json_output_without_ceiling_or_hosts(tmp_path, monkeypatch, capsys):
    path = _config_repo(tmp_path, monkeypatch, {"max_total_chars": 10})

    budget.main(["--budget-file", str(path), "--output-format", "json"])
    (entry,) = json.loads(capsys.readouterr().out)
    assert entry["max_listing_chars"] is None
    assert entry["within_listing_ceiling"] is True
    assert entry["host_fit"] == []


def test_json_reports_listing_ceiling_failure(tmp_path, monkeypatch, capsys):
    path = _config_repo(tmp_path, monkeypatch, {"max_total_chars": 10, "max_listing_chars": 1})

    code = budget.main(["--budget-file", str(path), "--output-format", "json"])
    (entry,) = json.loads(capsys.readouterr().out)
    assert code == budget.EXIT_OVER_BUDGET
    assert entry["within_listing_ceiling"] is False
    assert entry["within_budget"] is True


def test_live_roots_carry_host_budgets_with_state_and_source():
    config = budget.load_budget_config(_REPO / "scripts" / "skill_description_budget.json")

    assert {(h.host, h.chars, h.state) for h in config.host_budgets} == {
        ("copilot-cli", 15000, "INFERRED"),
        ("copilot-cli", 30000, "DISPUTED"),
    }
    assert all(h.source and h.date for h in config.host_budgets)


def test_budget_file_has_no_em_or_en_dashes():
    text = (_REPO / "scripts" / "skill_description_budget.json").read_text(encoding="utf-8")
    assert "\u2014" not in text
    assert "\u2013" not in text
