#!/usr/bin/env python3
"""Tests for the contradiction-lens prefilter and the additive inventory fields."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

prefilter = import_skill_script(
    ".claude/skills/panning-for-gold/scripts/prefilter.py", "panning_prefilter"
)
inventory = import_skill_script(
    ".claude/skills/panning-for-gold/scripts/inventory.py", "panning_inventory_lens"
)
synthesis = import_skill_script(
    ".claude/skills/panning-for-gold/scripts/synthesis.py", "panning_synthesis_lens"
)
pan = import_skill_script(".claude/skills/panning-for-gold/scripts/pan.py", "panning_pan_lens")

STRONG_TEXT = (
    "The probe was surprising. The one-line instruction scored 30/30 but the file map "
    "alone scored 22/30, which contradicts the docs claim."
)
TIER2_TEXT = (
    "We measured 12 ms against the baseline of 9 ms in the run today across the whole suite."
)
WEAK_BELIEF_TEXT = (
    "We expected the cache to help, but measured 12 ms to 9 ms on the same run, near nothing."
)
WEAK_NO_CONTRAST_TEXT = (
    "We expected the cache to help and measured 12 ms to 9 ms on the same run, near nothing."
)


def row(text: str, role: str = "assistant", path: str = "/s/a.jsonl", line: object = 1) -> dict:
    return {
        "source": "claude",
        "session": "s1",
        "path": path,
        "line": line,
        "ts": "2026-01-02T03:04:05Z",
        "role": role,
        "text": text,
    }


def write_corpus(tmp_path: Path, rows: list[dict], name: str = "corpus.jsonl") -> Path:
    path = tmp_path / name
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def kept(tmp_path: Path, rows: list[dict], **options: int) -> list[dict]:
    corpus = write_corpus(tmp_path, rows)
    out = tmp_path / "out"
    prefilter.run_prefilter(
        corpus, "contradiction", out, options.get("max_chars", prefilter.DEFAULT_MAX_BATCH_CHARS)
    )
    result = []
    for batch in sorted(out.glob("batch-*.jsonl")):
        result += [json.loads(line) for line in batch.read_text(encoding="utf-8").splitlines()]
    return result


# ---- tiers: positive ----


def test_tier1_signal_plus_number_is_kept(tmp_path: Path) -> None:
    result = kept(tmp_path, [row(STRONG_TEXT)])
    assert len(result) == 1
    assert result[0]["tier"] == 1
    assert result[0]["text"] == STRONG_TEXT
    assert result[0]["hid"] == "000-000"


def test_tier2_two_signals_and_a_number_is_kept(tmp_path: Path) -> None:
    result = kept(tmp_path, [row(TIER2_TEXT)])
    assert [r["tier"] for r in result] == [2]


def test_tier2_one_signal_needs_belief_contrast_and_comparison(tmp_path: Path) -> None:
    assert [r["tier"] for r in kept(tmp_path, [row(WEAK_BELIEF_TEXT)])] == [2]


def test_user_turn_with_a_very_strong_score_is_kept(tmp_path: Path) -> None:
    assert len(kept(tmp_path, [row(STRONG_TEXT, role="user")])) == 1


def test_output_row_carries_the_corpus_fields(tmp_path: Path) -> None:
    result = kept(tmp_path, [row(STRONG_TEXT, line="m-9")])[0]
    assert (result["source"], result["session"], result["line"], result["role"]) == (
        "claude",
        "s1",
        "m-9",
        "assistant",
    )
    assert result["ts"] == "2026-01-02T03:04:05Z"
    assert len(result["key"]) == 64


# ---- tiers: negative and edge ----


def test_signal_without_a_number_is_dropped(tmp_path: Path) -> None:
    text = "The probe was surprising and it contradicts what the documentation promised to us."
    assert kept(tmp_path, [row(text)]) == []


def test_number_without_a_signal_is_dropped(tmp_path: Path) -> None:
    text = "The build took 12 seconds on the machine, which is about what we saw all week long."
    assert kept(tmp_path, [row(text)]) == []


def test_one_signal_without_contrast_is_dropped(tmp_path: Path) -> None:
    assert kept(tmp_path, [row(WEAK_NO_CONTRAST_TEXT)]) == []


def test_short_text_is_dropped(tmp_path: Path) -> None:
    assert kept(tmp_path, [row("surprising 3 vs 2")]) == []


def test_user_turn_with_a_low_score_is_dropped(tmp_path: Path) -> None:
    assert kept(tmp_path, [row(TIER2_TEXT, role="user")]) == []


@pytest.mark.parametrize("role", ["system", "tool", "child-agent", ""])
def test_other_roles_are_skipped_and_counted(tmp_path: Path, role: str) -> None:
    corpus = write_corpus(tmp_path, [row(STRONG_TEXT, role=role)])
    stats = prefilter.run_prefilter(corpus, "contradiction", tmp_path / "out", 1000)
    assert (stats.rows_skipped_role, stats.windows_kept) == (1, 0)


@pytest.mark.parametrize(
    "tag", ["<system-reminder>", "<task-notification>", "<environment_context>"]
)
def test_injected_text_is_dropped(tmp_path: Path, tag: str) -> None:
    assert kept(tmp_path, [row(f"{tag} {STRONG_TEXT}")]) == []


def test_window_is_one_paragraph_of_context_each_side(tmp_path: Path) -> None:
    text = "\n\n".join(["before " * 10, STRONG_TEXT, "after " * 10, "far away " * 10])
    window = kept(tmp_path, [row(text)])[0]["text"]
    assert "before" in window and "after" in window and "far away" not in window


def test_window_text_is_capped(tmp_path: Path) -> None:
    text = STRONG_TEXT + " filler" * 400
    assert len(kept(tmp_path, [row(text)])[0]["text"]) == prefilter.WINDOW_MAX_CHARS


def test_secret_in_a_window_is_redacted(tmp_path: Path) -> None:
    token = "ghp_" + "q" * 36
    result = kept(tmp_path, [row(f"{STRONG_TEXT} Used {token} for it.")])
    assert token not in result[0]["text"]
    assert "[REDACTED]" in result[0]["text"]


# ---- dedupe ----


def test_duplicates_are_dropped_by_normalized_text(tmp_path: Path) -> None:
    variant = STRONG_TEXT.upper().replace(".", " !")
    corpus = write_corpus(
        tmp_path, [row(STRONG_TEXT), row(variant, line=2), row(STRONG_TEXT, line=3)]
    )
    stats = prefilter.run_prefilter(corpus, "contradiction", tmp_path / "out", 1000)
    assert (stats.windows_kept, stats.windows_duplicate) == (1, 2)


def test_distinct_findings_are_not_merged(tmp_path: Path) -> None:
    other = STRONG_TEXT.replace("30/30", "40/40")
    assert len(kept(tmp_path, [row(STRONG_TEXT), row(other, line=2)])) == 2


# ---- batching ----


def numbered(count: int) -> list[dict]:
    return [
        row(STRONG_TEXT.replace("one-line", f"variant {i} line"), line=i, path="/s/b.jsonl")
        for i in range(count)
    ]


def test_batches_close_past_the_character_budget(tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path, numbered(6))
    stats = prefilter.run_prefilter(corpus, "contradiction", tmp_path / "out", 300)
    sizes = [
        len((tmp_path / "out" / prefilter.batch_name(n)).read_text(encoding="utf-8").splitlines())
        for n in range(stats.batches)
    ]
    assert sum(sizes) == 6 and stats.batches > 1


def test_batches_cap_at_ninety_rows(tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path, numbered(95))
    stats = prefilter.run_prefilter(corpus, "contradiction", tmp_path / "out", 10**9)
    first = (tmp_path / "out" / "batch-000.jsonl").read_text(encoding="utf-8").splitlines()
    assert (stats.batches, len(first)) == (2, prefilter.MAX_BATCH_ROWS)


def test_row_larger_than_the_budget_still_gets_a_batch(tmp_path: Path) -> None:
    assert len(kept(tmp_path, [row(STRONG_TEXT)], max_chars=5)) == 1


def test_ids_and_order_are_deterministic_and_sorted(tmp_path: Path) -> None:
    rows = numbered(4)[::-1] + [row(TIER2_TEXT, path="/s/a.jsonl", line="z")]
    first = kept(tmp_path, rows)
    again_dir = tmp_path / "again"
    again_dir.mkdir()
    assert first == kept(again_dir, rows)
    assert [r["path"] for r in first][0] == "/s/a.jsonl"
    assert [r["hid"] for r in first] == [f"000-{i:03d}" for i in range(len(first))]
    assert [r["line"] for r in first][1:] == [0, 1, 2, 3]


def test_manifest_reports_counts(tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path, [row(STRONG_TEXT), row(TIER2_TEXT, line=2), row("x", line=3)])
    prefilter.run_prefilter(corpus, "contradiction", tmp_path / "out", 1000)
    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    assert (manifest["rows_read"], manifest["windows_kept"], manifest["tiers"]) == (
        3,
        2,
        {"1": 1, "2": 1},
    )


def test_empty_corpus_writes_a_manifest_and_no_batches(tmp_path: Path) -> None:
    corpus = tmp_path / "empty.jsonl"
    corpus.write_text("\n\n", encoding="utf-8")
    stats = prefilter.run_prefilter(corpus, "contradiction", tmp_path / "out", 1000)
    assert (stats.rows_read, stats.batches) == (0, 0)
    assert (tmp_path / "out" / "manifest.json").is_file()


# ---- CLI exit codes ----


def cli(tmp_path: Path, corpus: Path, *extra: str) -> int:
    argv = ["prefilter", "--corpus", str(corpus), "--lens", "contradiction"]
    return pan.main([*argv, "--out", str(tmp_path / "out"), *extra])


def test_cli_success_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    corpus = write_corpus(tmp_path, [row(STRONG_TEXT)])
    assert cli(tmp_path, corpus) == 0
    assert "1 window(s) kept in 1 batch(es)" in capsys.readouterr().out


def test_cli_missing_corpus_exits_two(tmp_path: Path) -> None:
    assert cli(tmp_path, tmp_path / "missing.jsonl") == 2


def test_cli_directory_as_corpus_exits_two(tmp_path: Path) -> None:
    assert cli(tmp_path, tmp_path) == 2


def test_cli_refuses_an_output_dir_that_holds_batches(tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path, [row(STRONG_TEXT)])
    assert cli(tmp_path, corpus) == 0
    assert cli(tmp_path, corpus) == 2


@pytest.mark.parametrize(
    "line",
    [
        "{not json",
        "[1, 2]",
        json.dumps({"source": "x"}),
        json.dumps({**row("t"), "text": 5}),
        json.dumps({**row("t"), "role": None}),
    ],
)
def test_cli_invalid_row_exits_one(tmp_path: Path, line: str) -> None:
    corpus = tmp_path / "bad.jsonl"
    corpus.write_text(line + "\n", encoding="utf-8")
    assert cli(tmp_path, corpus) == 1


def test_cli_names_the_failing_line(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    corpus = tmp_path / "bad.jsonl"
    corpus.write_text(json.dumps(row("t")) + "\n{oops\n", encoding="utf-8")
    assert cli(tmp_path, corpus) == 1
    assert "line 2" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["0", "-5", "many"])
def test_cli_rejects_a_bad_batch_size(tmp_path: Path, value: str) -> None:
    corpus = write_corpus(tmp_path, [row(STRONG_TEXT)])
    with pytest.raises(SystemExit) as exc:
        cli(tmp_path, corpus, "--max-batch-chars", value)
    assert exc.value.code == 2


def test_cli_rejects_an_unknown_lens(tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path, [row(STRONG_TEXT)])
    with pytest.raises(SystemExit) as exc:
        pan.main(["prefilter", "--corpus", str(corpus), "--lens", "nope", "--out", "x"])
    assert exc.value.code == 2


def test_unknown_lens_in_the_library_is_a_corpus_error(tmp_path: Path) -> None:
    with pytest.raises(prefilter.CorpusError):
        prefilter.run_prefilter(tmp_path / "c.jsonl", "nope", tmp_path / "out", 10)


# ---- additive inventory fields ----

OLD_INVENTORY = """# Thread Inventory

