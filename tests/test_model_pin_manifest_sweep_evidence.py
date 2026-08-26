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
                    "decision": "DROP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
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
        manifest entry claims it justifies."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "decision": "KEEP_PIN",
                    "winner": "claude-sonnet-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
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
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "different-sha",
                    "default_model": DEFAULT_MODEL,
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
        test_default_model_mismatch_returns_none in test_model_pin_manifest.py."""
        manifest = {
            _UNIT: _keep_pin_entry(
                tmp_path,
                artifact_content={
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": "claude-haiku-4-5",
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
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
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
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
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
                    "decision": "KEEP_PIN",
                    "winner": "claude-opus-4-6",
                    "fixtures_sha": "abc123",
                    "default_model": DEFAULT_MODEL,
                    "n_shared_fixtures": 8,
                    "recall_delta": 0.05,
                    "ci95": [0.0, 0.09],
                },
            )
        }
        result = resolve_manifest_model(manifest, _UNIT, tmp_path, today=_TODAY)
        assert result is None
