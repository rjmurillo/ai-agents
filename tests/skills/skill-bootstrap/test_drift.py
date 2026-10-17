# taste-lint: ignore file-size, one suite covers every check kind and status of one script.
"""Tests for bootstrap_drift.py: executable provenance re-verification."""

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
    / "bootstrap_drift.py"
)
_spec = importlib.util.spec_from_file_location("bootstrap_drift", SCRIPT)
assert _spec is not None and _spec.loader is not None
bootstrap_drift = importlib.util.module_from_spec(_spec)
sys.modules["bootstrap_drift"] = bootstrap_drift
_spec.loader.exec_module(bootstrap_drift)

PY = sys.executable


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "build" / "scripts").mkdir(parents=True)
    (root / "build" / "scripts" / "build_all.py").write_text("a\nb\nc\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("Python ADR-042 rules\n", encoding="utf-8")
    return root.resolve()


@pytest.fixture
def skills(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    return root


def add_skill(skills: Path, name: str, checks: Any = None, raw: str | None = None) -> Path:
    directory = skills / name
    directory.mkdir()
    if raw is not None:
        (directory / "reverify.json").write_text(raw, encoding="utf-8")
    elif checks is not None:
        (directory / "reverify.json").write_text(json.dumps({"checks": checks}), encoding="utf-8")
    return directory


def run(
    capsys: pytest.CaptureFixture[str], repo: Path, skills: Path, *extra: str
) -> tuple[int, dict[str, Any]]:
    code = bootstrap_drift.main(
        ["check", "--repo", str(repo), "--skills-root", str(skills), *extra]
    )
    return code, json.loads(capsys.readouterr().out)


def only_check(payload: dict[str, Any]) -> dict[str, Any]:
    check: dict[str, Any] = payload["skills"][0]["checks"][0]
    return check


def check_one(
    capsys: pytest.CaptureFixture[str], repo: Path, skills: Path, check: dict[str, Any], *extra: str
) -> tuple[int, dict[str, Any]]:
    add_skill(skills, "s1", [check])
    return run(capsys, repo, skills, *extra)


def test_all_passing_checks_make_the_skill_pass(capsys, repo, skills):
    add_skill(
        skills,
        "s1",
        [
            {"id": "R1", "kind": "path_exists", "path": "build/scripts/build_all.py"},
            {"id": "R2", "kind": "absent", "path": ".agents/HANDOFF.md"},
            {"id": "R3", "kind": "contains", "path": "AGENTS.md", "text": "ADR-042"},
            {"id": "R4", "kind": "line_count_at_least", "path": "build/scripts/build_all.py",
             "min": 3},
        ],
    )  # fmt: skip

    code, payload = run(capsys, repo, skills)

    assert code == 0
    assert payload["skills"][0]["status"] == "pass"
    assert [c["status"] for c in payload["skills"][0]["checks"]] == ["pass"] * 4
    assert payload["update_candidates"] == []
    assert payload["update_args"] == ""
    assert payload["examined"] == {"skills": 1, "checks": 4}


def test_path_exists_fails_when_missing(capsys, repo, skills):
    code, payload = check_one(
        capsys, repo, skills, {"id": "R1", "kind": "path_exists", "path": "nope"}
    )

    assert code == 1
    assert only_check(payload)["status"] == "fail"
    assert payload["skills"][0]["status"] == "fail"


def test_absent_fails_when_present(capsys, repo, skills):
    code, payload = check_one(
        capsys, repo, skills, {"id": "R2", "kind": "absent", "path": "AGENTS.md"}
    )

    assert code == 1
    assert only_check(payload)["status"] == "fail"


def test_absent_fails_for_a_dangling_symlink(capsys, repo, skills):
    (repo / "dangling").symlink_to(repo / "does-not-exist")

    code, payload = check_one(
        capsys, repo, skills, {"id": "R2", "kind": "absent", "path": "dangling"}
    )

    assert code == 1
    assert only_check(payload)["status"] == "fail"


def test_contains_fails_when_text_is_absent(capsys, repo, skills):
    check = {"id": "R3", "kind": "contains", "path": "AGENTS.md", "text": "ADR-999"}

    code, payload = check_one(capsys, repo, skills, check)

    assert code == 1
    assert only_check(payload)["status"] == "fail"


def test_contains_fails_when_path_is_a_directory(capsys, repo, skills):
    check = {"id": "R3", "kind": "contains", "path": "build", "text": "x"}

    code, payload = check_one(capsys, repo, skills, check)

    assert code == 1
    assert "not a file" in only_check(payload)["detail"]


def test_contains_matches_multiline_text(capsys, repo, skills):
    check = {"id": "R3", "kind": "contains", "path": "build/scripts/build_all.py", "text": "a\nb\n"}

    code, payload = check_one(capsys, repo, skills, check)

    assert code == 0
    assert only_check(payload)["status"] == "pass"


def test_line_count_passes_at_the_boundary_and_fails_below(capsys, repo, skills):
    path = "build/scripts/build_all.py"
    add_skill(
        skills,
        "s1",
        [
            {"id": "R4", "kind": "line_count_at_least", "path": path, "min": 3},
            {"id": "R5", "kind": "line_count_at_least", "path": path, "min": 4},
        ],
    )

    code, payload = run(capsys, repo, skills)

    assert code == 1
    assert [c["status"] for c in payload["skills"][0]["checks"]] == ["pass", "fail"]


def test_line_count_fails_for_a_missing_file(capsys, repo, skills):
    check = {"id": "R4", "kind": "line_count_at_least", "path": "gone.py", "min": 1}

    code, payload = check_one(capsys, repo, skills, check)

    assert code == 1
    assert "not a file" in only_check(payload)["detail"]


@pytest.mark.parametrize("kind", ["path_exists", "absent"])
@pytest.mark.parametrize(
    "path", ["../outside.txt", "a/../../outside.txt", "a\\..\\x", "/etc/passwd"]
)
def test_traversal_and_absolute_paths_are_invalid(capsys, repo, skills, kind, path):
    code, payload = check_one(capsys, repo, skills, {"id": "R1", "kind": kind, "path": path})

    assert code == 1
    assert only_check(payload)["status"] == "invalid"
    assert payload["skills"][0]["status"] == "fail"


def test_symlink_escape_is_invalid(capsys, repo, skills, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    (repo / "link").symlink_to(outside)
    check = {"id": "R3", "kind": "contains", "path": "link/secret.txt", "text": "secret"}

    code, payload = check_one(capsys, repo, skills, check)

    assert code == 1
    assert only_check(payload)["status"] == "invalid"


def test_symlink_inside_the_repo_is_allowed(capsys, repo, skills):
    (repo / "alias.md").symlink_to(repo / "AGENTS.md")
    check = {"id": "R3", "kind": "contains", "path": "alias.md", "text": "ADR-042"}

    code, payload = check_one(capsys, repo, skills, check)

    assert code == 0


def test_empty_path_in_resolver_is_rejected():
    assert bootstrap_drift._safe_path(Path("/"), "  ") is None


def test_the_repo_root_itself_resolves(repo):
    assert bootstrap_drift._safe_path(repo, ".") == repo


COMMAND_OK = [PY, "-c", "raise SystemExit(0)"]


def test_command_is_skipped_without_the_flag(capsys, repo, skills):
    marker = repo / "ran.txt"
    argv = [PY, "-c", f"open({str(marker)!r}, 'w').write('x')"]

    code, payload = check_one(capsys, repo, skills, {"id": "R5", "kind": "command", "argv": argv})

    assert code == 0
    assert only_check(payload)["status"] == "skipped"
    assert payload["skills"][0]["status"] == "pass"
    assert not marker.exists()


def test_command_passes_when_exit_matches_default(capsys, repo, skills):
    check = {"id": "R5", "kind": "command", "argv": COMMAND_OK}

    code, payload = check_one(capsys, repo, skills, check, "--allow-commands")

    assert code == 0
    assert only_check(payload)["status"] == "pass"


def test_command_runs_in_the_repo_directory(capsys, repo, skills):
    argv = [PY, "-c", "import os, sys; sys.exit(0 if os.path.exists('AGENTS.md') else 1)"]

    code, payload = check_one(
        capsys, repo, skills, {"id": "R5", "kind": "command", "argv": argv}, "--allow-commands"
    )

    assert code == 0


def test_command_fails_on_exit_mismatch(capsys, repo, skills):
    check = {"id": "R5", "kind": "command", "argv": [PY, "-c", "raise SystemExit(3)"]}

    code, payload = check_one(capsys, repo, skills, check, "--allow-commands")

    assert code == 1
    assert only_check(payload)["status"] == "fail"
    assert "exit 3" in only_check(payload)["detail"]


def test_command_passes_when_nonzero_exit_is_expected(capsys, repo, skills):
    argv = [PY, "-c", "raise SystemExit(3)"]
    check = {"id": "R5", "kind": "command", "argv": argv, "expect_exit": 3}

    code, payload = check_one(capsys, repo, skills, check, "--allow-commands")

    assert code == 0
    assert only_check(payload)["status"] == "pass"


def test_command_timeout_is_a_failure(capsys, repo, skills, monkeypatch):
    monkeypatch.setattr(bootstrap_drift, "COMMAND_TIMEOUT_S", 0.2)
    check = {"id": "R5", "kind": "command", "argv": [PY, "-c", "import time; time.sleep(30)"]}

    code, payload = check_one(capsys, repo, skills, check, "--allow-commands")

    assert code == 1
    assert only_check(payload)["status"] == "fail"
    assert "timed out" in only_check(payload)["detail"]


def test_command_that_cannot_start_is_a_failure(capsys, repo, skills):
    check = {"id": "R5", "kind": "command", "argv": ["definitely-not-a-real-binary-xyz"]}

    code, payload = check_one(capsys, repo, skills, check, "--allow-commands")

    assert code == 1
    assert "could not run" in only_check(payload)["detail"]


def test_command_does_not_use_a_shell(capsys, repo, skills):
    marker = repo / "injected.txt"
    argv = [PY, "-c", "pass", f"; touch {marker}"]

    code, payload = check_one(
        capsys, repo, skills, {"id": "R5", "kind": "command", "argv": argv}, "--allow-commands"
    )

    assert not marker.exists()


def test_skipped_checks_do_not_fail_a_skill_with_passing_checks(capsys, repo, skills):
    add_skill(
        skills,
        "s1",
        [
            {"id": "R1", "kind": "path_exists", "path": "AGENTS.md"},
            {"id": "R5", "kind": "command", "argv": COMMAND_OK},
        ],
    )

    code, payload = run(capsys, repo, skills)

    assert code == 0
    assert [c["status"] for c in payload["skills"][0]["checks"]] == ["pass", "skipped"]


def test_missing_reverify_is_no_provenance_and_exit_zero(capsys, repo, skills):
    add_skill(skills, "bare")

    code, payload = run(capsys, repo, skills)

    assert code == 0
    assert payload["skills"][0]["status"] == "no-provenance"
    assert payload["no_provenance"] == ["bare"]
    assert payload["update_candidates"] == []
    assert payload["examined"] == {"skills": 1, "checks": 0}


def test_require_fails_on_missing_provenance(capsys, repo, skills):
    add_skill(skills, "bare")

    code, payload = run(capsys, repo, skills, "--require")

    assert code == 1
    assert payload["no_provenance"] == ["bare"]
    assert payload["update_candidates"] == []


def test_require_passes_when_every_skill_has_provenance(capsys, repo, skills):
    add_skill(skills, "s1", [{"id": "R1", "kind": "path_exists", "path": "AGENTS.md"}])

    code, payload = run(capsys, repo, skills, "--require")

    assert code == 0


@pytest.mark.parametrize(
    "raw",
    [
        "{not json",
        "[]",
        json.dumps({"checks": "x"}),
        json.dumps({"checks": []}),
        json.dumps({"checks": ["x"]}),
        json.dumps({"checks": [{"kind": "path_exists", "path": "a"}]}),
        json.dumps({"checks": [{"id": "", "kind": "path_exists", "path": "a"}]}),
        json.dumps({"checks": [{"id": "R1", "kind": "teleport", "path": "a"}]}),
        json.dumps({"checks": [{"id": "R1", "kind": "path_exists"}]}),
        json.dumps({"checks": [{"id": "R1", "kind": "absent", "path": ""}]}),
        json.dumps({"checks": [{"id": "R1", "kind": "contains", "path": "a"}]}),
        json.dumps({"checks": [{"id": "R1", "kind": "contains", "path": "a", "text": ""}]}),
        json.dumps({"checks": [{"id": "R1", "kind": "line_count_at_least", "path": "a"}]}),
        json.dumps(
            {"checks": [{"id": "R1", "kind": "line_count_at_least", "path": "a", "min": "3"}]}
        ),
        json.dumps(
            {"checks": [{"id": "R1", "kind": "line_count_at_least", "path": "a", "min": True}]}
        ),
        json.dumps(
            {"checks": [{"id": "R1", "kind": "line_count_at_least", "path": "a", "min": -1}]}
        ),
        json.dumps({"checks": [{"id": "R1", "kind": "command"}]}),
        json.dumps({"checks": [{"id": "R1", "kind": "command", "argv": []}]}),
        json.dumps({"checks": [{"id": "R1", "kind": "command", "argv": "ls"}]}),
        json.dumps({"checks": [{"id": "R1", "kind": "command", "argv": ["ls", 1]}]}),
        json.dumps(
            {"checks": [{"id": "R1", "kind": "command", "argv": ["ls"], "expect_exit": "0"}]}
        ),
        json.dumps(
            {
                "checks": [
                    {"id": "R1", "kind": "path_exists", "path": "a"},
                    {"id": "R1", "kind": "path_exists", "path": "b"},
                ]
            }
        ),
    ],
)
def test_schema_defects_make_the_skill_malformed(capsys, repo, skills, raw):
    add_skill(skills, "bad", raw=raw)

    code, payload = run(capsys, repo, skills)

    assert code == 1
    assert payload["skills"][0]["status"] == "malformed"
    assert payload["skills"][0]["detail"]
    assert payload["update_candidates"] == ["bad"]
    assert payload["examined"] == {"skills": 1, "checks": 0}


def test_non_utf8_reverify_is_malformed(capsys, repo, skills):
    directory = add_skill(skills, "bad")
    (directory / "reverify.json").write_bytes(b"\xff\xfe\x00")

    code, payload = run(capsys, repo, skills)

    assert code == 1
    assert payload["skills"][0]["status"] == "malformed"


def test_update_args_lists_failing_and_malformed_skills(capsys, repo, skills):
    add_skill(skills, "a", [{"id": "R1", "kind": "path_exists", "path": "gone"}])
    add_skill(skills, "b", [{"id": "R1", "kind": "path_exists", "path": "AGENTS.md"}])
    add_skill(skills, "c", raw="{")

    code, payload = run(capsys, repo, skills)

    assert code == 1
    assert payload["update_candidates"] == ["a", "c"]
    assert payload["update_args"] == "--name a --update a --name c --update c"


def test_name_filter_checks_only_the_named_skill(capsys, repo, skills):
    add_skill(skills, "a", [{"id": "R1", "kind": "path_exists", "path": "gone"}])
    add_skill(skills, "b", [{"id": "R1", "kind": "path_exists", "path": "AGENTS.md"}])

    code, payload = run(capsys, repo, skills, "--name", "b")

    assert code == 0
    assert [s["name"] for s in payload["skills"]] == ["b"]
    assert payload["examined"] == {"skills": 1, "checks": 1}


def test_repeated_name_is_checked_once(capsys, repo, skills):
    add_skill(skills, "a", [{"id": "R1", "kind": "path_exists", "path": "AGENTS.md"}])

    code, payload = run(capsys, repo, skills, "--name", "a", "--name", "a")

    assert payload["examined"]["skills"] == 1


def test_unknown_name_is_a_config_error(capsys, repo, skills):
    add_skill(skills, "a", [{"id": "R1", "kind": "path_exists", "path": "AGENTS.md"}])

    code, payload = run(capsys, repo, skills, "--name", "nope")

    assert code == 2
    assert payload["error"] == "config"
    assert "nope" in payload["message"]


def test_name_that_is_a_file_not_a_directory_is_unknown(capsys, repo, skills):
    (skills / "stray.txt").write_text("x", encoding="utf-8")

    code, payload = run(capsys, repo, skills, "--name", "stray.txt")

    assert code == 2


def test_files_in_skills_root_are_not_skills(capsys, repo, skills):
    (skills / "README.md").write_text("x", encoding="utf-8")

    code, payload = run(capsys, repo, skills)

    assert code == 0
    assert payload["examined"] == {"skills": 0, "checks": 0}


def test_empty_skills_root_examines_zero_and_exits_zero(capsys, repo, skills):
    code, payload = run(capsys, repo, skills)

    assert code == 0
    assert payload["skills"] == []
    assert payload["examined"] == {"skills": 0, "checks": 0}
    assert payload["no_provenance"] == []


def test_bad_repo_is_a_config_error(capsys, tmp_path, skills):
    code, payload = run(capsys, tmp_path / "missing", skills)

    assert code == 2
    assert payload["error"] == "config"


def test_bad_skills_root_is_a_config_error(capsys, repo, tmp_path):
    code, payload = run(capsys, repo, tmp_path / "missing")

    assert code == 2
    assert payload["error"] == "config"


def test_missing_required_arguments_exit_two():
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_drift.main(["check"])

    assert excinfo.value.code == 2


def test_check_does_not_write_into_the_repo(capsys, repo, skills):
    add_skill(skills, "s1", [{"id": "R1", "kind": "path_exists", "path": "AGENTS.md"}])
    before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*"))

    run(capsys, repo, skills)

    assert sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*")) == before


def test_script_runs_as_a_process_and_returns_the_exit_code(repo, skills):
    add_skill(skills, "s1", [{"id": "R1", "kind": "path_exists", "path": "gone"}])

    proc = subprocess.run(
        [PY, str(SCRIPT), "check", "--repo", str(repo), "--skills-root", str(skills)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert proc.returncode == 1
    assert json.loads(proc.stdout)["update_candidates"] == ["s1"]


def test_module_entry_point_exits_with_main_status(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bootstrap_drift.py", "check"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert excinfo.value.code == 2
