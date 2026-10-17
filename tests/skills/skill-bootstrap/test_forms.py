"""Tests for bootstrap_forms.py: the map-or-GPS tool-form check."""

from __future__ import annotations

import importlib.util
import json
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "skill-bootstrap"
    / "scripts"
    / "bootstrap_forms.py"
)
_spec = importlib.util.spec_from_file_location("bootstrap_forms", SCRIPT)
assert _spec is not None and _spec.loader is not None
bootstrap_forms = importlib.util.module_from_spec(_spec)
sys.modules["bootstrap_forms"] = bootstrap_forms
_spec.loader.exec_module(bootstrap_forms)


def make_item(**overrides: Any) -> dict[str, Any]:
    """A valid instrument item; override or drop (value None) fields per test."""
    item: dict[str, Any] = {
        "id": "I1",
        "skill": "acme-change-control",
        "lens": "change-control",
        "claim": "Gates depend on the touched path.",
        "evidence": ["commit abc123"],
        "computable": True,
        "form": "instrument",
        "script": "scripts/gates_for_path.py",
        "baseline_case": "C3",
    }
    item.update(overrides)
    return {k: v for k, v in item.items() if v is not None}


def run_check(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    items: list[Any],
    *extra: str,
    mode: str = "workflow",
) -> tuple[int, dict[str, Any]]:
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"project": "acme", "mode": mode, "items": items}), encoding="utf-8")
    code = bootstrap_forms.main(["check", "--plan", str(plan), *extra])
    return code, json.loads(capsys.readouterr().out)


def rules(payload: dict[str, Any]) -> list[str]:
    return [v["rule"] for v in payload["violations"]]


def test_valid_plan_exits_zero_with_counts(capsys, tmp_path):
    items = [
        make_item(id="I1"),
        make_item(id="I2", form="both", why="script is not the whole story"),
        make_item(id="I3", form="scaffold", computable=False, script=None, why="needs judgment"),
    ]

    code, payload = run_check(capsys, tmp_path, items)

    assert code == 0
    assert payload["violations"] == []
    assert payload["forms"] == {"scaffold": 1, "instrument": 1, "both": 1}
    assert payload["computable_share"] == pytest.approx(2 / 3)
    assert payload["examined"] == {"items": 3}


def test_empty_items_reports_zero_examined(capsys, tmp_path):
    code, payload = run_check(capsys, tmp_path, [])

    assert code == 0
    assert payload["examined"] == {"items": 0}
    assert payload["computable_share"] == 0.0
    assert payload["forms"] == {"scaffold": 0, "instrument": 0, "both": 0}


def test_duplicate_id_is_flagged_once(capsys, tmp_path):
    code, payload = run_check(capsys, tmp_path, [make_item(), make_item()])

    assert code == 1
    assert rules(payload) == ["duplicate-id"]


@pytest.mark.parametrize("bad_id", [None, "", "  ", 7])
def test_missing_or_blank_id_is_flagged(capsys, tmp_path, bad_id):
    code, payload = run_check(capsys, tmp_path, [make_item(id=bad_id)])

    assert code == 1
    assert rules(payload) == ["id-invalid"]
    assert payload["violations"][0]["item"] == "#0"


@pytest.mark.parametrize("claim", [None, "", "   ", 5])
def test_missing_or_empty_claim_is_flagged(capsys, tmp_path, claim):
    code, payload = run_check(capsys, tmp_path, [make_item(claim=claim)])

    assert code == 1
    assert rules(payload) == ["claim-missing"]


@pytest.mark.parametrize(
    "evidence", [None, [], "commit abc", ["ok", ""], ["ok", "  "], ["ok", 3], {"a": "b"}]
)
def test_invalid_evidence_is_flagged(capsys, tmp_path, evidence):
    code, payload = run_check(capsys, tmp_path, [make_item(evidence=evidence)])

    assert code == 1
    assert rules(payload) == ["evidence-invalid"]


@pytest.mark.parametrize("lens", ["change-control", "research-methodology", "other:my-lens"])
def test_valid_lens_is_accepted(capsys, tmp_path, lens):
    code, payload = run_check(capsys, tmp_path, [make_item(lens=lens)])

    assert code == 0
    assert payload["violations"] == []


@pytest.mark.parametrize("lens", [None, "", "made-up", "other:", "other:Bad Name", "other:a--b", 4])
def test_unknown_lens_is_flagged(capsys, tmp_path, lens):
    code, payload = run_check(capsys, tmp_path, [make_item(lens=lens)])

    assert code == 1
    assert rules(payload) == ["unknown-lens"]


@pytest.mark.parametrize("form", [None, "", "map", "Instrument", 3])
def test_unknown_form_is_flagged(capsys, tmp_path, form):
    code, payload = run_check(capsys, tmp_path, [make_item(form=form)])

    assert code == 1
    assert rules(payload) == ["form-invalid"]
    assert payload["forms"] == {"scaffold": 0, "instrument": 0, "both": 0}


