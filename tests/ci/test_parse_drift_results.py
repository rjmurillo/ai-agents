"""Tests for scripts/ci/parse_drift_results.py.

Covers the bug in issue #2381: the workflow's inline parse read snake_case keys
(agent_name, overall_similarity) while build/scripts/detect_agent_drift.py emits
camelCase (agentName, overallSimilarity), so the body came out empty. These tests
pin the camelCase contract and prove a snake_case-only payload yields no body.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add scripts/ci to path for import.
_SCRIPTS_CI = Path(__file__).resolve().parent.parent.parent / "scripts" / "ci"
sys.path.insert(0, str(_SCRIPTS_CI))

from parse_drift_results import build_drift_details, main  # noqa: E402


def _drift_payload() -> dict:
    """A camelCase payload shaped like detect_agent_drift.py:format_json output."""
    return {
        "summary": {"totalAgents": 2, "ok": 1, "driftDetected": 1, "noCounterpart": 0},
        "results": [
            {
                "agentName": "implementer",
                "overallSimilarity": 62,
                "status": "DRIFT DETECTED",
                "driftingSections": ["Tools", "Workflow"],
                "sections": [
                    {"section": "Tools", "similarity": 40, "status": "DRIFT"},
                    {"section": "Workflow", "similarity": 55, "status": "DRIFT"},
                    {"section": "Header", "similarity": 99, "status": "OK"},
                ],
            },
            {
                "agentName": "architect",
                "overallSimilarity": 98,
                "status": "OK",
                "driftingSections": [],
                "sections": [],
            },
        ],
    }


def test_build_details_includes_only_drifting_agents() -> None:
    # Arrange
    results = _drift_payload()

    # Act
    body, count = build_drift_details(results)

    # Assert
    assert count == 1
    assert "### implementer" in body
    assert "### architect" not in body


def test_build_details_renders_similarity_and_sections() -> None:
    # Arrange
    results = _drift_payload()

    # Act
    body, _ = build_drift_details(results)

    # Assert
    assert "- **Overall similarity**: 62%" in body
    assert "- **Drifting sections**: Tools, Workflow" in body
    assert "**Section Details:**" in body
    assert "- Tools: 40% similar" in body
    assert "- Workflow: 55% similar" in body
    # OK section must not appear in section details.
    assert "Header" not in body


def test_build_details_empty_when_no_drift() -> None:
    # Arrange
    results = {
        "summary": {"driftDetected": 0},
        "results": [{"agentName": "x", "overallSimilarity": 99, "status": "OK"}],
    }

    # Act
    body, count = build_drift_details(results)

    # Assert
    assert body == ""
    assert count == 0


def test_snake_case_payload_fails_loud_not_silent() -> None:
    # Arrange: the pre-fix emitter contract bug, snake_case keys only. The
    # agent status matches, so a drifting agent is selected for rendering, but
    # the camelCase agentName key is absent. The fix turns this into a loud
    # KeyError instead of the silent empty body the old inline parse produced.
    snake = {
        "summary": {"drift_detected": 1},
        "results": [
            {
                "agent_name": "implementer",
                "overall_similarity": 62,
                "status": "DRIFT DETECTED",
            }
        ],
    }

    # Act / Assert
    with pytest.raises(KeyError):
        build_drift_details(snake)


def test_main_writes_details_and_count(tmp_path: Path) -> None:
    # Arrange
    input_path = tmp_path / "drift-results.json"
    input_path.write_text(json.dumps(_drift_payload()), encoding="utf-8")
    details_out = tmp_path / "drift-details.md"
    count_out = tmp_path / "drift-count.txt"

    # Act
    exit_code = main(
        [
            "--input",
            str(input_path),
            "--details-out",
            str(details_out),
            "--count-out",
            str(count_out),
        ]
    )

    # Assert
    assert exit_code == 0
    assert "### implementer" in details_out.read_text(encoding="utf-8")
    assert count_out.read_text(encoding="utf-8") == "1"


def test_main_exits_2_when_input_missing(tmp_path: Path) -> None:
    # Arrange
    missing = tmp_path / "nope.json"

    # Act / Assert
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--input",
                str(missing),
                "--details-out",
                str(tmp_path / "d.md"),
                "--count-out",
                str(tmp_path / "c.txt"),
            ]
        )
    assert exc.value.code == 2


def test_main_exits_1_on_invalid_json(tmp_path: Path) -> None:
    # Arrange
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    # Act / Assert
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--input",
                str(bad),
                "--details-out",
                str(tmp_path / "d.md"),
                "--count-out",
                str(tmp_path / "c.txt"),
            ]
        )
    assert exc.value.code == 1


def test_main_exits_1_on_missing_key(tmp_path: Path) -> None:
    # Arrange: drifting agent missing the camelCase overallSimilarity key.
    payload = {
        "summary": {"driftDetected": 1},
        "results": [{"agentName": "implementer", "status": "DRIFT DETECTED"}],
    }
    input_path = tmp_path / "drift-results.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    # Act
    exit_code = main(
        [
            "--input",
            str(input_path),
            "--details-out",
            str(tmp_path / "d.md"),
            "--count-out",
            str(tmp_path / "c.txt"),
        ]
    )

    # Assert
    assert exit_code == 1
