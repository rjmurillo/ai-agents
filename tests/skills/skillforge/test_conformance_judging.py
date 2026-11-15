"""The guideline rules conformance.py cannot check are judged by a model, with grounded quotes.

conformance.py never calls a model. It prints a packet of the unjudged rules,
and it imports verdicts only when every quote appears verbatim in the skill's
own files. One bad verdict rejects the whole file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.skills.skillforge.conformance_support import conformance, make_skill

BODY = "# Release notes\n\n## Gotchas\n\nThe changelog tool skips merge commits by default.\n"
QUOTE = "The changelog tool skips merge commits by default."


@pytest.fixture
def skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return make_skill(
        tmp_path, body=BODY, files={"references/guide.md": "# Guide\n\nRead me when releasing.\n"}
    )


def _packet(capsys: pytest.CaptureFixture[str], *extra: str) -> dict[str, Any]:
    assert conformance.main(["release-notes", "--judge-packet", *extra]) == 0
    return json.loads(capsys.readouterr().out)


def _judge(tmp_path: Path, judgments: list[dict[str, Any]], *extra: str) -> int:
    path = tmp_path / "judgments.json"
    path.write_text(json.dumps({"judgments": judgments}), encoding="utf-8")
    return conformance.main(["release-notes", "--judgments", str(path), "--format", "json", *extra])


def _status(capsys: pytest.CaptureFixture[str], rule_id: str) -> dict[str, Any]:
    payload = json.loads(capsys.readouterr().out)
    return next(r for r in payload["skills"][0]["results"] if r["id"] == rule_id)


def _verdict(
    verdict: str, quote: str = QUOTE, file: str = "SKILL.md", rule: str = "practice.gotchas"
) -> dict[str, Any]:
    evidence = [] if verdict == "unknown" else [{"file": file, "quote": quote}]
    return {
        "id": rule,
        "verdict": verdict,
        "reason": "Judged from the files.",
        "evidence": evidence,
    }


class TestPacket:
    def test_packet_lists_only_unjudged_guidelines_and_the_skill_files(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        packet = _packet(capsys)

        ids = {rule["id"] for rule in packet["rules"]}
        assert "practice.gotchas" in ids and "spec.name.charset" not in ids
        assert ids == {rule.id for rule in conformance.RULES if rule.manual}
        assert packet["files"] == ["SKILL.md", "references/guide.md"]
        assert "verbatim" in packet["instructions"]

    def test_project_profile_leaves_declared_deviations_out(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ids = {rule["id"] for rule in _packet(capsys, "--profile", "project")["rules"]}

        assert "scripts.relative-paths" not in ids
        assert "scripts.inline-dependencies" not in ids

    def test_packet_takes_exactly_one_skill(self, skill: Path) -> None:
        make_skill(skill.parent, "other-notes")

        with pytest.raises(SystemExit) as exit_info:
            conformance.main(["release-notes", "other-notes", "--judge-packet"])

        assert exit_info.value.code == 2


class TestApplying:
    def test_grounded_pass_becomes_judged_pass(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = _judge(skill.parent, [_verdict("pass")])

        result = _status(capsys, "practice.gotchas")
        assert code == 0
        assert result["status"] == "JUDGED_PASS"
        assert QUOTE in result["problems"][0]

    def test_reflowed_quote_still_matches(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        reflowed = "The changelog tool\n   skips merge commits\tby default."

        assert _judge(skill.parent, [_verdict("pass", quote=reflowed)]) == 0
        assert _status(capsys, "practice.gotchas")["status"] == "JUDGED_PASS"

    def test_unknown_needs_no_quote_and_never_passes(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = _judge(skill.parent, [_verdict("unknown", rule="evals.baseline")])

        assert code == 0
        assert _status(capsys, "evals.baseline")["status"] == "JUDGED_UNKNOWN"

    def test_judged_fail_fails_only_under_strict(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert _judge(skill.parent, [_verdict("fail")]) == 0
        assert _status(capsys, "practice.gotchas")["status"] == "JUDGED_FAIL"

        assert _judge(skill.parent, [_verdict("fail")], "--strict") == 1


class TestRejecting:
    @pytest.mark.parametrize(
        ("judgment", "message"),
        [
            (_verdict("pass", quote="An invented sentence about tools."), "not found verbatim"),
            (_verdict("pass", quote="Gotchas"), "at least 12 characters"),
            (_verdict("pass", file="../outside.md"), "not a text file in the skill"),
            (_verdict("pass", file="missing.md"), "not a text file in the skill"),
            (_verdict("pass", rule="no.such-rule"), "not an unjudged guideline rule"),
            (_verdict("pass", rule="spec.name.charset"), "not an unjudged guideline rule"),
            ({**_verdict("pass"), "evidence": []}, "needs at least one quote"),
            ({**_verdict("pass"), "verdict": "maybe"}, "pass, fail, or unknown"),
            ({**_verdict("pass"), "reason": " "}, "reason must be a non-empty string"),
        ],
    )
    def test_bad_verdict_rejects_the_whole_file(
        self,
        skill: Path,
        capsys: pytest.CaptureFixture[str],
        judgment: dict[str, Any],
        message: str,
    ) -> None:
        good = _verdict("unknown", rule="evals.baseline")

        code = _judge(skill.parent, [good, judgment])

        captured = capsys.readouterr()
        assert code == 2
        assert message in captured.err
        assert "nothing applied" in captured.err
        assert captured.out == ""

    def test_duplicate_rule_is_rejected(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert _judge(skill.parent, [_verdict("pass"), _verdict("fail")]) == 2
        assert "more than once" in capsys.readouterr().err

    @pytest.mark.parametrize("text", ["{not json", '{"verdicts": []}', "[]"])
    def test_malformed_file_is_rejected(
        self, skill: Path, capsys: pytest.CaptureFixture[str], text: str
    ) -> None:
        path = skill.parent / "judgments.json"
        path.write_text(text, encoding="utf-8")

        assert conformance.main(["release-notes", "--judgments", str(path)]) == 2
        assert "nothing applied" in capsys.readouterr().err

    @pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
    def test_file_outside_the_root_cannot_be_quoted(
        self,
        skill: Path,
        capsys: pytest.CaptureFixture[str],
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        outside = tmp_path_factory.mktemp("outside") / "secret.md"
        outside.write_text("An outside sentence that should never count.\n", encoding="utf-8")
        try:
            (skill / "references" / "secret.md").symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"cannot create a symlink here: {exc}")

        judgment = _verdict(
            "pass",
            quote="An outside sentence that should never count.",
            file="references/secret.md",
        )

        assert _judge(skill.parent, [judgment]) == 2
        assert "not a text file in the skill" in capsys.readouterr().err