def test_computable_scaffold_is_flagged(capsys, tmp_path):
    item = make_item(form="scaffold", script=None, why="judgment call")

    code, payload = run_check(capsys, tmp_path, [item])

    assert code == 1
    assert rules(payload) == ["computable-needs-instrument"]


def test_noncomputable_scaffold_with_why_passes(capsys, tmp_path):
    item = make_item(form="scaffold", computable=False, script=None, why="needs judgment")

    code, payload = run_check(capsys, tmp_path, [item])

    assert code == 0
    assert payload["computable_share"] == 0.0


def test_missing_computable_is_flagged(capsys, tmp_path):
    item = make_item(form="scaffold", computable=None, script=None, why="needs judgment")
    assert "computable" not in item

    code, payload = run_check(capsys, tmp_path, [item])

    assert code == 1
    assert rules(payload) == ["computable-type"]


def test_non_boolean_computable_is_flagged(capsys, tmp_path):
    code, payload = run_check(capsys, tmp_path, [make_item(computable="yes")])

    assert code == 1
    assert rules(payload) == ["computable-type"]
    assert payload["computable_share"] == 0.0


@pytest.mark.parametrize("why", [None, "", "   "])
def test_scaffold_without_why_is_flagged(capsys, tmp_path, why):
    item = make_item(form="scaffold", computable=False, script=None, why=why)

    code, payload = run_check(capsys, tmp_path, [item])

    assert code == 1
    assert rules(payload) == ["scaffold-needs-why"]


@pytest.mark.parametrize("form", ["instrument", "both"])
@pytest.mark.parametrize(
    "script",
    [
        None,
        "",
        7,
        "/abs/scripts/x.py",
        "C:\\scripts\\x.py",
        "scripts/../../etc/x.py",
        "scripts\\..\\x.py",
        "tools/x.py",
        "scripts",
        "scripts/",
    ],
)
def test_bad_script_path_is_flagged(capsys, tmp_path, form, script):
    code, payload = run_check(capsys, tmp_path, [make_item(form=form, script=script)])

    assert code == 1
    assert rules(payload) == ["script-path"]


@pytest.mark.parametrize("script", ["scripts/a.py", "scripts/sub/a.py", "scripts\\a.py"])
def test_relative_script_under_scripts_is_accepted(capsys, tmp_path, script):
    code, payload = run_check(capsys, tmp_path, [make_item(script=script)])

    assert code == 0
    assert payload["violations"] == []


def test_knowledge_mode_requires_baseline_case(capsys, tmp_path):
    code, payload = run_check(capsys, tmp_path, [make_item(baseline_case=None)], mode="knowledge")

    assert code == 1
    assert rules(payload) == ["baseline-case-missing"]


def test_knowledge_mode_rejects_blank_baseline_case(capsys, tmp_path):
    code, payload = run_check(capsys, tmp_path, [make_item(baseline_case=" ")], mode="knowledge")

    assert code == 1
    assert rules(payload) == ["baseline-case-missing"]


def test_workflow_mode_does_not_require_baseline_case(capsys, tmp_path):
    code, payload = run_check(capsys, tmp_path, [make_item(baseline_case=None)])

    assert code == 0
    assert payload["violations"] == []


def test_knowledge_mode_with_baseline_case_passes(capsys, tmp_path):
    code, payload = run_check(capsys, tmp_path, [make_item()], mode="knowledge")

    assert code == 0


@pytest.mark.parametrize("skill", [None, "", "Acme", "acme_x", "-acme", "acme-", "1acme", 4])
def test_bad_skill_name_is_flagged(capsys, tmp_path, skill):
    code, payload = run_check(capsys, tmp_path, [make_item(skill=skill)])

    assert code == 1
    assert rules(payload) == ["skill-name"]


def test_multiple_violations_accumulate_in_one_item(capsys, tmp_path):
    item = make_item(claim="", evidence=[], lens="nope")

    code, payload = run_check(capsys, tmp_path, [item])

    assert code == 1
    assert sorted(rules(payload)) == ["claim-missing", "evidence-invalid", "unknown-lens"]
    assert {v["item"] for v in payload["violations"]} == {"I1"}


def test_require_scripts_flags_missing_script(capsys, tmp_path):
    root = tmp_path / "skills"
    root.mkdir()

    code, payload = run_check(
        capsys, tmp_path, [make_item()], "--skills-root", str(root), "--require-scripts"
    )

    assert code == 1
    assert rules(payload) == ["script-missing"]


def test_require_scripts_passes_when_script_exists(capsys, tmp_path):
    script = tmp_path / "skills" / "acme-change-control" / "scripts" / "gates_for_path.py"
    script.parent.mkdir(parents=True)
    script.write_text("print(1)\n", encoding="utf-8")

    code, payload = run_check(
        capsys, tmp_path, [make_item()], "--skills-root", str(tmp_path / "skills"),
        "--require-scripts",
    )  # fmt: skip

    assert code == 0
    assert payload["violations"] == []


