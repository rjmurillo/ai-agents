"""Artifact and CLI tests for the claim ledger validator (issue #5388).

With ``--artifact`` the validator checks that the artifact carries the checked
wording, not the unreviewed draft, and that an internal-only skip cites no
outside URL. The CLI tests pin the ADR-035 exit codes.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claim_ledger_fixtures import (
    ledger_errors,
    make_claim,
    make_ledger,
    make_secondary,
    make_statistic,
    make_unavailable,
    mod,
    write,
)

# Artifact rules: the artifact carries the checked wording, not the draft.


def test_artifact_with_final_wording_passes() -> None:
    artifact = "Intro.\nKafka consumers pause fetches when the buffer is full.\n"
    assert ledger_errors(make_ledger(make_claim()), artifact) == []


def test_artifact_missing_final_wording_fails() -> None:
    errors = ledger_errors(make_ledger(make_claim()), "Nothing here.")
    assert any("absent" in e for e in errors)


def test_artifact_with_removed_claim_fails() -> None:
    artifact = "The SDK supports ARM64 on every platform."
    errors = ledger_errors(make_ledger(make_unavailable()), artifact)
    assert any("removed" in e for e in errors)


def test_artifact_with_unqualified_draft_fails() -> None:
    claim = make_statistic()
    artifact = f"{claim['final_wording']}. {claim['claim']}."
    assert any("draft" in e for e in ledger_errors(make_ledger(claim), artifact))


def test_artifact_match_ignores_whitespace_and_case() -> None:
    artifact = "KAFKA consumers pause\n  fetches when the buffer is full"
    assert ledger_errors(make_ledger(make_claim()), artifact) == []


def test_removed_draft_inside_kept_wording_passes() -> None:
    kept = make_claim(final_wording="Docs state the SDK supports ARM64 on every platform it lists")
    removed = make_unavailable() | {"id": "C9"}
    artifact = kept["final_wording"]
    assert ledger_errors(make_ledger(kept, removed), artifact) == []


def test_draft_match_needs_word_boundaries() -> None:
    removed = make_unavailable() | {"claim": "fast"}
    assert ledger_errors(make_ledger(removed), "The breakfast queue is steady.") == []


def test_memory_restating_a_subset_passes_with_its_own_ledger() -> None:
    memory = "Kafka consumers pause fetches when the buffer is full. See the analysis."
    assert ledger_errors(make_ledger(make_claim()), memory) == []


def test_memory_checked_against_the_analysis_ledger_fails() -> None:
    memory = "Kafka consumers pause fetches when the buffer is full."
    analysis_ledger = make_ledger(make_claim(), make_secondary())
    assert any("C3" in e for e in ledger_errors(analysis_ledger, memory))


def test_skip_with_outside_url_fails() -> None:
    ledger = make_ledger(decision="skip")
    artifact = "Per https://vendor.example.com/bench the queue is 3x faster."
    assert any("outside URL" in e for e in ledger_errors(ledger, artifact))


def test_skip_with_repository_paths_passes() -> None:
    ledger = make_ledger(decision="skip")
    artifact = "ADR-042 and `tests/skills/test_push_lock.py` constrain the queue."
    assert ledger_errors(ledger, artifact) == []


def test_activate_with_url_passes() -> None:
    artifact = "Kafka consumers pause fetches when the buffer is full (https://kafka.apache.org)."
    assert ledger_errors(make_ledger(make_claim()), artifact) == []


@pytest.mark.parametrize("value", ["", None, 7])
def test_artifact_field_must_be_a_string(value: object) -> None:
    ledger = make_ledger(make_claim())
    ledger["artifact"] = value
    assert any("`artifact`" in e for e in ledger_errors(ledger))


# CLI and exit codes.


def test_main_pass_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = write(tmp_path, "ledger.json", make_ledger(make_claim(), make_unavailable()))
    assert mod.main(["--ledger", str(ledger)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["decision"] == "activate"
    assert out["claims"] == 2
    assert out["dispositions"] == {"removed": 1, "verified": 1}
    assert out["defects"] == []
    assert out["ledger"] == str(ledger)
    assert out["artifact"] is None


def test_main_defects_exit_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = write(tmp_path, "ledger.json", make_ledger(make_claim(confidence="low")))
    assert mod.main(["--ledger", str(ledger)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert out["defects"]


def test_main_with_artifact(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = write(tmp_path, "ledger.json", make_ledger(make_claim()))
    artifact = write(tmp_path, "a.md", "Draft only.")
    assert mod.main(["--ledger", str(ledger), "--artifact", str(artifact)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["artifact"] == str(artifact)
    assert any("absent" in e for e in out["defects"])


def test_main_list_disposition_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = write(tmp_path, "ledger.json", make_ledger(make_claim(disposition=["verified"])))
    assert mod.main(["--ledger", str(ledger)]) == 1
    assert json.loads(capsys.readouterr().out)["dispositions"] == {}


def test_main_bad_json_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = write(tmp_path, "ledger.json", "{not json")
    assert mod.main(["--ledger", str(ledger)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_main_missing_file_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert mod.main(["--ledger", str(tmp_path / "absent.json")]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_main_missing_artifact_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ledger = write(tmp_path, "ledger.json", make_ledger(make_claim()))
    assert mod.main(["--ledger", str(ledger), "--artifact", str(tmp_path / "x.md")]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_main_bad_arguments_exit_2() -> None:
    with pytest.raises(SystemExit) as exc:
        mod.main([])
    assert exc.value.code == 2


def test_script_runs_as_a_program(tmp_path: Path) -> None:
    ledger = write(tmp_path, "ledger.json", make_ledger(make_claim()))
    result = subprocess.run(
        [sys.executable, mod.__file__, "--ledger", str(ledger)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout)["ok"] is True
