#!/usr/bin/env python3
"""Parse and validate an ADR-080 sweep artifact's own content.

Split out of ``build/model_pin_manifest.py`` (whole-repo file-size ratchet;
that file crossed 500 lines when this content-validation logic first
landed there). This module answers one question:

    Given a manifest entry's ``artifact`` path resolves to a real,
    committed file, does that file's CONTENT actually qualify as ADR-080
    rule 2 evidence, and does it agree with the manifest entry citing it?

``model_pin_manifest.py``'s ``_entry_evidence_valid`` already confirms the
artifact path is safe (CWE-22) and exists as a file before calling
``_sweep_report_satisfies_rule2`` here; existence alone proves nothing
about content, since a fixture (or a real but malformed report) can
satisfy ``is_file()`` while carrying none of rule 2's actual evidence bar:
``delta >= 0.05`` mean recall and a positive paired-bootstrap CI lower
bound, from a single-candidate-versus-default sweep, over at least 8
shared fixtures
(``.agents/architecture/ADR-080-model-pin-justification-policy.md:86-90``).

Canonical report schema: ``scripts/eval/_model_sweep_core.py:build_report``
(lines 460-511).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TypeGuard

# ADR-080 rule 2: a KEEP_PIN sweep must cover "at least 8 shared fixtures"
# (.agents/architecture/ADR-080-model-pin-justification-policy.md:90).
MIN_SHARED_FIXTURES = 8

# Mirrors scripts/eval/_model_sweep_core.py:62 (DEFAULT_MIN_EFFECT = 0.05)
# verbatim; the qualification formula it feeds
# (``qualifies = delta >= min_effect and ci_low > 0.0``) is at that module's
# line 306. Not imported: _model_sweep_core.py:35 does
# ``from _report_aggregator import (...)``, a bare module-relative import
# that requires scripts/eval on sys.path, the exact sys.path mutation
# build/model_pin_manifest.py's own docstring already avoids for
# check_model_pins.py's load_manifest.
MIN_RECALL_DELTA = 0.05

# Mirrors scripts/eval/_model_sweep_core.py:61 (SCHEMA_VERSION = "1")
# verbatim. build_report's own docstring (lines 469-474) says this field
# "gates future shape changes"; a report missing it, or carrying a
# different value, has not committed to the field set this module reads.
SWEEP_REPORT_SCHEMA_VERSION = "1"


def _normalize_id(model_id: str) -> str:
    """Collapse dots to hyphens so dotted and hyphenated ids compare equal.

    Mirrors ``scripts/validation/check_model_pins.py:119-125``
    (``_normalize_id``) verbatim: ``copilot-cli.yaml`` spells ids with dots
    (``claude-opus-4.6``); the manifest and pricing table use hyphens
    (``claude-opus-4-6``).
    """
    return model_id.replace(".", "-")


def _agent_name_from_unit(unit: object) -> str | None:
    """Derive the agent name ``build_report`` would have recorded for this unit.

    Mirrors ``build/generate_agents.py:265``
    (``agent_name = shared_file.stem.replace(".shared", "")``) verbatim: the
    unit is ``templates/agents/<name>.shared.md``, and
    ``scripts/eval/_model_sweep_core.py:481``'s ``build_report`` writes that
    same ``<name>`` into the report's ``agent`` field. Without this check, a
    sweep report for one agent could justify a manifest entry for a
    different one whenever winner, ``fixtures_sha``, and ``default_model``
    happen to coincide, since none of those fields are unit-specific by
    themselves.
    """
    if not isinstance(unit, str):
        return None
    return Path(unit).stem.replace(".shared", "")


def _report_model_id_matches(report_value: object, entry_value: object) -> bool:
    """Normalize-compare one report model-id field against the entry's.

    Shared by the ``winner``-vs-``model`` and ``default_model``-vs-
    ``default_model`` legs of ``_sweep_report_satisfies_rule2``; split out
    so that function stays under the cyclomatic-complexity ceiling
    (``.claude/rules/code-quality.md``: methods <= complexity 10).
    """
    if not isinstance(report_value, str):
        return False
    return _normalize_id(report_value) == _normalize_id(str(entry_value or ""))


def _is_finite_number(value: object) -> TypeGuard[int | float]:
    """True only for a real, finite ``int`` or ``float``, excluding ``bool``.

    Two malformed-JSON traps a bare ``isinstance(x, int | float)`` misses:

    - ``bool`` is a subclass of ``int`` in Python, so
      ``isinstance(True, int)`` is ``True`` and ``True > 0.0`` is also
      ``True``. An unguarded check accepts a JSON ``true``/``false`` in a
      numeric field as if it were a real measurement.
    - ``json.loads`` accepts ``NaN``, ``Infinity``, and ``-Infinity`` as
      valid float literals by default. ``float("nan") < 0.05`` is always
      ``False`` (NaN compares false against everything), so an unguarded
      ``delta < MIN_RECALL_DELTA`` rejection lets a NaN delta through as
      though it qualified.

    Reject both: require a real ``int``/``float`` that is not ``bool`` and
    is finite (``math.isfinite`` is ``False`` for NaN and both infinities).
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return math.isfinite(value)


