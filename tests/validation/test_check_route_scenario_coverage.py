"""Tests for scripts/validation/check_route_scenario_coverage.py (issue #6291).

Each case builds a throwaway git repository, commits a base routing table and
scenario file, edits the working tree, and runs the gate against HEAD.

- pos: a new route row plus a scenario naming its target passes
- neg: a new or changed route row with no scenario fails and names the route
- no-change: an untouched table passes, and so do intent rewordings
- edge: untargeted rows, namespaced expected_route, rationale-only edits
- config: bad ref, missing table, bad JSON, missing file exit 2
- regression: the live repository satisfies the gate against its own HEAD
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation import check_route_scenario_coverage as gate

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validation" / "check_route_scenario_coverage.py"

BASE_ROWS = [
    ("Merge conflicts", "Agent: merge-resolver"),
    ("Respond to PR review threads", "Skill: pr-comment-responder"),
    ("Build a feature", "Lifecycle chain per size tier above"),
]


def skill_text(rows: list[tuple[str, str]], header: str = "| Intent | Route |") -> str:
    lines = ["# autoplan", "", "| Context | Name |", "|---|---|", "| a | b |", ""]
    lines += [header, "|--------|-------|"]
    lines += [f"| {intent} | {route} |" for intent, route in rows]
    return "\n".join(lines) + "\n"


def scenario(sid: str, expected: list[str], **extra: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": sid,
        "input": f"request for {sid}",
        "expected_route": expected,
        "forbidden_routes": ["orchestrator"],
        "rationale": "base rationale",
    }
    body.update(extra)
    return body


BASE_SCENARIOS = [scenario("R1", ["merge-resolver"]), scenario("R2", ["pr-comment-responder"])]


def write_scenarios(root: Path, scenarios: list[dict[str, object]]) -> None:
    path = root / gate.SCENARIO_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"scenarios": scenarios}, indent=2) + "\n", encoding="utf-8")


def write_skill(
    root: Path, rows: list[tuple[str, str]], header: str = "| Intent | Route |"
) -> None:
    path = root / gate.SKILL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(skill_text(rows, header), encoding="utf-8")


def git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    write_skill(tmp_path, BASE_ROWS)
    write_scenarios(tmp_path, BASE_SCENARIOS)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def run_gate(root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    code = gate.main(["--repo-root", str(root), "--base-ref", "HEAD"])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_unchanged_table_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run_gate(repo, capsys)
    assert code == gate.EXIT_OK
    assert "no autoplan route added or changed" in out


def test_added_row_without_scenario_fails_and_names_route(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, [*BASE_ROWS, ("Rotate secrets", "Skill: secret-rotator")])
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_UNCOVERED
    assert "Rotate secrets" in err
    assert "Skill: secret-rotator" in err
    assert "expected_route includes: secret-rotator" in err
    assert "1 of 1 changed routes lack a scenario" in err


def test_added_row_with_new_scenario_passes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_skill(repo, [*BASE_ROWS, ("Rotate secrets", "Skill: secret-rotator")])
    write_scenarios(repo, [*BASE_SCENARIOS, scenario("R3", ["secret-rotator"])])
    code, out, _ = run_gate(repo, capsys)
    assert code == gate.EXIT_OK
    assert "1 changed routes each have an edited scenario" in out


def test_changed_route_without_scenario_edit_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [("Merge conflicts", "Agent: conflict-fixer"), *BASE_ROWS[1:]]
    write_skill(repo, rows)
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_UNCOVERED
    assert "Merge conflicts" in err
    assert "conflict-fixer" in err


def test_changed_route_with_updated_expected_route_passes(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, [("Merge conflicts", "Agent: conflict-fixer"), *BASE_ROWS[1:]])
    write_scenarios(repo, [scenario("R1", ["conflict-fixer"]), BASE_SCENARIOS[1]])
    code, _, _ = run_gate(repo, capsys)
    assert code == gate.EXIT_OK


def test_scenario_for_a_different_target_does_not_cover_the_row(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, [*BASE_ROWS, ("Rotate secrets", "Skill: secret-rotator")])
    write_scenarios(repo, [*BASE_SCENARIOS, scenario("R3", ["github"])])
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_UNCOVERED
    assert "Rotate secrets" in err


def test_two_new_rows_report_only_the_uncovered_one(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [
        *BASE_ROWS,
        ("Rotate secrets", "Skill: secret-rotator"),
        ("Audit logs", "Skill: log-auditor"),
    ]
    write_skill(repo, rows)
    write_scenarios(repo, [*BASE_SCENARIOS, scenario("R3", ["log-auditor"])])
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_UNCOVERED
    assert "Rotate secrets" in err
    assert "Audit logs" not in err
    assert "1 of 2 changed routes lack a scenario" in err


def test_intent_reword_with_same_route_is_not_a_route_change(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, [("Resolve merge conflicts", "Agent: merge-resolver"), *BASE_ROWS[1:]])
    code, out, _ = run_gate(repo, capsys)
    assert code == gate.EXIT_OK
    assert "no autoplan route added or changed" in out


def test_merging_two_rows_into_one_route_is_a_route_change(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, [("Merge conflicts", "Skill: pr-comment-responder"), BASE_ROWS[2]])
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_UNCOVERED
    assert "Merge conflicts" in err
    assert "pr-comment-responder" in err


def test_swapping_two_routes_is_a_route_change(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [
        ("Merge conflicts", "Skill: pr-comment-responder"),
        ("Respond to PR review threads", "Agent: merge-resolver"),
        BASE_ROWS[2],
    ]
    write_skill(repo, rows)
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_UNCOVERED
    assert "2 of 2 changed routes lack a scenario" in err


def test_swapping_two_routes_with_edited_scenarios_passes(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [
        ("Merge conflicts", "Skill: pr-comment-responder"),
        ("Respond to PR review threads", "Agent: merge-resolver"),
        BASE_ROWS[2],
    ]
    write_skill(repo, rows)
    write_scenarios(
        repo, [scenario("R1", ["pr-comment-responder"]), scenario("R2", ["merge-resolver"])]
    )
    code, out, _ = run_gate(repo, capsys)
    assert code == gate.EXIT_OK
    assert "2 changed routes each have an edited scenario" in out


def test_removed_row_is_not_a_route_change(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_skill(repo, BASE_ROWS[1:])
    code, _, _ = run_gate(repo, capsys)
    assert code == gate.EXIT_OK


def test_row_without_targets_needs_any_edited_scenario(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, [*BASE_ROWS, ("Plan a trip", "Handled by the lifecycle chain")])
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_UNCOVERED
    assert "includes: any route" in err
    write_scenarios(repo, [*BASE_SCENARIOS, scenario("R3", ["spec"])])
    code, _, _ = run_gate(repo, capsys)
    assert code == gate.EXIT_OK


def test_rationale_only_edit_does_not_count(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_skill(repo, [("Merge conflicts", "Agent: conflict-fixer"), *BASE_ROWS[1:]])
    write_scenarios(
        repo, [scenario("R1", ["merge-resolver"], rationale="new words"), BASE_SCENARIOS[1]]
    )
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_UNCOVERED
    assert "conflict-fixer" in err


def test_namespaced_expected_route_matches_bare_target(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, [*BASE_ROWS, ("Rotate secrets", "Skill: secret-rotator")])
    write_scenarios(repo, [*BASE_SCENARIOS, scenario("R3", ["project-toolkit:secret-rotator"])])
    code, _, _ = run_gate(repo, capsys)
    assert code == gate.EXIT_OK


def test_orchestrator_row_target_is_extracted() -> None:
    assert gate.extract_targets('Task(subagent_type="orchestrator")') == ("orchestrator",)


def test_slash_command_targets_apply_only_without_prefixed_targets() -> None:
    assert gate.extract_targets("/ship (or /push-pr for push-only)") == ("ship", "push-pr")
    assert gate.extract_targets("Skill: analyze, then /build for the fix") == ("analyze",)
    assert gate.extract_targets("Skill: context-gather, then Skill: research") == (
        "context-gather",
        "research",
    )


def test_scenarios_file_new_at_head_counts_every_scenario_as_edited(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(repo, "rm", "-q", "-f", gate.SCENARIO_PATH)
    git(repo, "commit", "-q", "-m", "drop scenarios")
    write_skill(repo, [*BASE_ROWS, ("Rotate secrets", "Skill: secret-rotator")])
    write_scenarios(repo, [scenario("R9", ["secret-rotator"])])
    code, _, _ = run_gate(repo, capsys)
    assert code == gate.EXIT_OK


def test_skill_new_at_head_treats_every_row_as_new(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(repo, "rm", "-q", "-f", gate.SKILL_PATH)
    git(repo, "commit", "-q", "-m", "drop skill")
    write_skill(repo, BASE_ROWS[:2])
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_UNCOVERED
    assert "Merge conflicts" in err


def test_unresolvable_base_ref_is_a_config_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = gate.main(["--repo-root", str(repo), "--base-ref", "no-such-ref"])
    assert code == gate.EXIT_CONFIG
    assert "cannot find a merge base" in capsys.readouterr().err


def test_option_shaped_base_ref_is_rejected(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = gate.main(["--repo-root", str(repo), "--base-ref=--help"])
    assert code == gate.EXIT_CONFIG
    assert "invalid base ref" in capsys.readouterr().err


def test_renamed_route_table_header_is_a_config_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, BASE_ROWS, header="| Request | Destination |")
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_CONFIG
    assert "no 'Intent | Route' table" in err


def test_malformed_scenario_json_is_a_config_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, [*BASE_ROWS, ("Rotate secrets", "Skill: secret-rotator")])
    (repo / gate.SCENARIO_PATH).write_text("{not json", encoding="utf-8")
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_CONFIG
    assert "not valid JSON" in err


@pytest.mark.parametrize("payload", ['{"scenarios": 3}', "[]", '{"scenarios": [{"x": 1}]}'])
def test_wrong_scenario_shape_is_a_config_error(
    repo: Path, capsys: pytest.CaptureFixture[str], payload: str
) -> None:
    write_skill(repo, [*BASE_ROWS, ("Rotate secrets", "Skill: secret-rotator")])
    (repo / gate.SCENARIO_PATH).write_text(payload, encoding="utf-8")
    code, _, _ = run_gate(repo, capsys)
    assert code == gate.EXIT_CONFIG


def test_missing_skill_file_is_a_config_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / gate.SKILL_PATH).unlink()
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_CONFIG
    assert "cannot read" in err


def test_missing_scenario_file_with_changed_route_is_a_config_error(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, [*BASE_ROWS, ("Rotate secrets", "Skill: secret-rotator")])
    (repo / gate.SCENARIO_PATH).unlink()
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_CONFIG
    assert "cannot read" in err


def test_cli_exit_code_through_a_subprocess(repo: Path) -> None:
    write_skill(repo, [*BASE_ROWS, ("Rotate secrets", "Skill: secret-rotator")])
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo-root", str(repo), "--base-ref", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == gate.EXIT_UNCOVERED
    assert "Rotate secrets" in result.stderr


def test_live_repository_has_no_uncovered_route_against_head() -> None:
    assert gate.main(["--repo-root", str(REPO_ROOT), "--base-ref", "HEAD"]) == gate.EXIT_OK


def test_live_route_table_parses_to_the_expected_shape() -> None:
    rows = gate.parse_route_rows((REPO_ROOT / gate.SKILL_PATH).read_text(encoding="utf-8"))
    assert len(rows) >= 15
    by_intent = {row.intent: row for row in rows}
    assert by_intent["Merge conflicts"].targets == ("merge-resolver",)
    assert all(row.intent and row.route for row in rows)


def test_scenario_with_non_list_expected_route_covers_nothing(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, [*BASE_ROWS, ("Rotate secrets", "Skill: secret-rotator")])
    bad = {**scenario("R3", []), "expected_route": "secret-rotator"}
    write_scenarios(repo, [*BASE_SCENARIOS, bad])
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_UNCOVERED
    assert "Rotate secrets" in err


def test_git_show_failure_is_a_config_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real = gate._git

    def flaky(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "show":
            return subprocess.CompletedProcess(args, 128, "", "boom")
        return real(root, *args)

    monkeypatch.setattr(gate, "_git", flaky)
    code, _, err = run_gate(repo, capsys)
    assert code == gate.EXIT_CONFIG
    assert "boom" in err


def test_default_repo_root_is_the_checkout_that_holds_the_script() -> None:
    assert gate._resolve_repo_root(None) == REPO_ROOT