## Thread 1: Cache claim

- **Signal**: high
- **Quote**: "stale after writes"
- **Context**: Cache walkthrough
- **Initial take**: Likely stale
"""

LENS_INVENTORY = (
    OLD_INVENTORY
    + """- **Claim**: The map alone scored 22/30
- **Conventional view**: Prefer retrieval
- **Evidence**: 30/30 vs 22/30
- **Strength**: Strong
"""
)


def test_old_inventory_still_validates_and_has_empty_lens_fields(tmp_path: Path) -> None:
    path = tmp_path / "inv.md"
    path.write_text(OLD_INVENTORY, encoding="utf-8")
    assert pan.main(["validate", "--inventory", str(path)]) == 0
    thread = inventory.parse_inventory(OLD_INVENTORY)[0]
    assert (thread.claim, thread.conventional_view, thread.evidence, thread.strength) == ("",) * 4


def test_old_inventory_renders_without_lens_lines() -> None:
    rendered = inventory.render_inventory(inventory.parse_inventory(OLD_INVENTORY))
    assert "Claim" not in rendered and "Strength" not in rendered


def test_lens_fields_parse_and_normalize_strength() -> None:
    thread = inventory.parse_inventory(LENS_INVENTORY)[0]
    assert thread.claim == "The map alone scored 22/30"
    assert thread.conventional_view == "Prefer retrieval"
    assert thread.evidence == "30/30 vs 22/30"
    assert thread.strength == "strong"


def test_lens_fields_survive_a_render_round_trip() -> None:
    threads = inventory.parse_inventory(LENS_INVENTORY)
    assert inventory.parse_inventory(inventory.render_inventory(threads)) == threads


def test_lens_fields_survive_a_merge() -> None:
    threads = inventory.parse_inventory(LENS_INVENTORY)
    assert inventory.merge([], threads)[0].strength == "strong"


def test_invalid_strength_fails_validation(tmp_path: Path) -> None:
    path = tmp_path / "inv.md"
    path.write_text(OLD_INVENTORY + "- **Strength**: certain\n", encoding="utf-8")
    assert pan.main(["validate", "--inventory", str(path)]) == 1


def test_empty_strength_is_accepted() -> None:
    assert inventory.parse_inventory(OLD_INVENTORY + "- **Strength**:\n")[0].strength == ""


def test_lens_fields_appear_in_gold_found(tmp_path: Path) -> None:
    threads = inventory.parse_inventory(LENS_INVENTORY)
    evaluations = tmp_path / "evals"
    evaluations.mkdir()
    (evaluations / synthesis.evaluation_filename(threads[0])).write_text(
        "Evaluation body.", encoding="utf-8"
    )
    text = synthesis.build_gold_found(threads, evaluations, source="s")
    assert "- **Strength**: strong" in text and "- **Claim**: The map alone scored 22/30" in text
