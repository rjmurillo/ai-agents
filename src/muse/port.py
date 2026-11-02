#!/usr/bin/env python3
"""Regenerate the Muse port of project-toolkit from the Hermes packs.

Source of truth for the portable form is src/hermes (itself adapted from
src/claude). The port copies both packs unchanged except SKILL.md
frontmatter, which is reduced to the two fields Muse custom skills use:
name and description. Plugin manifests are not copied; Muse has no
plugin manifest surface. Run from the repo root:

    python3 src/muse/port.py
"""
import shutil
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src" / "hermes"
DST = REPO / "src" / "muse"
PACKS = ["project-toolkit-knowledge", "project-toolkit-delivery"]


def convert_skill_md(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"{path}: missing frontmatter")
    _, front, body = text.split("---\n", 2)
    meta = yaml.safe_load(front)
    kept = {"name": meta["name"], "description": meta["description"]}
    new_front = yaml.safe_dump(kept, sort_keys=False, width=10000)
    path.write_text(f"---\n{new_front}---\n{body}", encoding="utf-8")


def main() -> int:
    count = 0
    for pack in PACKS:
        src_pack = SRC / pack
        dst_pack = DST / pack
        if dst_pack.exists():
            shutil.rmtree(dst_pack)
        shutil.copytree(src_pack, dst_pack, ignore=shutil.ignore_patterns("plugin.json"))
        for skill_md in sorted(dst_pack.glob("skills/*/SKILL.md")):
            convert_skill_md(skill_md)
            count += 1
    print(f"ported {count} skills")
    return 0


if __name__ == "__main__":
    sys.exit(main())