def _report_models_are_single_candidate(report: dict[str, object]) -> bool:
    """ADR-080 rule 2 requires "a single-candidate-versus-default sweep (so
    the CI is a plain 95 percent interval, not Bonferroni-widened)"
    (``.agents/architecture/ADR-080-model-pin-justification-policy.md:89-90``).

    ``eval-model-sweep.py --models`` can evaluate several candidates in one
    run, and the multi-candidate path reports its family-wise-adjusted
    interval in the SAME ``ci95`` field a single-candidate sweep uses
    (``scripts/eval/_model_sweep_core.py`` lines 395-420, the "family-wise
    CI" reason text). A numerically qualifying ``ci95`` alone cannot tell
    the two apart; the ``models`` list is the only field that reveals how
    many candidates were evaluated, so this function requires it to name
    exactly the winner and the default, no third candidate.

    Requires the two ids to be genuinely DISTINCT, not merely a 2-element
    list. Two sets can compare equal at size 1 each: a report claiming
    ``winner == default_model`` (nothing was actually a "winner" over
    anything), or a ``models`` list whose two entries are duplicates of
    the same id, both collapse ``{a, a}`` to ``{a}`` on both sides of the
    ``==`` and would otherwise pass. Neither is a real candidate-versus-
    default sweep, so require ``len(...) == 2`` on both sets before
    comparing them.
    """
    models = report.get("models")
    if not isinstance(models, list) or len(models) != 2:
        return False
    ids: set[str] = set()
    for candidate in models:
        if not isinstance(candidate, dict):
            return False
        model_id = candidate.get("model_id")
        if not isinstance(model_id, str):
            return False
        ids.add(_normalize_id(model_id))
    if len(ids) != 2:
        return False
    expected = {
        _normalize_id(str(report.get("winner", ""))),
        _normalize_id(str(report.get("default_model", ""))),
    }
    if len(expected) != 2:
        return False
    return ids == expected


def _report_measurements_qualify(report: dict[str, object]) -> bool:
    """ADR-080 rule 2's numeric thresholds on an already-parsed report.

    At least 8 shared fixtures, ``delta >= 0.05`` mean recall, and a
    positive paired-bootstrap CI lower bound
    (``.agents/architecture/ADR-080-model-pin-justification-policy.md:86-90``).
    Split out of ``_sweep_report_satisfies_rule2`` for the same
    complexity-ceiling reason as ``_report_model_id_matches``.
    """
    n_fixtures = report.get("n_shared_fixtures")
    if isinstance(n_fixtures, bool) or not isinstance(n_fixtures, int):
        return False
    if n_fixtures < MIN_SHARED_FIXTURES:
        return False
    delta = report.get("recall_delta")
    if not _is_finite_number(delta):
        return False
    if delta < MIN_RECALL_DELTA:
        return False
    ci95 = report.get("ci95")
    if not isinstance(ci95, list) or len(ci95) != 2:
        return False
    ci_low, ci_high = ci95
    if not _is_finite_number(ci_low) or not _is_finite_number(ci_high):
        return False
    # A real bootstrap interval is ordered low <= high; a malformed reversed
    # pair like [0.09, 0.01] would otherwise pass on ci_low alone.
    if ci_low > ci_high:
        return False
    return ci_low > 0.0


def sweep_report_satisfies_rule2(
    artifact_path: Path, entry: dict[str, object]
) -> bool:
    """Parse the sweep artifact and cross-check its content against ``entry``.

    ``(repo_root / artifact).is_file()`` in ``model_pin_manifest.py``'s
    ``_entry_evidence_valid`` proves only that some bytes exist at the
    path; a fixture that writes ``{}`` passes that check while carrying
    none of the evidence ADR-080 rule 2 requires. This function is the
    parse-and-check step that actually reads the sweep report: rule 2
    requires the report's own claims (winning model, fixtures_sha,
    default_model) to agree with the manifest entry citing it, not just be
    present, and requires the measured numbers (fixture count, delta, CI)
    to actually qualify (``_report_measurements_qualify``).

    Canonical report schema: ``scripts/eval/_model_sweep_core.py:build_report``
    (lines 460-511), specifically the ``schemaVersion``, ``agent``,
    ``decision``, ``winner``, ``fixtures_sha``, ``default_model``,
    ``models``, ``n_shared_fixtures``, ``recall_delta``, and ``ci95``
    fields that function writes. ``schemaVersion`` gates future shape
    changes per that function's own docstring; a report missing it, or
    reporting a different version, has not committed to the field set read
    below. ``agent`` ties the report to a specific source unit
    (``_agent_name_from_unit``); without that check a report for one agent
    could justify a manifest entry for a different one whenever winner,
    fixtures_sha, and default_model happen to coincide.
    """
    try:
        report = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(report, dict):
        return False
    if report.get("schemaVersion") != SWEEP_REPORT_SCHEMA_VERSION:
        return False
    if report.get("agent") != _agent_name_from_unit(entry.get("unit")):
        return False
    if report.get("decision") != "KEEP_PIN":
        return False
    if not _report_model_id_matches(report.get("winner"), entry.get("model")):
        return False
    if report.get("fixtures_sha") != entry.get("fixtures_sha"):
        return False
    if not _report_model_id_matches(
        report.get("default_model"), entry.get("default_model")
    ):
        return False
    if not _report_models_are_single_candidate(report):
        return False
    return _report_measurements_qualify(report)
