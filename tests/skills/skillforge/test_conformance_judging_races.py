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
        files_globals = conformance.apply_judgments.__globals__
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

        monkeypatch.setitem(files_globals, "open", racing_open)
        quote = (
            self.QUOTE_OUT if timing != "after-open" else "An inside sentence that may count here."
        )
        judgment = _verdict("pass", quote=quote, file="references/guide.md")

        code = _judge(skill.parent, [judgment])

        assert code == 2
        assert "references/guide.md is not a text file in the skill" in capsys.readouterr().err

    def test_unidentifiable_judgments_file_is_rejected(
        self, skill: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = conformance.__dict__["file_id"]
        monkeypatch.setitem(
            conformance.__dict__,
            "file_id",
            lambda p: None if p.name == "judgments.json" else real(p),
        )

        code = _judge(skill.parent, [_verdict("pass")])

        assert code == 2
        assert "cannot identify" in capsys.readouterr().err

    def test_unidentifiable_candidate_is_left_out(
        self, skill: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = conformance.__dict__["file_id"]
        monkeypatch.setitem(
            conformance.__dict__, "file_id", lambda p: None if p.name == "SKILL.md" else real(p)
        )

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
        real = conformance.__dict__["file_id"]
        monkeypatch.setitem(
            conformance.__dict__,
            "file_id",
            lambda p: (0, 0) if p.name == "evidence.json" else real(p),
        )

        code = conformance.main(["release-notes", "--judgments", str(path)])

        assert code == 2
        assert "references/evidence.json is not a text file in the skill" in capsys.readouterr().err
