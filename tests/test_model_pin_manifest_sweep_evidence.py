"""Tests for the sweep-artifact CONTENT validation in resolve_manifest_model.

Split out of tests/test_model_pin_manifest.py (whole-repo file-size ratchet)
to keep this file's concern separate from TestResolveManifestModel's
entry-level evidence checks (decision, unit, date, fixtures_sha presence,
default_model-vs-harness). ``(repo_root / artifact).is_file()`` proves only
that some bytes exist at the path; a fixture that writes ``{}`` passed that
check while carrying none of the evidence ADR-080 rule 2 requires. This file
covers the parse-and-cross-check step
(``build/model_pin_manifest.py:_sweep_report_satisfies_rule2``) that reads
the sweep report and verifies its own claims (winning model, fixtures_sha,
default_model, fixture count, delta, CI) rather than trusting the file's
mere existence.

Shares tests/test_model_pin_manifest.py's ``_keep_pin_entry`` fixture helper
and ``_UNIT``/``_TODAY`` constants by importing them directly, so the entry
shape has exactly one definition across both files.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add build directory to path for imports
_BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
sys.path.insert(0, str(_BUILD_DIR))

from model_pin_manifest import DEFAULT_MODEL, resolve_manifest_model  # noqa: E402

from tests.test_model_pin_manifest import _TODAY, _UNIT, _keep_pin_entry  # noqa: E402

# The report's own models list, exactly {winner, default_model}, matching
# every test in this file whose winner is "claude-opus-4-6" and whose
# default_model is DEFAULT_MODEL. Tests whose report claims a DIFFERENT
# winner or default_model (the mismatch tests below) build their own
# models list instead, so it stays internally consistent with what that
# specific report claims.
_SINGLE_CANDIDATE_MODELS = [
    {"model_id": "claude-opus-4-6"},
    {"model_id": DEFAULT_MODEL},
]


class TestSweepReportContentValidation:
    """Tests for _sweep_report_satisfies_rule2, via resolve_manifest_model."""

    def test_artifact_committed_but_empty_returns_none(self, tmp_path: Path) -> None:
        """The exact case a reviewer flagged: a committed artifact whose
        content carries no evidence at all. is_file() alone accepted this;
        _sweep_report_satisfies_rule2 must not."""
        manifest = {
            _UNIT: _keep_pin_entry(tmp_path, artifact_content={})
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_decision_not_keep_pin_returns_none(self, tmp_path: Path) -> None:
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "architect",
                    "decision": "DROP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_winner_mismatch_returns_none(self, tmp_path: Path) -> None:
        """The report's own winning model must agree with the model the
        manifest entry claims it justifies. The report's models list
        describes the report's OWN winner/default_model pair (internally
        consistent, so this isolates the entry-vs-report mismatch rather
        than also tripping the single-candidate check)."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "architect",
                    "decision": "KEEP_PIN",
                    "winner": "claude-sonnet-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": [
                        {"model_id": "claude-sonnet-4-6"},
                        {"model_id": DEFAULT_MODEL},
                    ],
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_fixtures_sha_mismatch_returns_none(self, tmp_path: Path) -> None:
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "architect",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "different-sha",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_default_model_mismatch_returns_none(self, tmp_path: Path) -> None:
        """The report's own default_model must agree with the manifest
        entry's, independent of the entry-vs-harness comparison covered by
        test_default_model_mismatch_returns_none in test_model_pin_manifest.py.
        The models list matches the report's own winner/default_model pair
        for the same isolation reason as the winner-mismatch test above."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "architect",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": "claude-haiku-4-5",
                    "models": [
                        {"model_id": "claude-opus-4-6"},
                        {"model_id": "claude-haiku-4-5"},
                    ],
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_insufficient_fixtures_returns_none(self, tmp_path: Path) -> None:
        """ADR-080 rule 2: at least 8 shared fixtures. 7 must fail closed."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "architect",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 7,
                    "recall_delta": 0.05,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_insufficient_delta_returns_none(self, tmp_path: Path) -> None:
        """ADR-080 rule 2: delta >= 0.05. 0.049 must fail closed."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "architect",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.049,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_non_positive_ci_lower_bound_returns_none(
        self, tmp_path: Path
    ) -> None:
        """ADR-080 rule 2: the bootstrap CI lower bound must be > 0. A CI
        that still straddles zero must fail closed even with a qualifying
        point-estimate delta."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "architect",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.0, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_wrong_schema_version_returns_none(self, tmp_path: Path) -> None:
        """build_report's schemaVersion "gates future shape changes"
        (scripts/eval/_model_sweep_core.py:469-474); a report claiming a
        different version has not committed to the field set this module
        reads, even if every other field looks otherwise valid."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "2",
                    "agent": "architect",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_agent_mismatch_returns_none(self, tmp_path: Path) -> None:
        """build_report records an "agent" field
        (scripts/eval/_model_sweep_core.py:481); without cross-checking it,
        a sweep for a DIFFERENT agent could justify this manifest entry
        whenever winner, fixtures_sha, and default_model happen to
        coincide, since none of those three fields are unit-specific by
        themselves. _UNIT is "templates/agents/architect.shared.md", so
        the report's own agent must be "architect", not "security" or
        anything else."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "security",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_missing_agent_returns_none(self, tmp_path: Path) -> None:
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_missing_schema_version_returns_none(
        self, tmp_path: Path
    ) -> None:
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_multi_candidate_sweep_returns_none(
        self, tmp_path: Path
    ) -> None:
        """ADR-080 rule 2 requires "a single-candidate-versus-default sweep
        (so the CI is a plain 95 percent interval, not Bonferroni-widened)"
        (.agents/architecture/ADR-080-model-pin-justification-policy.md:89-90).
        A third candidate in the models list, even with a numerically
        qualifying ci95, means this report cannot be that: the
        family-wise-adjusted CI a multi-candidate sweep computes lands in
        the same ci95 field (scripts/eval/_model_sweep_core.py, the
        "family-wise CI" reason text), so it must fail closed."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "architect",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": [
                        {"model_id": "claude-opus-4-6"},
                        {"model_id": DEFAULT_MODEL},
                        {"model_id": "claude-haiku-4-5"},
                    ],
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_boolean_recall_delta_returns_none(
        self, tmp_path: Path
    ) -> None:
        """bool is an int subclass in Python: an unguarded numeric check
        would accept JSON `true` as a qualifying delta (True >= 0.05 is
        True). Must fail closed instead."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "architect",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 8,
                    "recall_delta": True,
                    "ci95": [0.01, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_boolean_ci_bound_returns_none(self, tmp_path: Path) -> None:
        """Same bool-as-int trap as the delta case, on ci95[0]: an
        unguarded check would accept JSON `true` as if it were a positive
        CI lower bound (True > 0.0 is True)."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "schemaVersion": "1",
                    "agent": "architect",
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "models": _SINGLE_CANDIDATE_MODELS,
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [True, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None

    def test_artifact_nan_recall_delta_returns_none(self, tmp_path: Path) -> None:
        """json.loads accepts NaN as a valid float by default, and
        `float("nan") < 0.05` is always False (NaN compares false against
        everything), so an unguarded `delta < MIN_RECALL_DELTA` rejection
        would let a NaN delta through as though it qualified. Writes raw
        JSON text directly: json.dumps(float("nan")) also emits the bare
        `NaN` token by default, but constructing it via Python's own float
        keeps the intent explicit rather than relying on that default."""
        entry = _keep_pin_entry(tmp_path, create_artifact=False)
        manifest = {_UNIT: entry}
        artifact_path = tmp_path / str(entry["artifact"])
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            "{"
            '"schemaVersion": "1", "agent": "architect", '
            '"decision": "KEEP_PIN", '
            '"winner": "claude-opus-4-6", "fixtures_sha": "abc123", '
            f'"default_model": "{DEFAULT_MODEL}", '
            '"models": [{"model_id": "claude-opus-4-6"}, '
            f'{{"model_id": "{DEFAULT_MODEL}"}}], '
            '"n_shared_fixtures": 8, "recall_delta": NaN, "ci95": [0.01, 0.09]'
            "}",
            encoding="utf-8",
        )
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None
