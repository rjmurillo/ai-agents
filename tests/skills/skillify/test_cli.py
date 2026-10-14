"""CLI contract: JSON on stdout and exit codes 0 / 1 / 2."""

from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys

import pytest
import skillify
from skill_fixtures import SKILL_DIR, make_skill

TRIGGER = "ingest a meeting transcript"
AUDIT = {
    "tool_call_count": 6,
    "reusable_class": True,
    "decision_points": 2,
    "gotchas": 1,
    "trigger_phrase": TRIGGER,
}


def run_cli(capsys, *argv):
    code = skillify.main(list(argv))
    return code, json.loads(capsys.readouterr().out)


def write_json(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_gate_proceed_exits_zero(tmp_path, capsys):
    code, out = run_cli(capsys, "gate", "--audit", write_json(tmp_path / "a.json", AUDIT))
    assert (code, out["status"]) == (0, "PROCEED")


def test_gate_reject_exits_zero_with_reasons(tmp_path, capsys):
    audit = {**AUDIT, "tool_call_count": 1}
    code, out = run_cli(capsys, "gate", "--audit", write_json(tmp_path / "a.json", audit))
    assert code == 0
    assert out["status"] == "REJECT"
    assert out["reasons"][0]["code"] == "trivial_wrapper"


def test_gate_reads_stdin(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(AUDIT)))
    code, out = run_cli(capsys, "gate", "--audit", "-")
    assert (code, out["status"]) == (0, "PROCEED")


def test_gate_missing_file_exits_one(tmp_path, capsys):
    code, out = run_cli(capsys, "gate", "--audit", str(tmp_path / "absent.json"))
    assert code == 1
    assert out["status"] == "error"


