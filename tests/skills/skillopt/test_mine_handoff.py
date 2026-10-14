"""Tests for the pattern handoff and baseline validation."""

from __future__ import annotations

import json
from pathlib import Path

import _mine_handoff as mh
import mine_sessions as ms
import pytest
from skillopt_helpers import (
    Capture,
    pattern,
    write_handoff,
)


class TestMergeStats:
    def test_sums_across_parts(self) -> None:
        a = {"x": {"invocations": 3, "corrections": 1}}
        b = {"x": {"invocations": 2, "corrections": 2}, "y": {"invocations": 1, "corrections": 0}}
        merged = ms.merge_stats([a, b])
        assert merged["x"] == {"invocations": 5, "corrections": 3}
        assert merged["y"] == {"invocations": 1, "corrections": 0}

    def test_missing_keys_count_as_zero(self) -> None:
        assert ms.merge_stats([{"x": {}}])["x"] == {"invocations": 0, "corrections": 0}


class TestLoadBaseline:
    def test_valid(self, tmp_path: Path) -> None:
        f = tmp_path / "h.json"
        f.write_text(
            json.dumps({"host": "h", "stats": {"a": {"invocations": 1, "corrections": 0}}}),
            encoding="utf-8",
        )
        assert mh._load_baseline(f) == ("h", {"a": {"invocations": 1, "corrections": 0}})

    def test_host_defaults_to_stem_and_missing_stat_keys_ok(self, tmp_path: Path) -> None:
        f = tmp_path / "boxA.json"
        f.write_text(json.dumps({"stats": {"a": {"invocations": 2}}}), encoding="utf-8")
        assert mh._load_baseline(f)[0] == "boxA"

    def test_missing_file_names_file(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="gone.json"):
            mh._load_baseline(tmp_path / "gone.json")

    @pytest.mark.parametrize("content", [b"{nope", b"\xff\xfe\x00"])
    def test_unreadable_names_file(self, tmp_path: Path, content: bytes) -> None:
        f = tmp_path / "bad.json"
        f.write_bytes(content)
        with pytest.raises(ValueError, match="bad.json"):
            mh._load_baseline(f)

    @pytest.mark.parametrize("doc", [[], "x", {}, {"stats": []}, {"stats": "x"}])
    def test_bad_shape(self, tmp_path: Path, doc: object) -> None:
        f = tmp_path / "b.json"
        f.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ValueError, match="'stats' object"):
            mh._load_baseline(f)

    def test_non_string_host(self, tmp_path: Path) -> None:
        f = tmp_path / "b.json"
        f.write_text(json.dumps({"host": 5, "stats": {}}), encoding="utf-8")
        with pytest.raises(ValueError, match="host must be a string"):
            mh._load_baseline(f)

    def test_non_object_stat_row(self, tmp_path: Path) -> None:
        f = tmp_path / "b.json"
        f.write_text(json.dumps({"stats": {"a": 3}}), encoding="utf-8")
        with pytest.raises(ValueError, match="must be an object"):
            mh._load_baseline(f)

    @pytest.mark.parametrize("value", ["3", 1.5, True, None, -1, [1]])
    def test_stat_values_must_be_ints(self, tmp_path: Path, value: object) -> None:
        f = tmp_path / "b.json"
        f.write_text(
            json.dumps({"stats": {"a": {"invocations": 1, "corrections": value}}}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match=r"a\.corrections must be a non-negative integer"):
            mh._load_baseline(f)


class TestPatternHandoff:
    def test_load_and_reduce(self, tmp_path: Path) -> None:
        handoff = tmp_path / "patterns.json"
        write_handoff(handoff)
        patterns = ms.load_pattern_handoff(handoff)
        assert ms.pattern_stats(patterns)["build"] == {"invocations": 3, "corrections": 1}
        assert ms.pattern_tasks(patterns, "review") == ["review this PR"]

    def test_producer_is_optional(self, tmp_path: Path) -> None:
        handoff = tmp_path / "patterns.json"
        handoff.write_text(
            json.dumps({"schema": "session-patterns/1", "patterns": [pattern()]}), encoding="utf-8"
        )
        assert len(ms.load_pattern_handoff(handoff)) == 1

    @pytest.mark.parametrize("producer", [5, None, ["x"], {"a": 1}, True])
    def test_producer_present_but_not_string_rejected(
        self, tmp_path: Path, producer: object
    ) -> None:
        handoff = tmp_path / "patterns.json"
        write_handoff(handoff, [pattern()], producer=producer)
        with pytest.raises(ValueError, match="producer must be a string"):
            ms.load_pattern_handoff(handoff)

    @pytest.mark.parametrize(
        "document",
        [
            {},
            [],
            {"schema": "wrong", "patterns": []},
            {"schema": "session-patterns/1", "patterns": "not-a-list"},
            {"schema": "session-patterns/1"},
        ],
    )
    def test_rejects_invalid_handoff(self, tmp_path: Path, document: object) -> None:
        handoff = tmp_path / "patterns.json"
        handoff.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(ValueError, match="pattern handoff"):
            ms.load_pattern_handoff(handoff)

    @pytest.mark.parametrize("content", [b"not json", b"\xff\xfe"])
    def test_rejects_unreadable_handoff(self, tmp_path: Path, content: bytes) -> None:
        handoff = tmp_path / "patterns.json"
        handoff.write_bytes(content)
        with pytest.raises(ValueError, match="cannot read pattern handoff"):
            ms.load_pattern_handoff(handoff)

    def test_rejects_missing_handoff(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="cannot read pattern handoff"):
            ms.load_pattern_handoff(tmp_path / "gone.json")

    @pytest.mark.parametrize(
        ("pattern", "message"),
        [
            ("not-an-object", "must be an object"),
            (pattern(id=None), "missing or duplicate id"),
            (pattern(id=""), "missing or duplicate id"),
            (pattern(skill=None), "has no skill"),
            (pattern(skill=""), "has no skill"),
            (pattern(sessions="s1"), "needs nonempty session ids"),
            (pattern(sessions=[]), "needs nonempty session ids"),
            (pattern(sessions=[""]), "needs nonempty session ids"),
            (pattern(prompts=[""]), "prompts must be nonempty strings"),
            (pattern(prompts=[]), "prompts must be nonempty strings"),
            (pattern(prompts="build it"), "prompts must be nonempty strings"),
            (pattern(prompts=["  "]), "prompts must be nonempty strings"),
            (pattern(invocations=True), "invocations must be a positive integer"),
            (pattern(invocations=0), "invocations must be a positive integer"),
            (pattern(invocations=1.0), "invocations must be a positive integer"),
            (pattern(corrections=2), "corrections exceed invocations"),
            (pattern(corrections=-1), "corrections exceed invocations"),
            (pattern(corrections="0"), "corrections exceed invocations"),
        ],
    )
    def test_rejects_invalid_pattern_fields(
        self, tmp_path: Path, pattern: object, message: str
    ) -> None:
        handoff = tmp_path / "patterns.json"
        write_handoff(handoff, [pattern])
        with pytest.raises(ValueError, match=message):
            ms.load_pattern_handoff(handoff)

    def test_rejects_duplicate_ids(self, tmp_path: Path) -> None:
        handoff = tmp_path / "patterns.json"
        write_handoff(handoff, [pattern(), pattern()])
        with pytest.raises(ValueError, match="missing or duplicate id"):
            ms.load_pattern_handoff(handoff)

    def test_cli_reports_invalid_pattern_handoff(self, tmp_path: Path, capsys: Capture) -> None:
        handoff = tmp_path / "patterns.json"
        handoff.write_text("{}", encoding="utf-8")
        assert ms.main(["rank", "--patterns", str(handoff)]) == 2
        error = capsys.readouterr().err
        assert error.startswith("Error: ")
        assert "session-patterns/1" in error