def test_require_scripts_ignores_scaffold_items(capsys, tmp_path):
    item = make_item(form="scaffold", computable=False, script=None, why="judgment")

    code, payload = run_check(
        capsys, tmp_path, [item], "--skills-root", str(tmp_path), "--require-scripts"
    )

    assert code == 0


def test_require_scripts_does_not_double_report_a_bad_path(capsys, tmp_path):
    code, payload = run_check(
        capsys, tmp_path, [make_item(script="../x.py")], "--skills-root", str(tmp_path),
        "--require-scripts",
    )  # fmt: skip

    assert code == 1
    assert rules(payload) == ["script-path"]


def test_require_scripts_skips_script_check_for_bad_skill_name(capsys, tmp_path):
    code, payload = run_check(
        capsys, tmp_path, [make_item(skill="Bad Name")], "--skills-root", str(tmp_path),
        "--require-scripts",
    )  # fmt: skip

    assert code == 1
    assert rules(payload) == ["skill-name"]


def test_skills_root_without_require_scripts_is_config_error(capsys, tmp_path):
    code, payload = run_check(capsys, tmp_path, [make_item()], "--skills-root", str(tmp_path))

    assert code == 2
    assert payload["error"] == "config"
    assert "--require-scripts" in payload["message"]


def test_require_scripts_without_skills_root_is_config_error(capsys, tmp_path):
    code, payload = run_check(capsys, tmp_path, [make_item()], "--require-scripts")

    assert code == 2
    assert payload["error"] == "config"


def test_unreadable_plan_is_config_error(capsys, tmp_path):
    code = bootstrap_forms.main(["check", "--plan", str(tmp_path / "missing.json")])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"] == "config"


def test_malformed_json_is_config_error(capsys, tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text("{not json", encoding="utf-8")

    code = bootstrap_forms.main(["check", "--plan", str(plan)])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"] == "config"


@pytest.mark.parametrize(
    "document",
    [
        [],
        "text",
        {"mode": "workflow"},
        {"mode": "workflow", "items": {}},
        {"mode": "workflow", "items": ["not an object"]},
        {"mode": "other", "items": []},
        {"items": []},
    ],
)
def test_wrong_top_level_types_are_config_errors(capsys, tmp_path, document):
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(document), encoding="utf-8")

    code = bootstrap_forms.main(["check", "--plan", str(plan)])

    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"] == "config"


def test_missing_plan_argument_exits_two(capsys):
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_forms.main(["check"])

    assert excinfo.value.code == 2


def test_script_runs_as_a_process_and_returns_the_exit_code(tmp_path):
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps({"mode": "workflow", "items": [make_item(claim="")]}), encoding="utf-8"
    )

    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "check", "--plan", str(plan)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert proc.returncode == 1
    assert json.loads(proc.stdout)["examined"] == {"items": 1}


def test_module_entry_point_exits_with_main_status(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bootstrap_forms.py", "check"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert excinfo.value.code == 2


# --- security review F7: fullmatch, so a trailing newline is invalid --------


@pytest.mark.parametrize("skill", ["acme\n", "acme-skill\n", "\nacme"])
def test_skill_name_with_newline_is_flagged(capsys, tmp_path, skill):
    code, payload = run_check(capsys, tmp_path, [make_item(skill=skill)])

    assert code == 1
    assert rules(payload) == ["skill-name"]


@pytest.mark.parametrize("lens", ["other:my-lens\n", "\nother:my-lens"])
def test_other_lens_with_newline_is_flagged(capsys, tmp_path, lens):
    code, payload = run_check(capsys, tmp_path, [make_item(lens=lens)])

    assert code == 1
    assert rules(payload) == ["unknown-lens"]


def test_clean_skill_name_and_other_lens_still_pass(capsys, tmp_path):
    code, payload = run_check(
        capsys, tmp_path, [make_item(skill="acme-skill", lens="other:my-lens")]
    )

    assert code == 0
    assert payload["violations"] == []


def test_unknown_lens_message_lists_the_valid_ids(capsys, tmp_path):
    _, payload = run_check(capsys, tmp_path, [make_item(lens="build-and-environment")])

    message = payload["violations"][0]["message"]
    assert "build-and-env" in message
    assert "other:<kebab-name>" in message


@pytest.mark.parametrize("skill", ["a--b", "a" * 65])
def test_skill_name_with_double_hyphen_or_over_64_chars_is_flagged(capsys, tmp_path, skill):
    code, payload = run_check(capsys, tmp_path, [make_item(skill=skill)])

    assert code == 1
    assert rules(payload) == ["skill-name"]


def test_skill_name_of_64_chars_passes(capsys, tmp_path):
    code, _ = run_check(capsys, tmp_path, [make_item(skill="a" * 64)])

    assert code == 0


def test_missing_skills_root_is_config_error(capsys, tmp_path):
    code, payload = run_check(
        capsys, tmp_path, [make_item()], "--skills-root", str(tmp_path / "nope"),
        "--require-scripts",
    )  # fmt: skip

    assert code == 2
    assert payload["error"] == "config"
    assert "not a directory" in payload["message"]
