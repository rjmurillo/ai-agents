"""Tests for scripts/validation/check_skill_trigger_resolution.py.

Fixtures live in `trigger_resolution_fixtures`; config and resolver failures are in
`test_check_skill_trigger_resolution_config.py`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.validation import check_skill_trigger_resolution as gate
from tests.validation.trigger_resolution_fixtures import (
    _baseline,
    _run,
    _skill,
    _skills,
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    return tmp_path


REPO_ROOT = Path(__file__).resolve().parents[2]


class TestExtractPhrases:
    def test_double_quoted_and_backtick_segments(self) -> None:
        text = 'Use for "write an ADR" or `draft the spec` now.'
        assert gate.extract_phrases(text) == ["write an ADR", "draft the spec"]

    def test_drops_paths_commands_and_dotted_segments(self) -> None:
        text = 'Run `/spec now`, "see docs/x y", "open file.py today", "real two".'
        assert gate.extract_phrases(text) == ["real two"]

    def test_slash_prefix_dropped_even_when_two_words(self) -> None:
        assert gate.extract_phrases('"/plan this"') == []

    def test_drops_single_word_segments(self) -> None:
        assert gate.extract_phrases('"ship" and `review` and "ship it"') == ["ship it"]

    def test_punctuation_only_words_do_not_count(self) -> None:
        assert gate.extract_phrases('"--- ???" and "a b"') == ["a b"]

    def test_cuts_everything_after_first_do_not(self) -> None:
        text = 'Use for "write widget". Do NOT use for "review widget" or `fix widget`.'
        assert gate.extract_phrases(text) == ["write widget"]

    def test_do_not_cut_is_case_sensitive(self) -> None:
        text = 'Use for "write widget". Do not use for "review widget".'
        assert gate.extract_phrases(text) == ["write widget", "review widget"]

    def test_repeats_collapse_in_first_seen_order(self) -> None:
        assert gate.extract_phrases('"b c" `a b` "b c"') == ["b c", "a b"]

    def test_no_segments(self) -> None:
        assert gate.extract_phrases("plain text, no quotes") == []


class TestOwnPhrase:
    def test_own_phrase_routes_to_own_skill_passes(self, repo: Path) -> None:
        _skill(_skills(repo), "widget-maker", 'Use for "write a widget".', ["write widget"])
        assert _run(repo, _baseline(repo)) == gate.EXIT_OK

    def test_own_phrase_unrouted_fails(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _skill(_skills(repo), "widget-maker", 'Use for "frobnicate gadgets".', ["write widget"])
        assert _run(repo, _baseline(repo)) == gate.EXIT_VIOLATION
        out = capsys.readouterr().out
        assert f"{gate.CHECK_OWN}: widget-maker: 'frobnicate gadgets'" in out

    def test_skill_without_intents_never_fires_own(self, repo: Path) -> None:
        _skill(_skills(repo), "quiet", 'Use for "frobnicate gadgets".', role="specialist")
        assert _run(repo, _baseline(repo)) == gate.EXIT_OK

    def test_intents_on_non_front_door_role_are_not_own_checked(self, repo: Path) -> None:
        folder = _skills(repo) / "helper"
        folder.mkdir()
        (folder / "SKILL.md").write_text(
            "---\nname: helper\ndescription: 'Use for \"frobnicate gadgets\".'\n"
            "metadata:\n  routing:\n    role: internal\n    intents:\n      - other thing\n---\n",
            encoding="utf-8",
        )
        assert _run(repo, _baseline(repo)) == gate.EXIT_OK


class TestSibling:
    def test_phrase_routing_to_another_skill_fires_sibling(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _skill(_skills(repo), "widget-maker", "Makes widgets.", ["write widget"])
        _skill(_skills(repo), "no-intents", 'Use for "write a widget".')
        assert _run(repo, _baseline(repo)) == gate.EXIT_VIOLATION
        out = capsys.readouterr().out
        assert f"{gate.CHECK_SIBLING}: no-intents: 'write a widget'" in out
        assert gate.CHECK_OWN not in out

    def test_skill_with_intents_hitting_sibling_fires_both_checks(self, repo: Path) -> None:
        skills = _skills(repo)
        _skill(skills, "widget-maker", "Makes widgets.", ["write widget"])
        _skill(skills, "gadget-maker", 'Use for "write a widget".', ["build gadget"])
        found = gate.find_violations(gate.load_skills(skills), skills)
        assert found == {
            (gate.CHECK_OWN, "gadget-maker", "write a widget"),
            (gate.CHECK_SIBLING, "gadget-maker", "write a widget"),
        }

    def test_do_not_clause_phrase_is_not_checked(self, repo: Path) -> None:
        skills = _skills(repo)
        _skill(skills, "widget-maker", 'Makes widgets. Use for "write widget".', ["write widget"])
        _skill(skills, "other", 'Use for things. Do NOT use for "write a widget".')
        assert _run(repo, _baseline(repo)) == gate.EXIT_OK


class TestBaseline:
    def test_baselined_violation_passes(self, repo: Path) -> None:
        _skill(_skills(repo), "w", 'Use for "frobnicate gadgets".', ["write widget"])
        baseline = _baseline(repo, own={"w": ["frobnicate gadgets"]})
        assert _run(repo, baseline) == gate.EXIT_OK

    def test_violation_outside_baseline_fails(self, repo: Path) -> None:
        _skill(_skills(repo), "w", 'Use for "frobnicate gadgets".', ["write widget"])
        baseline = _baseline(repo, own={"w": ["some other phrase"]})
        assert _run(repo, baseline) == gate.EXIT_VIOLATION

    def test_stale_entry_is_reported_and_passes(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _skill(_skills(repo), "w", 'Use for "write a widget".', ["write widget"])
        baseline = _baseline(repo, own={"w": ["gone phrase"]})
        assert _run(repo, baseline) == gate.EXIT_OK
        out = capsys.readouterr().out
        assert "no longer fires" in out
        assert "'gone phrase'" in out
        assert "stale=1" in out

    def test_write_baseline_round_trips_and_is_byte_stable(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(repo)
        _skill(_skills(repo), "w", 'Use for "frobnicate gadgets" and "zap it".', ["write widget"])
        path = repo / "out.json"
        assert _run(repo, path, "--write-baseline") == gate.EXIT_OK
        first = path.read_bytes()
        assert gate.read_baseline(path) == {
            (gate.CHECK_OWN, "w", "frobnicate gadgets"),
            (gate.CHECK_OWN, "w", "zap it"),
        }
        assert _run(repo, path) == gate.EXIT_OK
        assert _run(repo, path, "--write-baseline") == gate.EXIT_OK
        assert path.read_bytes() == first
        assert not path.with_name("out.json.tmp").exists()


class TestRealTree:
    def test_real_tree_exits_0(self) -> None:
        assert gate.main([]) == gate.EXIT_OK

    def test_adapter_returns_true_on_real_tree(self) -> None:
        assert gate.validate_skill_trigger_resolution(REPO_ROOT) is True

    def test_adapter_returns_false_on_config_error(self, tmp_path: Path) -> None:
        assert gate.validate_skill_trigger_resolution(tmp_path) is False

    def test_adr_generator_phrases_all_route(self) -> None:
        skills = REPO_ROOT / gate.SKILLS_SUBDIR
        found = gate.find_violations(gate.load_skills(skills), skills)
        assert [i for i in found if i[1] == "adr-generator"] == []
        assert not any(
            i[1] == "adr-generator" for i in gate.read_baseline(REPO_ROOT / gate.BASELINE_RELATIVE)
        )


class TestFrontDoorWithoutIntents:
    """The 2026-11-19 adr-generator miss: phrases advertised, no intents declared."""

    def test_front_door_phrases_without_intents_fail_naming_every_phrase(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _skill(_skills(repo), "adr-maker", 'Use when you say "write an ADR" or "draft an ADR".')
        assert _run(repo, _baseline(repo)) == gate.EXIT_VIOLATION
        out = capsys.readouterr().out
        assert f"{gate.CHECK_NO_INTENTS}: adr-maker: 'write an ADR'" in out
        assert f"{gate.CHECK_NO_INTENTS}: adr-maker: 'draft an ADR'" in out

    def test_a_baselined_skill_cannot_add_an_unroutable_phrase(
        self, repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(repo)
        skills = _skills(repo)
        _skill(skills, "adr-maker", 'Use when you say "write an ADR".')
        baseline = _baseline(repo)
        assert _run(repo, baseline, "--write-baseline") == gate.EXIT_OK
        shutil.rmtree(skills / "adr-maker")
        _skill(skills, "adr-maker", 'Use when you say "write an ADR" or "implement it today".')

        assert _run(repo, baseline) == gate.EXIT_VIOLATION
        assert (
            f"{gate.CHECK_NO_INTENTS}: adr-maker: 'implement it today'" in capsys.readouterr().out
        )

    def test_declaring_intents_clears_it(self, repo: Path) -> None:
        _skill(
            _skills(repo),
            "adr-maker",
            'Use when you say "write an ADR".',
            intents=["write adr"],
        )
        assert _run(repo, _baseline(repo)) == gate.EXIT_OK

    def test_front_door_without_phrases_passes(self, repo: Path) -> None:
        skills = _skills(repo)
        _skill(skills, "plain", "Creates widgets. Use when widgets are needed.")
        _skill(skills, "w", 'Use for "write widget".', ["write widget"])
        assert _run(repo, _baseline(repo)) == gate.EXIT_OK

    def test_non_front_door_without_intents_passes(self, repo: Path) -> None:
        _skill(_skills(repo), "helper", 'Use for "write an ADR".', role="specialist")
        assert _run(repo, _baseline(repo)) == gate.EXIT_OK

    def test_baselined_entry_passes(self, repo: Path) -> None:
        _skill(_skills(repo), "adr-maker", 'Use when you say "write an ADR".')
        baseline = _baseline(repo, no_intents={"adr-maker": ["write an ADR"]})
        assert _run(repo, baseline) == gate.EXIT_OK

    def test_baseline_missing_the_check_is_config_error(self, repo: Path) -> None:
        _skill(_skills(repo), "plain", "No phrases here.")
        path = repo / "baseline.json"
        payload = {
            "schema_version": "1",
            "violations": {gate.CHECK_OWN: {}, gate.CHECK_SIBLING: {}},
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert _run(repo, path) == gate.EXIT_CONFIG


class TestWriteBaselineWorktreeIdentity:
    """ci-scripts MUST 7: no write into the resolved root from outside it."""

    def test_refuses_default_baseline_write_from_outside_root(
        self, repo: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _skill(_skills(repo), "plain", "No phrases here.")
        monkeypatch.chdir(tmp_path_factory.mktemp("elsewhere"))
        rc = gate.main(["--repo-root", str(repo), "--write-baseline"])
        assert rc == gate.EXIT_CONFIG
        assert not (repo / gate.BASELINE_RELATIVE).exists()

    def test_writes_default_baseline_from_inside_root(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _skill(_skills(repo), "plain", 'Use for "frobnicate gadgets".', ["write widget"])
        (repo / gate.BASELINE_RELATIVE).parent.mkdir(parents=True)
        monkeypatch.chdir(repo)
        assert gate.main(["--repo-root", str(repo), "--write-baseline"]) == gate.EXIT_OK
        assert (repo / gate.BASELINE_RELATIVE).is_file()


class TestExaminedCount:
    def test_summary_line_reports_what_was_examined(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        skills = _skills(repo)
        _skill(skills, "w", 'Use for "write widget" or "make a widget".', ["write widget"])
        _skill(skills, "plain", "Creates widgets.")
        baseline = _baseline(repo, sibling={}, own={})

        _run(repo, baseline)
        out = capsys.readouterr().out

        assert "examined skills=2 phrases=2 " in out

    def test_zero_phrases_exits_config_not_ok(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _skill(_skills(repo), "plain", "Creates widgets. No quoted phrases.")

        rc = _run(repo, _baseline(repo))
        captured = capsys.readouterr()

        assert rc == gate.EXIT_CONFIG
        assert "0 trigger phrases" in captured.err
        assert "violations=" not in captured.out

    def test_zero_phrases_after_do_not_cut_exits_config(self, repo: Path) -> None:
        _skill(_skills(repo), "other", 'Use for things. Do NOT use for "write a widget".')

        assert _run(repo, _baseline(repo)) == gate.EXIT_CONFIG

    def test_zero_skills_exits_config(self, repo: Path) -> None:
        assert _run(repo, _baseline(repo)) == gate.EXIT_CONFIG

    def test_new_violation_line_names_the_skill_md_path(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _skill(_skills(repo), "w", 'Use for "frobnicate gadgets".', ["write widget"])

        rc = _run(repo, _baseline(repo))
        out = capsys.readouterr().out

        assert rc == gate.EXIT_VIOLATION
        fail_lines = [line for line in out.splitlines() if line.startswith("[FAIL] new violation")]
        assert fail_lines
        assert all(str(_skills(repo) / "w" / "SKILL.md") in line for line in fail_lines)
        assert "examined skills=1 phrases=1 " in out


class TestAutoplanCatalog:
    """Phrases resolve against the shipped tree autoplan reads, not the install tree."""

    def test_a_repo_local_phrase_autoplan_cannot_reach_is_flagged(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        shipped = repo / "src" / "claude" / "skills"
        shipped.mkdir(parents=True)
        _skill(shipped, "build", 'Use for "build the widget".', ["build widget"])
        installed = _skills(repo)
        _skill(installed, "build", 'Use for "build the widget".', ["build widget"])
        _skill(installed, "local-only", 'Use for "prove the widget".', ["prove widget"])

        assert _run(repo, _baseline(repo)) == gate.EXIT_VIOLATION
        assert f"{gate.CHECK_OWN}: local-only: 'prove the widget'" in capsys.readouterr().out
