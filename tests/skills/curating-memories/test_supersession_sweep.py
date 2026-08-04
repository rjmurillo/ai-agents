"""Tests for the supersession sweep classifier (issue #3019).

Locks the classification contract that keeps the sweep useful and safe:

- The two confirmed append-never-delete cases classify as
  resolved-or-historical-but-present (AC2).
- The healthy-supersession exemplar classifies as healthy-supersession and
  is left alone, proving strikethrough density alone never triggers a rot
  proposal (AC3 false-positive guard).
- The sweep proposes and never edits (AC4).

Without these tests a future contributor could relax a threshold or reorder
the precedence and silently turn the false-positive guard off, which would
route a load-bearing memory toward archival.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "curating-memories" / "scripts"
_orig_sys_path = list(sys.path)
sys.path.insert(0, str(SCRIPT_DIR))
try:
    import supersession_sweep as sweep_mod
finally:
    sys.path[:] = _orig_sys_path

LIVE = sweep_mod.LIVE
HEALTHY = sweep_mod.HEALTHY_SUPERSESSION
ROT = sweep_mod.RESOLVED_HISTORICAL
SNAPSHOT = sweep_mod.TEMPORAL_SNAPSHOT

MEMORIES = REPO_ROOT / ".serena" / "memories"


# --- positive: each bucket ------------------------------------------------


def test_resolved_status_with_removed_refs_is_rot() -> None:
    text = (
        "# Bug\n\n**Status**: RESOLVED\n\n"
        "The old_script.py (removed) and helper_mod (removed) are gone.\n"
    )
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) == ROT


def test_blocking_status_with_removed_refs_is_rot() -> None:
    text = (
        "# Blocker\n\n**Status**: BLOCKING\n\n"
        "workflow-a (removed), workflow-b (removed), action-c (removed).\n"
    )
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) == ROT


def test_resolved_status_with_historical_tag_is_rot() -> None:
    text = "# Old\n\n**Status**: RESOLVED\n\n## Context (Historical)\n\nstuff\n"
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) == ROT


def test_dated_banner_with_strikethrough_is_healthy() -> None:
    text = (
        "# Ref\n\n> **IMPORTANT (2025-12-21)**: public repo, runners free.\n\n"
        "| ~~Old~~ | ~~gone~~ | ~~n/a~~ | ~~x~~ |\n"
    )
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) == HEALTHY


def test_dated_snapshot_framing_is_temporal_snapshot() -> None:
    text = "# Roadmap v0.3.0\n\nAs of 2026-01-23, the top 10 items are:\n\n- one\n"
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) == SNAPSHOT


def test_plain_guidance_is_live() -> None:
    text = "# How to do X\n\nRun the thing. Then check the result.\n"
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) == LIVE


def test_version_string_without_framing_is_not_snapshot() -> None:
    # Regression: a historical changelog with a version like v3.0.0 and a date
    # must not be flagged as temporal-snapshot-as-live. Only explicit framing
    # (top N, snapshot, as of, current state) qualifies.
    text = "# Skill - Version History\n\n## v3.0.0 (2026-01-03)\n\nChanged stuff.\n"
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) != SNAPSHOT


# --- negative / false-positive guards -------------------------------------


def test_strikethrough_alone_is_not_rot() -> None:
    # AC3: strikethrough density without a resolved/blocking status must not
    # be flagged for archival.
    text = "# Table\n\n| ~~a~~ | ~~b~~ | ~~c~~ | ~~d~~ | ~~e~~ |\n"
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) != ROT


def test_removed_refs_without_status_is_not_rot() -> None:
    text = "# Notes\n\nWe deleted old.py (removed) and gone.py (removed) last week.\n"
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) != ROT


def test_healthy_requires_banner_not_strikethrough_alone() -> None:
    text = "# Table\n\n| ~~a~~ | ~~b~~ | ~~c~~ | ~~d~~ |\n"
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) != HEALTHY


def test_resolved_status_alone_without_gone_artifacts_is_not_rot() -> None:
    # A resolved note that still points at live artifacts is not rot.
    text = "# Done\n\n**Status**: RESOLVED\n\nSee current_module for details.\n"
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) != ROT


# --- edge -----------------------------------------------------------------


def test_empty_file_is_live() -> None:
    assert sweep_mod.classify(sweep_mod.scan_signals("")) == LIVE


def test_single_removed_ref_below_threshold_is_not_rot() -> None:
    text = "# X\n\n**Status**: RESOLVED\n\nonly one.py (removed) here.\n"
    assert sweep_mod.classify(sweep_mod.scan_signals(text)) != ROT


def test_scan_signals_counts_pairs_and_refs() -> None:
    text = "**Status**: BLOCKING\n(removed) (removed) ~~a~~ ~~b~~ (Historical)\n"
    sig = sweep_mod.scan_signals(text)
    assert sig.status_resolved_blocking is True
    assert sig.removed_refs == 2
    assert sig.strikethrough_pairs == 2
    assert sig.historical_tags == 1


# --- sweep + CLI ----------------------------------------------------------


def test_sweep_proposes_without_editing(tmp_path: Path) -> None:
    rot = tmp_path / "a.md"
    rot.write_text("**Status**: RESOLVED\nx.py (removed) y.py (removed)\n")
    live = tmp_path / "b.md"
    live.write_text("# Live\n\nCurrent guidance.\n")
    before = {p: p.read_text(encoding="utf-8") for p in (rot, live)}

    proposals = sweep_mod.sweep(tmp_path)

    dispositions = {p.path: p.disposition for p in proposals}
    assert dispositions["a.md"] == ROT
    assert dispositions["b.md"] == LIVE
    # AC4: nothing on disk changed.
    for path, content in before.items():
        assert path.read_text(encoding="utf-8") == content


def test_main_json_exit_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.md").write_text("**Status**: RESOLVED\n(removed) (removed)\n")
    rc = sweep_mod.main(["--root", str(tmp_path), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"][ROT] == 1


def test_main_text_exit_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.md").write_text("# Live\n\nguidance\n")
    rc = sweep_mod.main(["--root", str(tmp_path)])
    assert rc == 0
    assert "proposal only" in capsys.readouterr().out


def test_healthy_supersession_not_listed_as_proposal() -> None:
    # Regression: healthy-supersession is "leave alone", so it must be counted
    # but never appear under Proposals, which would misroute operator attention.
    healthy = sweep_mod.Proposal("h.md", HEALTHY, {})
    rot = sweep_mod.Proposal("r.md", ROT, {})
    report = sweep_mod.render_text([healthy, rot])
    proposals_section = report.split("Proposals", 1)[1]
    assert "r.md" in proposals_section
    assert "h.md" not in proposals_section


def test_main_missing_root_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = sweep_mod.main(["--root", "/nonexistent/path/xyz"])
    assert rc == 0
    assert "root not found" in capsys.readouterr().err


def test_main_missing_root_json_emits_error_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # --json callers must get parseable JSON even on a bad root, not empty
    # stdout, so a downstream parser gets a structured error.
    rc = sweep_mod.main(["--root", "/nonexistent/path/xyz", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert json.loads(out)["error"].startswith("root not found")


def test_sweep_skips_unreadable_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = tmp_path / "good.md"
    good.write_text("# Live\n\nguidance\n")
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")

    proposals = sweep_mod.sweep(tmp_path)

    paths = {p.path for p in proposals}
    assert "good.md" in paths
    assert "bad.md" not in paths
    assert "skipping" in capsys.readouterr().err


# --- integration: real acceptance-criteria files --------------------------


@pytest.mark.skipif(not MEMORIES.is_dir(), reason="memories tree absent")
@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("session/session-protocol-validator-pipe-bug.md", ROT),
        ("ci/ci-infrastructure-droid-action-blocker.md", ROT),
        ("cost/cost-summary-reference.md", HEALTHY),
        ("planning/roadmap-v030-top-10-items.md", SNAPSHOT),
    ],
)
def test_confirmed_cases_classify_as_expected(rel: str, expected: str) -> None:
    # When the whole memories tree is absent (shallow checkout, foreign
    # environment) the module-level skipif above skips this test. But when
    # the tree IS present, a missing named case must FAIL, not skip: these
    # files are the #3019 contract, and a silent skip would hide a rename,
    # removal, or premature ratification that changed a proof case.
    path = MEMORIES / rel
    assert path.exists(), (
        f"confirmed-case memory {rel} is missing; the #3019 contract requires "
        "it. If it was intentionally renamed or ratified, update this test."
    )
    assert sweep_mod.classify_file(path) == expected
