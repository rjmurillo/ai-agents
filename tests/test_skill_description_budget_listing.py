"""Listing chars, ceilings, and host fit for scripts/skill_description_budget.py (PR #7871)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import skill_description_budget as budget  # noqa: E402

from tests.test_skill_description_budget import (  # noqa: E402
    _REPO,
    _ROOT_CLAUDE,
    _ROOT_COPILOT,
    _budget_repo,
    _write_skill,
)

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
    assert "listing over ceiling by 1 chars; largest entries:" in err
    assert f"{_ALPHA_LISTING:>5} chars  alpha" in err


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
