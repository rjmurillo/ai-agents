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


class TestReviewFindings:
    """Cases from the PR #7387 review: malformed input exits 2, never a traceback."""

    @pytest.mark.parametrize(
        ("judgment", "message"),
        [
            ({**_verdict("pass"), "id": []}, "is not an unjudged guideline rule"),
            ({**_verdict("pass"), "verdict": {}}, "pass, fail, or unknown"),
            (
                {**_verdict("pass"), "evidence": [{"file": "SKILL.md", "quote": 123456789012}]},
                "must both be strings",
            ),
            (
                {**_verdict("pass"), "evidence": [{"file": ["SKILL.md"], "quote": QUOTE}]},
                "must both be strings",
            ),
        ],
    )
    def test_non_string_fields_are_rejected_before_any_change(
        self,
        skill: Path,
        capsys: pytest.CaptureFixture[str],
        judgment: dict[str, Any],
        message: str,
    ) -> None:
        (skill / "references" / "digits.md").write_text(
            "Code 123456789012 here.\n", encoding="utf-8"
        )

        code = _judge(skill.parent, [judgment])

        captured = capsys.readouterr()
        assert code == 2
        assert message in captured.err
        assert captured.out == ""

    def test_repeated_array_ids_do_not_crash(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bad = {**_verdict("pass"), "id": ["practice.gotchas"]}

        assert _judge(skill.parent, [bad, bad]) == 2
        assert "is not an unjudged guideline rule" in capsys.readouterr().err

    def test_waived_judged_fail_does_not_fail_strict(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = _judge(skill.parent, [_verdict("fail")], "--strict", "--waive", "practice.gotchas")

        result = _status(capsys, "practice.gotchas")
        assert code == 0
        assert result["status"] == "WAIVED"
        assert "judged fail" in result["reason"] and QUOTE in result["problems"][0]

    def test_waiver_leaves_a_judged_pass_alone(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert _judge(skill.parent, [_verdict("pass")], "--waive", "practice.gotchas") == 0
        assert _status(capsys, "practice.gotchas")["status"] == "JUDGED_PASS"

    def test_every_recognized_script_type_is_in_the_packet_and_quotable(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        line = "console.error('release tag is missing');"
        (skill / "scripts").mkdir()
        (skill / "scripts" / "run.mjs").write_text(line + "\n", encoding="utf-8")

        assert "scripts/run.mjs" in _packet(capsys)["files"]
        assert _judge(skill.parent, [_verdict("pass", quote=line, file="scripts/run.mjs")]) == 0

    @pytest.mark.skipif(
        os.name == "nt" or os.geteuid() == 0, reason="needs POSIX permissions as non-root"
    )
    def test_unreadable_evidence_file_is_rejected_not_a_crash(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        locked = skill / "references" / "locked.md"
        locked.write_text("A sentence nobody may read here.\n", encoding="utf-8")
        locked.chmod(0)
        try:
            judgment = _verdict(
                "pass", quote="A sentence nobody may read here.", file="references/locked.md"
            )

            code = _judge(skill.parent, [judgment])
        finally:
            locked.chmod(0o644)

        assert code == 2
        assert "cannot read references/locked.md" in capsys.readouterr().err

    def test_judgments_file_in_the_skill_is_not_evidence(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        invented = "An invented sentence that only the judgments file holds."
        path = skill / "judgments.json"
        judgment = _verdict("pass", quote=invented, file="judgments.json")
        path.write_text(json.dumps({"judgments": [judgment]}), encoding="utf-8")

        code = conformance.main(["release-notes", "--judgments", str(path)])

        assert code == 2
        assert "judgments.json is not a text file in the skill" in capsys.readouterr().err

    def test_packet_states_the_quote_minimum(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert "at least 12 characters" in _packet(capsys)["instructions"]


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_looping_judgments_path_is_rejected_not_a_crash(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    loop = skill.parent / "loop.json"
    try:
        loop.symlink_to(loop)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")

    code = conformance.main(["release-notes", "--judgments", str(loop)])

    captured = capsys.readouterr()
    assert code == 2
    assert "nothing applied" in captured.err


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
def test_looping_file_in_the_skill_is_left_out_of_the_packet(
    skill: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    loop = skill / "references" / "loop.md"
    try:
        loop.symlink_to(loop)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")

    files = _packet(capsys)["files"]

    assert "references/loop.md" not in files
    assert "SKILL.md" in files


def test_resolution_error_on_the_judgments_path_is_rejected(
    skill: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Python 3.10 to 3.12 raise RuntimeError on a symlink loop; 3.13+ do not.

    Simulate the older behavior, so this test catches a crash on hosts the
    shipped script supports even when the suite runs on a newer Python.
    """
    import os.path
    import pathlib

    target = skill.parent / "loop.json"
    real_resolve, real_realpath = pathlib.Path.resolve, os.path.realpath

    def resolve(self: pathlib.Path, strict: bool = False) -> pathlib.Path:
        if self.name == "loop.json":
            raise RuntimeError(f"Symlink loop from {self}")
        return real_resolve(self, strict=strict)

    def realpath(path: Any, *args: Any, **kwargs: Any) -> str:
        if os.fspath(path).endswith("loop.json"):
            raise RuntimeError(f"Symlink loop from {path}")
        return real_realpath(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "resolve", resolve)
    monkeypatch.setattr(os.path, "realpath", realpath)

    code = conformance.main(["release-notes", "--judgments", str(target)])

    assert code == 2
    assert "nothing applied" in capsys.readouterr().err


class TestSecondReview:
    """Cases from the second PR #7387 review."""

    def test_hard_link_to_the_judgments_file_is_not_evidence(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        invented = "An invented sentence held only by the judgments file."
        path = skill.parent / "judgments.json"
        judgment = _verdict("pass", quote=invented, file="references/evidence.json")
        path.write_text(json.dumps({"judgments": [judgment]}), encoding="utf-8")
        try:
            os.link(path, skill / "references" / "evidence.json")
        except OSError as exc:
            pytest.skip(f"cannot create a hard link here: {exc}")

        code = conformance.main(["release-notes", "--judgments", str(path)])

        assert code == 2
        assert "references/evidence.json is not a text file in the skill" in capsys.readouterr().err

    @pytest.mark.skipif(not hasattr(os, "symlink"), reason="needs symlinks")
    def test_file_swapped_for_an_outside_symlink_after_listing_is_rejected(
        self,
        skill: Path,
        capsys: pytest.CaptureFixture[str],
        tmp_path_factory: pytest.TempPathFactory,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        guide = skill / "references" / "guide.md"
        outside = tmp_path_factory.mktemp("outside") / "secret.md"
        outside.write_text("An outside sentence that must never count.\n", encoding="utf-8")
        files = conformance.__dict__["skill_files"]

        def listed_then_swapped(*args: Any, **kwargs: Any) -> list[str]:
            listed = files(*args, **kwargs)
            guide.unlink()
            guide.symlink_to(outside)
            return listed

        monkeypatch.setattr(conformance, "skill_files", listed_then_swapped)
        judgment = _verdict(
            "pass", quote="An outside sentence that must never count.", file="references/guide.md"
        )

        assert _judge(skill.parent, [judgment]) == 2
        assert "references/guide.md is not a text file in the skill" in capsys.readouterr().err

    def test_packet_and_judgments_flags_are_exclusive(self, skill: Path) -> None:
        with pytest.raises(SystemExit) as exit_info:
            conformance.main(["release-notes", "--judge-packet", "--judgments", "missing.json"])

        assert exit_info.value.code == 2
