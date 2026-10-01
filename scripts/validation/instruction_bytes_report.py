"""Human-readable rendering of the instruction-context byte report (issue #5400)."""

from __future__ import annotations

from typing import Any

__all__ = ["format_table"]


def _group_lines(title: str, groups: dict[str, dict[str, int]], total: dict[str, int]) -> list[str]:
    lines = [title, f"  {'group':<20} {'files':>6} {'bytes':>10} {'tokens~':>10}"]
    for name, data in groups.items():
        lines.append(f"  {name:<20} {data['files']:>6} {data['bytes']:>10} {data['tokens']:>10}")
    lines.append(f"  {'TOTAL':<20} {total['files']:>6} {total['bytes']:>10} {total['tokens']:>10}")
    return lines


def _fixture_lines(fixtures: dict[str, Any]) -> list[str]:
    lines = [
        "Fixtures (Claude Code load path)",
        f"  {'id':<3} {'name':<22} {'files':>5} {'bytes':>9} {'tokens~':>9}"
        f" {'ceiling':>9} {'status':>7}",
    ]
    for fid, data in sorted(fixtures.items()):
        if "error" in data:
            lines.append(f"  {fid:<3} {data['name']:<22} not measurable: {data['error']}")
            continue
        ceiling = data["ceiling_bytes"]
        status = "n/a" if ceiling is None else ("FAIL" if data["bytes"] > ceiling else "PASS")
        shown = "-" if ceiling is None else str(ceiling)
        lines.append(
            f"  {fid:<3} {data['name']:<22} {data['artifacts']:>5} {data['bytes']:>9} "
            f"{data['tokens']:>9} {shown:>9} {status:>7}"
        )
    return lines


def _contributor_lines(title: str, rows: list[dict[str, Any]]) -> list[str]:
    return [title, *(f"  {r['bytes']:>9}  {r['path']}" for r in rows)]


def _delta_lines(delta: dict[str, Any]) -> list[str]:
    lines = [f"Delta versus {delta['base_ref']} ({delta['base_sha'][:12]})"]
    lines.append(f"  {'metric':<34} {'base':>10} {'head':>10} {'delta':>9}")
    lines.extend(
        f"  {m['name']:<34} {m['base']:>10} {m['head']:>10} {m['delta']:>+9}"
        for m in delta["metrics"]
        if m["delta"] != 0
    )
    if not any(m["delta"] for m in delta["metrics"]):
        lines.append("  no change")
    if delta["changed_paths"]:
        lines.append("  changed canonical paths (largest first)")
        lines.extend(f"    {r['delta']:>+9}  {r['path']}" for r in delta["changed_paths"])
    if delta["unmeasured_at_base"]:
        lines.append(f"  not measurable at base: {', '.join(delta['unmeasured_at_base'])}")
    lines.extend(
        f"  WARN: {name} grew by more than {delta['threshold_bytes']} bytes"
        for name in delta["material_growth"]
    )
    return lines


def _findings_lines(report: dict[str, Any]) -> list[str]:
    """List report-level findings, then each fixture's, so a partial measurement is visible."""
    lines = [f"  {finding}" for finding in report["findings"]]
    for fid, data in sorted(report["fixtures"].items()):
        lines.extend(f"  {fid}: {finding}" for finding in data.get("findings", []))
    return ["Findings", *lines] if lines else []


def format_table(report: dict[str, Any]) -> str:
    """Render the report as text sections separated by blank lines."""
    canonical, generated = report["canonical"], report["generated"]
    always = report["always_on"]
    sections = [
        _group_lines("Canonical authored corpus", canonical["groups"], canonical["total"]),
        _group_lines(
            "Generated projections (excluded from authored totals)",
            generated["families"],
            generated["total"],
        ),
        [
            "Always-on (all tasks)",
            *(
                f"  {h:<12} files={d['files']:<3} bytes={d['bytes']:<8} tokens~={d['tokens']}"
                for h, d in always.items()
            ),
        ],
        _fixture_lines(report["fixtures"]),
        _contributor_lines("Top canonical contributors", canonical["top_contributors"]),
    ]
    findings = _findings_lines(report)
    if findings:
        sections.append(findings)
    if "delta" in report:
        sections.append(_delta_lines(report["delta"]))
    if report["ceiling_breaches"]:
        sections.append(
            ["FAIL: fixture ceiling exceeded", *(f"  {b}" for b in report["ceiling_breaches"])]
        )
    sections.append([f"Estimator: {report['estimator']}"])
    return "\n\n".join("\n".join(lines) for lines in sections)
