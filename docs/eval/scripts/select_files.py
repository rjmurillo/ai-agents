#!/usr/bin/env python3
"""Regenerate eval_files24.json: 24 size-diverse product files from moq.analyzers
(Analyzers, CodeFixes, Common; excludes the PerfDiff tools and generated .g.cs).
Deterministic: sorts by byte size and samples evenly across the range, so the
sample spans 271 bytes to ~30 KB. Run from anywhere with MOQ_REPO set.
"""
import json
import os
import subprocess
from pathlib import Path

import evalkit

N = 24


def main():
    repo = evalkit.moq_repo()
    found = subprocess.run(
        ["bash", "-c",
         "find src/Analyzers src/CodeFixes src/Common -name '*.cs' -not -name '*.g.cs'"],
        cwd=repo, capture_output=True, text=True).stdout.split()
    sized = sorted((len(open(os.path.join(repo, f), encoding="utf-8").read()), f) for f in found)
    idx = sorted(set(round(i * (len(sized) - 1) / (N - 1)) for i in range(N)))
    i = 0
    while len(idx) < N and i < len(sized):
        if i not in idx:
            idx.append(i)
        i += 1
    sel = [sized[i][1] for i in sorted(idx)[:N]]
    out = Path(__file__).resolve().parent / "eval_files24.json"
    json.dump(sel, open(out, "w"), indent=0)
    print(f"wrote {len(sel)} files to {out} (bytes {sized[idx[0]][0]}..{sized[idx[-1]][0]})")


if __name__ == "__main__":
    main()
