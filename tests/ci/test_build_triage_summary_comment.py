"""Tests for scripts/ci/build_triage_summary_comment.py (issue #2967).

The "Post Triage Summary" step in .github/workflows/ai-issue-triage.yml built
its comment inline in a PowerShell here-string (ADR-006 violation). The logic
now lives in the module under test. These tests prove behavior is preserved
byte-for-byte: the golden fixtures under fixtures/triage_summary/ were captured
by running the original PowerShell block under pwsh 7 across representative
inputs, and test_byte_exactness_matches_original_powershell drives main() with
the same inputs and asserts the written bytes are identical.

Regenerate a golden by running the original step's assembly script under pwsh
with the scenario's env plus the three /tmp analysis files, then capturing
/tmp/triage-comment.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add scripts/ci to path for import.
_SCRIPTS_CI = Path(__file__).resolve().parent.parent.parent / "scripts" / "ci"
sys.path.insert(0, str(_SCRIPTS_CI))

from build_triage_summary_comment import (  # noqa: E402
    build_triage_comment,
    main,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "triage_summary"

# Baseline kwargs for the pure builder: no optional rows, no analysis output.
_BASE = {
    "category": "bug",
    "labels": "",
    "priority": "P3",
    "milestone": "",
    "escalate_to_prd": "false",
    "feature_review": "UNKNOWN",
    "repository": "rjmurillo/ai-agents2",
    "categorize_output": "N/A",
    "align_output": "N/A",
    "feature_review_output": "",
}


def _build(**overrides: str) -> str:
    return build_triage_comment(**{**_BASE, **overrides})


# --- Byte-exactness against the original PowerShell output ------------------

# Scenario inputs that produced each committed golden fixture.
_SCENARIOS = {
    "full": {
        "env": {"CATEGORY": "bug", "LABELS": '["bug","docs"]', "PRIORITY": "P1",
                "MILESTONE": "v1.0", "ESCALATE_TO_PRD": "true",
                "FEATURE_REVIEW": "APPROVE",
                "GITHUB_REPOSITORY": "rjmurillo/ai-agents2"},
        "categorize": '{"category":"bug","labels":["bug","docs"]}\n',
        "align": '{"priority":"P1","milestone":"v1.0"}\n',
        "feature": "Feature looks reasonable. Approve.\n",
    },
    "minimal": {
        "env": {"CATEGORY": "question", "LABELS": "", "PRIORITY": "P3",
                "MILESTONE": "", "ESCALATE_TO_PRD": "false",
                "FEATURE_REVIEW": "UNKNOWN",
                "GITHUB_REPOSITORY": "rjmurillo/ai-agents2"},
        "categorize": None,
        "align": None,
        "feature": None,
    },
    "prd_uppercase_no_feature": {
        "env": {"CATEGORY": "enhancement", "LABELS": "[]", "PRIORITY": "P0",
                "MILESTONE": "backlog", "ESCALATE_TO_PRD": "TRUE",
                "FEATURE_REVIEW": "",
                "GITHUB_REPOSITORY": "rjmurillo/ai-agents2"},
        "categorize": '{"category":"enhancement"}\n',
        "align": '{"priority":"P0"}\n',
        "feature": None,
    },
    "feature_lowercase_unknown_no_prd": {
        "env": {"CATEGORY": "enhancement", "LABELS": '["enhancement"]',
                "PRIORITY": "P2", "MILESTONE": "v2.0", "ESCALATE_TO_PRD": "false",
                "FEATURE_REVIEW": "unknown",
                "GITHUB_REPOSITORY": "rjmurillo/ai-agents2"},
        "categorize": '{"category":"enhancement"}\n',
        "align": '{"priority":"P2","milestone":"v2.0"}\n',
        "feature": "Some reviewer notes here.\n",
    },
}

_ENV_KEYS = {"CATEGORY", "LABELS", "PRIORITY", "MILESTONE", "ESCALATE_TO_PRD",
             "FEATURE_REVIEW", "GITHUB_REPOSITORY"}


@pytest.mark.parametrize("name", sorted(_SCENARIOS))
def test_byte_exactness_matches_original_powershell(name, monkeypatch, tmp_path):
    spec = _SCENARIOS[name]
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, val in spec["env"].items():
        monkeypatch.setenv(key, val)

    # Redirect the fixed /tmp analysis paths into tmp_path so the test is
    # isolated and never touches global /tmp state.
    import build_triage_summary_comment as mod

    for const, key in (("_CATEGORIZE_FILE", "categorize"),
                       ("_ALIGN_FILE", "align"),
                       ("_FEATURE_REVIEW_FILE", "feature")):
        target = tmp_path / f"{key}.txt"
        if spec[key] is not None:
            target.write_text(spec[key], encoding="utf-8")
        monkeypatch.setattr(mod, const, str(target))

    out = tmp_path / "triage-comment.md"
    exit_code = main(["--output", str(out)])

    assert exit_code == 0
    assert out.read_bytes() == (_FIXTURES / f"{name}.golden").read_bytes()


def test_golden_output_is_utf8_no_bom_with_trailing_newline():
    data = (_FIXTURES / "full.golden").read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf")
    assert data.endswith(b"</sub>\n")


# --- Positive: optional rows and block render when their inputs are present --


def test_prd_row_present_when_escalated():
    assert "| **PRD Escalation** | Generated (see below) |" in _build(
        escalate_to_prd="true"
    )


def test_prd_row_case_insensitive_like_powershell_eq():
    # PowerShell `-eq 'true'` is case-insensitive; TRUE must still show the row.
    assert "PRD Escalation" in _build(escalate_to_prd="TRUE")


def test_feature_review_row_present_for_real_recommendation():
    assert "| **Feature Review** | `APPROVE` |" in _build(feature_review="APPROVE")


def test_feature_block_present_when_output_nonempty():
    body = _build(feature_review_output="Reviewer notes.")
    assert "<summary>Feature Request Review</summary>" in body
    assert "Reviewer notes." in body


def test_labels_and_milestone_display_raw_values_when_set():
    body = _build(labels='["bug"]', milestone="v1.0")
    assert "| **Labels** | [\"bug\"] |" in body
    assert "| **Milestone** | v1.0 |" in body


def test_empty_labels_json_array_is_shown_verbatim():
    # "[]" is a non-empty string, so PowerShell `if ($env:LABELS)` is truthy.
    assert "| **Labels** | [] |" in _build(labels="[]")


# --- Negative: optional rows and block absent when inputs empty/UNKNOWN ------


def test_prd_row_absent_when_not_escalated():
    assert "PRD Escalation" not in _build(escalate_to_prd="false")


def test_feature_review_row_absent_when_unknown():
    assert "Feature Review" not in _build(feature_review="UNKNOWN")


def test_feature_review_row_absent_when_lowercase_unknown():
    # `-ne 'UNKNOWN'` is case-insensitive; lowercase unknown hides the row too.
    assert "Feature Review" not in _build(feature_review="unknown")


def test_feature_review_row_absent_when_empty():
    assert "Feature Review" not in _build(feature_review="")


def test_feature_block_absent_when_output_empty():
    assert "Feature Request Review" not in _build(feature_review_output="")


def test_none_assigned_placeholders_when_labels_and_milestone_empty():
    body = _build(labels="", milestone="")
    assert "| **Labels** | *None assigned* |" in body
    assert "| **Milestone** | *Not assigned* |" in body


# --- Edge: preserved PowerShell quirks --------------------------------------


def test_priority_cell_keeps_two_leading_spaces():
    # The original switch mapped every priority to "", leaving a double space.
    assert "|  **Priority** | `P1` |" in _build(priority="P1")


def test_row_hidden_but_block_shown_are_independent():
    # Row keys on FEATURE_REVIEW; block keys on the file content. They differ.
    body = _build(feature_review="unknown", feature_review_output="Notes.")
    assert "| **Feature Review**" not in body
    assert "<summary>Feature Request Review</summary>" in body


def test_analysis_output_trailing_newline_is_preserved_in_fence():
    # Get-Content -Raw kept the file's trailing newline, adding a blank line
    # before the closing fence. The module must not strip it.
    body = _build(categorize_output='{"a":1}\n')
    assert '```json\n{"a":1}\n\n```' in body


def test_builder_returns_without_trailing_newline():
    # The builder returns the here-string value; the CLI adds Set-Content's \n.
    assert not _build().endswith("\n")


# --- CLI contract -----------------------------------------------------------


def test_main_writes_default_output_and_returns_zero(monkeypatch, tmp_path):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CATEGORY", "bug")
    import build_triage_summary_comment as mod

    for const in ("_CATEGORIZE_FILE", "_ALIGN_FILE", "_FEATURE_REVIEW_FILE"):
        monkeypatch.setattr(mod, const, str(tmp_path / "absent.txt"))

    out = tmp_path / "comment.md"
    assert main(["--output", str(out)]) == 0
    written = out.read_bytes()
    assert written.endswith(b"\n")
    assert b"| **Category** | `bug` |" in written


def test_main_uses_na_default_when_analysis_files_absent(monkeypatch, tmp_path):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    import build_triage_summary_comment as mod

    for const in ("_CATEGORIZE_FILE", "_ALIGN_FILE", "_FEATURE_REVIEW_FILE"):
        monkeypatch.setattr(mod, const, str(tmp_path / "absent.txt"))

    out = tmp_path / "comment.md"
    main(["--output", str(out)])
    body = out.read_text(encoding="utf-8")
    assert "```json\nN/A\n```" in body


def test_main_rejects_unknown_flag():
    with pytest.raises(SystemExit) as exc:
        main(["--nope"])
    assert exc.value.code == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
