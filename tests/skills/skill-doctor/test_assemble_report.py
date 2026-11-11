"""Tests for assemble_report: report.json built from recomputed scores (epic #7248, M3/M4)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import assemble_report
import audit_scores
import pytest

INPUTS = Path(__file__).resolve().parent / "fixtures" / "audit" / "reproduction"


def load(name: str) -> Any:
    return json.loads((INPUTS / name).read_text(encoding="utf-8"))


def write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run(tmp_path: Path, *extra: str, draft: Any = None, scores: Any = None) -> tuple[int, Path]:
    out = tmp_path / "report.json"
    argv = [
        str(write(tmp_path / "draft.json", load("draft.json") if draft is None else draft)),
        "--scores",
        str(write(tmp_path / "scores.json", load("scores.json") if scores is None else scores)),
        "--out",
        str(out),
        *extra,
    ]
    return assemble_report.main(argv), out


def test_report_scores_come_from_the_recomputed_artifact(tmp_path: Path) -> None:
    code, out = run(tmp_path)

    report = json.loads(out.read_text(encoding="utf-8"))
    artifact = audit_scores.build_artifact(load("scores.json")["sessions"])
    assert code == 0
    for key in audit_scores.WEIGHTS:
        assert report["scores"][key] == artifact["dimensions"][key]["score"]
    assert report["scores"]["overall"] == artifact["overall"]
    assert report["stats"]["sessions_analyzed"] == 6
    assert report["audit"]["scores"] == artifact
    assert [r["session_id"] for r in report["audit"]["records"]] == [
        s["session_id"] for s in load("scores.json")["sessions"]
    ]


def test_per_harness_overall_is_scored_on_each_harness_alone(tmp_path: Path) -> None:
    _, out = run(tmp_path)

    report = json.loads(out.read_text(encoding="utf-8"))
    per_harness = report["sampling"]["per_harness"]
    sessions = load("scores.json")["sessions"]
    codex = [s for s in sessions if s["harness"] == "codex"]
    assert per_harness["codex"]["overall"] == audit_scores.aggregate(codex)["overall"]
    assert per_harness["codex"]["scoreable"] == 8
    assert per_harness["copilot"]["sampled"] == 3


def test_stale_grade_in_the_draft_is_dropped(tmp_path: Path) -> None:
    draft = {**load("draft.json"), "grade": "F", "scores": {"overall": 0.1}}

    code, out = run(tmp_path, draft=draft)

    report = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert "grade" not in report
    assert report["scores"]["overall"] > 0.8


def test_manifest_catalog_is_copied_into_audit(tmp_path: Path) -> None:
    code, out = run(tmp_path, "--manifest", str(INPUTS / "audit_manifest.json"))

    report = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert report["audit"]["catalog"] == load("audit_manifest.json")["catalog"]


def test_without_a_manifest_no_catalog_is_invented(tmp_path: Path) -> None:
    _, out = run(tmp_path)

    assert "catalog" not in json.loads(out.read_text(encoding="utf-8"))["audit"]


def test_matching_artifact_is_accepted(tmp_path: Path) -> None:
    artifact = audit_scores.build_artifact(load("scores.json")["sessions"])

    code, _ = run(tmp_path, "--artifact", str(write(tmp_path / "artifact.json", artifact)))

    assert code == 0


def test_artifact_that_does_not_recompute_exits_1_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    artifact = audit_scores.build_artifact(load("scores.json")["sessions"])
    artifact["overall"] += 0.01

    code, out = run(tmp_path, "--artifact", str(write(tmp_path / "artifact.json", artifact)))

    assert code == 1
    assert not out.exists()
    assert "does not recompute" in capsys.readouterr().err


def test_invalid_scores_exit_1_and_write_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scores = copy.deepcopy(load("scores.json"))
    scores["sessions"][0]["scores"]["efficiency"]["score"] = 0.5

    code, out = run(tmp_path, scores=scores)

    assert code == 1
    assert not out.exists()
    assert "requires score" in capsys.readouterr().err


def test_empty_scores_exit_1(tmp_path: Path) -> None:
    code, out = run(tmp_path, scores={"sessions": []})

    assert code == 1
    assert not out.exists()


def test_draft_that_is_not_an_object_exits_1(tmp_path: Path) -> None:
    code, out = run(tmp_path, draft=["not", "an", "object"])

    assert code == 1
    assert not out.exists()


def test_manifest_without_catalog_exits_1(tmp_path: Path) -> None:
    manifest = write(tmp_path / "manifest.json", {"scope": {}})

    code, out = run(tmp_path, "--manifest", str(manifest))

    assert code == 1
    assert not out.exists()


def test_unsupported_evaluation_claim_in_the_draft_exits_1(tmp_path: Path) -> None:
    draft = copy.deepcopy(load("draft.json"))
    draft["suggestions"][0]["status"] = "accepted"

    code, out = run(tmp_path, draft=draft)

    assert code == 1
    assert not out.exists()


def test_failed_run_keeps_the_previous_report(tmp_path: Path) -> None:
    code, out = run(tmp_path)
    before = out.read_bytes()

    second, _ = run(tmp_path, scores={"sessions": []})

    assert (code, second) == (0, 1)
    assert out.read_bytes() == before


def test_unreadable_input_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "scores.json"
    bad.write_text("{not json", encoding="utf-8")

    code = assemble_report.main(
        [str(INPUTS / "draft.json"), "--scores", str(bad), "--out", str(tmp_path / "r.json")]
    )

    assert code == 2


def test_missing_file_exits_2(tmp_path: Path) -> None:
    code = assemble_report.main(
        [
            str(tmp_path / "absent.json"),
            "--scores",
            str(INPUTS / "scores.json"),
            "--out",
            str(tmp_path / "r.json"),
        ]
    )

    assert code == 2


def test_missing_out_argument_exits_2() -> None:
    assert assemble_report.main([str(INPUTS / "draft.json"), "--scores", "x.json"]) == 2


def test_unscored_harness_keeps_no_overall_from_the_draft(tmp_path: Path) -> None:
    draft = copy.deepcopy(load("draft.json"))
    draft["sampling"]["per_harness"]["claude"] = {"scoreable": 2, "sampled": 0, "overall": 0.0}

    code, out = run(tmp_path, draft=draft)

    per_harness = json.loads(out.read_text(encoding="utf-8"))["sampling"]["per_harness"]
    assert code == 0
    assert per_harness["claude"] == {"scoreable": 2, "sampled": 0}
    assert "overall" in per_harness["codex"]
