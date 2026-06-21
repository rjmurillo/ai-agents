#!/usr/bin/env python3
"""Compute the statistics in the comparison doc from one or more sweep reports:
per-config score distributions, paired within-file gaps with 95% CIs, token +
latency distributions, and cost (token $ standard/batch + human opportunity $).

Usage:
  python3 analyze.py out/flagship.json [out/lesser.json ...] [--hourly 184]
  python3 analyze.py out/flagship.json --pair opus-4-8/xhigh gpt-5.5/xhigh

Per-token rates (USD / 1M, standard tier) verified 2026-06-21 against GitHub
Copilot, OpenAI API, and Anthropic API pricing (all three agree; Copilot resells
at provider-direct rates). Batch API is 50% off. Edit RATES if prices move.
"""
import argparse
import json
import math
import statistics as st

# (input, output) USD per 1M tokens, standard tier. Matched by substring of label.
RATES = {
    "opus": (5.0, 25.0),
    "gpt-5.5-mini": (0.25, 2.00),   # Copilot "GPT-5 mini" tier
    "gpt-5.5": (5.0, 30.0),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4": (2.5, 15.0),
    "gpt-5.3-codex": (1.75, 14.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
}


def rate_for(label):
    for key in sorted(RATES, key=len, reverse=True):  # longest match first
        if key in label:
            return RATES[key]
    raise SystemExit(f"no rate for '{label}'; add it to RATES")


def load(paths):
    cells = {}
    for p in paths:
        for label, c in json.load(open(p, encoding="utf-8"))["cells"].items():
            cells.setdefault(label, {}).update(c)
    return cells


def ok(c):
    return isinstance(c, dict) and "scores" in c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--hourly", type=float, default=184.0, help="human opportunity cost $/hr")
    ap.add_argument("--pair", nargs=2, metavar=("A", "B"), action="append",
                    help="paired gap A minus B (repeatable)")
    args = ap.parse_args()
    cells = load(args.reports)
    psec = args.hourly / 3600.0
    Q = ["cohesion", "coupling", "encapsulation", "testability", "non_redundancy", "overall"]
    labels = list(cells)

    print("=== overall score: mean +/- sd ===")
    for lbl in labels:
        ov = [c["scores"]["overall"] for c in cells[lbl].values() if ok(c)]
        if ov:
            print(f"  {lbl:20} mean={st.mean(ov):.2f} sd={st.pstdev(ov):.2f} "
                  f"median={st.median(ov)} min={min(ov)} max={max(ov)} n={len(ov)}")

    print("\n=== per-quality mean ===")
    print(f"  {'config':20}" + "".join(f"{q[:5]:>7}" for q in Q))
    for lbl in labels:
        vals = [c for c in cells[lbl].values() if ok(c)]
        if vals:
            ms = [st.mean([c["scores"][q] for c in vals]) for q in Q]
            print(f"  {lbl:20}" + "".join(f"{m:>7.2f}" for m in ms))

    if args.pair:
        print("\n=== paired overall gaps (within-file) ===")
        for a, b in args.pair:
            files = set(cells.get(a, {})) & set(cells.get(b, {}))
            d = [cells[a][f]["scores"]["overall"] - cells[b][f]["scores"]["overall"]
                 for f in files if ok(cells[a][f]) and ok(cells[b][f])]
            n = len(d)
            if not n:
                print(f"  {a} minus {b}: no shared cells")
                continue
            m, sd = st.mean(d), st.pstdev(d)
            se = sd / math.sqrt(n)
            print(f"  {a} minus {b}: mean={m:+.2f} sd={sd:.2f} "
                  f"95%CI=[{m - 1.96 * se:+.2f},{m + 1.96 * se:+.2f}] "
                  f"(<: {sum(x < 0 for x in d)}, =: {sum(x == 0 for x in d)}, "
                  f">: {sum(x > 0 for x in d)}, n={n})")

    print(f"\n=== tokens, latency, cost (human=${args.hourly}/hr) ===")
    print(f"  {'config':20}{'out':>7}{'lat_s':>7}{'tok$std':>9}{'tok$bat':>9}"
          f"{'human$':>9}{'allin$':>9}{'h/tok':>7}")
    for lbl in labels:
        vals = [c for c in cells[lbl].values() if ok(c) and c.get("out_total") and c.get("in_clean")]
        if not vals:
            continue
        ri, ro = rate_for(lbl)
        tok = [c["in_clean"] / 1e6 * ri + c["out_total"] / 1e6 * ro for c in vals]
        hum = [c["ms"] / 1000 * psec for c in vals]
        out = [c["out_total"] for c in vals]
        lat = [c["ms"] / 1000 for c in vals]
        allin = [t + h for t, h in zip(tok, hum)]
        print(f"  {lbl:20}{st.mean(out):>7.0f}{st.mean(lat):>7.0f}{st.mean(tok):>9.4f}"
              f"{st.mean(tok) * 0.5:>9.4f}{st.mean(hum):>9.3f}{st.mean(allin):>9.3f}"
              f"{st.mean(hum) / st.mean(tok):>6.0f}x")


if __name__ == "__main__":
    main()
