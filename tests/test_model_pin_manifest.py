"""Tests for build/model_pin_manifest.py.

Covers the ADR-080 sidecar-manifest-to-generator wiring: loading the
manifest, resolving a fresh KEEP_PIN entry for a source unit, and formatting
a resolved id in a platform's own spelling. See build/model_pin_manifest.py
for the canonical-source citations this module's contract is built from.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Add build directory to path for imports
_BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
sys.path.insert(0, str(_BUILD_DIR))

from model_pin_manifest import (  # noqa: E402
    MANIFEST_MAX_AGE_DAYS,
    format_model_id_for_platform,
    load_pin_manifest,
    resolve_manifest_model,
)


class TestLoadPinManifest:
    """Tests for load_pin_manifest."""

    def test_loads_pins_keyed_by_unit(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "model-pin-evidence.json"
        manifest_path.write_text(
            '{"schema_version": "1", "pins": ['
            '{"unit": "templates/agents/architect.shared.md", '
            '"model": "claude-opus-4-6", "decision": "KEEP_PIN"}'
            "]}",
            encoding="utf-8",
        )
        result = load_pin_manifest(manifest_path)
        assert result == {
            "templates/agents/architect.shared.md": {
                "unit": "templates/agents/architect.shared.md",
                "model": "claude-opus-4-6",
                "decision": "KEEP_PIN",
            }
        }

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = load_pin_manifest(tmp_path / "does-not-exist.json")
        assert result == {}

    def test_malformed_json_returns_empty(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "model-pin-evidence.json"
        manifest_path.write_text("{not valid json", encoding="utf-8")
        result = load_pin_manifest(manifest_path)
        assert result == {}

    def test_empty_pins_list_returns_empty(self, tmp_path: Path) -> None:
        """The real .agents/governance/model-pin-evidence.json today."""
        manifest_path = tmp_path / "model-pin-evidence.json"
        manifest_path.write_text('{"schema_version": "1", "pins": []}', encoding="utf-8")
        result = load_pin_manifest(manifest_path)
        assert result == {}

    def test_entries_missing_unit_field_are_skipped(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "model-pin-evidence.json"
        manifest_path.write_text(
            '{"pins": [{"model": "claude-opus-4-6", "decision": "KEEP_PIN"}]}',
            encoding="utf-8",
        )
        result = load_pin_manifest(manifest_path)
        assert result == {}

    def test_non_dict_entries_are_skipped(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "model-pin-evidence.json"
        manifest_path.write_text('{"pins": ["not-a-dict", 42]}', encoding="utf-8")
        result = load_pin_manifest(manifest_path)
        assert result == {}

    def test_pins_not_a_list_returns_empty(self, tmp_path: Path) -> None:
        manifest_path = tmp_path / "model-pin-evidence.json"
        manifest_path.write_text('{"pins": "not-a-list"}', encoding="utf-8")
        result = load_pin_manifest(manifest_path)
        assert result == {}


class TestResolveManifestModel:
    """Tests for resolve_manifest_model."""

    _UNIT = "templates/agents/architect.shared.md"
    _TODAY = date(2026, 8, 26)

    def _entry(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "unit": self._UNIT,
            "model": "claude-opus-4-6",
            "decision": "KEEP_PIN",
            "date": "2026-08-01",
        }
        base.update(overrides)
        return base

    def test_valid_keep_pin_entry_resolves(self) -> None:
        manifest = {self._UNIT: self._entry()}
        result = resolve_manifest_model(manifest, self._UNIT, today=self._TODAY)
        assert result == "claude-opus-4-6"

    def test_missing_entry_returns_none(self) -> None:
        result = resolve_manifest_model({}, self._UNIT, today=self._TODAY)
        assert result is None

    def test_decision_not_keep_pin_returns_none(self) -> None:
        manifest = {self._UNIT: self._entry(decision="RETIRE_PIN")}
        result = resolve_manifest_model(manifest, self._UNIT, today=self._TODAY)
        assert result is None

    def test_unit_mismatch_returns_none(self) -> None:
        """A malformed manifest keying an entry under one unit while the
        entry itself names another must not resolve for either."""
        manifest = {self._UNIT: self._entry(unit="templates/agents/other.shared.md")}
        result = resolve_manifest_model(manifest, self._UNIT, today=self._TODAY)
        assert result is None

    def test_blank_model_returns_none(self) -> None:
        manifest = {self._UNIT: self._entry(model="   ")}
        result = resolve_manifest_model(manifest, self._UNIT, today=self._TODAY)
        assert result is None

    def test_non_string_model_returns_none(self) -> None:
        manifest = {self._UNIT: self._entry(model=None)}
        result = resolve_manifest_model(manifest, self._UNIT, today=self._TODAY)
        assert result is None

    def test_missing_date_returns_none(self) -> None:
        entry = self._entry()
        del entry["date"]
        manifest = {self._UNIT: entry}
        result = resolve_manifest_model(manifest, self._UNIT, today=self._TODAY)
        assert result is None

    def test_malformed_date_returns_none(self) -> None:
        manifest = {self._UNIT: self._entry(date="not-a-date")}
        result = resolve_manifest_model(manifest, self._UNIT, today=self._TODAY)
        assert result is None

    def test_evidence_exactly_at_max_age_is_fresh(self) -> None:
        """age > MANIFEST_MAX_AGE_DAYS fails; age == MANIFEST_MAX_AGE_DAYS passes."""
        recorded = date(2026, 1, 1)
        # Ordinal math avoids month/day rollover edge cases from manual arithmetic.
        today = date.fromordinal(recorded.toordinal() + MANIFEST_MAX_AGE_DAYS)
        manifest = {self._UNIT: self._entry(date=recorded.isoformat())}
        result = resolve_manifest_model(manifest, self._UNIT, today=today)
        assert result == "claude-opus-4-6"

    def test_evidence_one_day_past_max_age_is_stale(self) -> None:
        recorded = date(2026, 1, 1)
        today = date.fromordinal(recorded.toordinal() + MANIFEST_MAX_AGE_DAYS + 1)
        manifest = {self._UNIT: self._entry(date=recorded.isoformat())}
        result = resolve_manifest_model(manifest, self._UNIT, today=today)
        assert result is None

    def test_defaults_today_to_real_date_when_omitted(self) -> None:
        """A fresh entry dated today, with no `today` override, still resolves."""
        manifest = {self._UNIT: self._entry(date=date.today().isoformat())}
        result = resolve_manifest_model(manifest, self._UNIT)
        assert result == "claude-opus-4-6"


class TestFormatModelIdForPlatform:
    """Tests for format_model_id_for_platform."""

    _COPILOT_TIERS = {
        "opus": "claude-opus-4.6",
        "sonnet": "claude-sonnet-4.6",
        "haiku": "claude-haiku-4.5",
    }
    _VSCODE_TIERS = {
        "opus": "Claude Opus 4.6 (copilot)",
        "sonnet": "Claude Sonnet 4.6 (copilot)",
        "haiku": "Claude Haiku 4.5 (copilot)",
    }

    def test_dot_form_platform_substitutes_manifest_version(self) -> None:
        """A manifest pin for a version the platform default doesn't carry
        yet still formats correctly, because the function substitutes
        digits into the template's shape rather than copying the template."""
        result = format_model_id_for_platform("claude-opus-5-1", self._COPILOT_TIERS)
        assert result == "claude-opus-5.1"

    def test_display_form_platform_substitutes_manifest_version(self) -> None:
        result = format_model_id_for_platform("claude-opus-5-1", self._VSCODE_TIERS)
        assert result == "Claude Opus 5.1 (copilot)"

    def test_dot_separator_in_manifest_id_also_parses(self) -> None:
        """The manifest schema does not mandate hyphen-only spelling; the
        parser accepts either separator ADR-080's _normalize_id treats as
        equivalent."""
        result = format_model_id_for_platform("claude-sonnet-4.6", self._COPILOT_TIERS)
        assert result == "claude-sonnet-4.6"

    def test_haiku_tier_formats_too(self) -> None:
        result = format_model_id_for_platform("claude-haiku-5-0", self._VSCODE_TIERS)
        assert result == "Claude Haiku 5.0 (copilot)"

    def test_date_stamped_id_fails_closed(self) -> None:
        """Outside the documented major.minor shape: emit no pin rather
        than guess (ADR-080 rule 5)."""
        result = format_model_id_for_platform(
            "claude-opus-4-20250514", self._COPILOT_TIERS
        )
        assert result is None

    def test_unknown_tier_fails_closed(self) -> None:
        result = format_model_id_for_platform("claude-ultra-4-6", self._COPILOT_TIERS)
        assert result is None

    def test_tier_missing_from_platform_tiers_fails_closed(self) -> None:
        result = format_model_id_for_platform(
            "claude-opus-4-6", {"sonnet": "claude-sonnet-4.6"}
        )
        assert result is None

    def test_unrecognized_template_shape_fails_closed(self) -> None:
        """The platform's own default spelling doesn't match either known
        shape (a hypothetical third platform format): fail closed rather
        than guess at a format nobody has verified."""
        result = format_model_id_for_platform(
            "claude-opus-4-6", {"opus": "gpt-5-opus"}
        )
        assert result is None

    def test_non_string_template_fails_closed(self) -> None:
        result = format_model_id_for_platform("claude-opus-4-6", {"opus": None})
        assert result is None
