"""Tests for scripts/eval/_model_panel_core.py (issue #3042)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import _model_panel_core as core  # noqa: E402


def _panel(threshold=0.15):
    return core.Panel(
        tiers=(
            core.PanelTier("opus", core.ROLE_REFERENCE, "anthropic", "claude-opus-4-8"),
            core.PanelTier("sol", core.ROLE_REFERENCE, "openai", "openai/gpt-5.6"),
            core.PanelTier("sonnet", core.ROLE_PROBE, "anthropic", "claude-sonnet-4-6"),
        ),
        drop_threshold=threshold,
    )


# --- parse_panel -------------------------------------------------------------


def test_parse_panel_ok():
    payload = {
        "drop_threshold": 0.2,
        "tiers": [
            {"label": "opus", "role": "reference", "provider": "anthropic", "model": "m1"},
            {"label": "sonnet", "role": "probe", "provider": "anthropic", "model": "m2"},
        ],
    }
    panel = core.parse_panel(payload)
    assert panel.drop_threshold == 0.2
    assert [t.label for t in panel.reference_tiers] == ["opus"]
    assert [t.label for t in panel.probe_tiers] == ["sonnet"]


def test_parse_panel_empty_tiers_raises():
    with pytest.raises(core.PanelConfigError, match="non-empty"):
        core.parse_panel({"tiers": []})


def test_parse_panel_missing_field_raises():
    with pytest.raises(core.PanelConfigError, match="missing"):
        core.parse_panel({"tiers": [{"label": "x", "role": "probe", "provider": "a"}]})


def test_parse_panel_bad_role_raises():
    with pytest.raises(core.PanelConfigError, match="role"):
        core.parse_panel({"tiers": [
            {"label": "x", "role": "gate", "provider": "a", "model": "m"},
        ]})


def test_parse_panel_no_reference_raises():
    with pytest.raises(core.PanelConfigError, match="reference"):
        core.parse_panel({"tiers": [
            {"label": "x", "role": "probe", "provider": "a", "model": "m"},
        ]})


def test_parse_panel_unknown_provider_raises():
    with pytest.raises(core.PanelConfigError, match="unknown provider"):
        core.parse_panel(
            {"tiers": [
                {"label": "x", "role": "reference", "provider": "nope", "model": "m"},
            ]},
            known_providers={"anthropic", "openai"},
        )


def test_load_panel_config_bad_json_raises():
    with pytest.raises(core.PanelConfigError, match="not valid JSON"):
        core.load_panel_config("{not json")


def test_default_panel_shape():
    panel = core.default_panel()
    assert len(panel.reference_tiers) == 2
    assert len(panel.probe_tiers) == 2


# --- cell_from_report --------------------------------------------------------


def test_cell_from_report_extracts_delta_and_ci():
    cell = core.cell_from_report("qa", "opus", {
        "recall_delta": 0.42, "bootstrap_ci_95": [0.3, 0.5],
    })
    assert cell.ok
    assert cell.recall_delta == 0.42
    assert cell.ci_low == 0.3 and cell.ci_high == 0.5


def test_cell_from_report_missing_delta_is_error():
    cell = core.cell_from_report("qa", "opus", {"foo": 1})
    assert not cell.ok
    assert "recall_delta" in cell.error


# --- summarize ---------------------------------------------------------------


def _cells(**deltas):
    return [
        core.CellResult(unit="qa", tier=t, recall_delta=d)
        for t, d in deltas.items()
    ]


def test_robust_when_probe_matches_reference():
    panel = _panel()
    cells = {c.tier: c for c in _cells(opus=0.5, sol=0.5, sonnet=0.45)}
    v = core.summarize_unit("qa", panel, cells)
    assert v.reference_delta == pytest.approx(0.5)
    assert v.robust is True
    assert v.degraded_tiers == []


def test_degrades_when_probe_drops_past_threshold():
    panel = _panel(threshold=0.15)
    cells = {c.tier: c for c in _cells(opus=0.5, sol=0.5, sonnet=0.2)}  # drop 0.3 > 0.15
    v = core.summarize_unit("qa", panel, cells)
    assert v.robust is False
    assert v.degraded_tiers == ["sonnet"]


def test_incomplete_when_reference_missing():
    panel = _panel()
    # only a probe scored; no reference band
    cells = {c.tier: c for c in _cells(sonnet=0.3)}
    v = core.summarize_unit("qa", panel, cells)
    assert v.incomplete is True
    assert v.robust is False


def test_reference_band_is_mean_of_reference_tiers():
    panel = _panel()
    cells = {c.tier: c for c in _cells(opus=0.6, sol=0.4, sonnet=0.45)}
    v = core.summarize_unit("qa", panel, cells)
    assert v.reference_delta == pytest.approx(0.5)  # mean(0.6,0.4)
    assert v.robust is True  # 0.5 - 0.45 = 0.05 < 0.15


def test_summarize_groups_and_orders_units():
    panel = _panel()
    results = [
        core.CellResult("b", "opus", recall_delta=0.5),
        core.CellResult("a", "opus", recall_delta=0.5),
    ]
    verdicts = core.summarize(panel, results)
    assert [v.unit for v in verdicts] == ["a", "b"]


# --- renderers ---------------------------------------------------------------


def test_to_json_shape():
    panel = _panel()
    cells = {c.tier: c for c in _cells(opus=0.5, sol=0.5, sonnet=0.2)}
    verdicts = [core.summarize_unit("qa", panel, cells)]
    payload = core.to_json(panel, verdicts)
    assert payload["reference_tiers"] == ["opus", "sol"]
    assert payload["units"][0]["degraded_tiers"] == ["sonnet"]


def test_to_human_labels_degradation():
    panel = _panel()
    cells = {c.tier: c for c in _cells(opus=0.5, sol=0.5, sonnet=0.2)}
    text = core.to_human(panel, [core.summarize_unit("qa", panel, cells)])
    assert "DEGRADES at sonnet" in text