def test_gate_malformed_json_exits_one(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    code, out = run_cli(capsys, "gate", "--audit", str(bad))
    assert code == 1
    assert "malformed JSON" in out["error"]


def test_gate_invalid_audit_exits_one(tmp_path, capsys):
    code, out = run_cli(capsys, "gate", "--audit", write_json(tmp_path / "a.json", {}))
    assert (code, out["status"]) == (1, "error")


def test_resolve_explicit_exits_zero(tmp_path, capsys):
    code, out = run_cli(capsys, "resolve", "--explicit", str(tmp_path), "--cwd", str(tmp_path))
    assert (code, out["source"]) == (0, "explicit")


def test_resolve_env_var_exits_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SKILLIFY_TEST_ROOT", str(tmp_path))
    code, out = run_cli(
        capsys, "resolve", "--env-var", "NOPE_UNSET", "--env-var", "SKILLIFY_TEST_ROOT"
    )
    assert (code, out["source"], out["env_var"]) == (0, "env", "SKILLIFY_TEST_ROOT")


def test_resolve_cwd_flag_detects_root(tmp_path, capsys):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    code, out = run_cli(capsys, "resolve", "--cwd", str(tmp_path))
    assert (code, out["source"]) == (0, "cwd")


def test_resolve_defaults_to_process_cwd(tmp_path, monkeypatch, capsys):
    (tmp_path / ".github" / "skills").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    code, out = run_cli(capsys, "resolve")
    assert (code, out["harness"]) == (0, "copilot-cli")


def test_resolve_unresolved_exits_two_and_writes_nothing(tmp_path, capsys):
    code, out = run_cli(capsys, "resolve", "--cwd", str(tmp_path))
    assert code == 2
    assert out["status"] == "needs_clarification"
    assert list(tmp_path.iterdir()) == []


def test_overlap_patch_and_create(tmp_path, skills_root, capsys):
    make_skill(skills_root, "meeting-ingest", description="Ingest a meeting transcript.")
    workflow = write_json(tmp_path / "w.json", {"terms": ["ingest meeting transcript"]})
    code, out = run_cli(capsys, "overlap", "--workflow", workflow, "--root", str(skills_root))
    assert (code, out["status"], out["skill"]) == (0, "PATCH", "meeting-ingest")
    other = write_json(tmp_path / "o.json", {"terms": ["rotate database credentials"]})
    code, out = run_cli(capsys, "overlap", "--workflow", other, "--root", str(skills_root))
    assert (code, out["status"]) == (0, "CREATE")


def test_overlap_bad_workflow_exits_one(tmp_path, skills_root, capsys):
    workflow = write_json(tmp_path / "w.json", {"terms": []})
    code, out = run_cli(capsys, "overlap", "--workflow", workflow, "--root", str(skills_root))
    assert (code, out["status"]) == (1, "error")


def test_verify_pass_exits_zero(skills_root, capsys):
    make_skill(skills_root, "meeting-ingest")
    code, out = run_cli(
        capsys, "verify", "--skill", str(skills_root / "meeting-ingest"), "--trigger", TRIGGER
    )
    assert (code, out["status"], out["name"]) == (0, "PASS", "meeting-ingest")


def test_verify_fail_exits_one(skills_root, capsys):
    make_skill(skills_root, "meeting-ingest", body="---\nname: meeting-ingest\n---\n# x\n")
    code, out = run_cli(
        capsys, "verify", "--skill", str(skills_root / "meeting-ingest"), "--trigger", TRIGGER
    )
    assert (code, out["status"]) == (1, "FAIL")
    assert "section_triggers" in out["failures"]


def test_verify_external_actions_flag(skills_root, capsys):
    make_skill(skills_root, "meeting-ingest")
    code, out = run_cli(
        capsys,
        "verify",
        "--skill",
        str(skills_root / "meeting-ingest" / "SKILL.md"),
        "--trigger",
        TRIGGER,
        "--external-actions",
    )
    assert (code, out["status"]) == (0, "PASS")


def test_verify_missing_skill_exits_one(tmp_path, capsys):
    code, out = run_cli(capsys, "verify", "--skill", str(tmp_path / "x"), "--trigger", TRIGGER)
    assert (code, out["status"]) == (1, "error")


def test_script_runs_as_a_subprocess_from_unrelated_directory(tmp_path):
    audit = write_json(tmp_path / "a.json", AUDIT)
    proc = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts" / "skillify.py"), "gate", "--audit", audit],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["status"] == "PROCEED"


def test_unknown_subcommand_is_json_error_exit_one(capsys):
    code, out = run_cli(capsys, "bogus")
    assert code == 1
    assert out["status"] == "error"
    assert "usage" in out["error"]


def test_missing_required_option_is_json_error_exit_one(capsys):
    code, out = run_cli(capsys, "gate")
    assert (code, out["status"]) == (1, "error")


def test_run_rejects_unregistered_command():
    with pytest.raises(skillify.SkillifyError, match="unknown command"):
        skillify.run(argparse.Namespace(command="bogus"), {})


def test_usage_error_exit_code_differs_from_no_destination(tmp_path, capsys):
    usage, _ = run_cli(capsys, "resolve", "--nope")
    unresolved, _ = run_cli(capsys, "resolve", "--cwd", str(tmp_path))
    assert (usage, unresolved) == (1, 2)


def test_verify_reads_trigger_and_flags_from_audit(skills_root, tmp_path, capsys):
    make_skill(skills_root, "meeting-ingest")
    audit = write_json(tmp_path / "a.json", {**AUDIT, "external_actions": True})
    code, out = run_cli(
        capsys, "verify", "--skill", str(skills_root / "meeting-ingest"), "--audit", audit
    )
    assert (code, out["status"], out["trigger"]) == (0, "PASS", TRIGGER)
    names = [c["id"] for c in out["checks"]]
    assert "approval_gate_present" in names
    assert "recovery_path_marked" not in names


def test_verify_flag_overrides_audit(skills_root, tmp_path, capsys):
    make_skill(skills_root, "meeting-ingest")
    audit = write_json(tmp_path / "a.json", AUDIT)
    code, out = run_cli(
        capsys,
        "verify",
        "--skill",
        str(skills_root / "meeting-ingest"),
        "--audit",
        audit,
        "--trigger",
        "something else",
        "--recovery-paths",
    )
    assert code == 1
    assert out["trigger"] == "something else"
    assert set(out["failures"]) == {
        "description_leads_with_trigger",
        "recovery_path_marked",
    }


def test_verify_shell_metacharacters_in_audit_trigger_are_data(skills_root, tmp_path, capsys):
    phrase = 'ingest $(touch pwned); "x"'
    audit = write_json(tmp_path / "a.json", {**AUDIT, "trigger_phrase": phrase})
    make_skill(skills_root, "meeting-ingest", description=phrase)
    code, out = run_cli(
        capsys, "verify", "--skill", str(skills_root / "meeting-ingest"), "--audit", audit
    )
    assert (code, out["trigger"]) == (0, phrase)
    assert not (tmp_path / "pwned").exists()


@pytest.mark.parametrize(
    "audit",
    [
        [],
        {"tool_call_count": 3},
        {"trigger_phrase": 4},
        {"trigger_phrase": "x", "recovery_paths": 1},
    ],
)
def test_verify_bad_audit_exits_one(skills_root, tmp_path, capsys, audit):
    make_skill(skills_root, "meeting-ingest")
    path = write_json(tmp_path / "a.json", audit)
    code, out = run_cli(
        capsys, "verify", "--skill", str(skills_root / "meeting-ingest"), "--audit", path
    )
    assert (code, out["status"]) == (1, "error")


def test_verify_needs_trigger_or_audit(skills_root, capsys):
    make_skill(skills_root, "meeting-ingest")
    code, out = run_cli(capsys, "verify", "--skill", str(skills_root / "meeting-ingest"))
    assert (code, out["status"]) == (1, "error")


def test_verify_mode_patch_flag(skills_root, tmp_path, capsys):
    desc = "Does things when you say ingest a meeting transcript."
    host = f"---\nname: host\ndescription: {desc}\n---\n\n## Process\n\n1. Go.\n"
    make_skill(skills_root, "host", body=host)
    audit = write_json(tmp_path / "a.json", AUDIT)
    argv = ["verify", "--skill", str(skills_root / "host"), "--audit", audit]
    code, out = run_cli(capsys, *argv)
    assert (code, out["mode"]) == (1, "create")
    code, out = run_cli(capsys, *argv, "--mode", "patch")
    assert (code, out["status"], out["mode"]) == (0, "PASS", "patch")


def test_verify_mode_rejects_unknown_value(skills_root, capsys):
    code, out = run_cli(capsys, "verify", "--skill", "x", "--trigger", "t", "--mode", "bogus")
    assert (code, out["status"]) == (1, "error")
