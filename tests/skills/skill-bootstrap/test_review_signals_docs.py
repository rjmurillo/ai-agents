"""The shipped text names the review-friction signals, the gate, and the limit of the proof."""

from __future__ import annotations

from pathlib import Path

import review_clusters as rc

SKILL = Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "skill-bootstrap"
TEMPLATE = Path(__file__).resolve().parents[3] / "templates" / "skills"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def flat(path: Path) -> str:
    """The file with line wrapping collapsed, so a needle can span a wrapped line."""
    return " ".join(read(path).split())


def test_the_template_names_both_signals_the_gate_and_the_limit() -> None:
    text = read(TEMPLATE / "skill-bootstrap.SKILL.md.tmpl")

    for needle in (
        "review_failures",
        "missed_items",
        f"{rc.THRESHOLD} or more pull requests in {rc.WINDOW_DAYS} days",
        "satisfies the workflow gate",
        "not a shared cause",
        "arXiv:2610.32313",
        "CRBugBench",
    ):
        assert needle in text, needle


def test_the_workflow_mode_gate_row_lists_the_new_evidence() -> None:
    text = read(TEMPLATE / "skill-bootstrap.SKILL.md.tmpl")
    row = next(
        line for line in text.splitlines() if line.lstrip().startswith("| `workflow` (default)")
    )

    assert "review failures" in row
    assert "missed items" in row


def test_the_render_matches_the_template_wording() -> None:
    assert "review_failures" in read(SKILL / "SKILL.md")


def test_discovery_defines_the_signals_gate_and_what_the_script_proves() -> None:
    text = flat(SKILL / "references" / "discovery.md")

    for needle in (
        "`review_failures`",
        "`missed_items`",
        f"needs {rc.THRESHOLD} distinct pull requests",
        f"trailing {rc.WINDOW_DAYS} days",
        "satisfies the workflow mode gate once you have read",
        "What the script proves",
        "compares no free text",
        "Zero is a result",
        "thread_data_provided",
    ):
        assert needle in text, needle


def test_discovery_counts_a_disposition_over_the_whole_file_not_per_pull_request() -> None:
    text = flat(SKILL / "references" / "discovery.md")

    assert (
        f"A disposition category needs {rc.THRESHOLD} distinct `--dispositions-json` entries"
        in text
    )
    assert "counted over the whole file" in text


def test_discovery_describes_the_area_key_as_the_directory_not_the_file() -> None:
    text = flat(SKILL / "references" / "discovery.md")

    assert f"cut to its first {'four' if rc.AREA_DEPTH == 4 else rc.AREA_DEPTH} segments" in text
    assert "`src/x.py` gives `src`" in text
    assert "(repo root)" in text


def test_the_export_shape_documents_every_field_the_miner_reads() -> None:
    text = read(SKILL / "references" / "hosted-platforms.md")
    section = text[text.index("## Review export for mined review friction") :]

    for field in (
        "review_threads",
        "files",
        "body",
        "commit_messages",
        "introduced_by",
        "thread_id",
        "created_at",
        "human",
        "path",
    ):
        assert f"`{field}`" in section, field
    assert "Required" in section
    assert "Required when `human` is true" in section
