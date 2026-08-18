#!/usr/bin/env python3
"""Governance check for model: pins (ADR-080, issue #2840 criterion 3).

Enforces the ADR-080 policy as a draining ratchet:

- Skills and commands may not carry a versioned model id. Their only allowed
  states are no ``model:`` line, or a bare rolling alias (sonnet/opus/haiku)
  that carries a ``model-rationale:`` field.
- Agents may carry a versioned pin only when a valid entry in the sidecar
  manifest ``.agents/governance/model-pin-evidence.json`` justifies it
  (decision KEEP_PIN, unit/model match, fixtures_sha present, within max age,
  recorded against the current default model).
- A bare alias with a ``model-rationale:`` cost exception is valid only when the
  alias resolves, via the platform ``model_tiers`` map, to a versioned id priced
  strictly below the harness default in the pricing table.

Current pins predate the policy, so the check ships against a frozen baseline
(unit path -> model id). It fails only on a new pin, a baselined pin whose value
changed without evidence, or a baseline whose entry count grew. The baseline
carries a burn-down obligation: its count must shrink over time until empty, at
which point the check can flip to enforce.

Exit codes (AGENTS.md): 0 ok, 1 policy violation (enforce mode), 2 config error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parent.parent

# Reuse the single frontmatter parser rather than hand-rolling a second one.
# ``skill_frontmatter`` imports ``scripts.validation.models`` (absolute), so the
# repo root must be importable even when this runs as a plain script, not only
# via ``python -m`` or from pre-commit's repo-root cwd (Issue #3073).
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_SCRIPT_DIR))
from portability_baseline import (  # noqa: E402  (path set above)
    refuse_oversized_baseline,
    refuse_symlinked_baseline,
    refuse_undiffable_baseline,
)
from skill_frontmatter import parse_frontmatter  # noqa: E402  (path set above)

# Single source of truth for pricing lives with the eval harness.
sys.path.insert(0, str(_REPO_ROOT / "scripts" / "eval"))
from _eval_common import (  # noqa: E402  (path set above)
    MODEL_PRICING_RATES_USD_PER_1K_TOKENS,
)

# The harness-inherited default. Rolling-alias cost rationales must price below
# this model, and manifest evidence is only valid while it was measured against
# this default. Kept as a constant with a pointer to the eval default.
DEFAULT_MODEL = "claude-sonnet-4-6"

ROLLING_ALIASES = ("sonnet", "opus", "haiku")

# Keys that carry a model identifier in skill/agent frontmatter.
# Any key added here is subject to ADR-080 enforcement.
MODEL_BEARING_KEYS: frozenset[str] = frozenset({"model", "subagent_model"})

# Manifest evidence older than this many days is stale (harness/pricing drift).
MANIFEST_MAX_AGE_DAYS = 180

# A versioned Claude id: tier plus at least one numeric version component.
# Matches claude-opus-4-6, claude-sonnet-4-20250514, claude-haiku-4.5, etc.
_VERSIONED_RE = re.compile(r"^claude-(?:opus|sonnet|haiku)-[0-9]")

_BASELINE_PATH = _SCRIPT_DIR / "model_pin_baseline.json"
_MANIFEST_PATH = _REPO_ROOT / ".agents" / "governance" / "model-pin-evidence.json"
_TIERS_PATH = _REPO_ROOT / "templates" / "platforms" / "copilot-cli.yaml"

# Source unit trees and self-host copies scanned for model-pin policy.
_UNIT_GLOBS: tuple[tuple[str, str], ...] = (
    ("skill", ".claude/skills/*/SKILL.md"),
    ("agent", ".claude/agents/*.md"),
    ("agent", ".github/agents/*.md"),
    ("agent", "templates/agents/*.shared.md"),
    ("command", ".claude/commands/**/*.md"),
)

_DOC_EXAMPLE_NAMES = frozenset({"AGENTS.md", "CLAUDE.md"})


@dataclass(frozen=True)
class Unit:
    """A scanned unit and the model state read from its frontmatter."""

    path: str
    kind: str
    model: str | None
    rationale: str | None
    nested_pins: tuple[tuple[str, str], ...] = ()


@dataclass
class CheckReport:
    """Hard violations (fail enforce) versus grandfathered backlog (warn only)."""

    violations: list[str] = field(default_factory=list)
    backlog: list[str] = field(default_factory=list)
    scanned: int = 0

    def fail(self, path: str, message: str) -> None:
        self.violations.append(f"{path}: {message}")

    def defer(self, path: str, message: str) -> None:
        self.backlog.append(f"{path}: {message}")


def _normalize_id(model_id: str) -> str:
    """Normalize a version id so dotted and hyphenated spellings compare equal.

    copilot-cli.yaml spells ids with dots (claude-opus-4.6); the pricing table
    uses hyphens (claude-opus-4-6). Collapse dots to hyphens for lookup.
    """
    return model_id.replace(".", "-")


def _is_versioned(model_id: str) -> bool:
    return bool(_VERSIONED_RE.match(_normalize_id(model_id)))


def load_tier_map(tiers_path: Path = _TIERS_PATH) -> dict[str, str]:
    """Read the alias -> versioned-id map from the platform config.

    Falls back to an empty map when the file or block is absent; callers treat a
    missing alias resolution as an invalid cost rationale.
    """
    try:
        import yaml

        data = yaml.safe_load(tiers_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    tiers = _find_model_tiers(data)
    if tiers is None:
        return {}
    return {str(k): str(v) for k, v in tiers.items()}


def _find_model_tiers(node: object) -> dict[object, object] | None:
    """Locate the ``model_tiers`` mapping wherever it nests in the config."""
    if isinstance(node, dict):
        tiers = node.get("model_tiers")
        if isinstance(tiers, dict):
            return tiers
        for value in node.values():
            found = _find_model_tiers(value)
            if found is not None:
                return found
    return None


def _input_price(model_id: str) -> float | None:
    rate = MODEL_PRICING_RATES_USD_PER_1K_TOKENS.get(_normalize_id(model_id))
    if not isinstance(rate, dict):
        return None
    price = rate.get("input")
    return float(price) if isinstance(price, (int, float)) else None


def alias_prices_below_default(
    alias: str, tier_map: dict[str, str], default_model: str = DEFAULT_MODEL
) -> bool:
    """True when the rolling alias resolves to an id priced below the default."""
    resolved = tier_map.get(alias)
    if resolved is None:
        return False
    alias_price = _input_price(resolved)
    default_price = _input_price(default_model)
    if alias_price is None or default_price is None:
        return False
    return alias_price < default_price


def _record_bearing_key_pins(
    path: str, value: object, out: list[tuple[str, str]]
) -> bool:
    """Record pins for a model-bearing key's value; report whether it was handled.

    Preserve model-bearing context through lists and mappings. A generic YAML
    walk cannot infer that ``id`` in ``subagent_model: {id: ...}`` is a model
    value after it descends past ``subagent_model``; every non-blank string
    leaf below that key must therefore be collected here.

    The traversal has its own visited set because a mapping may first appear
    through a non-model alias and later through a model-bearing key. Reusing
    the generic walk's visited set would make detection depend on YAML key
    order and restore the bypass for that alias shape.
    """
    if not isinstance(value, (str, dict, list)):
        return False

    bearing_seen: set[int] = set()

    def collect(node: object, node_path: str) -> None:
        if isinstance(node, str):
            if node.strip():
                out.append((node_path, node.strip()))
            return
        if not isinstance(node, (dict, list)) or id(node) in bearing_seen:
            return
        bearing_seen.add(id(node))
        if isinstance(node, dict):
            for key, item in node.items():
                collect(item, f"{node_path}.{key}")
        else:
            for index, item in enumerate(node):
                collect(item, f"{node_path}[{index}]")

    collect(value, path)
    return True


def _collect_nested_pins(
    node: object, prefix: str, seen: set[int], out: list[tuple[str, str]]
) -> None:
    """Append every ``model`` value at or below ``node`` as (dotted path, value).

    Walks the typed YAML rather than the flat frontmatter view, which drops
    indented keys entirely (issue #2840). Collecting every occurrence rather
    than the first matters: a unit can carry a compliant top-level alias and a
    versioned id under ``metadata`` at the same time, and reporting only one of
    them lets the other ship.

    ``seen`` holds the id of every container already walked, so each container
    is visited once no matter how many aliases reach it. That bounds the walk
    at O(nodes): an earlier recursion-path guard stopped cycles but still let a
    32-line alias DAG expand exponentially and hang the gate. Visiting once is
    also the honest report, because two alias paths to one node are one anchor
    in the source, so one line to delete. Two mappings that merely look alike
    are distinct objects and are still reported separately.
    """
    if isinstance(node, (dict, list)):
        if id(node) in seen:
            return
        seen.add(id(node))
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in MODEL_BEARING_KEYS and _record_bearing_key_pins(path, value, out):
                continue
            _collect_nested_pins(value, path, seen, out)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _collect_nested_pins(item, f"{prefix}[{index}]", seen, out)


def _prefer_typed(typed: object, flat: object) -> object:
    """Return the typed-view value when it is a non-blank string, else flat.

    Both ``model`` and ``model-rationale`` are read this way. The typed view
    normalises alternate YAML key spellings (quoted keys, explicit key
    notation) that the flat view misses, so preferring it stops a valid
    rationale from reading as missing. The flat fallback keeps files whose
    YAML failed to parse scannable.
    """
    if isinstance(typed, str) and typed.strip():
        return typed
    return flat


def _classify_and_read(path: Path, kind: str, repo_root: Path) -> Unit | None:
    """Read a unit's model state, or None when it has no frontmatter."""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    parsed = parse_frontmatter(content)
    fm = parsed.frontmatter
    # The typed view is authoritative: it is what a harness reading YAML sees.
    # The flat view is a line scan that misses every alternate spelling of the
    # same key ('model':, ? model, !!str model), each of which otherwise hides
    # a pin from the gate while still shipping it. The flat view is the
    # fallback whenever the typed view has no usable string for the key, which
    # covers a file whose YAML failed to parse as well as one whose key holds a
    # mapping or a blank; see _prefer_typed for the exact rule.
    model = _prefer_typed(parsed.typed.get("model"), fm.get("model"))
    rationale = _prefer_typed(parsed.typed.get("model-rationale"), fm.get("model-rationale"))
    try:
        rel = path.relative_to(repo_root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return Unit(
        path=rel,
        kind=kind,
        model=model.strip() if isinstance(model, str) and model.strip() else None,
        # Blank normalises to None for the same reason model does: a whitespace
        # rationale is an absent rationale, and leaving "" in place would give
        # Unit.rationale a third state that means nothing to any reader.
        rationale=rationale.strip() if isinstance(rationale, str) and rationale.strip() else None,
        nested_pins=_nested_pins(parsed.typed),
    )


def _nested_pins(typed: dict[object, object]) -> tuple[tuple[str, str], ...]:
    """Every model pin below the top level, sorted by its dotted path.

    A pin written as ``metadata.model`` still ships to customers in the
    generated mirrors and still rots when the id retires, so it carries the
    same drift and retirement cost ADR-080 exists to remove.
    """
    out: list[tuple[str, str]] = []
    seen: set[int] = set()
    for key, value in typed.items():
        # A scalar top-level model is the compliant shape and is judged by the
        # alias rules instead. A structured one is not, so walk into it.
        # NOTE: only 'model' has alias-rule coverage; other MODEL_BEARING_KEYS
        # (e.g. subagent_model), and any non-scalar 'model' (e.g. a list),
        # are collected directly as pins via the shared helper below.
        if key == "model" and isinstance(value, str):
            continue
        if key in MODEL_BEARING_KEYS and _record_bearing_key_pins(str(key), value, out):
            continue
        _collect_nested_pins(value, str(key), seen, out)
    return tuple(sorted(out))


def scan_units(repo_root: Path = _REPO_ROOT) -> list[Unit]:
    """Collect every source unit that carries a model: pin."""
    units: list[Unit] = []
    seen: set[str] = set()
    for kind, glob in _UNIT_GLOBS:
        for path in sorted(repo_root.glob(glob)):
            if path.name in _DOC_EXAMPLE_NAMES:
                continue
            if ".claude/worktrees/" in path.as_posix():
                continue
            key = path.as_posix()
            if key in seen:
                continue
            seen.add(key)
            unit = _classify_and_read(path, kind, repo_root)
            if unit is not None and (unit.model or unit.nested_pins):
                units.append(unit)
    return units


def _artifact_within_repo(artifact: str, repo_root: Path) -> bool:
    """Reject path-traversal artifact paths (CWE-22)."""
    try:
        resolved = (repo_root / artifact).resolve()
        resolved.relative_to(repo_root.resolve())
    except (ValueError, OSError):
        return False
    return True


def _manifest_entry_valid(
    entry: dict[str, object],
    unit: Unit,
    repo_root: Path,
    today: date,
    default_model: str,
) -> str | None:
    """Return a failure reason for a manifest entry, or None when it is valid."""
    if entry.get("decision") != "KEEP_PIN":
        return "manifest entry decision is not KEEP_PIN"
    if entry.get("unit") != unit.path:
        return "manifest entry unit does not match"
    if _normalize_id(str(entry.get("model", ""))) != _normalize_id(unit.model or ""):
        return "manifest entry model does not match the pin"
    if not entry.get("fixtures_sha"):
        return "manifest entry missing fixtures_sha"
    artifact = entry.get("artifact")
    if not isinstance(artifact, str) or not artifact:
        return "manifest entry missing artifact path"
    if not _artifact_within_repo(artifact, repo_root):
        return "manifest artifact path escapes the repository"
    if _normalize_id(str(entry.get("default_model", ""))) != _normalize_id(default_model):
        return "manifest evidence recorded against a different default model"
    recorded = entry.get("date")
    if not isinstance(recorded, str):
        return "manifest entry missing date"
    try:
        recorded_date = datetime.strptime(recorded, "%Y-%m-%d").date()
    except ValueError:
        return "manifest entry date is not YYYY-MM-DD"
    age = (today - recorded_date).days
    if age > MANIFEST_MAX_AGE_DAYS:
        return f"manifest evidence is stale ({age} days > {MANIFEST_MAX_AGE_DAYS})"
    return None


_MAX_DISPLAY_CHARS = 80


def _display(value: str) -> str:
    """Render a file-controlled value as one bounded, escaped token.

    ``repr`` escapes newlines and control characters, so a pin value cannot
    forge an extra status line in the gate's output (CWE-117), and the cap
    stops a padded value from burying the rest of the report.

    The cap is applied to the rendered form, not the raw value. Escaping
    expands: eighty newlines render as a hundred and sixty characters, so
    capping first measures a string nobody ever sees and lets the printed
    token run to twice the stated bound.
    """
    rendered = repr(value)
    if len(rendered) > _MAX_DISPLAY_CHARS:
        return rendered[:_MAX_DISPLAY_CHARS] + "..."
    return rendered


def _unit_rule_failure(
    unit: Unit,
    manifest: dict[str, dict[str, object]],
    tier_map: dict[str, str],
    repo_root: Path,
    today: date,
    default_model: str,
) -> str | None:
    """Return why a unit violates ADR-080 rules 1-3, or None when it complies."""
    model = unit.model or ""
    if unit.nested_pins:
        listed = ", ".join(
            f"{_display(value)} under {_display(key)}" for key, value in unit.nested_pins
        )
        return (
            f"unsupported model-bearing key value(s): {listed}; no harness "
            f"reads them, so they are drift with no effect (ADR-080)"
        )
    if model in ROLLING_ALIASES:
        if not unit.rationale:
            return f"bare alias '{model}' lacks a model-rationale field"
        if not alias_prices_below_default(model, tier_map, default_model):
            return (
                f"cost rationale on '{model}' but it does not price below the "
                f"default '{default_model}'"
            )
        return None

    if not _is_versioned(model):
        return f"model '{model}' is neither a rolling alias nor a versioned id"

    if unit.kind in ("skill", "command"):
        return (
            f"{unit.kind} carries versioned id '{model}'; skills and commands "
            f"may not pin a version (ADR-080 rule 1)"
        )

    entry = manifest.get(unit.path)
    if entry is None:
        return f"versioned agent pin '{model}' has no manifest evidence entry"
    return _manifest_entry_valid(entry, unit, repo_root, today, default_model)


def load_baseline(baseline_path: Path = _BASELINE_PATH) -> tuple[dict[str, str], int]:
    """Load baseline pins and the frozen count.

    Returns (pins_dict, frozen_count). The frozen count is the maximum number
    of pins allowed in the baseline; exceeding it is a hard violation (draining
    ratchet). When the baseline file doesn't contain an explicit frozen_count,
    the count of pins in the file is used for backwards compatibility.
    """
    if not baseline_path.is_file():
        return {}, 0
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}, 0
    pins_data = data.get("pins", data)
    pins = {str(k): str(v) for k, v in pins_data.items()} if isinstance(pins_data, dict) else {}
    frozen_count = data.get("frozen_count")
    if isinstance(frozen_count, int):
        return pins, frozen_count
    return pins, len(pins)


def load_manifest(manifest_path: Path = _MANIFEST_PATH) -> dict[str, dict[str, object]]:
    if not manifest_path.is_file():
        return {}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    pins = data.get("pins") if isinstance(data, dict) else None
    result: dict[str, dict[str, object]] = {}
    if isinstance(pins, list):
        for entry in pins:
            if isinstance(entry, dict) and isinstance(entry.get("unit"), str):
                result[str(entry["unit"])] = entry
    return result


def run_check(
    repo_root: Path = _REPO_ROOT,
    baseline_path: Path = _BASELINE_PATH,
    manifest_path: Path = _MANIFEST_PATH,
    tiers_path: Path = _TIERS_PATH,
    default_model: str = DEFAULT_MODEL,
    today: date | None = None,
) -> CheckReport:
    """Scan the tree and evaluate ADR-080. Grandfather baselined debt as backlog.

    A rule-compliant pin always passes. A non-compliant pin is a hard violation
    when it is new (absent from the baseline) or changed to a still-non-compliant
    value; it is grandfathered backlog only when the baseline already records it
    unchanged. This is the draining ratchet: existing debt is reported, never
    fails CI, and new debt is blocked so the baseline can only shrink.
    """
    resolved_today = today or datetime.now(timezone.utc).date()
    units = scan_units(repo_root)
    manifest = load_manifest(manifest_path)
    baseline, frozen_count = load_baseline(baseline_path)
    tier_map = load_tier_map(tiers_path)

    report = CheckReport(scanned=len(units))

    if len(baseline) > frozen_count:
        report.fail(
            str(baseline_path),
            f"[baseline growth] baseline has {len(baseline)} pins but frozen count "
            f"is {frozen_count}; the draining ratchet allows only shrinking",
        )

    for unit in units:
        failure = _unit_rule_failure(
            unit, manifest, tier_map, repo_root, resolved_today, default_model
        )
        if failure is None:
            continue
        model = unit.model or ""
        if unit.nested_pins:
            report.fail(unit.path, f"[unsupported model-bearing value] {failure}")
        elif unit.path not in baseline:
            report.fail(unit.path, f"[new pin] {failure}")
        elif _normalize_id(baseline[unit.path]) != _normalize_id(model):
            report.fail(
                unit.path,
                f"[changed pin] was '{baseline[unit.path]}', now '{model}' without "
                f"evidence: {failure}",
            )
        else:
            report.defer(unit.path, failure)
    return report


def write_baseline(units: list[Unit], baseline_path: Path = _BASELINE_PATH) -> int:
    """Freeze the current pins as the baseline. Returns the entry count.

    Preserves the existing frozen_count if present to prevent baseline growth.
    On first write (no existing baseline), sets frozen_count to current count.
    """
    _, existing_frozen_count = load_baseline(baseline_path)

    # A nested-only unit has no top-level model to freeze, and a nested pin is a
    # hard violation forever, so it must never enter the baseline as an empty
    # string that a later comparison would read as a matching pin.
    pins = {u.path: u.model for u in sorted(units, key=lambda u: u.path) if u.model}

    frozen_count = existing_frozen_count if existing_frozen_count > 0 else len(pins)

    payload = {
        "schema_version": "1",
        "description": (
            "Frozen ADR-080 model-pin baseline. Draining ratchet: this count "
            "must never grow and should shrink each release until empty."
        ),
        "frozen_count": frozen_count,
        "pins": pins,
    }
    baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return len(pins)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate model: pins against ADR-080.")
    parser.add_argument(
        "--mode",
        choices=("warn", "enforce"),
        default="warn",
        help="warn reports and exits 0; enforce exits nonzero on any violation.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the frozen baseline from the current tree, then exit.",
    )
    parser.add_argument("--baseline", type=Path, default=_BASELINE_PATH)
    parser.add_argument("--manifest", type=Path, default=_MANIFEST_PATH)
    return parser


def _vet_baseline(repo_root: Path, baseline: Path) -> bool:
    """Return True if baseline fails any integrity guard (caller should return 2)."""
    return bool(
        refuse_symlinked_baseline(repo_root, baseline)
        or refuse_undiffable_baseline(repo_root, baseline)
        or refuse_oversized_baseline(baseline)
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Refuse a baseline whose diff attribute is unset (issue #4249).
    if _vet_baseline(_REPO_ROOT, args.baseline):
        return 2

    if args.update_baseline:
        count = write_baseline(scan_units(), args.baseline)
        print(f"[model-pins] baseline written: {count} pins -> {args.baseline}")
        return 0

    try:
        report = run_check(baseline_path=args.baseline, manifest_path=args.manifest)
    except (OSError, ValueError) as exc:
        print(f"[model-pins] config error: {exc}", file=sys.stderr)
        return 2

    print(f"[model-pins] scanned {report.scanned} pinned units")
    if report.backlog:
        print(
            f"[model-pins] grandfathered backlog: {len(report.backlog)} pin(s) "
            f"awaiting migration (ADR-080 draining ratchet)"
        )
        for item in report.backlog:
            print(f"[model-pins]   backlog: {item}")

    if not report.violations:
        print("[model-pins] OK: no new or changed pin violations")
        return 0

    for violation in report.violations:
        print(f"[model-pins] VIOLATION: {violation}")
    print(f"[model-pins] {len(report.violations)} hard violation(s)")

    if args.mode == "enforce":
        return 1
    print("[model-pins] warn mode: reporting only, exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
