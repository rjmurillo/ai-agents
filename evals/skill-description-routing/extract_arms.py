"""Extract before and after skill frontmatter for the description routing eval.

Usage: uv run python extract_arms.py <candidate-worktree> <out-dir> [before-ref]
"""

from __future__ import annotations

import collections
import json
import os
import re
import subprocess
import sys

import yaml


def frontmatter(text: str) -> str | None:
    m = re.match(r"^---\n(.*?)\n---\n", text, flags=re.S)
    return m.group(1) if m else None


def main() -> None:
    tree, out_dir = sys.argv[1], sys.argv[2]
    ref = sys.argv[3] if len(sys.argv) > 3 else "origin/main"
    root = f"{tree}/.claude/skills"
    names = sorted(n for n in os.listdir(root) if os.path.exists(f"{root}/{n}/SKILL.md"))
    arms: dict[str, dict[str, dict[str, object]]] = {"before": {}, "after": {}}
    missing = []
    for name in names:
        rel = os.path.relpath(os.path.realpath(f"{root}/{name}/SKILL.md"), tree)
        after = open(f"{tree}/{rel}").read()
        shown = subprocess.run(
            ["git", "-C", tree, "show", f"{ref}:{rel}"], capture_output=True, text=True
        )
        if shown.returncode != 0:
            missing.append(name)
            continue
        for arm, text in (("before", shown.stdout), ("after", after)):
            block = frontmatter(text)
            data = yaml.safe_load(block)
            arms[arm][name] = {
                "frontmatter": block,
                "description": " ".join(str(data.get("description", "")).split()),
                "other": {k: v for k, v in data.items() if k != "description"},
            }
    json.dump(arms, open(f"{out_dir}/arms.json", "w"), indent=1, default=str)
    before, after_arm = arms["before"], arms["after"]
    changed = [n for n in before if before[n]["description"] != after_arm[n]["description"]]
    odd = [n for n in before if before[n]["other"] != after_arm[n]["other"]]
    print("skills", len(names), "missing", missing, "changed", len(changed))
    print(
        "chars before",
        sum(len(str(v["description"])) for v in before.values()),
        "after",
        sum(len(str(v["description"])) for v in after_arm.values()),
    )
    print("non-description frontmatter diffs:", odd)
    json.dump(changed, open(f"{out_dir}/changed.json", "w"), indent=1)
    json.dump(
        {n: before[n]["description"] for n in before},
        open(f"{out_dir}/before-descriptions.json", "w"),
        indent=1,
    )
    verbatim = {}
    pattern = re.compile(r"[Uu]se (?:when|for|after|before)[^.]*?[`\"“]([^`\"”]{4,80})[`\"”]")
    for name, value in before.items():
        hit = pattern.search(str(value["description"]))
        if hit:
            verbatim[name] = hit.group(1)
    json.dump(verbatim, open(f"{out_dir}/verbatim.json", "w"), indent=1)
    print("verbatim triggers", len(verbatim), "of", len(before))
    flags = collections.Counter(
        tuple(
            sorted(
                (k, str(v))
                for k, v in value["other"].items()
                if k in ("disable-model-invocation", "user-invocable")
            )
        )
        for value in after_arm.values()
    )
    print(flags)


if __name__ == "__main__":
    main()
