"""Pure model and aggregation for the tiered model-panel sweep (issue #3042).

The eval harness (`eval-agent-vs-baseline.py`) validates a unit (agent/skill)
against ONE model. #3042 wants each unit swept across a tiered panel: two
frontier tiers as the pass/fail reference band and lower tiers as degradation
observation points, reporting effect size per tier per unit so a unit that
degrades sharply below frontier is visible instead of assumed.

This module is pure: the panel config, the per-tier effect-size matrix, the
degradation classification, and the report shapes. All eval execution (running
the harness through a provider) lives in `eval-model-panel.py` behind a single
runner seam, so this logic is unit-testable with no API spend.

Effect size per (unit, tier) is the harness's `recall_delta` (variant recall
minus baseline recall): how much the unit's prompt helps at that tier. The
reference band is the mean recall_delta over the frontier tiers; a probe tier
"degrades" when its recall_delta falls more than `drop_threshold` below that
band. The two frontier models (roles == "reference") set the band; the lower
tiers (roles == "probe") are observed, never gating.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

# Roles a panel tier can play. A reference tier defines the pass/fail band; a
# probe tier is observed for degradation and never gates.
ROLE_REFERENCE = "reference"
ROLE_PROBE = "probe"
_ROLES = (ROLE_REFERENCE, ROLE_PROBE)

# Default recall_delta drop (below the reference band) that flags a probe tier
# as degraded for a unit. Overridable per run.
DEFAULT_DROP_THRESHOLD = 0.15


class PanelConfigError(ValueError):
    """A panel config is malformed or names an unknown provider."""


@dataclass(frozen=True)
class PanelTier:
    """One row of the model panel: a labelled (provider, model) at a role.

    The GPT-5.6 tier model ids (Sol/Terra) are deployment-specific, so the panel
    is data, not hardcoded: supply it via `--panel-config` (see `default_panel`
    for the documented shape). `label` is the human tier name (opus/sol/...).
    """

    label: str
    role: str
    provider: str
    model: str

    @property
    def is_reference(self) -> bool:
        return self.role == ROLE_REFERENCE


@dataclass(frozen=True)
class Panel:
    """The ordered tier list plus the degradation threshold."""

    tiers: tuple[PanelTier, ...]
    drop_threshold: float = DEFAULT_DROP_THRESHOLD

    @property
    def reference_tiers(self) -> tuple[PanelTier, ...]:
        return tuple(t for t in self.tiers if t.is_reference)

    @property
    def probe_tiers(self) -> tuple[PanelTier, ...]:
        return tuple(t for t in self.tiers if not t.is_reference)


def default_panel() -> Panel:
    """Generic fallback panel for documentation and testing. NOT confirmed for production.

    Two frontier reference tiers (Opus, Sol) plus two degradation probes
    (Sonnet, Terra). The Anthropic tier ids are current at the time of writing.
    The GPT-5.6 tier ids (Sol, Terra) are unconfirmed placeholders: the string
    "openai/gpt-5.6" and "openai/gpt-5.6-mini" have not been verified against
    any live deployment and may produce HTTP 404 errors.

    For a confirmed panel use --panel-config with a JSON file. See issue #3905
    for the task of replacing these placeholders with verified ids.
    """
    return Panel(
        tiers=(
            PanelTier("opus", ROLE_REFERENCE, "anthropic", "claude-opus-4-8"),
            PanelTier("sol", ROLE_REFERENCE, "openai", "openai/gpt-5.6"),
            PanelTier("sonnet", ROLE_PROBE, "anthropic", "claude-sonnet-4-6"),
            PanelTier("terra", ROLE_PROBE, "openai", "openai/gpt-5.6-mini"),
        ),
    )


def parse_panel(
    payload: dict[str, Any],
    *,
    known_providers: set[str] | None = None,
) -> Panel:
    """Build a Panel from a config mapping. Raises PanelConfigError on any defect.

    Shape: ``{"drop_threshold"?: float, "tiers": [{"label","role","provider",
    "model"}, ...]}``. At least one reference tier is required (an empty
    reference band cannot define pass/fail). ``known_providers``, when given,
    rejects a tier naming a provider the transport cannot resolve.
    """
    raw_tiers = payload.get("tiers")
    if not isinstance(raw_tiers, list) or not raw_tiers:
        raise PanelConfigError("panel config must have a non-empty 'tiers' list")
    tiers: list[PanelTier] = []
    for index, row in enumerate(raw_tiers):
        if not isinstance(row, dict):
            raise PanelConfigError(f"tier {index} is not an object")
        missing = [k for k in ("label", "role", "provider", "model") if not row.get(k)]
        if missing:
            raise PanelConfigError(f"tier {index} missing field(s): {', '.join(missing)}")
        role = str(row["role"])
        if role not in _ROLES:
            raise PanelConfigError(
                f"tier {row['label']!r} has role {role!r}; expected one of {_ROLES}"
            )
        provider = str(row["provider"])
        if known_providers is not None and provider not in known_providers:
            raise PanelConfigError(
                f"tier {row['label']!r} names unknown provider {provider!r}; "
                f"known: {sorted(known_providers)}"
            )
        tiers.append(PanelTier(str(row["label"]), role, provider, str(row["model"])))
    if not any(t.is_reference for t in tiers):
        raise PanelConfigError("panel needs at least one 'reference' tier")
    threshold = payload.get("drop_threshold", DEFAULT_DROP_THRESHOLD)
    try:
        threshold = float(threshold)
    except (TypeError, ValueError) as exc:
        raise PanelConfigError("drop_threshold must be a number") from exc
    if not math.isfinite(threshold) or threshold < 0:
        raise PanelConfigError("drop_threshold must be finite and non-negative")
    return Panel(tiers=tuple(tiers), drop_threshold=threshold)


@dataclass
class CellResult:
    """One (unit, tier) sweep outcome: the effect size or an error."""

    unit: str
    tier: str
    recall_delta: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.recall_delta is not None


@dataclass
class UnitVerdict:
    """Per-unit degradation summary across the panel."""

    unit: str
    reference_delta: float | None
    probe_deltas: dict[str, float | None]
    degraded_tiers: list[str] = field(default_factory=list)
    robust: bool = False
    incomplete: bool = False


def cell_from_report(unit: str, tier: str, report: dict[str, Any]) -> CellResult:
    """Extract the effect size from a harness report.json mapping."""
    error_count = report.get("error_count")
    if not isinstance(error_count, int) or isinstance(error_count, bool) or error_count != 0:
        return CellResult(unit, tier, error="report error_count must be exactly 0")
    delta = report.get("recall_delta")
    ci = report.get("bootstrap_ci_95")
    if (
        not isinstance(delta, (int, float))
        or isinstance(delta, bool)
        or not math.isfinite(delta)
        or not -1.0 <= float(delta) <= 1.0
    ):
        return CellResult(unit, tier, error="report recall_delta must be finite and in [-1, 1]")
    if not isinstance(ci, list) or len(ci) != 2:
        return CellResult(unit, tier, error="report bootstrap_ci_95 must be a pair")
    low, high = ci
    if (
        not isinstance(low, (int, float))
        or isinstance(low, bool)
        or not isinstance(high, (int, float))
        or isinstance(high, bool)
        or not math.isfinite(low)
        or not math.isfinite(high)
        or not -1.0 <= float(low) <= 1.0
        or not -1.0 <= float(high) <= 1.0
        or float(low) > float(high)
    ):
        return CellResult(unit, tier, error="report bootstrap_ci_95 must be finite and bounded")
    return CellResult(
        unit=unit,
        tier=tier,
        recall_delta=float(delta),
        ci_low=float(low) if isinstance(low, (int, float)) else None,
        ci_high=float(high) if isinstance(high, (int, float)) else None,
    )


def summarize_unit(
    unit: str,
    panel: Panel,
    cells: dict[str, CellResult],
) -> UnitVerdict:
    """Classify one unit's degradation across the panel.

    The reference band is the mean recall_delta over the reference tiers that
    scored. A probe tier degrades when its recall_delta is more than
    ``panel.drop_threshold`` below that band. A unit with no scored reference
    tier is ``incomplete`` (no band to compare against). A unit with a complete
    band and no degraded probe is ``robust`` (a good `auto`/cheap candidate).
    """
    ref_deltas: list[float] = []
    for tier in panel.reference_tiers:
        cell = cells.get(tier.label)
        if cell is not None and cell.ok and cell.recall_delta is not None:
            ref_deltas.append(cell.recall_delta)
    reference = (sum(ref_deltas) / len(ref_deltas)) if ref_deltas else None

    probe_deltas: dict[str, float | None] = {}
    degraded: list[str] = []
    for tier in panel.probe_tiers:
        cell = cells.get(tier.label)
        value = cell.recall_delta if cell and cell.ok else None
        probe_deltas[tier.label] = value
        if reference is not None and value is not None:
            if reference - value > panel.drop_threshold:
                degraded.append(tier.label)

    incomplete = reference is None or any(v is None for v in probe_deltas.values())
    robust = (not incomplete) and not degraded
    return UnitVerdict(
        unit=unit,
        reference_delta=reference,
        probe_deltas=probe_deltas,
        degraded_tiers=degraded,
        robust=robust,
        incomplete=incomplete,
    )


def summarize(
    panel: Panel,
    results: list[CellResult],
) -> list[UnitVerdict]:
    """Group cells by unit and classify each. Deterministic unit order."""
    by_unit: dict[str, dict[str, CellResult]] = {}
    for cell in results:
        by_unit.setdefault(cell.unit, {})[cell.tier] = cell
    return [summarize_unit(u, panel, by_unit[u]) for u in sorted(by_unit)]


def to_json(panel: Panel, verdicts: list[UnitVerdict]) -> dict[str, object]:
    return {
        "drop_threshold": panel.drop_threshold,
        "reference_tiers": [t.label for t in panel.reference_tiers],
        "probe_tiers": [t.label for t in panel.probe_tiers],
        "units": [
            {
                "unit": v.unit,
                "reference_delta": (
                    round(v.reference_delta, 4) if v.reference_delta is not None else None
                ),
                "probe_deltas": {
                    k: (round(x, 4) if x is not None else None) for k, x in v.probe_deltas.items()
                },
                "degraded_tiers": v.degraded_tiers,
                "robust": v.robust,
                "incomplete": v.incomplete,
            }
            for v in verdicts
        ],
    }


def to_human(panel: Panel, verdicts: list[UnitVerdict]) -> str:
    lines = [
        f"Model-panel sweep: {len(verdicts)} unit(s), reference band "
        f"{[t.label for t in panel.reference_tiers]}, "
        f"drop threshold {panel.drop_threshold:g}",
    ]
    for v in verdicts:
        if v.incomplete:
            tag = "INCOMPLETE"
        elif v.robust:
            tag = "robust across tiers"
        else:
            tag = f"DEGRADES at {', '.join(v.degraded_tiers)}"
        ref = "n/a" if v.reference_delta is None else f"{v.reference_delta:+.3f}"
        probes = ", ".join(
            f"{k}={'n/a' if x is None else f'{x:+.3f}'}" for k, x in v.probe_deltas.items()
        )
        lines.append(f"  {v.unit}: ref={ref} | {probes} | {tag}")
    return "\n".join(lines)


def load_panel_config(text: str, *, known_providers: set[str] | None = None) -> Panel:
    """Parse a JSON panel-config string into a Panel."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PanelConfigError(f"panel config is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PanelConfigError("panel config must be a JSON object")
    return parse_panel(payload, known_providers=known_providers)
