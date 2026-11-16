"""Aggregation and paired comparison for the third-party review gap replay.

Pure functions over scored rows; no I/O. ``eval_third_party_gap_replay.py``
calls them for a run, ``--rescore``, and ``--compare``.
"""

from __future__ import annotations

import math
from typing import Any

import _third_party_gap_core as core
from _adr_catch_rate_stats import wilson_interval


def _rate(hits: int, total: int) -> dict[str, Any]:
    low, high = wilson_interval(hits, total) if total else (0.0, 0.0)
    return {"hits": hits, "n": total, "rate": hits / total if total else 0.0, "ci": [low, high]}


def aggregate(rows: list[dict[str, Any]], revisions: list[core.Revision]) -> dict[str, Any]:
    """Per-defect rates overall and by context, theme, and bot; per-review finding counts."""
    by_id = {r.id: r for r in revisions}
    cells: dict[str, dict[str, list[int]]] = {}

    def bump(group: str, key: str, caught: bool, same: bool) -> None:
        cell = cells.setdefault(group, {}).setdefault(key, [0, 0, 0])
        cell[0] += int(caught)
        cell[1] += int(same)
        cell[2] += 1

    for row in rows:
        rev = by_id[row["revision"]]
        for defect in rev.defects:
            got = row["defects"][defect.thread]
            for group, key in (
                ("all", "all"),
                ("context", defect.context),
                ("theme", defect.theme),
                ("bot", defect.bot),
            ):
                bump(group, key, got["caught"], got["same_file"])
    out: dict[str, Any] = {}
    for group, keyed in cells.items():
        out[group] = {
            key: {"caught": _rate(c, n), "same_file": _rate(s, n)}
            for key, (c, s, n) in sorted(keyed.items())
        }
    findings = [row["findings"] for row in rows]
    out["reviews"] = {
        "n": len(rows),
        "no_findings": sum(1 for row in rows if row["no_findings"]),
        "mean_findings": sum(findings) / len(findings) if findings else 0.0,
        "cut_at_ceiling": sum(1 for row in rows if row.get("finish_reason") == "length"),
        "output_tokens": sum(int(row.get("output_tokens") or 0) for row in rows),
    }
    return out


def mcnemar_exact_p(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p: a binomial test on the discordant pairs at p = 0.5."""
    n = only_a + only_b
    if n == 0:
        return 1.0
    tail: float = sum(math.comb(n, i) for i in range(min(only_a, only_b) + 1)) / 2**n
    return min(1.0, 2 * tail)


def compare(
    baseline: list[dict[str, Any]],
    treatment: list[dict[str, Any]],
    revisions: list[core.Revision],
) -> dict[str, Any]:
    """Pair the two arms by (revision, trial, defect) and test the caught difference.

    Only jobs both arms finished are paired, so an arm that ran further never
    gets credit for the extra jobs. ``context`` splits the same counts by the
    defect's ``context`` label.
    """
    contexts = {d.thread: d.context for r in revisions for d in r.defects}
    by_key = {(r["revision"], int(r["trial"])): r for r in treatment}
    cells: dict[str, dict[str, int]] = {}
    outcome = ("both", "baseline_only", "treatment_only", "neither")
    for row in baseline:
        other = by_key.get((row["revision"], int(row["trial"])))
        if other is None:
            continue
        for thread, got in row["defects"].items():
            mine, theirs = got["caught"], other["defects"][thread]["caught"]
            key = (
                "both"
                if mine and theirs
                else "baseline_only"
                if mine
                else ("treatment_only" if theirs else "neither")
            )
            for group in ("all", f"context:{contexts.get(thread, 'unknown')}"):
                cell = cells.setdefault(
                    group, dict.fromkeys((*outcome, "same_file_baseline", "same_file_treatment"), 0)
                )
                cell[key] += 1
                cell["same_file_baseline"] += int(got["same_file"])
                cell["same_file_treatment"] += int(other["defects"][thread]["same_file"])
    paired: dict[str, dict[str, Any]] = {}
    for group, cell in sorted(cells.items()):
        paired[group] = {
            **cell,
            "n": sum(cell[k] for k in outcome),
            "mcnemar_p": mcnemar_exact_p(cell["baseline_only"], cell["treatment_only"]),
        }
    return {"paired": paired}
