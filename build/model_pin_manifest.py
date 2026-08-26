#!/usr/bin/env python3
"""Resolve a manifest-justified versioned model pin for agent generation.

ADR-080 rule 5 says the generator must "emit no ``model:`` unless the source
unit carries a justified one." Rule 2 defines "justified" as a versioned pin
backed by a ``KEEP_PIN`` entry in the sidecar manifest,
``.agents/governance/model-pin-evidence.json``. Until this module, the
generator never read that manifest at all: ``convert_frontmatter_for_platform``
only ever emitted the ``haiku`` rolling-alias cost exception (ADR-080 rule 3)
and otherwise omitted ``model:`` outright, so a manifest entry had no path to
reach a generated agent. The 2026-08-12 ADR-080 Amendment (finding 4) names
this the "open gap": "cross-platform manifest-to-generator wiring... remains
an open gap." This module closes it.

Two responsibilities, kept separate because they answer different questions:

- ``load_pin_manifest`` / ``resolve_manifest_model``: is there a manifest
  entry, and is it fresh enough to trust? (ADR-080 rules 2 and 4.)
- ``format_model_id_for_platform``: given a canonical id, what does *this*
  platform call it? (The declared open gap itself.)

Canonical source and reuse decision (`.claude/rules/canonical-source-mirror.md`):
``load_pin_manifest`` and the freshness leg of ``resolve_manifest_model`` mirror
``scripts/validation/check_model_pins.py``'s ``load_manifest`` (lines 479-489)
and the ``KEEP_PIN``/freshness legs of ``_manifest_entry_valid`` (lines 358-391).
This module reimplements rather than imports that script: importing it inserts
two entries onto ``sys.path`` as a side effect and pulls in
``scripts/eval/_eval_common``'s pricing table, which resolving a model id for
generation has no use for. See the "Stricter/looser/different than canonical"
note on ``resolve_manifest_model`` for exactly which canonical checks this
module does and does not re-run.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

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


def load_pin_manifest(manifest_path: Path) -> dict[str, dict[str, object]]:
    """Load ADR-080 sidecar manifest pins keyed by unit path.

    Mirrors ``scripts/validation/check_model_pins.py:479-489``
    (``load_manifest``) verbatim in behavior: a missing file or a malformed
    ``pins`` shape returns an empty mapping rather than raising, so a broken
    or absent manifest degrades generation to "emit no manifest-justified
    pin" instead of failing the build. The required ``Model Pin Governance``
    CI check (``check_model_pins.py --mode enforce``) is what fails a PR that
    ships a malformed manifest; this function only needs to not crash on one.
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


def resolve_manifest_model(
    manifest: Mapping[str, dict[str, object]],
    source_unit: str,
    today: date | None = None,
) -> str | None:
    """Return the manifest-justified versioned model id for ``source_unit``.

    ``source_unit`` is the repo-relative path
    (``templates/agents/<name>.shared.md``), matching the ``unit`` field the
    ADR-080 manifest schema and ``check_model_pins.py``'s own
    ``_UNIT_GLOBS`` (line 86) both use for this unit kind. Returns ``None``
    when no entry exists, the entry does not carry ``decision: KEEP_PIN``, the
    unit does not match, the model field is blank, or the evidence has aged
    past ``MANIFEST_MAX_AGE_DAYS``.

    Stricter/looser than canonical: this reimplements only the
    ``decision``/``unit``/freshness legs of
    ``check_model_pins.py:_manifest_entry_valid`` (lines 358-391). It
    deliberately omits three checks that function also performs:
    ``fixtures_sha`` presence, the artifact path existing within the repo,
    and the entry's ``default_model`` matching the harness default. Those
    three audit the evidence file's OWN integrity (was a real sweep run, does
    its artifact exist, what did it compare against) rather than answer "is
    this id still safe to emit right now." They are enforced independently
    and exhaustively by the required ``Model Pin Governance`` CI check on
    every PR that touches the manifest, so an entry that fails them already
    fails CI before it reaches ``main``; re-running them here would be dead
    weight duplicating a gate that already blocks the bad state. What this
    function DOES check (decision, unit match, non-blank model, freshness)
    guards the one failure mode that check cannot: evidence that was valid
    when the sweep landed becoming stale between that PR merging and a later
    generation run reading the same manifest file.
    """
    entry = manifest.get(source_unit)
    if entry is None:
        return None
    if entry.get("decision") != "KEEP_PIN":
        return None
    if entry.get("unit") != source_unit:
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
    if (resolved_today - recorded_date).days > MANIFEST_MAX_AGE_DAYS:
        return None
    return model.strip()


def format_model_id_for_platform(
    model_id: str, platform_tiers: Mapping[str, object]
) -> str | None:
    """Format a canonical versioned model id in a platform's own spelling.

    This is the ADR-080 "open gap" itself: a manifest entry records one
    canonical id (the hyphenated ``claude-{tier}-{major}-{minor}`` form
    ``check_model_pins.py``'s ``_normalize_id`` treats as canonical), but each
    platform's ``model_tiers`` map spells its OWN default id differently, for
    example:

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
    such as ``claude-opus-4-20250514``), or when ``platform_tiers`` has no
    entry for the id's tier, or that entry's spelling matches neither known
    shape. ADR-080 rule 5 requires the generator to "emit no ``model:``
    unless the source unit carries a justified one"; a pin this function
    cannot confidently reformat is not one it should guess at.
    """
    match = _CANONICAL_MAJOR_MINOR_RE.match(model_id.strip())
    if match is None:
        return None
    tier, major, minor = match.groups()
    template = platform_tiers.get(tier)
    if not isinstance(template, str):
        return None
    if _DOT_FORM_RE.match(template):
        return f"claude-{tier}-{major}.{minor}"
    display_match = _DISPLAY_FORM_RE.match(template)
    if display_match:
        return f"Claude {display_match.group(1)} {major}.{minor} (copilot)"
    return None
