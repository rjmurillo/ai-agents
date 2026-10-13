"""Tests for skill_collision_report.py (issue #5763).

Covers the regression policy, the pairs-file emitter, rendering, and the CLI exit
codes. The comparison engine is tested in test_skill_collision_core.py.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
for _path in (_EVAL_DIR, Path(__file__).resolve().parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import _skill_collision as core  # noqa: E402
import skill_collision_report as scr  # noqa: E402
from _skill_collision_test_support import SHARED_PREFIX, make_catalog, write_skill  # noqa: E402


@pytest.fixture
def catalog(tmp_path: Path) -> Path:
    return make_catalog(tmp_path)


class TestPolicy:
    def accepted_file(self, tmp_path: Path, entries: list[object]) -> Path:
        path = tmp_path / "baseline.json"
        path.write_text(json.dumps({"accepted": entries}), encoding="utf-8")
        return path

    def entry(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "kind": "exact",
            "field": "description",
            "profile": "full",
            "skills": ["alpha-copy", "alpha"],
            "reason": "Intentional mirror pending retirement.",
            "owner": "rjmurillo",
        }
        base.update(overrides)
        return base

    def test_new_high_finding_is_reported(self, catalog: Path) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        report = core.build_report(catalog)

        assert [f.skills for f in scr.new_high_findings(report, {})] == [("alpha", "alpha-copy")]

    def test_accepted_finding_is_not_new_regardless_of_skill_order(
        self, catalog: Path, tmp_path: Path
    ) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        report = core.build_report(catalog)
        accepted = scr.load_accepted(self.accepted_file(tmp_path, [self.entry()]))

        assert scr.new_high_findings(report, accepted) == []

    def test_low_confidence_finding_never_counts_as_new(self, catalog: Path) -> None:
        write_skill(
            catalog, "bravo-v2", "Render a dashboard of weekly build durations as charts today."
        )
        report = core.build_report(catalog)

        assert report.findings
        assert scr.new_high_findings(report, {}) == []

    def test_unreadable_baseline_is_a_config_error(self, tmp_path: Path) -> None:
        with pytest.raises(core.ReportError, match="not readable"):
            scr.load_accepted(tmp_path / "missing.json")

    def test_invalid_json_baseline_is_a_config_error(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{nope", encoding="utf-8")

        with pytest.raises(core.ReportError, match="not valid JSON"):
            scr.load_accepted(path)

    @pytest.mark.parametrize("payload", ["[]", '{"accepted": "x"}', "{}"])
    def test_baseline_without_accepted_list_is_rejected(self, tmp_path: Path, payload: str) -> None:
        path = tmp_path / "shape.json"
        path.write_text(payload, encoding="utf-8")

        with pytest.raises(core.ReportError, match="'accepted' list"):
            scr.load_accepted(path)

    def test_non_object_entry_is_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(core.ReportError, match="must be an object"):
            scr.load_accepted(self.accepted_file(tmp_path, ["text"]))

    @pytest.mark.parametrize("missing", ["kind", "field", "profile", "reason", "owner"])
    def test_entry_without_required_text_is_rejected(self, tmp_path: Path, missing: str) -> None:
        entry = self.entry()
        entry[missing] = "  "

        with pytest.raises(core.ReportError, match=f"non-empty '{missing}'"):
            scr.load_accepted(self.accepted_file(tmp_path, [entry]))

    @pytest.mark.parametrize("skills", [None, ["one"], ["a", "b", "c"], ["a", 2]])
    def test_entry_with_bad_skills_is_rejected(self, tmp_path: Path, skills: object) -> None:
        with pytest.raises(core.ReportError, match="two non-empty names"):
            scr.load_accepted(self.accepted_file(tmp_path, [self.entry(skills=skills)]))


class TestPairsEmitter:
    PROMPTS = {
        "alpha": [{"prompt": "p", "expected": "e", "owner": "alpha"}],
        "alpha-copy": [{"prompt": "p", "expected": "e", "owner": "alpha-copy"}],
        "bravo": [{"prompt": "p", "expected": "e", "owner": "bravo"}],
    }

    def test_clusters_become_pairs_with_prompts_for_both_skills(self) -> None:
        payload, missing = scr.build_pairs_file([("alpha", "alpha-copy")], self.PROMPTS)

        assert payload["pairs"] == [["alpha", "alpha-copy"]]
        assert sorted(payload["prompts"]) == ["alpha", "alpha-copy"]
        assert missing == []

    def test_pair_without_prompts_is_skipped_and_named(self) -> None:
        payload, missing = scr.build_pairs_file(
            [("alpha", "alpha-copy"), ("bravo", "stranger")], self.PROMPTS
        )

        assert payload["pairs"] == [["alpha", "alpha-copy"]]
        assert missing == ["stranger"]

    def test_three_skill_cluster_yields_every_pair(self) -> None:
        prompts = {**self.PROMPTS, "charlie": self.PROMPTS["bravo"]}

        payload, _ = scr.build_pairs_file([("alpha", "bravo", "charlie")], prompts)

        assert payload["pairs"] == [["alpha", "bravo"], ["alpha", "charlie"], ["bravo", "charlie"]]

    def test_emitted_payload_loads_in_the_overlap_evaluator(self, tmp_path: Path) -> None:
        payload, _ = scr.build_pairs_file([("alpha", "alpha-copy")], self.PROMPTS)
        out = tmp_path / "pairs.json"
        out.write_text(json.dumps(payload), encoding="utf-8")
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "overlap", _EVAL_DIR / "eval-skill-overlap.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["overlap"] = module
        spec.loader.exec_module(module)

        config = module.load_pairs_file(str(out))

        assert config.pairs == [("alpha", "alpha-copy")]

    def test_load_prompts_reads_the_prompts_object(self, tmp_path: Path) -> None:
        path = tmp_path / "p.json"
        path.write_text(json.dumps({"prompts": self.PROMPTS}), encoding="utf-8")

        assert scr.load_prompts(path) == self.PROMPTS

    def test_load_prompts_rejects_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(core.ReportError, match="not readable"):
            scr.load_prompts(tmp_path / "none.json")

    def test_load_prompts_rejects_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "p.json"
        path.write_text("{", encoding="utf-8")

        with pytest.raises(core.ReportError, match="not valid JSON"):
            scr.load_prompts(path)

    @pytest.mark.parametrize("payload", ["[]", '{"prompts": {}}', '{"prompts": []}'])
    def test_load_prompts_rejects_empty_or_wrong_shape(self, tmp_path: Path, payload: str) -> None:
        path = tmp_path / "p.json"
        path.write_text(payload, encoding="utf-8")

        with pytest.raises(core.ReportError, match="non-empty object"):
            scr.load_prompts(path)


class TestRendering:
    def test_human_output_names_profile_limits_and_remediation(self, catalog: Path) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        report = core.build_report(catalog)

        text = scr.render_human(report)

        assert "controlled, not measured host limits" in text
        assert "Host abbreviation: not observed" in text
        assert "[high] exact description profile=full" in text
        assert "alpha/SKILL.md" in text
        assert "Fix: Merge the skills" in text
        assert "Clusters:" in text
        assert "[NEW]" not in text

    def test_human_output_marks_findings_the_policy_rejects(self, catalog: Path) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        report = core.build_report(catalog)

        text = scr.render_human(report, scr.new_high_findings(report, {}))

        assert "[NEW]" in text

    def test_human_output_for_clean_catalog_lists_no_findings(self, catalog: Path) -> None:
        text = scr.render_human(core.build_report(catalog))

        assert "Findings: 0 (0 high confidence)" in text
        assert "Clusters:" not in text

    def test_json_output_is_deterministic_and_parses(self, catalog: Path) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        report = core.build_report(catalog)

        first, second = scr.render_json(report), scr.render_json(report)
        data = json.loads(first)

        assert first == second
        assert data["skills_scanned"] == 4
        assert data["findings"][0]["kind"] == "exact"
        assert "policy" not in data

    def test_json_output_includes_policy_when_a_baseline_was_applied(self, catalog: Path) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        report = core.build_report(catalog)

        data = json.loads(scr.render_json(report, scr.new_high_findings(report, {})))

        assert len(data["policy"]["new_high_confidence"]) == 1


class TestMain:
    def test_clean_catalog_exits_zero(
        self, catalog: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = scr.main(["--root", str(catalog)])

        assert code == scr.EXIT_OK
        assert "Findings: 0" in capsys.readouterr().out

    def test_report_mode_exits_zero_even_with_high_findings(
        self, catalog: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )

        code = scr.main(["--root", str(catalog), "--format", "json"])

        assert code == scr.EXIT_OK
        assert json.loads(capsys.readouterr().out)["findings"]

    def test_baseline_gate_exits_one_on_new_high_confidence_collision(
        self, catalog: Path, tmp_path: Path
    ) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"accepted": []}', encoding="utf-8")

        code = scr.main(["--root", str(catalog), "--baseline", str(baseline)])

        assert code == scr.EXIT_NEW_COLLISION

    def test_baseline_gate_exits_zero_for_low_confidence_only(
        self, catalog: Path, tmp_path: Path
    ) -> None:
        write_skill(
            catalog, "bravo-v2", "Render a dashboard of weekly build durations as charts today."
        )
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"accepted": []}', encoding="utf-8")

        code = scr.main(["--root", str(catalog), "--baseline", str(baseline)])

        assert code == scr.EXIT_OK

    def test_truncate_flag_drives_the_boundary_through_the_cli(
        self, catalog: Path, tmp_path: Path
    ) -> None:
        write_skill(catalog, "ledger-read", SHARED_PREFIX + "Read balances only.")
        write_skill(catalog, "ledger-write", SHARED_PREFIX + "Post new journal entries.")
        baseline = tmp_path / "baseline.json"
        baseline.write_text('{"accepted": []}', encoding="utf-8")
        base = ["--root", str(catalog), "--baseline", str(baseline)]

        wide = scr.main([*base, "--truncate", str(len(SHARED_PREFIX) + 4)])
        narrow = scr.main([*base, "--truncate", str(len(SHARED_PREFIX))])

        assert (wide, narrow) == (scr.EXIT_OK, scr.EXIT_NEW_COLLISION)

    def test_only_flag_restricts_to_selected_skills(
        self, catalog: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        write_skill(catalog, "zeta", "Rotate expired API credentials in the secrets manager.")

        scr.main(["--root", str(catalog), "--format", "json", "--only", "zeta"])
        data = json.loads(capsys.readouterr().out)

        assert [f["skills"] for f in data["findings"]] == [["charlie", "zeta"]]

    def test_only_flag_with_no_findings_for_skill_reports_clean(
        self, catalog: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = scr.main(["--root", str(catalog), "--only", "alpha"])

        assert code == scr.EXIT_OK
        assert "Findings: 0" in capsys.readouterr().out

    def test_changed_since_with_no_changed_skills_short_circuits(
        self, catalog: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(scr, "changed_skills", lambda root, ref: [])

        code = scr.main(["--root", str(catalog), "--changed-since", "HEAD"])

        assert code == scr.EXIT_OK
        assert "Nothing to report" in capsys.readouterr().out

    def test_changed_since_restricts_to_changed_skills(
        self, catalog: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        monkeypatch.setattr(scr, "changed_skills", lambda root, ref: ["alpha-copy"])

        scr.main(["--root", str(catalog), "--changed-since", "main", "--format", "json"])

        assert len(json.loads(capsys.readouterr().out)["findings"]) == 1

    def test_git_failure_exits_external(
        self, catalog: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = scr.main(["--root", str(catalog), "--changed-since", "no-such-ref-5763"])

        assert code == scr.EXIT_EXTERNAL
        assert "error:" in capsys.readouterr().err

    def test_option_like_ref_exits_config(
        self, catalog: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        sink = tmp_path / "sink.txt"

        code = scr.main(["--root", str(catalog), f"--changed-since=--output={sink}"])

        assert code == scr.EXIT_CONFIG
        assert not sink.exists()
        assert "must not start with '-'" in capsys.readouterr().err

    def test_missing_root_exits_config(self, tmp_path: Path) -> None:
        assert scr.main(["--root", str(tmp_path / "absent")]) == scr.EXIT_CONFIG

    def test_bad_baseline_exits_config(self, catalog: Path, tmp_path: Path) -> None:
        assert scr.main(["--root", str(catalog), "--baseline", str(tmp_path / "x.json")]) == 2

    @pytest.mark.parametrize(
        "flags",
        [["--near-threshold", "1.5"], ["--near-threshold", "-0.1"], ["--truncate", "0"]],
    )
    def test_out_of_range_numbers_exit_config(self, catalog: Path, flags: list[str]) -> None:
        assert scr.main(["--root", str(catalog), *flags]) == scr.EXIT_CONFIG

    def test_emit_pairs_without_prompts_file_exits_config(
        self, catalog: Path, tmp_path: Path
    ) -> None:
        code = scr.main(["--root", str(catalog), "--emit-pairs", str(tmp_path / "o.json")])

        assert code == scr.EXIT_CONFIG

    def test_emit_pairs_writes_a_pairs_file_for_clusters(
        self, catalog: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        prompts = tmp_path / "prompts.json"
        prompts.write_text(json.dumps({"prompts": TestPairsEmitter.PROMPTS}), encoding="utf-8")
        out = tmp_path / "out.json"

        code = scr.main(
            ["--root", str(catalog), "--emit-pairs", str(out), "--prompts-file", str(prompts)]
        )

        assert code == scr.EXIT_OK
        assert json.loads(out.read_text(encoding="utf-8"))["pairs"] == [["alpha", "alpha-copy"]]

    def test_emit_pairs_names_skills_lacking_prompts_and_fails_when_none_remain(
        self, catalog: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )
        prompts = tmp_path / "prompts.json"
        prompts.write_text(json.dumps({"prompts": {"bravo": [{}]}}), encoding="utf-8")
        out = tmp_path / "out.json"

        code = scr.main(
            ["--root", str(catalog), "--emit-pairs", str(out), "--prompts-file", str(prompts)]
        )

        captured = capsys.readouterr()
        assert code == scr.EXIT_CONFIG
        assert "No prompts for: alpha, alpha-copy" in captured.err
        assert not out.exists()

    def test_defaults_scan_the_real_catalog_without_a_policy_violation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        monkeypatch.chdir(repo_root)

        code = scr.main(["--baseline", "scripts/eval/skill_collision_baseline.json"])

        assert code == scr.EXIT_OK


class TestScriptEntryPoint:
    def test_runs_as_a_script_from_another_directory(self, catalog: Path, tmp_path: Path) -> None:
        write_skill(
            catalog, "alpha-copy", "Parse YAML configuration files and report schema errors."
        )

        result = subprocess.run(
            [sys.executable, str(_EVAL_DIR / "skill_collision_report.py"), "--root", str(catalog)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == scr.EXIT_OK
        assert "[high] exact description profile=full" in result.stdout
