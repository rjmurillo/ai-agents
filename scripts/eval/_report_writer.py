"""ReportWriter: render REPORT.md and report.json.

DESIGN-004 §5.7. Writes both files via write-temp-then-rename so a
crash mid-write does not leave a partial report on disk. The
`recommendation` field is whatever the caller supplies: `None` for
T4-5 records (decision pending), one of `graduate-to-CI`,
`keep-as-audit`, `scrap` when T4-7 records the manual verdict, or
`halt-due-to-flakiness` when AC-10's flakiness gate trips and the
runner records the halt automatically. The writer does not interpret
the value; it persists what the caller passes.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from _eval_agent_types import SCHEMA_VERSION
from _report_aggregator import AggregateResult, FormFactorComparison


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def _format_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_pp(value: float) -> str:
    """Render a signed fraction as percentage points (e.g. +38.10pp).

    The summary table mixes recall (percent) with the recall delta and CI
    bounds (formerly raw fractions like +0.3810). A fraction next to a
    percent value is easy to misread as percentage points; using the
    explicit `pp` suffix removes the ambiguity. The JSON shape is
    unchanged: `report.json` still carries raw fractions for downstream
    tooling.
    """
    return f"{value * 100:+.2f}pp"


def _build_report_json(
    *,
    aggregate: AggregateResult,
    run_id: str,
    model_id: str,
    agent_prompt_sha: str,
    baseline_prompt_sha: str,
    fixture_set_sha: str,
    wall_clock_seconds: float,
    recommendation: str | None = None,
    form_factor: FormFactorComparison | None = None,
) -> dict:
    """Serialize the AggregateResult into the report.json shape.

    `recommendation` is `null` until a caller supplies the verdict
    (`graduate-to-CI`, `keep-as-audit`, `scrap`, or
    `halt-due-to-flakiness`). The runner is the authoritative source;
    earlier code passed `None` unconditionally, which made the report
    non-reproducible. All field names match DESIGN-004 §5.6 verbatim so
    external consumers can rely on them.
    """
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "run_id": run_id,
        "model_id": model_id,
        "agent_prompt_sha": agent_prompt_sha,
        "baseline_prompt_sha": baseline_prompt_sha,
        "fixture_set_sha": fixture_set_sha,
        "agent_recall": round(aggregate.agent_recall, 6),
        "baseline_recall": round(aggregate.baseline_recall, 6),
        "recall_delta": round(aggregate.recall_delta, 6),
        "bootstrap_ci_95": [
            round(aggregate.bootstrap_ci_95[0], 6),
            round(aggregate.bootstrap_ci_95[1], 6),
        ],
        "recall_with_errors": round(aggregate.recall_with_errors, 6),
        "recall_excluding_errors": round(aggregate.recall_excluding_errors, 6),
        "per_fixture_pass_rates": aggregate.per_fixture_pass_rates,
        "flakiness": aggregate.flakiness,
        "flaky_fixtures_detected": aggregate.flaky_fixtures_detected,
        "flaky_fixtures_excluded": aggregate.flaky_fixtures_excluded,
        "flaky_halt_threshold_crossed": aggregate.flaky_halt_threshold_crossed,
        "total_tokens_in": aggregate.total_tokens_in,
        "total_tokens_out": aggregate.total_tokens_out,
        "wall_clock_seconds": round(wall_clock_seconds, 2),
        "cost_estimate_usd": round(aggregate.cost_estimate_usd, 4),
        "tokens_estimated": aggregate.tokens_estimated,
        "error_count": aggregate.error_count,
        "pricing_rate_as_of": aggregate.pricing_rate_as_of,
        "recommendation": recommendation,
    }
    if form_factor is not None:
        payload["form_factor"] = _form_factor_payload(form_factor)
    return payload


def _form_factor_payload(form_factor: FormFactorComparison) -> dict:
    return {
        "schemaVersion": form_factor.schema_version,
        "agent_recall": round(form_factor.agent_recall, 6),
        "baseline_recall": round(form_factor.baseline_recall, 6),
        "skill_recall": round(form_factor.skill_recall, 6),
        "agent_baseline_delta": round(form_factor.agent_baseline_delta, 6),
        "skill_baseline_delta": round(form_factor.skill_baseline_delta, 6),
        "agent_skill_delta": round(form_factor.agent_skill_delta, 6),
        "agent_baseline_ci_95": [
            round(form_factor.agent_baseline_ci[0], 6),
            round(form_factor.agent_baseline_ci[1], 6),
        ],
        "skill_baseline_ci_95": [
            round(form_factor.skill_baseline_ci[0], 6),
            round(form_factor.skill_baseline_ci[1], 6),
        ],
        "agent_skill_ci_95": [
            round(form_factor.agent_skill_ci[0], 6),
            round(form_factor.agent_skill_ci[1], 6),
        ],
        "agent_tokens_in": form_factor.agent_tokens_in,
        "agent_tokens_out": form_factor.agent_tokens_out,
        "skill_tokens_in": form_factor.skill_tokens_in,
        "skill_tokens_out": form_factor.skill_tokens_out,
        "verdict": form_factor.verdict,
    }


def _render_summary_table(aggregate: AggregateResult) -> str:
    ci_low, ci_high = aggregate.bootstrap_ci_95
    return (
        "## Summary\n\n"
        "| Metric | Value |\n"
        "|---|---|\n"
        f"| Agent recall | {_format_pct(aggregate.agent_recall)} |\n"
        f"| Baseline recall | {_format_pct(aggregate.baseline_recall)} |\n"
        f"| Signed delta (agent - baseline) | {_format_pp(aggregate.recall_delta)} |\n"
        f"| 95% bootstrap CI | [{_format_pp(ci_low)}, {_format_pp(ci_high)}] |\n"
        f"| Recall with errors | {_format_pct(aggregate.recall_with_errors)} |\n"
        f"| Recall excluding errors | {_format_pct(aggregate.recall_excluding_errors)} |\n"
        f"| Error count | {aggregate.error_count} |\n"
        f"| Flakiness | {'true' if aggregate.flakiness else 'false'} |\n"
    )


def _render_form_factor_section(form_factor: FormFactorComparison | None) -> str:
    if form_factor is None:
        return ""
    return (
        "## Form-Factor Comparison\n\n"
        "| Metric | Value |\n"
        "|---|---|\n"
        f"| Agent recall | {_format_pct(form_factor.agent_recall)} |\n"
        f"| Skill recall | {_format_pct(form_factor.skill_recall)} |\n"
        f"| Skill - baseline delta | {_format_pp(form_factor.skill_baseline_delta)} |\n"
        f"| Agent - skill delta | {_format_pp(form_factor.agent_skill_delta)} |\n"
        f"| Agent - skill 95% bootstrap CI | "
        f"[{_format_pp(form_factor.agent_skill_ci[0])}, "
        f"{_format_pp(form_factor.agent_skill_ci[1])}] |\n"
        f"| Agent tokens | {form_factor.agent_tokens_in + form_factor.agent_tokens_out} |\n"
        f"| Skill tokens | {form_factor.skill_tokens_in + form_factor.skill_tokens_out} |\n"
        f"| Verdict | `{form_factor.verdict}` |\n"
    )


def _render_per_fixture_section(aggregate: AggregateResult) -> str:
    if not aggregate.per_fixture_pass_rates:
        return "## Per-Fixture Pass Rates\n\n_No fixtures recorded._\n"
    lines = [
        "## Per-Fixture Pass Rates",
        "",
        "Pass rate per run (variant: agent | baseline).",
        "",
        "| Fixture | Agent | Baseline |",
        "|---|---|---|",
    ]
    for fixture_id in sorted(aggregate.per_fixture_pass_rates):
        variants = aggregate.per_fixture_pass_rates[fixture_id]
        agent = ",".join(f"{r:.2f}" for r in variants.get("agent", []))
        baseline = ",".join(f"{r:.2f}" for r in variants.get("baseline", []))
        lines.append(f"| {fixture_id} | {agent or '-'} | {baseline or '-'} |")
    return "\n".join(lines) + "\n"


def _render_ci_section(aggregate: AggregateResult) -> str:
    ci_low, ci_high = aggregate.bootstrap_ci_95
    excludes_zero = ci_low > 0 or ci_high < 0
    # Guard the significance language. Per ADR-058, a halt-due-to-flakiness
    # run cannot graduate or scrap regardless of the CI shape: AC-10
    # halts before the verdict gate runs. Without this caveat, a halted
    # run with a CI that excludes zero reads as if the agent had a
    # blessed positive verdict, which the methodology explicitly forbids.
    halted = aggregate.halt_due_to_flakiness
    flaky_no_halt = aggregate.flakiness and not halted
    if halted:
        caveat = (
            "**Note**: this run halted at AC-10's flakiness gate. The CI "
            "below is reported for diagnostic context; statistical "
            "significance does not unblock the verdict, which is fixed at "
            "`halt-due-to-flakiness` until the variance source is "
            "investigated and the methodology is re-run.\n\n"
        )
    elif flaky_no_halt and aggregate.flaky_halt_threshold_crossed:
        caveat = (
            "**Warning**: the flaky-fixture count crossed AC-10's "
            "\"more than 30%\" halt threshold, but flag-and-continue mode "
            "suppressed the halt. Treat the delta below as provisional: the "
            "methodology is near the instability boundary. Investigate the "
            "variance source before relying on this verdict.\n\n"
        )
    elif flaky_no_halt:
        caveat = (
            "**Note**: at least one fixture exhibited non-zero pass-rate "
            "variance; flaky fixtures are excluded from the delta computed "
            "below. The CI describes the stable subset only.\n\n"
        )
    else:
        caveat = ""
    return (
        "## Confidence Interval\n\n"
        f"{caveat}"
        f"Paired bootstrap, n=10000 resamples at fixture level. The 95% CI on the "
        f"signed recall delta is **[{_format_pp(ci_low)}, {_format_pp(ci_high)}]**. "
        f"The interval {'**excludes** zero' if excludes_zero else '**includes** zero'}, "
        f"so the observed delta is "
        f"{'statistically distinguishable from no effect' if excludes_zero else 'not statistically distinguishable from no effect at the 95% level'}.\n"
    )


def _render_recommendation_section(recommendation: str | None = None) -> str:
    if recommendation is None:
        return (
            "## Recommendation\n\n"
            "_Pending. T4-7 records the verdict (graduate-to-CI, "
            "keep-as-audit, scrap, or halt-due-to-flakiness) with at "
            "least two pieces of evidence drawn from the data above._\n"
        )
    return (
        "## Recommendation\n\n"
        f"**Verdict**: `{recommendation}`\n"
    )


def _render_cost_section(
    aggregate: AggregateResult, wall_clock_seconds: float
) -> str:
    estimate_caveat = (
        "\n\n_Token counts are estimated from a text-length heuristic "
        "(~4 chars per token); cost is not authoritative. Replace with "
        "measured `usage` from the API response in a follow-up._"
        if aggregate.tokens_estimated
        else ""
    )
    return (
        "## Cost and Resource Summary\n\n"
        f"- Total tokens in: {aggregate.total_tokens_in:,}\n"
        f"- Total tokens out: {aggregate.total_tokens_out:,}\n"
        f"- Estimated cost: ${aggregate.cost_estimate_usd:.4f} USD "
        f"(rate as of {aggregate.pricing_rate_as_of})\n"
        f"- Wall-clock time: {wall_clock_seconds:.1f}s"
        f"{estimate_caveat}\n"
    )


def _render_flakiness_section(aggregate: AggregateResult) -> str:
    if not aggregate.flakiness:
        return "## Flakiness\n\nNo non-zero pass-rate variance detected.\n"
    excluded = (
        ", ".join(aggregate.flaky_fixtures_excluded)
        if aggregate.flaky_fixtures_excluded
        else "_(none excluded)_"
    )
    return (
        "## Flakiness\n\n"
        "At least one fixture exhibited non-zero pass-rate variance across runs "
        "on the same `(prompt_sha, fixture_set_sha)`.\n\n"
        f"Excluded from delta: {excluded}\n"
    )


def _render_markdown(
    *,
    aggregate: AggregateResult,
    run_id: str,
    model_id: str,
    agent_prompt_sha: str,
    baseline_prompt_sha: str,
    fixture_set_sha: str,
    wall_clock_seconds: float,
    recommendation: str | None = None,
    form_factor: FormFactorComparison | None = None,
) -> str:
    """Compose REPORT.md in stepdown order: header → summary → details."""
    header = (
        f"# Eval Report: {run_id}\n\n"
        f"- Model: `{model_id}`\n"
        f"- Agent prompt SHA: `{agent_prompt_sha[:16]}...`\n"
        f"- Baseline prompt SHA: `{baseline_prompt_sha[:16]}...`\n"
        f"- Fixture set SHA: `{fixture_set_sha[:16]}...`\n"
    )
    sections = [
        header,
        _render_summary_table(aggregate),
        _render_form_factor_section(form_factor),
        _render_per_fixture_section(aggregate),
        _render_ci_section(aggregate),
        _render_recommendation_section(recommendation),
        _render_cost_section(aggregate, wall_clock_seconds),
        _render_flakiness_section(aggregate),
    ]
    return "\n".join(sections)


class ReportWriter:
    """Render and persist REPORT.md and report.json for one run."""

    def __init__(self, reports_dir: Path) -> None:
        self._reports_dir = reports_dir

    def write(
        self,
        *,
        aggregate: AggregateResult,
        run_id: str,
        model_id: str,
        agent_prompt_sha: str,
        baseline_prompt_sha: str,
        fixture_set_sha: str,
        wall_clock_seconds: float,
        recommendation: str | None = None,
        form_factor: FormFactorComparison | None = None,
    ) -> tuple[Path, Path]:
        """Render both files. Returns (json_path, markdown_path)."""
        run_reports_dir = self._reports_dir / run_id
        report_json = _build_report_json(
            aggregate=aggregate,
            run_id=run_id,
            model_id=model_id,
            agent_prompt_sha=agent_prompt_sha,
            baseline_prompt_sha=baseline_prompt_sha,
            fixture_set_sha=fixture_set_sha,
            wall_clock_seconds=wall_clock_seconds,
            recommendation=recommendation,
            form_factor=form_factor,
        )
        report_md = _render_markdown(
            aggregate=aggregate,
            run_id=run_id,
            model_id=model_id,
            agent_prompt_sha=agent_prompt_sha,
            baseline_prompt_sha=baseline_prompt_sha,
            fixture_set_sha=fixture_set_sha,
            wall_clock_seconds=wall_clock_seconds,
            recommendation=recommendation,
            form_factor=form_factor,
        )
        json_path = run_reports_dir / "report.json"
        md_path = run_reports_dir / "REPORT.md"
        _atomic_write(json_path, json.dumps(report_json, indent=2, sort_keys=True))
        _atomic_write(md_path, report_md)
        return json_path, md_path
