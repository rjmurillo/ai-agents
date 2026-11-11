"""The shipped text names the review-friction signals, the gate, and the limit of the proof."""

from __future__ import annotations

from pathlib import Path

import review_clusters as rc

SKILL = Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "skill-bootstrap"
TEMPLATE = Path(__file__).resolve().parents[3] / "templates" / "skills"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
    text = read(SKILL / "references" / "discovery.md")

    for needle in (
        "`review_failures`",
        "`missed_items`",
        f"{rc.THRESHOLD} distinct pull",
        f"trailing {rc.WINDOW_DAYS} days",
        "satisfies the workflow mode gate",
        "What the script proves",
        "compares no free text",
        "Zero is a result",
        "thread_data_provided",
    ):
        assert needle in text, needle


def test_discovery_states_the_area_depth_the_module_enforces() -> None:
    text = read(SKILL / "references" / "discovery.md")

    assert f"first {'four' if rc.AREA_DEPTH == 4 else rc.AREA_DEPTH} path segments" in text


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
