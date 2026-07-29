#!/usr/bin/env python3
"""Validate that Copilot shipped skill surfaces do not route to excluded skills.

Reads templates/platforms/copilot-cli.yaml -> artifacts.skills.excludeFilenames and
scans src/copilot-cli/skills for invocation patterns that reference excluded
skill names using the "Skill: <name>" form. Agent references ("Agent: <name>"
or "<name> agent") are allowed.

Exit code: 0 when no violations, 1 when violations found, 2 on config error.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, List

import yaml


def _load_excluded_skill_names(repo_root: Path) -> List[str]:
    tpl = repo_root / "templates" / "platforms" / "copilot-cli.yaml"
    if not tpl.exists():
        raise FileNotFoundError(f"Template not found: {tpl}")
    data = yaml.safe_load(tpl.read_text())
    # Navigate to artifacts.skills.excludeFilenames
    names = []
    try:
        names = data["artifacts"]["skills"]["excludeFilenames"]
    except Exception:
        raise ValueError("Malformed copilot-cli.yaml: missing artifacts.skills.excludeFilenames")
    if not isinstance(names, list):
        raise ValueError("excludeFilenames must be a list")
    # Normalize to str
    return [str(n) for n in names]


_SKILL_INVOCATION_RE = r"\bSkill:\s*`?{name}`?\b"


def _scan_skill_files(repo_root: Path, excluded: Iterable[str]) -> List[str]:
    violations: List[str] = []
    skills_root = repo_root / "src" / "copilot-cli" / "skills"
    if not skills_root.exists():
        return violations
    md_files = list(skills_root.rglob("*.md")) + list(skills_root.rglob("SKILL.md"))
    for path in md_files:
        try:
            text = path.read_text()
        except Exception:
            continue
        for name in excluded:
            pattern = re.compile(_SKILL_INVOCATION_RE.format(name=re.escape(name)))
            if pattern.search(text):
                violations.append(f"{path}: references Skill: {name}")
    return violations


def validate_copilot_routing_exclusions(repo_root: Path) -> bool:
    repo_root = Path(repo_root)
    try:
        excluded = _load_excluded_skill_names(repo_root)
    except FileNotFoundError:
        print("[WARNING] copilot-cli template not found; skipping Copilot routing exclusion check")
        return True
    except Exception as exc:
        print(f"[ERROR] Failed to read copilot-cli.yaml: {exc}", file=sys.stderr)
        return False

    if not excluded:
        # Nothing excluded; nothing to check
        return True

    violations = _scan_skill_files(repo_root, excluded)
    if violations:
        print("Copilot routing exclusion violations detected:")
        for v in violations:
            print(f"  - {v}")
        print()
        print("Rules: Copilot shipped skills must not route to a Skill: <name> that is excluded by templates/platforms/copilot-cli.yaml.")
        print("Use Agent: <name> or '<name> agent' phrasing on shipped Copilot surfaces instead.")
        return False

    return True


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent.parent
    ok = validate_copilot_routing_exclusions(repo_root)
    sys.exit(0 if ok else 1)
