#!/usr/bin/env python3
"""Tests for panning-for-gold skill scripts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

inventory = import_skill_script(
    ".claude/skills/panning-for-gold/scripts/inventory.py", "panning_inventory"
)
synthesis = import_skill_script(
    ".claude/skills/panning-for-gold/scripts/synthesis.py", "panning_synthesis"
)
pan = import_skill_script(".claude/skills/panning-for-gold/scripts/pan.py", "panning_pan")

Thread = inventory.Thread
parse_inventory = inventory.parse_inventory
merge = inventory.merge
render_inventory = inventory.render_inventory
InventoryError = inventory.InventoryError

build_gold_found = synthesis.build_gold_found
SynthesisError = synthesis.SynthesisError
evaluation_filename = synthesis.evaluation_filename

main = pan.main
resolve_workspace = pan.resolve_workspace
SUBDIRS = pan.SUBDIRS


SAMPLE_THREAD = """## Thread 1: Memory caching strategy

- **Signal**: high
- **Quote**: "We never invalidate the cache after writes"
- **Context**: Discussion about why agent runs see stale memory
- **Initial take**: Likely the source of cross-session drift
"""


SECOND_THREAD = """
## Thread 2: Logging gap

- **Signal**: medium
- **Quote**: "There is no structured log on retry"
- **Context**: Mentioned during the retry walkthrough
- **Initial take**: Probably blocks postmortems
"""


# ---- inventory parsing ----


class TestParseInventory:
    def test_empty_input(self):
        assert parse_inventory("") == []

    def test_whitespace_only(self):
        assert parse_inventory("\n\n   \n") == []

    def test_single_thread(self):
        threads = parse_inventory(SAMPLE_THREAD)
        assert len(threads) == 1
        t = threads[0]
        assert t.number == 1
        assert t.title == "Memory caching strategy"
        assert t.signal == "high"
        assert "stale memory" in t.context

    def test_multiple_threads(self):
        text = SAMPLE_THREAD + SECOND_THREAD
        threads = parse_inventory(text)
        assert [t.number for t in threads] == [1, 2]
        assert threads[1].signal == "medium"

    def test_missing_field_raises(self):
        bad = "## Thread 1: Bad\n\n- **Signal**: high\n- **Quote**: \"missing fields\"\n"
        with pytest.raises(InventoryError):
            parse_inventory(bad)

    def test_invalid_signal_raises(self):
        bad = SAMPLE_THREAD.replace("**Signal**: high", "**Signal**: critical")
        with pytest.raises(InventoryError):
            parse_inventory(bad)

    def test_crlf_line_endings(self):
        text = SAMPLE_THREAD.replace("\n", "\r\n")
        threads = parse_inventory(text)
        assert len(threads) == 1

    def test_unicode_in_title_and_quote(self):
        text = "## Thread 1: Caching - stale data\n\n" \
               "- **Signal**: low\n" \
               "- **Quote**: \"naive cache; no invalidate step\"\n" \
               "- **Context**: Foreign-language term used by the speaker\n" \
               "- **Initial take**: Worth a glossary entry\n"
        threads = parse_inventory(text)
        assert "stale data" in threads[0].title
        assert "invalidate" in threads[0].quote


# ---- merge ----


class TestMerge:
    def _t(self, n, title, signal="low"):
        return Thread(
            number=n,
            title=title,
            signal=signal,
            quote="q",
            context="c",
            initial_take="i",
        )

    def test_final_takes_precedence(self):
        pass1 = [self._t(1, "Topic A", signal="low")]
        final = [self._t(1, "Topic A", signal="high")]
        merged = merge(pass1, final)
        assert len(merged) == 1
        assert merged[0].signal == "high"

    def test_appends_new_threads_from_pass1(self):
        pass1 = [self._t(1, "Topic A"), self._t(2, "Topic B")]
        final = [self._t(1, "Topic A")]
        merged = merge(pass1, final)
        titles = [t.title for t in merged]
        assert titles == ["Topic A", "Topic B"]

    def test_renumbers_from_one(self):
        pass1 = [self._t(7, "Topic A"), self._t(11, "Topic B")]
        merged = merge(pass1, [])
        assert [t.number for t in merged] == [1, 2]

    def test_dedup_by_title_case_insensitive(self):
        pass1 = [self._t(1, "  Topic A  ")]
        final = [self._t(1, "topic a")]
        merged = merge(pass1, final)
        assert len(merged) == 1


# ---- render_inventory ----


class TestRenderInventory:
    def test_round_trip(self):
        threads = parse_inventory(SAMPLE_THREAD)
        rendered = render_inventory(threads, source="t.md")
        again = parse_inventory(rendered)
        assert again[0].title == threads[0].title
        assert again[0].signal == threads[0].signal
        assert again[0].quote == threads[0].quote


# ---- synthesis ----


class TestSynthesis:
    def _make(self, tmp_path, signals):
        threads = [
            Thread(
                number=i + 1,
                title=f"Topic {i + 1}",
                signal=sig,
                quote=f"quote {i + 1}",
                context=f"context {i + 1}",
                initial_take=f"take {i + 1}",
            )
            for i, sig in enumerate(signals)
        ]
        evals_dir = tmp_path / "evaluations"
        evals_dir.mkdir()
        for t in threads:
            (evals_dir / evaluation_filename(t)).write_text(
                f"Evaluation body for {t.title}.", encoding="utf-8"
            )
        return threads, evals_dir

    def test_section_order_is_high_medium_low(self, tmp_path):
        threads, evals = self._make(tmp_path, ["low", "medium", "high"])
        text = build_gold_found(threads, evals, source="t.md")
        h = text.index("## High-Signal")
        m = text.index("## Medium-Signal")
        low_idx = text.index("## Low-Signal")
        assert h < m < low_idx

    def test_metadata_block(self, tmp_path):
        threads, evals = self._make(tmp_path, ["high"])
        text = build_gold_found(threads, evals, source="t.md")
        assert "**Source**: t.md" in text
        assert "**Threads**: 1" in text

    def test_empty_section_marked_none(self, tmp_path):
        threads, evals = self._make(tmp_path, ["high"])
        text = build_gold_found(threads, evals, source="t.md")
        assert "_None._" in text

    def test_missing_evaluation_raises(self, tmp_path):
        threads, evals = self._make(tmp_path, ["high"])
        for f in evals.iterdir():
            f.unlink()
        with pytest.raises(SynthesisError):
            build_gold_found(threads, evals, source="t.md")

    def test_evaluation_body_appears(self, tmp_path):
        threads, evals = self._make(tmp_path, ["high"])
        text = build_gold_found(threads, evals, source="t.md")
        assert "Evaluation body for Topic 1." in text


# ---- CLI: resolve_workspace ----


class TestResolveWorkspace:
    def test_arg_takes_precedence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PANNING_WORKSPACE", str(tmp_path / "env-ws"))
        chosen = resolve_workspace(str(tmp_path / "arg-ws"))
        assert chosen == (tmp_path / "arg-ws").resolve()

    def test_env_used_when_arg_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PANNING_WORKSPACE", str(tmp_path / "env-ws"))
        chosen = resolve_workspace(None)
        assert chosen == (tmp_path / "env-ws").resolve()

    def test_default_when_neither(self, monkeypatch):
        monkeypatch.delenv("PANNING_WORKSPACE", raising=False)
        chosen = resolve_workspace(None)
        assert chosen.name == ".panning"


# ---- CLI: end-to-end ----


class TestCLI:
    def test_init_creates_subdirs(self, tmp_path, capsys):
        ws = tmp_path / "ws"
        rc = main(["init", "--workspace", str(ws)])
        assert rc == 0
        for sub in SUBDIRS:
            assert (ws / sub).is_dir()
        captured = capsys.readouterr()
        assert "Initialized workspace" in captured.out

    def test_init_idempotent(self, tmp_path):
        ws = tmp_path / "ws"
        assert main(["init", "--workspace", str(ws)]) == 0
        assert main(["init", "--workspace", str(ws)]) == 0

    def test_validate_ok(self, tmp_path):
        path = tmp_path / "i.md"
        path.write_text(SAMPLE_THREAD, encoding="utf-8")
        assert main(["validate", "--inventory", str(path)]) == 0

    def test_validate_bad_returns_one(self, tmp_path):
        path = tmp_path / "i.md"
        path.write_text("## Thread 1: Bad\n\n- **Signal**: high\n", encoding="utf-8")
        assert main(["validate", "--inventory", str(path)]) == 1

    def test_merge_writes_output(self, tmp_path):
        p1 = tmp_path / "pass1.md"
        fn = tmp_path / "final.md"
        out = tmp_path / "merged.md"
        p1.write_text(SAMPLE_THREAD, encoding="utf-8")
        fn.write_text(SAMPLE_THREAD, encoding="utf-8")
        rc = main([
            "merge",
            "--pass1", str(p1),
            "--final", str(fn),
            "--output", str(out),
        ])
        assert rc == 0
        assert out.exists()

    def test_merge_refuses_to_clobber_without_force(self, tmp_path):
        p1 = tmp_path / "pass1.md"
        fn = tmp_path / "final.md"
        out = tmp_path / "merged.md"
        p1.write_text(SAMPLE_THREAD, encoding="utf-8")
        fn.write_text(SAMPLE_THREAD, encoding="utf-8")
        out.write_text("existing", encoding="utf-8")
        rc = main([
            "merge",
            "--pass1", str(p1),
            "--final", str(fn),
            "--output", str(out),
        ])
        assert rc == 2
        assert out.read_text(encoding="utf-8") == "existing"

    def test_synth_end_to_end(self, tmp_path):
        inv = tmp_path / "final.md"
        inv.write_text(SAMPLE_THREAD, encoding="utf-8")
        evals_dir = tmp_path / "evals"
        evals_dir.mkdir()
        threads = parse_inventory(SAMPLE_THREAD)
        for t in threads:
            (evals_dir / evaluation_filename(t)).write_text(
                "Evaluation text.", encoding="utf-8"
            )
        out = tmp_path / "gold.md"
        rc = main([
            "synth",
            "--inventory", str(inv),
            "--evaluations", str(evals_dir),
            "--output", str(out),
            "--source", "fixture",
        ])
        assert rc == 0
        text = out.read_text(encoding="utf-8")
        assert "**Source**: fixture" in text
        assert "Evaluation text." in text
