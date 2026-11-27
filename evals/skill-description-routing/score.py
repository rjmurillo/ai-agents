"""Score routing runs against the pre-registered gate G1 to G4.

Usage: python3 score.py <dir-with-arms-and-queries> <results.jsonl> [<results.jsonl> ...]

Each results file holds one model. The last non-error row per (model, arm, id) wins.
"""

from __future__ import annotations

import collections
import json
import math
import sys
from typing import Any


def sign_p(wins_a: int, wins_b: int) -> float:
    """Two-tailed exact sign test on discordant pairs."""
    n = wins_a + wins_b
    if n == 0:
        return 1.0
    k = min(wins_a, wins_b)
    tail: float = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def load(paths: list[str]) -> dict[tuple[str, str, str], dict[str, Any]]:
    rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in paths:
        for line in open(path, encoding="utf-8"):
            row = json.loads(line)
            key = (row["model"], row["arm"], row["id"])
            if key in rows and rows[key]["outcome"] != "error" and row["outcome"] == "error":
                continue
            rows[key] = row
    return rows


def rates(pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    n = len(pairs)
    out: dict[str, Any] = {"n": n}
    if not n:
        return out
    counts = {
        arm: collections.Counter(p[idx]["outcome"] for p in pairs)
        for arm, idx in (("before", 0), ("after", 1))
    }
    for arm, tally in counts.items():
        out[arm] = {k: round(tally[k] / n, 4) for k in ("correct", "wrong", "none")}
    b_win = sum(1 for b, a in pairs if b["outcome"] == "correct" and a["outcome"] != "correct")
    a_win = sum(1 for b, a in pairs if a["outcome"] == "correct" and b["outcome"] != "correct")
    # Gate on outcome counts. Subtracting rounded rates puts a delta that sits
    # exactly on the 0.03 margin outside it: 0.97 - 1.0 < -0.03 in binary floats.
    more_correct = counts["after"]["correct"] - counts["before"]["correct"]
    more_wrong = counts["after"]["wrong"] - counts["before"]["wrong"]
    p = sign_p(b_win, a_win)
    out.update(
        {
            "d_correct": round(more_correct / n, 4),
            "d_wrong": round(more_wrong / n, 4),
            "before_wins": b_win,
            "after_wins": a_win,
            "sign_p": round(p, 4),
            "G1": 100 * more_correct >= -3 * n,
            "G2": 100 * more_wrong <= 3 * n,
            "G3": not (b_win > a_win and p < 0.05),
        }
    )
    return out


def main() -> int:
    base = sys.argv[1]
    rows = load(sys.argv[2:])
    queries = {q["id"]: q for q in json.load(open(f"{base}/queries.json", encoding="utf-8"))}
    changed = set(json.load(open(f"{base}/changed.json", encoding="utf-8")))
    models = sorted({k[0] for k in rows})
    report: dict[str, Any] = {"models": {}}
    per_skill: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    for model in models:
        pairs, excluded = [], []
        for qid in queries:
            b, a = rows.get((model, "before", qid)), rows.get((model, "after", qid))
            if b is None or a is None:
                excluded.append((qid, "missing"))
            elif "error" in (b["outcome"], a["outcome"]):
                excluded.append((qid, "error"))
            else:
                pairs.append((b, a))
        listed = collections.Counter(r.get("listed") for k, r in rows.items() if k[0] == model)
        block: dict[str, object] = {
            "all": rates(pairs),
            "excluded": len(excluded),
            "excluded_kinds": dict(collections.Counter(why for _, why in excluded)),
            "listed": {str(k): v for k, v in listed.items()},
            "changed_skills_only": rates([p for p in pairs if p[0]["skill"] in changed]),
            "unchanged_skills_only": rates([p for p in pairs if p[0]["skill"] not in changed]),
            "no_name_bearing_verbatim": rates(
                [
                    p
                    for p in pairs
                    if not (
                        p[0]["kind"] == "verbatim"
                        and p[0]["skill"].lower() in queries[p[0]["id"]]["query"].lower()
                    )
                ]
            ),
        }
        for kind in ("verbatim", "close", "paraphrase"):
            block[kind] = rates([p for p in pairs if p[0]["kind"] == kind])
        report["models"][model] = block
        for b, a in pairs:
            tally = per_skill[b["skill"]]
            tally[0] += b["outcome"] == "correct"
            tally[1] += a["outcome"] == "correct"
            tally[2] += 1
    g4_fail = sorted(s for s, (b, a, _n) in per_skill.items() if s in changed and b - a >= 2)
    unscored = sorted(s for s in changed if per_skill.get(s, [0, 0, 0])[2] == 0)
    report["G4_failing_skills"] = {s: per_skill[s] for s in g4_fail}
    report["changed_skills_unscored"] = unscored
    report["skills_after_better_by_2"] = sorted(
        s for s, (b, a, _n) in per_skill.items() if a - b >= 2
    )
    report["verdict"] = {
        m: all(report["models"][m]["all"].get(g, False) for g in ("G1", "G2", "G3")) for m in models
    }
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
