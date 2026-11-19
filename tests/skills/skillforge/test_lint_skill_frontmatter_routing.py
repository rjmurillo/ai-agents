"""Tests for lint_skill_frontmatter.py: routing, Handoff, description, and CLI rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.skills.skillforge.lint_support import (  # noqa: F401
    _DESCRIPTION,
    _REPO_ROOT,
    _SKILLS_TREE,
    RULE_IDS,
    _lint,
    _messages,
    _skill_text,
    _write_skill,
    lint,
)


def test_intents_on_conditional_adjunct_role_fail(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = "  routing:\n    role: conditional-adjunct\n    intents:\n      - schema design\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 1
    assert rows["fm.routing.intents-role"]["status"] == "FAIL"
    assert "front-door" in _messages(rows["fm.routing.intents-role"])


def test_intents_on_front_door_role_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = "  routing:\n    role: front-door\n    intents:\n      - schema design\n"

    _, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert rows["fm.routing.intents-role"]["status"] == "PASS"


_FRONT_DOOR = "  routing:\n    role: front-door\n    intents:\n      - {intent}\n"


def test_trigger_phrase_with_wrong_token_order_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    description = "Use when you say `design this schema`. Do NOT use for other work."
    metadata = _FRONT_DOOR.format(intent="schema design")

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata, description=description))

    assert code == 0
    assert rows["fm.routing.phrases-routable"]["status"] == "WARN"
    assert "'design this schema'" in _messages(rows["fm.routing.phrases-routable"])


def test_trigger_phrase_matching_an_intent_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    description = "Use when you say `design this schema`. Do NOT use for other work."
    metadata = _FRONT_DOOR.format(intent="design this schema")

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata, description=description))

    assert code == 0
    assert rows["fm.routing.phrases-routable"]["status"] == "PASS"


def test_slash_name_trigger_phrase_is_skipped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    description = "Use when you say `/demo run`. Do NOT use for other work."
    metadata = _FRONT_DOOR.format(intent="schema design")

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata, description=description))

    assert code == 0
    assert rows["fm.routing.phrases-routable"]["status"] == "PASS"


def test_phrases_rule_not_applicable_without_intents(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    description = "Use when you say `design this schema`. Do NOT use for other work."

    code, rows = _lint(tmp_path, capsys, _skill_text(description=description))

    assert code == 0
    assert rows["fm.routing.phrases-routable"]["status"] == "NOT_APPLICABLE"


def test_intents_without_any_quoted_phrases_warn(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = _FRONT_DOOR.format(intent="schema design")

    code, rows = _lint(tmp_path, capsys, _skill_text(metadata))

    assert code == 0
    assert rows["fm.routing.phrases-routable"]["status"] == "WARN"
    assert "no" in _messages(rows["fm.routing.phrases-routable"])


def test_malformed_writes_handoff_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    body = "## Handoff\n\nWrites: plan. Next: build.\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(body=body))

    assert code == 1
    assert rows["fm.handoff.shape"]["status"] == "FAIL"
    assert "Writes:" in _messages(rows["fm.handoff.shape"])


def test_well_formed_writes_handoff_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "## Handoff\n\nWrites: `plan.md`, `notes.md`. Next: `/build`.\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(body=body))

    assert code == 0
    assert rows["fm.handoff.shape"]["status"] == "PASS"


def test_prose_handoff_section_is_not_applicable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "## Handoff\n\nHand the result back to the user.\n"

    code, rows = _lint(tmp_path, capsys, _skill_text(body=body))

    assert code == 0
    assert rows["fm.handoff.shape"]["status"] == "NOT_APPLICABLE"


def test_description_without_redirect_warns(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, rows = _lint(tmp_path, capsys, _skill_text(description="Demo skill that does a thing."))

    assert code == 0
    assert rows["fm.description.redirect"]["status"] == "WARN"
    assert "Do NOT use" in _messages(rows["fm.description.redirect"])


@pytest.mark.parametrize("phrase", ["Do NOT use for x.", "Not for x."])
def test_description_with_redirect_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], phrase: str
) -> None:
    code, rows = _lint(tmp_path, capsys, _skill_text(description=f"Demo skill. {phrase}"))

    assert code == 0
    assert rows["fm.description.redirect"]["status"] == "PASS"


def test_description_redirect_not_applicable_when_not_user_facing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata = "  routing:\n    user-facing: false\n"

    code, rows = _lint(
        tmp_path, capsys, _skill_text(metadata, description="Demo skill that does a thing.")
    )

    assert code == 0
    assert rows["fm.description.redirect"]["status"] == "NOT_APPLICABLE"


def test_missing_skill_md_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()

    code = lint.main([str(skill_dir), "--root", str(tmp_path), "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    statuses = {row["id"]: row["status"] for row in payload["skills"][0]["results"]}
    assert code == 1
    assert statuses["fm.subset-parse"] == "NOT_EVALUATED"


def test_text_format_lists_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    skill_dir = _write_skill(tmp_path, _skill_text("  capability:\n    kind: wizard\n"))

    code = lint.main([str(skill_dir), "--root", str(tmp_path)])

    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL" in out
    assert "fm.capability.shape" in out


def test_no_skill_dir_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        lint.main([])

    assert excinfo.value.code == 2
    assert "SKILL_DIR" in capsys.readouterr().err


def test_path_outside_root_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SKILL.md").write_text(_skill_text(), encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        lint.main([str(outside), "--root", str(root)])

    assert excinfo.value.code == 2
    assert "outside the root" in capsys.readouterr().err


def test_root_that_is_not_a_directory_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill_dir = _write_skill(tmp_path, _skill_text())
    not_a_dir = tmp_path / "missing"

    with pytest.raises(SystemExit) as excinfo:
        lint.main([str(skill_dir), "--root", str(not_a_dir)])

    assert excinfo.value.code == 2
    assert "--root is not a directory" in capsys.readouterr().err


def test_missing_skill_dir_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        lint.main([str(tmp_path / "nope"), "--root", str(tmp_path)])

    assert excinfo.value.code == 2
    assert "not a directory" in capsys.readouterr().err


def test_list_prints_all_nine_rule_ids_as_text(capsys: pytest.CaptureFixture[str]) -> None:
    code = lint.main(["--list"])

    out = capsys.readouterr().out
    assert code == 0
    assert [line.split()[0] for line in out.splitlines()] == list(RULE_IDS)


def test_list_prints_all_nine_rule_ids_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = lint.main(["--list", "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert [row["id"] for row in payload["rules"]] == list(RULE_IDS)
    assert {row["level"] for row in payload["rules"]} == {"MUST", "SHOULD"}


def test_every_shipped_skill_has_no_must_failure(capsys: pytest.CaptureFixture[str]) -> None:
    skill_dirs = sorted(p for p in _SKILLS_TREE.iterdir() if (p / "SKILL.md").is_file())

    code = lint.main([*(str(p) for p in skill_dirs), "--root", str(_REPO_ROOT), "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    failures = {
        Path(skill["path"]).name: [
            f"{row['id']}: {row['status']}"
            for row in skill["results"]
            if row["status"] == "FAIL"
            or (row["status"] == "NOT_EVALUATED" and row["level"] == "MUST")
        ]
        for skill in payload["skills"]
    }
    failures = {name: rows for name, rows in failures.items() if rows}
    assert len(skill_dirs) > 100, f"examined only {len(skill_dirs)} skills"
    assert len(payload["skills"]) == len(skill_dirs)
    assert failures == {}
    assert code == 0
