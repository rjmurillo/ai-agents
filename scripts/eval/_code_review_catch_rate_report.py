"""Aggregation and reporting for the code-review catch-rate harness (issue #7149).

Pure functions over trial rows. The Wilson interval is the one the ADR harness
uses (`_adr_catch_rate_stats.wilson_interval`), so both harnesses report the
same method.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import _code_review_catch_rate_core as core
from _adr_catch_rate_stats import wilson_interval


def rate_cell(hits: int, total: int) -> dict[str, Any]:
    low, high = wilson_interval(hits, total)
    return {
        "hits": hits,
        "n": total,
        "rate": (hits / total) if total else None,
        "ci95": [round(low, 4), round(high, 4)],
    }


def _scored(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows without an error. Errored calls never enter `n`, so a failure is no miss."""
    return [r for r in rows if not r.get("error")]


def per_entry(rows: list[dict[str, Any]], corpus: core.Corpus) -> list[dict[str, Any]]:
    out = []
    for entry in corpus.entries:
        mine = [r for r in rows if r["entry"] == entry.id]
        good = _scored(mine)
        out.append(
            {
                "entry": entry.id,
                "defect_class": entry.defect_class,
                "trials": len(good),
                "caught": sum(1 for r in good if r["caught"]),
                "near_miss": sum(1 for r in good if r["near_miss"] and not r["caught"]),
                "no_findings": sum(1 for r in good if not r.get("findings")),
                "errors": len(mine) - len(good),
            }
        )
    return out


def aggregate(rows: list[dict[str, Any]], corpus: core.Corpus) -> dict[str, Any]:
    good = _scored(rows)
    caught = sum(1 for r in good if r["caught"])
    file_hit = sum(1 for r in good if r["caught"] or r["near_miss"])
    by_class: dict[str, dict[str, Any]] = {}
    classes = {e.id: e.defect_class for e in corpus.entries}
    for klass in sorted(set(classes.values())):
        sub = [r for r in good if classes.get(r["entry"]) == klass]
        by_class[klass] = rate_cell(sum(1 for r in sub if r["caught"]), len(sub))
    return {
        "caught_top5": rate_cell(caught, len(good)),
        "file_only_top5": rate_cell(file_hit, len(good)),
        "no_findings": sum(1 for r in good if not r.get("findings")),
        "errors": len(rows) - len(good),
        "by_class": by_class,
    }


def summarize(
    rows: list[dict[str, Any]], meta: dict[str, Any], corpus: core.Corpus
) -> dict[str, Any]:
    return {
        "meta": meta,
        "aggregate": aggregate(rows, corpus),
        "entries": per_entry(rows, corpus),
        "rows": [{k: v for k, v in row.items() if k != "raw"} for row in rows],
    }


def _pct(cell: dict[str, Any]) -> str:
    if cell["rate"] is None:
        return f"{cell['hits']}/{cell['n']} (no trials)"
    low, high = cell["ci95"]
    return f"{cell['hits']}/{cell['n']} ({cell['rate']:.0%}, CI {low:.0%} to {high:.0%})"


def _resumed_note(meta: dict[str, Any]) -> str:
    """Say so when the header describes a rescore or omits work reused from a checkpoint."""
    if meta.get("rescored"):
        return (
            "(rescored from stored responses with no model call; model, provider, "
            "and date come from the rescore invocation, not the original run) "
        )
    resumed = meta.get("resumed_rows") or 0
    if not resumed:
        return ""
    return f"(this invocation only; {resumed} rows were reused from a checkpoint) "


def render_report(result: dict[str, Any]) -> str:
    meta, agg = result["meta"], result["aggregate"]
    lines = [
        "# Code-review catch rate",
        "",
        f"Model `{meta['model']}` via `{meta['provider']}`, run {meta['date']}, "
        f"{meta['entries']} entries x {meta['trials']} trial(s). "
        f"Calls: {meta.get('calls')}. Output tokens: {meta.get('output_tokens')}. "
        f"{_resumed_note(meta)}"
        f"Cost: {meta.get('cost', 'not recorded')}.",
        "",
        "| Measure | Result (95 percent Wilson interval) |",
        "|---|---|",
        f"| Caught in top 5 (same file and class) | {_pct(agg['caught_top5'])} |",
        f"| Same file in top 5 (class ignored) | {_pct(agg['file_only_top5'])} |",
        "",
        f"Reviews with no findings: {agg['no_findings']}. "
        f"Errored calls (not counted in n): {agg['errors']}.",
        "",
        "| Defect class | Caught |",
        "|---|---|",
    ]
    lines += [f"| {klass} | {_pct(cell)} |" for klass, cell in agg["by_class"].items() if cell["n"]]
    lines += ["", "| Entry | Class | Caught | Near miss | No findings |", "|---|---|---|---|---|"]
    for e in result["entries"]:
        if not (e["trials"] or e["errors"]):
            continue
        lines.append(
            f"| {e['entry']} | {e['defect_class']} | {e['caught']}/{e['trials']} "
            f"| {e['near_miss']} | {e['no_findings']} |"
        )
    return "\n".join(lines)


def dump_results(result: dict[str, Any]) -> str:
    """Serialize one row or one entry per line, so the file stays reviewable."""
    lines = ["{"]
    keys = list(result)
    for index, key in enumerate(keys):
        value = result[key]
        tail = "," if index < len(keys) - 1 else ""
        if isinstance(value, dict):
            body = ",\n".join(f"    {json.dumps(k)}: {json.dumps(v)}" for k, v in value.items())
            lines.append(f"  {json.dumps(key)}: {{\n{body}\n  }}{tail}")
        elif isinstance(value, list):
            body = ",\n".join(f"    {json.dumps(item)}" for item in value)
            lines.append(f"  {json.dumps(key)}: [\n{body}\n  ]{tail}")
        else:
            lines.append(f"  {json.dumps(key)}: {json.dumps(value)}{tail}")
    return "\n".join(lines + ["}"]) + "\n"


def render_from_results(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not {"meta", "aggregate", "entries"} <= data.keys():
        raise ValueError(f"{path} is not a results file (needs meta, aggregate, entries)")
    return render_report(data)
