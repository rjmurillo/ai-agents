#!/usr/bin/env python3
"""Resolve a manifest-justified versioned model pin for agent generation.

ADR-080 rule 5 says the generator must "emit no ``model:`` unless the source
unit carries a justified one." Rule 2 defines "justified" as a versioned pin
backed by a ``KEEP_PIN`` entry in the sidecar manifest,
``.agents/governance/model-pin-evidence.json``. Until this module, the
generator never read that manifest at all: ``convert_frontmatter_for_platform``
only ever emitted the ``haiku`` rolling-alias cost exception (ADR-080 rule 3)
and otherwise omitted ``model:`` outright, so a manifest entry had no path to
reach a generated agent.

The 2026-08-12 ADR-080 Amendment (finding 4) does not use the phrase "manifest
wiring"; its finding is about generated-agent ``model_tier`` translation and
rule 3's cost exception, closing with: "Whether that override is acceptable
for generated agents, and how it interacts with rule 3's cost exception, is
undecided here and remains an open gap." What this module closes is the
mechanical half rule 5 actually requires: giving a manifest ``KEEP_PIN`` entry
a path to a generated agent, and resolving the cross-platform id-spelling
difference that path needs. It does not resolve the Amendment's separate,
still-open policy question about the ``haiku``-tier fallback itself; see
``convert_frontmatter_for_platform``'s model-resolution comment for how the
two mechanisms are ordered.

Two responsibilities, kept separate because they answer different questions:

- ``load_pin_manifest`` / ``resolve_manifest_model``: is there a manifest
  entry, and is it fully valid and fresh enough to trust? (ADR-080 rules 2
  and 4.)
- ``format_model_id_for_platform``: given a canonical id, what does *this*
  platform call it? (The cross-platform spelling gap.)

Canonical source and reuse decision (`.claude/rules/canonical-source-mirror.md`):
``load_pin_manifest`` mirrors ``scripts/validation/check_model_pins.py``'s
``load_manifest`` (lines 479-489); ``resolve_manifest_model`` mirrors
``_manifest_entry_valid`` (lines 358-391) and ``_normalize_id`` (lines
119-125). This module reimplements rather than imports that script:
importing it inserts two entries onto ``sys.path`` as a side effect and pulls
in ``scripts/eval/_eval_common``'s pricing table, which resolving a model id
for generation has no use for. See the "Stricter/looser/different than
canonical" notes on ``load_pin_manifest`` and ``resolve_manifest_model`` for
exactly where this module's behavior departs from the cited canonical
functions.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

# Mirrors scripts/validation/check_model_pins.py:62 (DEFAULT_MODEL) verbatim.
# The harness-inherited default a manifest entry's own default_model field
# must match; see resolve_manifest_model.
DEFAULT_MODEL = "claude-sonnet-4-6"

# Mirrors scripts/validation/check_model_pins.py:71
# (MANIFEST_MAX_AGE_DAYS = 180) verbatim. Kept as a separate constant, not an
# import, per the reuse decision above.
MANIFEST_MAX_AGE_DAYS = 180

# A canonical versioned Claude id in the major.minor shape ADR-080's open-gap
# finding names: ``claude-{tier}-{major}.{minor}`` or the hyphenated spelling
# ``claude-{tier}-{major}-{minor}`` (scripts/validation/check_model_pins.py's
# ``_normalize_id`` treats the two as equivalent by collapsing dots to
# hyphens). Deliberately narrower than
# ``check_model_pins._VERSIONED_RE`` (``^claude-(?:opus|sonnet|haiku)-[0-9]``),
# which also matches a date-stamped id like ``claude-opus-4-20250514``. This
# module fails closed on any shape outside major.minor rather than guess at a
# per-platform spelling for a shape it was not designed against. Major and
# minor are capped at two digits each: every observed Claude version number
# (4.5, 4.6, 4-20, ...) fits that, while a capped digit count is what keeps
# a date-stamped id (claude-opus-4-20250514) from matching as though
# "20250514" were a minor version -- an 8-digit run cannot satisfy \d{1,2}.
_CANONICAL_MAJOR_MINOR_RE = re.compile(
    r"^claude-(opus|sonnet|haiku)-(\d{1,2})[.-](\d{1,2})$"
)

# The two known target shapes a platform's own ``model_tiers`` map spells its
# tier defaults in today. See templates/platforms/copilot-cli.yaml:101-103
# (dot form) and templates/platforms/vscode.yaml:15-17 (display form, shared
# by visual-studio.yaml). Matching against these rather than hardcoding a
# per-platform-name template means a platform YAML's spelling stays the one
# source of truth for its own format.
_DOT_FORM_RE = re.compile(r"^claude-(opus|sonnet|haiku)-\d+\.\d+$")
_DISPLAY_FORM_RE = re.compile(
    r"^Claude (Opus|Sonnet|Haiku) \d+\.\d+ \(copilot\)$"
)


def _normalize_id(model_id: str) -> str:
    """Collapse dots to hyphens so dotted and hyphenated ids compare equal.

    Mirrors ``scripts/validation/check_model_pins.py:119-125``
    (``_normalize_id``) verbatim: ``copilot-cli.yaml`` spells ids with dots
    (``claude-opus-4.6``); the manifest and pricing table use hyphens
    (``claude-opus-4-6``).
    """
    return model_id.replace(".", "-")


def _artifact_within_repo(artifact: str, repo_root: Path) -> bool:
    """Reject a path-traversal artifact path (CWE-22).

    Mirrors ``scripts/validation/check_model_pins.py:348-355``
    (``_artifact_within_repo``) verbatim: resolve the artifact path against
    ``repo_root`` and confirm it stays a descendant. This is a path-safety
    check only, not an existence check; the canonical function performs
    neither more nor less.
    """
    try:
        resolved = (repo_root / artifact).resolve()
        resolved.relative_to(repo_root.resolve())
    except (ValueError, OSError):
        return False
    return True


def load_pin_manifest(manifest_path: Path) -> dict[str, dict[str, object]]:
    """Load ADR-080 sidecar manifest pins keyed by unit path.

    Mirrors ``scripts/validation/check_model_pins.py:479-489``
    (``load_manifest``) for the missing-file and shape-parsing behavior: a
    missing file, or a ``pins`` value that is not a list, or a list entry
    that is not a dict with a string ``unit``, is skipped or treated as
    absent rather than raising.

    Stricter/looser than canonical: the canonical ``load_manifest`` does
    NOT catch a JSON decode error or a file-read error; both propagate to
    its caller (``run_check`` / ``main``), which is a validation CLI whose
    job is to fail loudly on a broken manifest. This function additionally
    catches ``(OSError, ValueError)`` around the read and parse and returns
    an empty mapping instead of propagating. The caller here is
    ``build/generate_agents.py``, a build script that generates ~90 other
    files in the same run; failing the entire build over a malformed
    sidecar evidence file would be a worse failure mode than generating
    with no manifest-justified pins for this run. The required
    ``Model Pin Governance`` CI check (``check_model_pins.py --mode
    enforce``) is what actually fails a PR that ships a malformed manifest;
    this function's broader catch only prevents the generator from
    crashing on one, it does not substitute for that check.
    """
    if not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    pins = data.get("pins") if isinstance(data, dict) else None
    result: dict[str, dict[str, object]] = {}
    if isinstance(pins, list):
        for entry in pins:
            if isinstance(entry, dict) and isinstance(entry.get("unit"), str):
                result[str(entry["unit"])] = entry
    return result


def _entry_evidence_valid(
    entry: dict[str, object], source_unit: str, repo_root: Path, default_model: str
) -> bool:
    """Check the evidence-integrity legs: fixtures_sha, artifact, default_model.

    Split from ``resolve_manifest_model`` to keep that function's cyclomatic
    complexity low. Mirrors the corresponding legs of
    ``scripts/validation/check_model_pins.py:358-391``
    (``_manifest_entry_valid``), except it does not compare ``entry["model"]``
    against a scanned unit's own ``model:`` frontmatter value: this module's
    callers are ``model_tier``-carrying templates that (by ADR-080 rule 1's
    design) do not have a ``model:`` field for the manifest entry to be
    checked against. See ``resolve_manifest_model``'s divergence note.
    """
    if entry.get("decision") != "KEEP_PIN":
        return False
    if entry.get("unit") != source_unit:
        return False
    if not entry.get("fixtures_sha"):
        return False
    artifact = entry.get("artifact")
    if not isinstance(artifact, str) or not artifact:
        return False
    if not _artifact_within_repo(artifact, repo_root):
        return False
    return _normalize_id(str(entry.get("default_model", ""))) == _normalize_id(
        default_model
    )


def resolve_manifest_model(
    manifest: Mapping[str, dict[str, object]],
    source_unit: str,
    repo_root: Path,
    today: date | None = None,
    default_model: str = DEFAULT_MODEL,
) -> str | None:
    """Return the manifest-justified versioned model id for ``source_unit``.

    ``source_unit`` is the repo-relative path
    (``templates/agents/<name>.shared.md``), matching the ``unit`` field the
    ADR-080 manifest schema and ``check_model_pins.py``'s own
    ``_UNIT_GLOBS`` (line 86) both use for this unit kind. Returns ``None``
    unless the entry carries ``decision: KEEP_PIN``, a matching unit, a
    non-blank model, a present ``fixtures_sha``, an ``artifact`` path that
    stays within the repository, a ``default_model`` matching the current
    harness default, and a ``date`` within ``MANIFEST_MAX_AGE_DAYS`` of
    ``today`` (never in the future; see the divergence note below).

    Canonical source: ``scripts/validation/check_model_pins.py:358-391``
    (``_manifest_entry_valid``).

    Stricter/looser/different than canonical:

    - **No unit-model cross-check.** Canonical additionally requires
      ``_normalize_id(entry["model"]) == _normalize_id(unit.model)``,
      comparing the manifest entry against a *scanned* unit's own
      ``model:`` frontmatter value. This module's callers are
      ``model_tier``-carrying templates (for example ``model_tier:
      haiku``), which by ADR-080 rule 1's design have no ``model:``
      frontmatter field for the manifest to agree with. There is nothing
      to cross-check against; the manifest entry's ``model`` field is
      itself the value being resolved.
    - **Full evidence-integrity validation, where canonical structurally
      cannot reach these units.** ``check_model_pins.scan_units()``
      (line 328) only collects a unit when ``unit.model or
      unit.nested_pins`` is truthy, and a ``model_tier``-only template has
      neither: it is invisible to the scanner, so
      ``_manifest_entry_valid`` never runs for it and the required
      ``Model Pin Governance`` CI check provides no independent
      validation of ``fixtures_sha``, ``artifact``, or ``default_model``
      for this class of manifest entry. An earlier version of this
      function omitted those three checks on the assumption that CI
      already covered them; it does not, for exactly this unit shape.
      This function now performs the full check itself
      (``_entry_evidence_valid``) rather than trust a governance check
      that cannot see the entry.
    - **Rejects a future-dated ``date`` (a negative age).** Canonical's
      ``age = (today - recorded_date).days; if age >
      MANIFEST_MAX_AGE_DAYS`` accepts any negative age (a typo'd future
      date), which both extends the entry's effective freshness window
      past 180 days and accepts a pin whose sweep supposedly has not
      happened yet. This function additionally rejects ``age < 0``.
      Canonical has the same gap; fixing it there is a separate change
      to a shipped, required CI script and is out of scope here.
    """
    entry = manifest.get(source_unit)
    if entry is None:
        return None
    if not _entry_evidence_valid(entry, source_unit, repo_root, default_model):
        return None
    model = entry.get("model")
    if not isinstance(model, str) or not model.strip():
        return None
    recorded = entry.get("date")
    if not isinstance(recorded, str):
        return None
    try:
        recorded_date = datetime.strptime(recorded, "%Y-%m-%d").date()
    except ValueError:
        return None
    resolved_today = today or datetime.now(timezone.utc).date()
    age = (resolved_today - recorded_date).days
    if age < 0 or age > MANIFEST_MAX_AGE_DAYS:
        return None
    return model.strip()


def format_model_id_for_platform(
    model_id: str, platform_tiers: Mapping[str, object]
) -> str | None:
    """Format a canonical versioned model id in a platform's own spelling.

    This is the cross-platform spelling gap rule 5's generator change
    creates: a manifest entry records one canonical id (the hyphenated
    ``claude-{tier}-{major}-{minor}`` form ``check_model_pins.py``'s
    ``_normalize_id`` treats as canonical), but each platform's
    ``model_tiers`` map spells its OWN default id differently, for example:

        templates/platforms/copilot-cli.yaml:101-103 (dot form):
            opus: "claude-opus-4.6"
        templates/platforms/vscode.yaml:15-17 (display form, shared by
        visual-studio.yaml):
            opus: "Claude Opus 4.6 (copilot)"

    Rather than hardcode both target formats as Python string templates (a
    second source of truth that drifts the moment either YAML file's own
    spelling changes), this derives the platform's format from
    ``platform_tiers[tier]`` -- the SAME string ``convert_frontmatter_for_platform``
    already reads to resolve the haiku-tier default -- by matching it against
    the two known shapes above and substituting the manifest id's own
    ``(major, minor)`` digits into whichever shape matched.

    Fails closed (returns ``None``, meaning: emit no pin) when ``model_id``
    is not the documented major.minor shape (for example a date-stamped id
    such as ``claude-opus-4-20250514``), when ``platform_tiers`` has no
    entry for the id's tier, when that entry's spelling matches neither
    known shape, or when the tier embedded in the template string does not
    match the tier being formatted (see below). ADR-080 rule 5 requires the
    generator to "emit no ``model:`` unless the source unit carries a
    justified one"; a pin this function cannot confidently reformat is not
    one it should guess at.

    The tier cross-check matters because ``platform_tiers[tier]`` is looked
    up by key, but the *value*'s own embedded tier name (``Sonnet`` in
    ``"Claude Sonnet 4.6 (copilot)"``) is what the display-form branch
    copies into its output. A mismatched config entry (``opus:`` mapped to
    a Sonnet-shaped string, a copy-paste error in the platform YAML) would
    otherwise silently emit an Opus manifest pin labeled Sonnet instead of
    failing closed. Both branches now verify the template's own tier
    matches the tier being formatted before using it, rather than trusting
    the dict key alone.
    """
    match = _CANONICAL_MAJOR_MINOR_RE.match(model_id.strip())
    if match is None:
        return None
    tier, major, minor = match.groups()
    template = platform_tiers.get(tier)
    if not isinstance(template, str):
        return None
    dot_match = _DOT_FORM_RE.match(template)
    if dot_match and dot_match.group(1) == tier:
        return f"claude-{tier}-{major}.{minor}"
    display_match = _DISPLAY_FORM_RE.match(template)
    if display_match and display_match.group(1).lower() == tier:
        return f"Claude {display_match.group(1)} {major}.{minor} (copilot)"
    return None
