#!/usr/bin/env python3
"""Count the failure-archaeology corpus: retros, INDEX coverage, failure modes, memories.

Read-only. Prints one JSON object. Exit 0 ok, 1 retro_index_missing is non-empty,
2 configuration or bad arguments, 3 git missing or failed (only with --shas).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

RETRO_DIR = ".project-toolkit/retrospective"
FM_FILE = ".agents/governance/FAILURE-MODES.md"
MEMORY_DIR = ".serena/memories"
ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|")


def parse_failure_modes(text: str) -> list[dict[str, Any]]:
    """Return {n, name} rows from the '## Index' table, else from '## N. Name' headings."""
    modes: list[dict[str, Any]] = []
    in_index = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_index = line.strip().lower() == "## index"
            continue
        if in_index:
            m = ROW.match(line)
            if m:
                modes.append({"n": int(m.group(1)), "name": m.group(2)})
    if modes:
        return modes
    for m in re.finditer(r"^## (\d+)\.\s+(.+?)\s*$", text, re.MULTILINE):
        modes.append({"n": int(m.group(1)), "name": m.group(2)})
    return modes


def retro_coverage(repo: Path) -> tuple[int, int, list[str]]:
    d = repo / RETRO_DIR
    files = sorted(p.name for p in d.glob("*.md") if p.name != "INDEX.md")
    idx = d / "INDEX.md"
    index_text = idx.read_text(encoding="utf-8", errors="replace") if idx.is_file() else ""
    missing = [f"{RETRO_DIR}/{n}" for n in files if n not in index_text]
    return len(files), len(files) - len(missing), missing


def resolve_shas(repo: Path, shas: list[str]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for sha in shas:
        try:
            r = subprocess.run(
                ["git", "-C", str(repo), "cat-file", "-t", "--end-of-options", sha],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError as exc:
            raise RuntimeError(f"git unavailable: {exc}") from exc
        if r.returncode not in (0, 128):
            raise RuntimeError(f"git cat-file failed ({r.returncode}): {r.stderr.strip()}")
        out[sha] = r.returncode == 0
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Count retros, INDEX.md coverage, failure modes, and memory files.",
    )
    p.add_argument("--repo", default=".", help="repository root (default: .)")
    p.add_argument(
        "--shas",
        nargs="+",
        metavar="SHA",
        help="also report whether each short SHA resolves locally (git cat-file -t)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo)
    if not (repo / RETRO_DIR).is_dir() or not (repo / FM_FILE).is_file():
        print(json.dumps({"error": f"missing {RETRO_DIR} or {FM_FILE} under {repo}"}))
        return 2
    total, covered, missing = retro_coverage(repo)
    modes = parse_failure_modes((repo / FM_FILE).read_text(encoding="utf-8", errors="replace"))
    mem_dir = repo / MEMORY_DIR
    memories = len(list(mem_dir.glob("*.md"))) if mem_dir.is_dir() else 0
    result: dict[str, Any] = {
        "retro_files": total,
        "retro_index_covered": covered,
        "retro_index_missing": missing,
        "failure_modes": modes,
        "failure_mode_count": len(modes),
        "memory_files": memories,
        "examined": total + len(modes) + memories,
    }
    if args.shas:
        bad = [s for s in args.shas if s.startswith("-")]
        if bad:
            print(
                json.dumps({"error": f"sha must not start with '-': {bad!r}", "examined": 0}),
                file=sys.stderr,
            )
            return 2
        try:
            result["shas"] = resolve_shas(repo, args.shas)
        except RuntimeError as exc:
            print(json.dumps({"error": str(exc)}))
            return 3
    print(json.dumps(result, indent=2))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
