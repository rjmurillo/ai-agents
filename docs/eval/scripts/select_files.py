#!/usr/bin/env python3
"""Regenerate eval_files24.json: 24 size-diverse product files from moq.analyzers
(Analyzers, CodeFixes, Common; excludes the PerfDiff tools and generated .g.cs).
Deterministic: sorts by byte size and samples evenly across the range, so the
sample spans 271 bytes to ~30 KB. Run from anywhere with MOQ_REPO set.
"""
import json
from pathlib import Path

import evalkit

N = 24


def main():
    repo = evalkit.moq_repo()
    repo_path = Path(repo)
    roots = [repo_path / "src" / name for name in ("Analyzers", "CodeFixes", "Common")]
    found = [
        path.relative_to(repo_path).as_posix()
        for root in roots
        for path in root.rglob("*.cs")
        if not path.name.endswith(".g.cs")
    ]
    sized = sorted(((repo_path / f).stat().st_size, f) for f in found)
    idx = sorted(set(round(i * (len(sized) - 1) / (N - 1)) for i in range(N)))
    i = 0
    while len(idx) < N and i < len(sized):
        if i not in idx:
            idx.append(i)
        i += 1
    selected_indices = sorted(idx)[:N]
    sel = [sized[i][1] for i in selected_indices]
    out = Path(__file__).resolve().parent / "eval_files24.json"
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(sel, handle, indent=0)
    print(
        f"wrote {len(sel)} files to {out} "
        f"(bytes {sized[selected_indices[0]][0]}..{sized[selected_indices[-1]][0]})"
    )


if __name__ == "__main__":
    main()
