#!/usr/bin/env python3
"""Tiered model-panel sweep CLI (issue #3042).

Sweeps each unit (agent/skill) across a tiered model panel by invoking the
existing `eval-agent-vs-baseline.py` harness once per (unit, tier) with that
tier's `--provider`/`--model`, then aggregates the per-tier `recall_delta` into
a degradation report (see `_model_panel_core`). Two frontier tiers set the
pass/fail reference band; lower tiers are observed for degradation, never gating.

Spend boundary: `--dry-run` validates the panel and prints the planned harness
invocations with ZERO API spend. A live run costs (units x tiers x n-runs x 2)
model calls across two vendors, so the panel and run budget are an owner
decision (#3042); the harness, dry-run, and report land first behind offline
tests.

Exit codes (AGENTS.md): 0 ok, 2 config (bad panel/args), 3 external (a harness
invocation failed during a live run).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

from _model_panel_core import (  # noqa: E402
    CellResult,
    Panel,
    PanelConfigError,
    PanelTier,
    cell_from_report,
    default_panel,
    load_panel_config,
    summarize,
    to_human,
    to_json,
)

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3

_HARNESS = _EVAL_DIR / "eval-agent-vs-baseline.py"
_REPO_ROOT = _EVAL_DIR.parents[1]
_REPORTS_DIR_TEMPLATE = "evals/{agent}-spike/reports"

# A runner turns a (unit, tier, n_runs, fixtures) request into the harness's
# report.json mapping, or raises RuntimeError. The default runner shells out to
# eval-agent-vs-baseline.py; tests inject a fake to exercise aggregation offline.
Runner = Callable[[str, PanelTier, int, str], dict[str, object]]


def _make_run_id(unit: str, tier_label: str) -> str:
    """Build a unique run id for one (unit, tier) cell: panel-<unit>-<tier>-<8hex>."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"panel-{unit}-{tier_label}"[:55]
    return f"{slug}-{suffix}"


def _child_report_path(unit: str, run_id: str) -> Path:
    """Path to the report.json the harness writes for a run."""
    return (
        _REPO_ROOT
        / _REPORTS_DIR_TEMPLATE.format(agent=unit)
        / run_id
        / "report.json"
    )


def _default_runner(unit: str, tier: PanelTier, n_runs: int, fixtures: str) -> dict[str, object]:
    """Run the harness for one (unit, tier) and return its parsed report.json.

    Reuses the whole existing pipeline (recall, bootstrap CI, cost) via the
    documented `--provider`/`--model` flags added in #2710. Raises RuntimeError
    on a non-zero exit or unreadable report so the caller records the cell as an
    error instead of a silent zero.
    """
    run_id = _make_run_id(unit, tier.label)
    argv = [
        sys.executable, str(_HARNESS),
        "--agent", unit,
        "--fixtures", fixtures,
        "--n-runs", str(n_runs),
        "--provider", tier.provider,
        "--model", tier.model,
        "--run-id", run_id,
    ]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"harness invocation failed: {exc}") from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"harness exited {completed.returncode}: "
            f"{(completed.stderr or completed.stdout)[:200]}"
        )
    report_path = _child_report_path(unit, run_id)
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"harness exited 0 but report at {report_path} is unreadable: {exc}"
        ) from exc
    if not isinstance(report, dict):
        raise RuntimeError("harness report was not a JSON object")
    return report


def sweep(
    panel: Panel,
    units: list[str],
    *,
    fixtures_template: str,
    n_runs: int,
    runner: Runner,
) -> list[CellResult]:
    """Run every (unit, tier) cell through the runner and collect results.

    `fixtures_template` is formatted with `{unit}` per unit. A cell whose runner
    raises is recorded as an errored CellResult (the sweep continues), so one
    provider outage does not lose the rest of the matrix.
    """
    results: list[CellResult] = []
    for unit in units:
        fixtures = fixtures_template.format(unit=unit)
        for tier in panel.tiers:
            try:
                report = runner(unit, tier, n_runs, fixtures)
            except RuntimeError as exc:
                results.append(CellResult(unit, tier.label, error=str(exc)))
                continue
            results.append(cell_from_report(unit, tier.label, report))
    return results


def _resolve_panel(args: argparse.Namespace) -> Panel:
    known = _known_providers()
    if args.panel_config:
        text = Path(args.panel_config).read_text(encoding="utf-8")
        return load_panel_config(text, known_providers=known)
    return default_panel()


def _known_providers() -> set[str] | None:
    """Provider names the transport can resolve, or None if unavailable."""
    try:
        from _providers import known_provider_names
    except Exception:  # transport optional at config time
        return None
    try:
        return set(known_provider_names())
    except Exception:
        return None


def _dry_run_report(panel: Panel, units: list[str], n_runs: int) -> str:
    planned = len(units) * len(panel.tiers)
    lines = [
        f"DRY RUN: {len(units)} unit(s) x {len(panel.tiers)} tier(s) = "
        f"{planned} harness invocation(s), n-runs={n_runs}, ZERO spend.",
        f"  reference band: {[t.label for t in panel.reference_tiers]}",
    ]
    for unit in units:
        for tier in panel.tiers:
            lines.append(
                f"  - {unit} @ {tier.label} ({tier.role}): "
                f"provider={tier.provider} model={tier.model}"
            )
    return "\n".join(lines)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep each unit across a tiered model panel and report per-tier "
            "effect size / degradation (issue #3042)."
        )
    )
    parser.add_argument(
        "--agents", nargs="+", required=True,
        help="Units (agent names) to sweep.",
    )
    parser.add_argument(
        "--fixtures-template",
        default="evals/{unit}-spike/fixtures",
        help="Fixtures path per unit; {unit} substitutes the unit name.",
    )
    parser.add_argument("--n-runs", type=int, default=3, help="Runs per cell (default: 3).")
    parser.add_argument(
        "--panel-config", default=None,
        help="JSON panel config path; omit to use the documented default panel.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate the panel and print the plan with zero spend.",
    )
    parser.add_argument(
        "--report", type=Path, default=None,
        help="Write the JSON summary to this path (accretes a sample log).",
    )
    parser.add_argument(
        "--output-format", choices=("human", "json"), default="human",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, runner: Runner | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.n_runs < 1:
        print(f"error: --n-runs must be >= 1, got {args.n_runs}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        panel = _resolve_panel(args)
    except (PanelConfigError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if args.dry_run:
        print(_dry_run_report(panel, args.agents, args.n_runs))
        return EXIT_OK

    results = sweep(
        panel, args.agents,
        fixtures_template=args.fixtures_template,
        n_runs=args.n_runs,
        runner=runner or _default_runner,
    )
    verdicts = summarize(panel, results)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(to_json(panel, verdicts), indent=2), encoding="utf-8",
        )
    if args.output_format == "json":
        print(json.dumps(to_json(panel, verdicts), indent=2))
    else:
        print(to_human(panel, verdicts))
    return EXIT_EXTERNAL if any(not c.ok for c in results) else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
