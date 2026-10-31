#!/usr/bin/env python3
"""Hook inventory instrument for the ai-agents-portability-campaign skill.

Subcommands (read-only, standard library only):

  counts       events and registrations per hook manifest.
  phase-tests  every pytest path the skill's SKILL.md names, and whether it exists.
  qualifiers   every tracked file under src/ and .claude/skills/autoplan that names
               the skill, and whether the same line or paragraph carries the
               "ai-agents repository" qualifier.

Exit codes: 0 ok, 1 findings, 2 configuration or bad arguments, 3 external failure.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKILL_NAME = "ai-agents-portability-campaign"
MANIFESTS = (
    ".claude/settings.json",
    ".claude/hooks/hooks.json",
    "src/copilot-cli/hooks/hooks.json",
)
DEFAULT_SKILL_MD = f".claude/skills/{SKILL_NAME}/SKILL.md"
QUALIFIER_ROOTS = ("src/", ".claude/skills/autoplan")
QUALIFIER_RE = re.compile(r"ai-agents repo(?:sitory)?\b", re.IGNORECASE)
TEST_PATH_RE = re.compile(r"tests/[A-Za-z0-9_./-]+\.py")


class ConfigError(Exception):
    """Bad input: unreadable or malformed file."""


def count_manifest(repo: Path, rel: str) -> dict:
    path = repo / rel
    if not path.is_file():
        return {"path": rel, "exists": False, "events": 0, "registrations": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"{rel}: {exc}") from exc
    hooks = data.get("hooks", {}) if isinstance(data, dict) else {}
    if not isinstance(hooks, dict):
        raise ConfigError(f"{rel}: 'hooks' is not an object")
    events = 0
    registrations = 0
    for groups in hooks.values():
        if not isinstance(groups, list) or not groups:
            continue
        events += 1
        for group in groups:
            inner = group.get("hooks") if isinstance(group, dict) else None
            registrations += len(inner) if isinstance(inner, list) else 1
    return {"path": rel, "exists": True, "events": events, "registrations": registrations}


def cmd_counts(repo: Path, _args: argparse.Namespace) -> tuple[dict, int]:
    files = [count_manifest(repo, rel) for rel in MANIFESTS]
    return {"files": files, "examined": len(files)}, 0


def cmd_phase_tests(repo: Path, args: argparse.Namespace) -> tuple[dict, int]:
    skill_md = repo / args.skill_md
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"{args.skill_md}: {exc}") from exc
    paths = sorted(set(TEST_PATH_RE.findall(text)))
    rows = [{"path": p, "exists": (repo / p).is_file()} for p in paths]
    missing = [r["path"] for r in rows if not r["exists"]]
    out = {"skill_md": args.skill_md, "tests": rows, "missing": missing, "examined": len(rows)}
    return out, 1 if missing else 0


def tracked_files(repo: Path) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z", "--", *QUALIFIER_ROOTS],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise OSError(f"git ls-files failed: {exc}") from exc
    return [p for p in proc.stdout.decode("utf-8", "replace").split("\0") if p]


def paragraphs(lines: list[str]) -> list[tuple[int, int]]:
    """Return (start, end) index ranges of blank-line-separated paragraphs."""
    spans: list[tuple[int, int]] = []
    start = None
    for i, line in enumerate(lines):
        if line.strip():
            if start is None:
                start = i
        elif start is not None:
            spans.append((start, i))
            start = None
    if start is not None:
        spans.append((start, len(lines)))
    return spans


def scan_file(repo: Path, rel: str) -> list[dict]:
    path = repo / rel
    if path.is_symlink() or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    if not any(SKILL_NAME in line for line in lines):
        return []
    spans = paragraphs(lines)
    rows = []
    for i, line in enumerate(lines):
        if SKILL_NAME not in line:
            continue
        span = next(((a, b) for a, b in spans if a <= i < b), (i, i + 1))
        block = "\n".join(lines[span[0] : span[1]])
        rows.append(
            {
                "path": rel,
                "line": i + 1,
                "qualified": bool(QUALIFIER_RE.search(line) or QUALIFIER_RE.search(block)),
            }
        )
    return rows


def cmd_qualifiers(repo: Path, _args: argparse.Namespace) -> tuple[dict, int]:
    rows: list[dict] = []
    files = tracked_files(repo)
    for rel in files:
        rows.extend(scan_file(repo, rel))
    unqualified = [r for r in rows if not r["qualified"]]
    out = {
        "references": rows,
        "unqualified": unqualified,
        "files_scanned": len(files),
        "examined": len(rows),
    }
    return out, 1 if unqualified else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".", help="repository root (default: .)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("counts", help="events and registrations per hook manifest")
    pt = sub.add_parser("phase-tests", help="check pytest paths named in SKILL.md exist")
    pt.add_argument("--skill-md", default=DEFAULT_SKILL_MD, help="SKILL.md path under --repo")
    sub.add_parser("qualifiers", help="check the 'ai-agents repository' qualifier")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"error: --repo {args.repo} is not a directory", file=sys.stderr)
        return 2
    handlers = {"counts": cmd_counts, "phase-tests": cmd_phase_tests, "qualifiers": cmd_qualifiers}
    try:
        out, code = handlers[args.command](repo, args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(out, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
