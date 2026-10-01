"""CLI, report shape, ratchet, and rendering for instruction_bytes (issue #5400)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import instruction_bytes as ib
from scripts.validation.instruction_budget_constants import FIXTURE_CEILINGS_BYTES
from scripts.validation.instruction_bytes_report import format_table
from scripts.validation.instruction_bytes_types import SizedFile, summarize, top_contributors
from tests.validation._instruction_bytes_helpers import (
    FIXTURE,
    add_skill,
    build_repo,
    commit_all,
    git,
    init_git,
    write,
)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    build_repo(tmp_path)
    monkeypatch.setattr(ib, "FIXTURES", (FIXTURE,))
    monkeypatch.setattr(ib, "FIXTURE_CEILINGS_BYTES", {"T1": 1_000_000})
    return tmp_path


def _json(root: Path, *extra: str, capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    assert ib.main(["--path", str(root), "--format", "json", *extra]) == 0
    return json.loads(capsys.readouterr().out)


class TestReportShape:
    def test_reports_canonical_generated_always_on_and_fixtures(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report = _json(repo, capsys=capsys)
        assert set(report) >= {"canonical", "generated", "always_on", "fixtures", "estimator"}
        assert set(report["always_on"]) == {"claude_code", "copilot", "codex"}
        assert report["fixtures"]["T1"]["artifacts"] > 0

    def test_generated_mirrors_are_reported_apart_from_canonical(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report = _json(repo, capsys=capsys)
        assert "src/copilot-cli" in report["generated"]["families"]
        assert "src/copilot-cli" not in report["canonical"]["groups"]
        assert "excluded from canonical totals" in report["generated"]["note"]
        assert not any(p.startswith("src/") for p in report["canonical"]["paths"])

    def test_growing_a_mirror_leaves_canonical_totals_unchanged(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        before = _json(repo, capsys=capsys)
        write(repo, "src/copilot-cli/skills/alpha/SKILL.md", "x" * 50_000)
        after = _json(repo, capsys=capsys)
        assert after["canonical"]["total"] == before["canonical"]["total"]
        assert after["generated"]["total"]["bytes"] > before["generated"]["total"]["bytes"]

    def test_top_contributors_are_sorted_and_bounded(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        report = _json(repo, "--top", "2", capsys=capsys)
        rows = report["canonical"]["top_contributors"]
        assert len(rows) == 2
        assert rows[0]["bytes"] >= rows[1]["bytes"]
        assert len(report["fixtures"]["T1"]["top_contributors"]) == 2

    def test_fixture_bytes_split_by_source_and_sum_to_the_total(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry = _json(repo, capsys=capsys)["fixtures"]["T1"]
        assert sum(entry["bytes_by_source"].values()) == entry["bytes"]
        assert entry["bytes_by_source"]["dependency"] > 0

    def test_output_is_deterministic(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert _json(repo, capsys=capsys) == _json(repo, capsys=capsys)

    def test_table_output_names_each_section(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert ib.main(["--path", str(repo)]) == 0
        out = capsys.readouterr().out
        for heading in (
            "Canonical authored corpus",
            "Generated projections (excluded from authored totals)",
            "Always-on (all tasks)",
            "Fixtures (Claude Code load path)",
            "Top canonical contributors",
            "Estimator: scripts.validation.token_budget.estimate_token_count",
        ):
            assert heading in out


class TestReductionsAppearAutomatically:
    def test_shrinking_a_skill_lowers_every_fixture_that_loads_it(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        before = _json(repo, capsys=capsys)["fixtures"]["T1"]["bytes"]
        write(repo, ".claude/skills/gamma/SKILL.md", "---\nname: g\n---\n")
        after = _json(repo, capsys=capsys)["fixtures"]["T1"]["bytes"]
        assert after < before


class TestCeilingRatchet:
    def test_over_ceiling_fails_in_ci_mode(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(ib, "FIXTURE_CEILINGS_BYTES", {"T1": 10})
        assert ib.main(["--path", str(repo), "--ci"]) == 1
        assert "FAIL: fixture ceiling exceeded" in capsys.readouterr().out

    def test_over_ceiling_only_reports_outside_ci_mode(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(ib, "FIXTURE_CEILINGS_BYTES", {"T1": 10})
        monkeypatch.delenv("CI", raising=False)
        assert ib.main(["--path", str(repo)]) == 0
        assert "T1: " in capsys.readouterr().out

    def test_within_ceiling_passes_in_ci_mode(self, repo: Path) -> None:
        assert ib.main(["--path", str(repo), "--ci"]) == 0

    def test_fixture_breaches_treats_the_ceiling_as_inclusive(self) -> None:
        report = {
            "fixtures": {
                "A": {"bytes": 10, "ceiling_bytes": 10},
                "B": {"bytes": 11, "ceiling_bytes": 10},
            }
        }
        assert ib.fixture_breaches(report) == ["B: 11 bytes exceeds ceiling 10"]

    def test_fixture_breaches_skips_a_fixture_with_no_ceiling(self) -> None:
        assert ib.fixture_breaches({"fixtures": {"A": {"bytes": 99, "ceiling_bytes": None}}}) == []

    def test_fixture_breaches_skips_an_errored_fixture(self) -> None:
        assert ib.fixture_breaches({"fixtures": {"A": {"name": "n", "error": "x"}}}) == []

    def test_every_shipped_fixture_has_a_ceiling_and_no_orphans(self) -> None:
        assert set(FIXTURE_CEILINGS_BYTES) == {f.fixture_id for f in ib.FIXTURES}
        assert all(v > 0 for v in FIXTURE_CEILINGS_BYTES.values())

    def test_a_ceiling_appears_in_the_report_for_its_fixture(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert _json(repo, capsys=capsys)["fixtures"]["T1"]["ceiling_bytes"] == 1_000_000


class TestBaseRefDelta:
    def _commit_base(self, root: Path) -> str:
        init_git(root)
        return commit_all(root, "base")

    def test_growth_between_base_and_head_is_reported_and_flagged(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        base_sha = self._commit_base(repo)
        write(repo, ".claude/skills/beta/SKILL.md", "---\nname: b\n---\n" + "x" * 5_000)
        report = _json(repo, "--base-ref", base_sha, capsys=capsys)
        delta = report["delta"]
        assert delta["base_sha"] == base_sha
        assert "fixtures.T1.bytes" in delta["material_growth"]

    def test_an_unchanged_tree_shows_zero_delta_even_with_partials(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, "templates/agents/partials/shared.mustache", "p" * 300)
        base_sha = self._commit_base(repo)
        delta = _json(repo, "--base-ref", base_sha, capsys=capsys)["delta"]
        assert [m for m in delta["metrics"] if m["delta"] != 0] == []
        assert delta["changed_paths"] == []

    def test_the_threshold_flag_silences_a_small_growth(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        base_sha = self._commit_base(repo)
        write(repo, ".claude/skills/beta/SKILL.md", "---\nname: b\n---\n" + "x" * 500)
        report = _json(
            repo, "--base-ref", base_sha, "--growth-threshold-bytes", "100000", capsys=capsys
        )
        assert report["delta"]["material_growth"] == []

    def test_table_output_warns_on_material_growth(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        base_sha = self._commit_base(repo)
        write(repo, ".claude/skills/beta/SKILL.md", "---\nname: b\n---\n" + "x" * 5_000)
        assert ib.main(["--path", str(repo), "--base-ref", base_sha]) == 0
        out = capsys.readouterr().out
        assert "WARN: fixtures.T1.bytes grew by more than 2000 bytes" in out

    def test_a_fixture_entrypoint_added_after_base_does_not_abort(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        base_sha = self._commit_base(repo)
        add_skill(repo, "newcomer")
        monkeypatch.setattr(ib, "FIXTURES", (replace(FIXTURE, skills=("alpha", "newcomer")),))
        report = _json(repo, "--base-ref", base_sha, capsys=capsys)
        assert "fixtures.T1.bytes" in report["delta"]["unmeasured_at_base"]

    def test_an_unknown_base_ref_exits_3(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._commit_base(repo)
        assert ib.main(["--path", str(repo), "--base-ref", "no-such-ref"]) == 3
        assert "does not resolve" in capsys.readouterr().err

    def test_an_option_shaped_base_ref_exits_3(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert ib.main(["--path", str(repo), "--base-ref=--exec=x"]) == 3
        assert "refusing base ref" in capsys.readouterr().err

    def test_a_base_without_canonical_trees_exits_2_and_names_the_ref(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        init_git(repo)
        write(repo, "thin.md", "x\n")
        git(repo, "add", "thin.md")
        git(repo, "commit", "-q", "-m", "thin")
        sha = git(repo, "rev-parse", "HEAD")
        assert ib.main(["--path", str(repo), "--base-ref", sha]) == 2
        assert "cannot be measured" in capsys.readouterr().err


class TestConfigErrors:
    def test_a_missing_path_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert ib.main(["--path", str(tmp_path / "nope")]) == 2
        assert "not a directory" in capsys.readouterr().err

    def test_a_tree_without_canonical_groups_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert ib.main(["--path", str(tmp_path)]) == 2
        assert "holds no files" in capsys.readouterr().err

    def test_a_missing_fixture_entrypoint_exits_2(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad = FIXTURE.__class__("T1", "x", None, ("ghost",), ())
        monkeypatch.setattr(ib, "FIXTURES", (bad,))
        assert ib.main(["--path", str(repo)]) == 2
        assert "ghost" in capsys.readouterr().err

    def test_an_unsupported_glob_in_a_rule_exits_2(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write(repo, ".claude/rules/klass.md", '---\npaths:\n  - "*.[ch]"\n---\nx\n')
        assert ib.main(["--path", str(repo)]) == 2
        assert "character class" in capsys.readouterr().err

    @pytest.mark.parametrize("flag", ["--top", "--growth-threshold-bytes"])
    @pytest.mark.parametrize("value", ["-1", "abc"])
    def test_a_bad_numeric_flag_is_rejected(self, flag: str, value: str) -> None:
        with pytest.raises(SystemExit) as raised:
            ib.build_parser().parse_args([flag, value])
        assert raised.value.code == 2

    def test_top_zero_is_allowed_and_lists_nothing(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert _json(repo, "--top", "0", capsys=capsys)["canonical"]["top_contributors"] == []


class TestRendering:
    def _report(self) -> dict[str, Any]:
        return {
            "estimator": "e",
            "canonical": {
                "groups": {"g": {"files": 1, "bytes": 2, "tokens": 3}},
                "total": {"files": 1, "bytes": 2, "tokens": 3},
                "top_contributors": [],
            },
            "generated": {"families": {}, "total": {"files": 0, "bytes": 0, "tokens": 0}},
            "always_on": {"claude_code": {"files": 1, "bytes": 2, "tokens": 3}},
            "fixtures": {
                "A": {
                    "name": "with-ceiling",
                    "artifacts": 1,
                    "bytes": 5,
                    "tokens": 2,
                    "ceiling_bytes": 9,
                },
                "B": {"name": "over", "artifacts": 1, "bytes": 50, "tokens": 2, "ceiling_bytes": 9},
                "C": {
                    "name": "no-ceiling",
                    "artifacts": 1,
                    "bytes": 5,
                    "tokens": 2,
                    "ceiling_bytes": None,
                },
                "D": {"name": "broken", "error": "skill `x` has no file"},
            },
            "ceiling_breaches": [],
            "findings": [],
        }

    def test_fixture_statuses_render_pass_fail_na_and_error(self) -> None:
        out = format_table(self._report())
        lines = {
            line.split()[0]: line
            for line in out.splitlines()
            if line.startswith("  ") and line.split()[0] in "ABCD"
        }
        assert lines["A"].endswith("PASS")
        assert lines["B"].endswith("FAIL")
        assert lines["C"].endswith("n/a")
        assert "not measurable: skill `x` has no file" in lines["D"]

    def test_delta_with_no_change_says_so(self) -> None:
        report = self._report()
        report["delta"] = {
            "base_ref": "main",
            "base_sha": "a" * 40,
            "threshold_bytes": 1,
            "metrics": [{"name": "m", "base": 1, "head": 1, "delta": 0}],
            "changed_paths": [],
            "material_growth": [],
            "unmeasured_at_base": [],
        }
        assert "no change" in format_table(report)

    def test_delta_lists_changed_paths_and_warnings(self) -> None:
        report = self._report()
        report["delta"] = {
            "base_ref": "main",
            "base_sha": "a" * 40,
            "threshold_bytes": 7,
            "metrics": [{"name": "fixtures.A.bytes", "base": 1, "head": 20, "delta": 19}],
            "changed_paths": [{"path": "templates/a.md", "base": 1, "head": 20, "delta": 19}],
            "material_growth": ["fixtures.A.bytes"],
            "unmeasured_at_base": [],
        }
        out = format_table(report)
        assert "+19  templates/a.md" in out
        assert "WARN: fixtures.A.bytes grew by more than 7 bytes" in out

    def test_delta_names_fixtures_that_could_not_be_measured_at_base(self) -> None:
        report = self._report()
        report["delta"] = {
            "base_ref": "main",
            "base_sha": "a" * 40,
            "threshold_bytes": 7,
            "metrics": [],
            "changed_paths": [],
            "material_growth": [],
            "unmeasured_at_base": ["fixtures.F9.bytes", "fixtures.F9.tokens"],
        }
        assert "not measurable at base: fixtures.F9.bytes, fixtures.F9.tokens" in format_table(
            report
        )

    def test_findings_render_report_level_then_per_fixture(self) -> None:
        report = self._report()
        report["findings"] = ["always-on x: missing y"]
        report["fixtures"]["A"]["findings"] = ["skill `s` has no capability block"]
        out = format_table(report)
        assert "Findings\n  always-on x: missing y\n  A: skill `s` has no capability block" in out

    def test_no_findings_renders_no_findings_section(self) -> None:
        assert "Findings" not in format_table(self._report())

    def test_ceiling_breaches_render_a_fail_block(self) -> None:
        report = self._report()
        report["ceiling_breaches"] = ["B: 50 bytes exceeds ceiling 9"]
        assert "FAIL: fixture ceiling exceeded\n  B: 50 bytes exceeds ceiling 9" in format_table(
            report
        )


class TestTypes:
    def test_summarize_of_nothing_is_zero(self) -> None:
        assert summarize([]) == {"files": 0, "bytes": 0, "tokens": 0}

    def test_top_contributors_break_ties_by_path(self) -> None:
        files = [SizedFile("b", 5, 1), SizedFile("a", 5, 1), SizedFile("c", 9, 2)]
        assert [r["path"] for r in top_contributors(files, 3)] == ["c", "a", "b"]

    @pytest.mark.parametrize("limit", [0, -3])
    def test_a_non_positive_limit_returns_nothing(self, limit: int) -> None:
        assert top_contributors([SizedFile("a", 1, 1)], limit) == []
