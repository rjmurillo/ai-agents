"""CLI contract for spec_audit.py: exit codes and JSON output."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import pytest
import spec_audit
from audit_paths import FIXTURES, SKILL_DIR
from ledgers import anchor, ask, ledger


class Result(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


SCRIPT = SKILL_DIR / "scripts" / "spec_audit.py"
SPEC = FIXTURES / "contradiction_spec.md"


def write(path: Path, data: Any) -> str:
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def cli_subprocess(*args: str, script: Path = SCRIPT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, check=False
    )


@pytest.fixture
def cli(capsys: pytest.CaptureFixture[str]) -> Callable[..., Result]:
    """Run spec_audit.main in process so coverage sees it."""

    def run(*args: str) -> Result:
        code = spec_audit.main(list(args))
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return run


def question() -> dict[str, Any]:
    return ask("Q1", "edge_case", [anchor("3.2", "idle session expires")])


def test_check_with_a_question_exits_zero(tmp_path: Path, cli: Callable[..., Result]) -> None:
    ledger_path = write(tmp_path / "l.json", ledger([question()]))
    done = cli("check", "--source", str(SPEC), "--ledger", ledger_path)
    assert done.returncode == 0
    assert json.loads(done.stdout)["status"] == "ask"


def test_check_with_nothing_to_ask_prints_the_verdict(
    tmp_path: Path, cli: Callable[..., Result]
) -> None:
    ledger_path = write(tmp_path / "l.json", ledger([]))
    done = cli("check", "--source", str(FIXTURES / "clean_spec.md"), "--ledger", ledger_path)
    assert done.returncode == 0
    assert json.loads(done.stdout)["verdict"] == "NO MATERIAL GAPS"


def test_check_exits_one_for_an_invalid_ledger(tmp_path: Path, cli: Callable[..., Result]) -> None:
    bad = {**question(), "anchors": [anchor("3.2", "absent phrase")]}
    done = cli(
        "check", "--source", str(SPEC), "--ledger", write(tmp_path / "l.json", ledger([bad]))
    )
    assert done.returncode == 1
    assert json.loads(done.stdout)["status"] == "invalid"


def test_check_exits_one_for_an_incomplete_question(
    tmp_path: Path, cli: Callable[..., Result]
) -> None:
    bare = {**question(), "why_now": ""}
    done = cli(
        "check", "--source", str(SPEC), "--ledger", write(tmp_path / "l.json", ledger([bare]))
    )
    assert done.returncode == 1
    assert json.loads(done.stdout)["status"] == "incomplete"


def test_check_exits_one_for_an_answer_that_is_not_an_option(
    tmp_path: Path, cli: Callable[..., Result]
) -> None:
    data = ledger([question()], answers={"Q1": "zzz"})
    done = cli("check", "--source", str(SPEC), "--ledger", write(tmp_path / "l.json", data))
    assert done.returncode == 1
    assert "not one of its options" in done.stderr


def test_check_exits_one_for_malformed_json(tmp_path: Path, cli: Callable[..., Result]) -> None:
    broken = tmp_path / "l.json"
    broken.write_text("{nope", encoding="utf-8")
    assert cli("check", "--source", str(SPEC), "--ledger", str(broken)).returncode == 1


def test_check_exits_two_when_a_file_is_missing(tmp_path: Path, cli: Callable[..., Result]) -> None:
    done = cli("check", "--source", str(tmp_path / "nope.md"), "--ledger", str(tmp_path / "l.json"))
    assert done.returncode == 2


def test_cap_flags_reach_the_planner(tmp_path: Path, cli: Callable[..., Result]) -> None:
    many = [ask(f"Q{n}", "edge_case", [anchor("3.2", "idle session expires")]) for n in range(1, 4)]
    path = write(tmp_path / "l.json", ledger(many))
    done = cli("check", "--source", str(SPEC), "--ledger", path, "--max-questions", "2")
    assert [e["id"] for e in json.loads(done.stdout)["batch"]] == ["Q1", "Q2"]


def test_check_exits_two_without_the_decision_question_engine(tmp_path: Path) -> None:
    lone = tmp_path / "requirements-interview" / "scripts"
    shutil.copytree(SKILL_DIR / "scripts", lone)
    path = write(tmp_path / "l.json", ledger([question()]))
    done = cli_subprocess(
        "check", "--source", str(SPEC), "--ledger", path, script=lone / "spec_audit.py"
    )
    assert done.returncode == 2
    assert "decision-question engine not found" in done.stderr


def verify_args(tmp_path: Path, rebuilt: Path) -> list[str]:
    candidates = [ask("Q2", "edge_case", [anchor("6. Terms", "An active user is anyone")])]
    return [
        "verify",
        "--source",
        str(FIXTURES / "rebuild_source.md"),
        "--ledger",
        write(tmp_path / "l.json", ledger(candidates)),
        "--log",
        write(tmp_path / "log.json", [{"id": "Q2", "outcome": "open"}]),
        "--rebuilt",
        str(rebuilt),
    ]


def test_verify_exits_zero_for_the_full_fixture_rebuild(
    tmp_path: Path, cli: Callable[..., Result]
) -> None:
    candidates = [
        ask(
            "Q1",
            "contradiction",
            [
                anchor("3. Limits", "at most 3 active sessions"),
                anchor("5. Account policy", "up to 5 concurrent"),
            ],
        ),
        ask("Q2", "edge_case", [anchor("6. Terms", "An active user is anyone")]),
    ]
    log = [
        {
            "id": "Q1",
            "outcome": "accepted",
            "text": "The concurrent session limit is 3 per account.",
            "replaces": ["Each account supports up to 5 concurrent sessions."],
        },
        {"id": "Q2", "outcome": "open"},
    ]
    args = verify_args(tmp_path, FIXTURES / "rebuild_ok.md")
    args[args.index("--ledger") + 1] = write(tmp_path / "full.json", ledger(candidates))
    args[args.index("--log") + 1] = write(tmp_path / "full-log.json", log)
    done = cli(*args)
    assert done.returncode == 0, done.stdout
    assert json.loads(done.stdout)["status"] == "verified"


def test_verify_exits_zero_when_only_open_decisions_change(
    tmp_path: Path, cli: Callable[..., Result]
) -> None:
    source = (FIXTURES / "rebuild_source.md").read_text(encoding="utf-8")
    rebuilt = tmp_path / "rebuilt.md"
    rebuilt.write_text(
        source + "\n## Open decisions\n\n- Q2: suspended sessions.\n", encoding="utf-8"
    )
    done = cli(*verify_args(tmp_path, rebuilt))
    assert done.returncode == 0, done.stdout
    assert json.loads(done.stdout)["status"] == "verified"


def test_verify_exits_one_for_a_failed_rebuild(tmp_path: Path, cli: Callable[..., Result]) -> None:
    done = cli(*verify_args(tmp_path, FIXTURES / "rebuild_source.md"))
    assert done.returncode == 1
    assert json.loads(done.stdout)["status"] == "failed"


def test_verify_exits_one_for_an_invalid_ledger(tmp_path: Path, cli: Callable[..., Result]) -> None:
    args = verify_args(tmp_path, FIXTURES / "rebuild_ok.md")
    args[args.index("--ledger") + 1] = write(tmp_path / "bad.json", ledger([{"id": "Q1"}]))
    done = cli(*args)
    assert done.returncode == 1
    assert json.loads(done.stdout)["status"] == "invalid"


def test_script_runs_as_a_program(tmp_path: Path) -> None:
    path = write(tmp_path / "l.json", ledger([question()]))
    done = cli_subprocess("check", "--source", str(SPEC), "--ledger", path)
    assert done.returncode == 0
    assert json.loads(done.stdout)["status"] == "ask"
