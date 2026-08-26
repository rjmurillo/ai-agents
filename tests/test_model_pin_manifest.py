"""Tests for build/model_pin_manifest.py.

Covers the ADR-080 sidecar-manifest-to-generator wiring: loading the
manifest, resolving a fresh KEEP_PIN entry for a source unit, and formatting
a resolved id in a platform's own spelling. See build/model_pin_manifest.py
for the canonical-source citations this module's contract is built from.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# Add build directory to path for imports
_BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
sys.path.insert(0, str(_BUILD_DIR))

from model_pin_manifest import (  # noqa: E402
    DEFAULT_MODEL,
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


# Shared by TestResolveManifestModel here and
# TestSweepReportContentValidation in
# tests/test_model_pin_manifest_sweep_evidence.py (split out to keep this
# file under the whole-repo file-size ratchet; see that file's module
# docstring). A module-level helper, not a class method, so both files'
# test classes call the identical fixture-construction logic rather than
# each keeping their own partial copy.
_UNIT = "templates/agents/architect.shared.md"
_TODAY = date(2026, 8, 26)
_ARTIFACT = "evals/architect-spike/sweep.json"


def _keep_pin_entry(
    repo_root: Path,
    *,
    create_artifact: bool = True,
    artifact_content: dict[str, object] | None = None,
    **overrides: object,
) -> dict[str, object]:
    """Build a KEEP_PIN manifest entry, writing its sweep artifact by default.

    ADR-080 rule 2 requires a *committed* sweep artifact whose CONTENT shows
    a qualifying result (resolve_manifest_model parses it; see
    _sweep_report_satisfies_rule2 in build/model_pin_manifest.py), not
    merely a file that exists. create_artifact=False covers the negative
    cases where creating a file would be wrong: a blank artifact, a
    path-traversal artifact, and "nothing was ever committed".
    artifact_content lets a caller write a deliberately non-qualifying
    report (wrong winner, too few fixtures, etc.) while every other
    positive-path caller gets a report that actually agrees with the
    entry, matching what a real scripts/eval/eval-model-sweep.py run would
    produce.
    """
    base: dict[str, object] = {
        "unit": _UNIT,
        "model": "claude-opus-4-6",
        "decision": "KEEP_PIN",
        "date": "2026-08-01",
        "fixtures_sha": "abc123",
        "artifact": _ARTIFACT,
        "default_model": DEFAULT_MODEL,
    }
    base.update(overrides)
    if create_artifact and isinstance(base.get("artifact"), str) and base["artifact"]:
        artifact_path = repo_root / str(base["artifact"])
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if artifact_content is None:
            model = base.get("model")
            default_model = base.get("default_model")
            winner_id = model if isinstance(model, str) else "claude-opus-4-6"
            default_id = (
                default_model if isinstance(default_model, str) else DEFAULT_MODEL
            )
            artifact_content = {
                "schemaVersion": "1",
                "decision": "KEEP_PIN",
                "winner": winner_id,
                "fixtures_sha": base.get("fixtures_sha"),
                "default_model": default_id,
                "models": [
                    {"model_id": winner_id},
                    {"model_id": default_id},
                ],
                "n_shared_fixtures": 8,
                "recall_delta": 0.05,
                "ci95": [0.01, 0.09],
            }
        artifact_path.write_text(json.dumps(artifact_content), encoding="utf-8")
    return base


class TestResolveManifestModel:
    """Tests for resolve_manifest_model.

    ``check_model_pins.scan_units()`` only collects a unit whose frontmatter
    carries a truthy ``model`` or nested pin (scripts/validation/check_model_pins.py:343).
    A ``model_tier``-only template (this module's actual caller shape) has
    neither, so it is invisible to that scanner and the required
    ``Model Pin Governance`` CI check never independently validates a
    manifest entry for it. That is why every entry fixture here carries a
    full evidence shape (fixtures_sha, artifact, default_model): this
    function is the only place that evidence is checked for this unit
    class, so the tests must exercise all of it, not just decision/unit/date.

    Tests for the sweep-artifact CONTENT validation
    (_sweep_report_satisfies_rule2) live in
    tests/test_model_pin_manifest_sweep_evidence.py, split out to keep this
    file under the whole-repo file-size ratchet.
    """

    def test_valid_keep_pin_entry_resolves(self, tmp_path: Path) -> None:
        manifest = {_UNIT: _keep_pin_entry(tmp_path)}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result == "claude-opus-4-6"

    def test_missing_entry_returns_none(self, tmp_path: Path) -> None:
        result = resolve_manifest_model({}, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_decision_not_keep_pin_returns_none(self, tmp_path: Path) -> None:
        manifest = {_UNIT: _keep_pin_entry(tmp_path, decision="RETIRE_PIN")}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_unit_mismatch_returns_none(self, tmp_path: Path) -> None:
        """A malformed manifest keying an entry under one unit while the
        entry itself names another must not resolve for either."""
        manifest = {
            _UNIT: _keep_pin_entry(tmp_path, unit="templates/agents/other.shared.md")
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_blank_model_returns_none(self, tmp_path: Path) -> None:
        manifest = {_UNIT: _keep_pin_entry(tmp_path, model="   ")}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_non_string_model_returns_none(self, tmp_path: Path) -> None:
        manifest = {_UNIT: _keep_pin_entry(tmp_path, model=None)}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_missing_date_returns_none(self, tmp_path: Path) -> None:
        entry = _keep_pin_entry(tmp_path)
        del entry["date"]
        manifest = {_UNIT: entry}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_malformed_date_returns_none(self, tmp_path: Path) -> None:
        manifest = {_UNIT: _keep_pin_entry(tmp_path, date="not-a-date")}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_evidence_exactly_at_max_age_is_fresh(self, tmp_path: Path) -> None:
        """age > MANIFEST_MAX_AGE_DAYS fails; age == MANIFEST_MAX_AGE_DAYS passes."""
        recorded = date(2026, 1, 1)
        # Ordinal math avoids month/day rollover edge cases from manual arithmetic.
        today = date.fromordinal(recorded.toordinal() + MANIFEST_MAX_AGE_DAYS)
        manifest = {_UNIT: _keep_pin_entry(tmp_path, date=recorded.isoformat())}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=today)
        assert result == "claude-opus-4-6"

    def test_evidence_one_day_past_max_age_is_stale(self, tmp_path: Path) -> None:
        recorded = date(2026, 1, 1)
        today = date.fromordinal(recorded.toordinal() + MANIFEST_MAX_AGE_DAYS + 1)
        manifest = {_UNIT: _keep_pin_entry(tmp_path, date=recorded.isoformat())}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=today)
        assert result is None

    def test_future_dated_evidence_is_rejected(self, tmp_path: Path) -> None:
        """A negative age (date typo'd into the future) must not resolve,
        even though it is well within MANIFEST_MAX_AGE_DAYS of today."""
        today = date(2026, 8, 1)
        recorded = date(2026, 8, 2)  # one day after "today"
        manifest = {_UNIT: _keep_pin_entry(tmp_path, date=recorded.isoformat())}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=today)
        assert result is None

    def test_defaults_today_to_real_date_when_omitted(self, tmp_path: Path) -> None:
        """A fresh entry dated today, with no `today` override, still resolves.

        Built from the UTC date, matching resolve_manifest_model's own
        default (datetime.now(timezone.utc).date()), not the host's local
        date: on a host ahead of UTC, date.today() can already read as
        "tomorrow" in UTC terms, which would make this fixture look
        future-dated and fail via the age < 0 guard for reasons unrelated
        to what this test is checking."""
        utc_today = datetime.now(timezone.utc).date()
        manifest = {_UNIT: _keep_pin_entry(tmp_path, date=utc_today.isoformat())}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path)
        assert result == "claude-opus-4-6"

    def test_missing_fixtures_sha_returns_none(self, tmp_path: Path) -> None:
        manifest = {_UNIT: _keep_pin_entry(tmp_path, fixtures_sha="")}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_missing_artifact_returns_none(self, tmp_path: Path) -> None:
        manifest = {
            _UNIT: _keep_pin_entry(tmp_path, artifact="", create_artifact=False)
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_path_traversal_returns_none(self, tmp_path: Path) -> None:
        """CWE-22: an artifact path escaping repo_root must not resolve."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path, artifact="../../etc/passwd", create_artifact=False
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_not_committed_returns_none(self, tmp_path: Path) -> None:
        """The path is safely contained but nothing was ever written there:
        ADR-080 rule 2 requires a *committed* sweep artifact, not merely a
        well-formed path to one."""
        manifest = {
            _UNIT: _keep_pin_entry(tmp_path, create_artifact=False)
        }
        assert not (tmp_path / _ARTIFACT).exists()
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_default_model_mismatch_returns_none(self, tmp_path: Path) -> None:
        """Evidence recorded against a different harness default is stale
        in the sense that matters: the comparison it made no longer
        reflects the current baseline."""
        manifest = {_UNIT: _keep_pin_entry(tmp_path, default_model="claude-opus-4-6")}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_default_model_matches_via_dot_hyphen_normalization(
        self, tmp_path: Path
    ) -> None:
        """default_model comparison normalizes dots and hyphens, matching
        check_model_pins.py's _normalize_id. DEFAULT_MODEL is
        "claude-sonnet-4-6"; recording it with a dot before the final
        digit ("claude-sonnet-4.6") must still compare equal."""
        assert DEFAULT_MODEL == "claude-sonnet-4-6"
        dotted = "claude-sonnet-4.6"
        manifest = {_UNIT: _keep_pin_entry(tmp_path, default_model=dotted)}
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result == "claude-opus-4-6"

    def test_custom_default_model_parameter_is_honored(self, tmp_path: Path) -> None:
        manifest = {
            _UNIT: _keep_pin_entry(tmp_path, default_model="claude-haiku-4-5")
        }
        result = resolve_manifest_model(
            manifest, _UNIT, tmp_path, today=_TODAY,
            default_model="claude-haiku-4-5",
        )
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

    def test_mismatched_tier_template_fails_closed_display_form(self) -> None:
        """A platform config bug (opus: mapped to a Sonnet-shaped string)
        must not silently emit an Opus manifest pin labeled Sonnet."""
        result = format_model_id_for_platform(
            "claude-opus-4-6", {"opus": "Claude Sonnet 4.6 (copilot)"}
        )
        assert result is None

    def test_mismatched_tier_template_fails_closed_dot_form(self) -> None:
        result = format_model_id_for_platform(
            "claude-opus-4-6", {"opus": "claude-sonnet-4.6"}
        )
        assert result is None
