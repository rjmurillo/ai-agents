#!/usr/bin/env python3
"""Test layout probes for the ai-agents-validation-and-qa skill.

  test_layout.py --repo . pester [--skill-md PATH]
  test_layout.py --repo . skill-tests NAME [--no-pytest]

pester: count *.Tests.ps1 files (filesystem walk). Exit 1 when the skill prose
still carries the Pester stale-doc warning, the count is 0, and the governance
doc named in the warning no longer mentions Pester (the warning is dead prose).

skill-tests: list the test files pytest collects by default under
tests/skills/NAME/. Default mode runs `uv run pytest --collect-only -q`.
--no-pytest walks test_*.py and *_test.py instead. Exit 1 when none are found.

Read-only. Prints JSON with an `examined` count.
Exit codes: 0 ok, 1 findings, 2 bad arguments or missing config, 3 external
failure (uv or pytest missing, or collection errored).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SKILL = "ai-agents-validation-and-qa"
DOC = ".agents/governance/test-location-standards.md"
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".uv-cache"}
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _walk(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            entries = list(cur.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_dir() and not e.is_symlink():
                if e.name not in SKIP_DIRS:
                    stack.append(e)
            elif any(e.match(p) for p in patterns):
                found.append(e)
    return sorted(found)


def cmd_pester(repo: Path, skill_md: Path) -> tuple[int, dict[str, Any]]:
    if not skill_md.is_file():
        return 2, {"error": f"skill file not found: {skill_md}"}
    files = _walk(repo, ("*.Tests.ps1",))
    prose = skill_md.read_text(encoding="utf-8")
    prose_stays = bool(re.search(r"Tests\.ps1", prose))
    doc = repo / DOC
    doc_pester = doc.is_file() and bool(
        re.search(r"pester|\.Tests\.ps1", doc.read_text(encoding="utf-8"), re.I)
    )
    dead = prose_stays and not files and not doc_pester
    return (1 if dead else 0), {
        "pester_test_files": len(files),
        "prose_mentions_tests_ps1": prose_stays,
        "governance_doc_mentions_pester": doc_pester,
        "warning_is_dead_prose": dead,
        "examined": len(files) + 2,
    }


def _collect_pytest(repo: Path, name: str) -> tuple[int, list[str], str]:
    target = f"tests/skills/{name}"
    try:
        proc = subprocess.run(
            ["uv", "run", "pytest", target, "--collect-only", "-q", "-o", "addopts="],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return 3, [], f"failed to start uv: {exc}"
    if proc.returncode not in (0, 5):
        return 3, [], f"pytest collection exited {proc.returncode}"
    files = sorted({ln.split("::", 1)[0] for ln in proc.stdout.splitlines() if "::" in ln})
    return 0, files, ""


def cmd_skill_tests(repo: Path, name: str, no_pytest: bool) -> tuple[int, dict[str, Any]]:
    if not NAME_RE.match(name):
        return 2, {"error": f"invalid skill name: {name}"}
    base = repo / "tests" / "skills" / name
    if no_pytest:
        files = (
            [str(p.relative_to(repo)) for p in _walk(base, ("test_*.py", "*_test.py"))]
            if base.is_dir()
            else []
        )
        mode = "filesystem"
    elif not base.is_dir():
        files, mode = [], "pytest"
    else:
        rc, files, err = _collect_pytest(repo, name)
        if rc:
            return rc, {"error": err, "mode": "pytest"}
        mode = "pytest"
    return (0 if files else 1), {
        "skill": name,
        "mode": mode,
        "test_files": files,
        "dir_exists": base.is_dir(),
        "examined": len(files),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Probe the ai-agents test layout.")
    p.add_argument("--repo", default=".", help="repository root (default: .)")
    sub = p.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("pester", help="count *.Tests.ps1 files and check the stale-doc prose")
    pe.add_argument("--skill-md", default=None, help="prose file to check")
    st = sub.add_parser("skill-tests", help="list test files collected for a skill")
    st.add_argument("name")
    st.add_argument("--no-pytest", action="store_true", help="walk the filesystem")
    a = p.parse_args(argv)
    repo = Path(a.repo).resolve()
    if a.cmd == "pester":
        md = Path(a.skill_md) if a.skill_md else repo / ".claude/skills" / SKILL / "SKILL.md"
        rc, out = cmd_pester(repo, md)
    else:
        rc, out = cmd_skill_tests(repo, a.name, a.no_pytest)
    print(json.dumps(out, indent=2))
    return rc


if __name__ == "__main__":
    sys.exit(main())
