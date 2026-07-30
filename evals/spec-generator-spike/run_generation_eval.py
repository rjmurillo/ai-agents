#!/usr/bin/env python3
"""Generation eval for issue #2001: does the spec-generator skill emit
schema-valid frontmatter where the agent drifted?

Directly measures the reported bug. For each adversarial feature description it
asks the before prompt (the removed agent) and the after prompt (the new skill)
to emit only the YAML frontmatter, then runs the real validator
(.claude/skills/spec-generator/scripts/validate_spec_frontmatter.py) on the
output. Reports valid-frontmatter counts per prompt.

Run from the worktree root:
    python3 evals/spec-generator-spike/run_generation_eval.py --runs 3
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "eval"))

from _anthropic_api import call_api, load_api_key  # noqa: E402

VALIDATOR = REPO / ".claude/skills/spec-generator/scripts/validate_spec_frontmatter.py"
MODEL = "claude-sonnet-4-20250514"

# Adversarial features: each tempts a documented drift (priority=medium,
# category=tooling, task status=ready, design missing status/priority).
FEATURES = [
    {"id": "REQ-001", "type": "requirement",
     "desc": "Users can reset their password via email. This is a medium-priority functional feature."},
    {"id": "REQ-002", "type": "requirement",
     "desc": "Add a build tooling script that lints config files. It is a tooling and infrastructure concern."},
    {"id": "TASK-001", "type": "task",
     "desc": "Implement the password-reset endpoint. It is ready to start, small, about one hour of work."},
    {"id": "TASK-002", "type": "task",
     "desc": "Refactor the auth module to remove duplication. Currently in progress, medium effort."},
    {"id": "DESIGN-001", "type": "design",
     "desc": "Design the session state machine that persists phase transitions. High priority, traces REQ-001."},
    {"id": "REQ-003", "type": "requirement",
     "desc": "The system shall encrypt all data at rest. Critical, non-functional."},
]

USER_TMPL = (
    "Generate ONLY the YAML frontmatter block for a {type} spec with id {id} for "
    "this feature:\n\n{desc}\n\nOutput just the frontmatter between --- fences and "
    "nothing else. Include every required field for a {type}."
)


def extract_frontmatter_block(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    if not text.startswith("---"):
        first = text.find("---")
        if first != -1:
            text = text[first:]
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text if text.startswith("---") else f"---\n{text}\n---\n"
    out = ["---"]
    for line in lines[1:]:
        out.append(line)
        if line.strip() == "---":
            break
    if out[-1].strip() != "---":
        out.append("---")
    return "\n".join(out) + "\n"


def validate(block: str) -> tuple[bool, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(block + "\n# body\n")
        path = fh.name
    proc = subprocess.run(
        ["python3", str(VALIDATOR), path], capture_output=True, text=True, check=False
    )
    Path(path).unlink(missing_ok=True)
    return proc.returncode == 0, proc.stdout.strip()


def run_prompt(api_key: str, prompt_text: str, feature: dict, runs: int) -> dict:
    valid = 0
    details = []
    for _ in range(runs):
        user = USER_TMPL.format(**feature)
        try:
            raw = call_api(api_key, [{"role": "user", "content": user}],
                           system=prompt_text, model=MODEL, max_tokens=800)
        except Exception as exc:  # noqa: BLE001 - record and continue
            details.append({"ok": False, "err": str(exc)[:120]})
            continue
        block = extract_frontmatter_block(raw)
        ok, report = validate(block)
        valid += 1 if ok else 0
        details.append({"ok": ok, "report": report[:200], "block": block[:300]})
        time.sleep(0.6)
    return {"valid": valid, "runs": runs, "details": details}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--output", default="evals/spec-generator-spike/generation-results.json")
    args = ap.parse_args()

    api_key = load_api_key()
    before = subprocess.run(
        ["git", "show", "origin/main:.claude/agents/spec-generator.md"],
        capture_output=True, text=True, check=True,
    ).stdout
    after = (REPO / ".claude/skills/spec-generator/SKILL.md").read_text(encoding="utf-8")

    results = {"model": MODEL, "runs_per_feature": args.runs, "features": []}
    b_valid = a_valid = total = 0
    for feat in FEATURES:
        b = run_prompt(api_key, before, feat, args.runs)
        a = run_prompt(api_key, after, feat, args.runs)
        b_valid += b["valid"]
        a_valid += a["valid"]
        total += args.runs
        results["features"].append({"id": feat["id"], "type": feat["type"], "before": b, "after": a})
        print(f"{feat['id']:11} agent(before)={b['valid']}/{args.runs}  skill(after)={a['valid']}/{args.runs}")

    results["summary"] = {
        "before_valid": b_valid, "after_valid": a_valid, "total": total,
        "before_rate": round(b_valid / total, 4), "after_rate": round(a_valid / total, 4),
        "delta": round((a_valid - b_valid) / total, 4),
    }
    Path(args.output).write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nAGENT  valid frontmatter: {b_valid}/{total} ({results['summary']['before_rate']:.0%})")
    print(f"SKILL  valid frontmatter: {a_valid}/{total} ({results['summary']['after_rate']:.0%})")
    print(f"delta: {results['summary']['delta']:+.0%}  -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
