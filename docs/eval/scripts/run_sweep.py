#!/usr/bin/env python3
"""Generalized CLI-transport sweep. Runs every (config x file) cell and captures
scores + output tokens + latency, with one retry on the flaky empty-result. This
single driver reproduces the codex/claude tables in the comparison doc: the
flagship N=24 run, the lesser-model run, the version sweep, and the effort sweeps
(vary the `effort` field).

A config is {"label","transport","model","effort"}; transport in {codex, claude}.

Usage:
  export MOQ_REPO=~/src/moq.analyzers
  python3 run_sweep.py --configs configs/flagship_xhigh.json --out out/flagship.json
  python3 run_sweep.py --configs configs/lesser_xhigh.json   --out out/lesser.json

Reproduces (config files shipped alongside):
  configs/flagship_xhigh.json  -> Statistical run (N=24): opus-4-8, gpt-5.5, gpt-5.4
  configs/lesser_xhigh.json    -> Lesser models: gpt-5.4-mini, sonnet-4-6, haiku-4-5
  configs/versions.json        -> Version sweep: opus 4.8/4.7/4.6, gpt-5.4
  configs/effort_codex.json    -> codex effort: gpt-5.5 medium/high/xhigh
  configs/effort_claude.json   -> Claude effort: opus-4-8 medium/high/xhigh/max
"""
import argparse
import json
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import evalkit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", required=True, help="JSON list of {label,transport,model,effort}")
    ap.add_argument("--out", required=True, help="output report path")
    ap.add_argument("--files", default=evalkit.FILES_DEFAULT, help="JSON list of repo-relative .cs paths")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()

    with open(args.configs, encoding="utf-8") as handle:
        configs = json.load(handle)
    files = evalkit.load_files(args.files)
    report = {"repo": "rjmurillo/moq.analyzers", "n_files": len(files), "cells": {}}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    tasks = [(c, rel) for c in configs for rel in files]

    def work(c, rel):
        rec = evalkit.run_cell(c["transport"], c["model"], c["effort"], rel, c["label"].replace("/", "_"))
        return c["label"], rel, rec

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for fut in [ex.submit(work, c, rel) for c, rel in tasks]:
            label, rel, rec = fut.result()
            with lock:
                report["cells"].setdefault(label, {})[rel] = rec
                with open(out_path, "w", encoding="utf-8") as handle:
                    json.dump(report, handle, indent=2)
            done += 1
            ov = rec.get("scores", {}).get("overall") if "scores" in rec else "ERR"
            print(f"[{done:2}/{len(tasks)}] {label:18} {rel.split('/')[-1][:32]:32} "
                  f"ov={ov} out={rec.get('out_total')} ({rec.get('ms', 0) / 1000:.0f}s)", flush=True)
    print("\nsaved " + args.out)


if __name__ == "__main__":
    main()
