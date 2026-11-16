"""Judgment import against swaps around the read and failed identity lookups.

Split from test_conformance_judging.py to keep each file under 500 lines.
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
# The judging module's namespace, where the import calls open and file_id.
JUDGING = conformance.apply_judgments_file.__globals__


@pytest.fixture
def skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return make_skill(
        tmp_path, body=BODY, files={"references/guide.md": "# Guide\n\nRead me when releasing.\n"}
    )


def _judge(tmp_path: Path, judgments: list[dict[str, Any]], *extra: str) -> int:
    path = tmp_path / "judgments.json"
    path.write_text(json.dumps({"judgments": judgments}), encoding="utf-8")
    return conformance.main(["release-notes", "--judgments", str(path), "--format", "json", *extra])


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


class TestReadRaceAndIdentity:
    """Third review round: a swap around the read, and identity lookup failures."""

    QUOTE_OUT = "An outside sentence that must never count."

    @pytest.fixture
    def swap(self, skill: Path, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
        guide = skill / "references" / "guide.md"
        guide.write_text("# Guide\n\nAn inside sentence that may count here.\n", encoding="utf-8")
        outside = tmp_path_factory.mktemp("outside") / "secret.md"
        outside.write_text(self.QUOTE_OUT + "\n", encoding="utf-8")
        probe = outside.parent / "probe-link"
        try:
            probe.symlink_to(outside)
        except OSError as exc:
            pytest.skip(f"cannot create a symlink here: {exc}")
        probe.unlink()
        return guide, outside

    @staticmethod
    def _point(guide: Path, target: Path) -> None:
        guide.unlink()
        guide.symlink_to(target)

    @pytest.mark.parametrize("timing", ["before-open", "after-open", "out-and-back"])
    def test_swap_around_the_open_is_rejected(
        self,
        skill: Path,
        swap: tuple[Path, Path],
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
        timing: str,
    ) -> None:
        guide, outside = swap
        inside_copy = guide.parent / "guide-inside.md"
        inside_copy.write_bytes(guide.read_bytes())
        judging_globals = JUDGING
        real_open = open

        def racing_open(path: Any, *args: Any, **kwargs: Any) -> Any:
            if Path(path).name != "guide.md":
                return real_open(path, *args, **kwargs)
            if timing == "before-open":
                self._point(guide, outside)
                return real_open(path, *args, **kwargs)
            if timing == "after-open":
                handle = real_open(path, *args, **kwargs)
                self._point(guide, outside)
                return handle
            self._point(guide, outside)
            handle = real_open(path, *args, **kwargs)
            self._point(guide, inside_copy)
            return handle

        monkeypatch.setitem(judging_globals, "open", racing_open)
        quote = (
            self.QUOTE_OUT if timing != "after-open" else "An inside sentence that may count here."
        )
        judgment = _verdict("pass", quote=quote, file="references/guide.md")

        code = _judge(skill.parent, [judgment])

        assert code == 2
        assert "references/guide.md is not a text file in the skill" in capsys.readouterr().err

    def test_missing_judgments_file_is_rejected(
        self, skill: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = conformance.main(["release-notes", "--judgments", str(skill.parent / "absent.json")])

        assert code == 2
        assert "cannot read" in capsys.readouterr().err

    def test_judgments_identity_comes_from_the_file_that_is_read(
        self, skill: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        invented = "An invented sentence held only by the judgments text."
        judgment = _verdict("pass", quote=invented, file="references/evidence.json")
        evidence = skill / "references" / "evidence.json"
        evidence.write_text(json.dumps({"judgments": [judgment]}), encoding="utf-8")
        decoy = skill.parent / "decoy.json"
        decoy.write_text(json.dumps({"judgments": []}), encoding="utf-8")
        link = skill.parent / "judgments.json"
        try:
            link.symlink_to(decoy)
        except OSError as exc:
            pytest.skip(f"cannot create a symlink here: {exc}")
        real_open = open

        def swapping_open(path: Any, *args: Any, **kwargs: Any) -> Any:
            if Path(path).name == "judgments.json":
                link.unlink()
                link.symlink_to(evidence)
            return real_open(path, *args, **kwargs)

        monkeypatch.setitem(JUDGING, "open", swapping_open)

        code = conformance.main(["release-notes", "--judgments", str(link)])

        assert code == 2
        assert "references/evidence.json is not a text file in the skill" in capsys.readouterr().err

    def test_unidentifiable_candidate_is_left_out(
        self, skill: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = JUDGING["file_id"]
        monkeypatch.setitem(JUDGING, "file_id", lambda p: None if p.name == "SKILL.md" else real(p))

        code = _judge(skill.parent, [_verdict("pass")])

        assert code == 2
        assert "SKILL.md is not a text file in the skill" in capsys.readouterr().err

    def test_judgments_file_missed_at_listing_is_caught_at_read(
        self, skill: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        invented = "An invented sentence held only by the judgments file."
        path = skill.parent / "judgments.json"
        judgment = _verdict("pass", quote=invented, file="references/evidence.json")
        path.write_text(json.dumps({"judgments": [judgment]}), encoding="utf-8")
        try:
            os.link(path, skill / "references" / "evidence.json")
        except OSError as exc:
            pytest.skip(f"cannot create a hard link here: {exc}")
        real = JUDGING["file_id"]
        monkeypatch.setitem(
            JUDGING,
            "file_id",
            lambda p: (0, 0) if p.name == "evidence.json" else real(p),
        )

        code = conformance.main(["release-notes", "--judgments", str(path)])

        assert code == 2
        assert "references/evidence.json is not a text file in the skill" in capsys.readouterr().err


def test_swap_back_between_identity_and_containment_is_rejected(
    skill: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """Cursor's case: the path is outside for the identity check, inside for containment.

    After the open, each identity or resolution lookup on guide.md swaps it back
    inside, the window a two-resolution check left open. One resolution closes
    it. The hooks cover both the old lookup (file_id in the importer) and the
    current one (_real in the parser).
    """
    guide = skill / "references" / "guide.md"
    inside_copy = guide.parent / "guide-inside.md"
    inside_copy.write_bytes(guide.read_bytes())
    outside = tmp_path_factory.mktemp("outside") / "secret.md"
    outside_quote = "An outside sentence that must never count."
    outside.write_text(outside_quote + "\n", encoding="utf-8")
    probe = outside.parent / "probe-link"
    try:
        probe.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"cannot create a symlink here: {exc}")
    probe.unlink()
    judging_globals = JUDGING
    parse_globals = conformance.load_skill.__globals__
    real_open = open
    opened: list[bool] = []

    def point(target: Path) -> None:
        guide.unlink()
        guide.symlink_to(target)

    def outside_then_open(path: Any, *args: Any, **kwargs: Any) -> Any:
        if Path(path).name == "guide.md":
            point(outside)
            opened.append(True)
        return real_open(path, *args, **kwargs)

    def swap_back_after(lookup: Any) -> Any:
        def hooked(path: Any) -> Any:
            result = lookup(path)
            if opened and Path(path).name == "guide.md":
                point(inside_copy)
            return result

        return hooked

    monkeypatch.setitem(judging_globals, "open", outside_then_open)
    monkeypatch.setitem(parse_globals, "_real", swap_back_after(parse_globals["_real"]))
    if "file_id" in judging_globals:
        monkeypatch.setitem(judging_globals, "file_id", swap_back_after(judging_globals["file_id"]))
    judgment = _verdict("pass", quote=outside_quote, file="references/guide.md")

    code = _judge(skill.parent, [judgment])

    assert code == 2
    assert "references/guide.md is not a text file in the skill" in capsys.readouterr().err
    # The swap back ran, so the rejection is not the plain after-open case.
    assert guide.resolve() == inside_copy.resolve()
