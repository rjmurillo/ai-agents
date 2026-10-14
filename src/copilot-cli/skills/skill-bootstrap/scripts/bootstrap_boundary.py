#!/usr/bin/env python3
"""Check the write boundary of a skill-bootstrap run.

A bootstrap run may write only inside one skills root (`.claude/skills` or
`.github/skills`) and only into the skill directories it named. This script
makes that boundary checkable on Linux, macOS, and Windows.

Subcommands:

    plan      Validate the output root and the proposed skill names. Report
              each name as new, an authorized update, or a conflict.
    snapshot  Record HEAD, the branch, and a content hash of every dirty or
              untracked path. Write the record outside the repository.
    verify    Compare the repository with a snapshot. Report each changed
              path outside the authorized skill directories, and any change
              to HEAD or the branch.

Exit codes:

    0  The plan has no conflict, or verify found no violation.
    1  The plan has a conflict or an invalid name, or verify found a
       violation.
    2  Configuration error: bad arguments, root outside the allowed set,
       snapshot path inside the repository, unreadable snapshot.
    3  External error: git is missing or a git command failed.

Limits: verify sees only paths that git reports. Changes to ignored files
are not detected. Stdlib only, so the script runs from any plugin root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

ALLOWED_ROOTS = (".claude/skills", ".github/skills")
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")
MAX_NAME = 64
SNAPSHOT_SCHEMA = "skill-bootstrap-snapshot/1"


class ConfigError(Exception):
    """Bad input: exit 2."""


class GitError(Exception):
    """git is missing or failed: exit 3."""


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def repo_root(path: Path) -> Path:
    """Return the work-tree root that contains `path`."""
    if not path.is_dir():
        raise ConfigError(f"repository path is not a directory: {path}")
    return Path(_git(path, "rev-parse", "--show-toplevel").strip()).resolve()


def check_root(root: Path, output_root: str) -> Path:
    """Return the absolute output root, or raise when it is not allowed."""
    rel = PurePosixPath(output_root.replace("\\", "/").strip("/"))
    if str(rel) not in ALLOWED_ROOTS:
        raise ConfigError(f"output root {output_root!r} is not one of {', '.join(ALLOWED_ROOTS)}")
    target = (root / Path(*rel.parts)).resolve()
    if root != target and root not in target.parents:
        raise ConfigError(f"output root {output_root!r} resolves outside the repository")
    return target


def name_defects(name: str, project: str | None) -> list[str]:
    """Return the reasons a proposed skill name is invalid."""
    defects = []
    if len(name) > MAX_NAME:
        defects.append(f"longer than {MAX_NAME} characters")
    if not NAME_RE.match(name) or "--" in name:
        defects.append("not lowercase hyphen-case")
    if project and not name.startswith(f"{project}-"):
        defects.append(f"does not use the <project>-<lens> form for project {project!r}")
    return defects


def plan(args: argparse.Namespace) -> tuple[int, dict]:
    root = repo_root(Path(args.repo))
    skills_dir = check_root(root, args.output_root)
    updates = set(args.update or [])
    entries = []
    blocking = False
    for name in args.name or []:
        defects = name_defects(name, args.project)
        exists = (skills_dir / name).exists()
        if defects:
            status = "invalid"
        elif exists and name in updates:
            status = "update"
        elif exists:
            status = "conflict"
        else:
            status = "new"
        blocking = blocking or status in ("invalid", "conflict")
        entries.append({"name": name, "status": status, "defects": defects})
    for name in sorted(updates - set(args.name or [])):
        entries.append({"name": name, "status": "invalid", "defects": ["--update without --name"]})
        blocking = True
    existing = (
        sorted(p.name for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else []
    )
    return (1 if blocking else 0), {
        "repo": root.as_posix(),
        "output_root": args.output_root,
        "existing_skills": existing,
        "proposed": entries,
    }


def _status_paths(root: Path) -> list[str]:
    """Return every path git reports as changed or untracked, posix form."""
    raw = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    fields = raw.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(fields):
        entry = fields[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":
            # Rename and copy entries carry the source path in the next field.
            paths.append(fields[i])
            i += 1
    return sorted(set(paths))


def _hash(path: Path) -> str:
    if path.is_symlink():
        return "symlink:" + str(path.readlink())
    if not path.exists():
        return "absent"
    if path.is_dir():
        return "dir"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _head(root: Path) -> str:
    """Return the HEAD commit, or an empty string in a repository with no commit."""
    try:
        return _git(root, "rev-parse", "--verify", "--quiet", "HEAD").strip()
    except GitError:
        return ""


def _state(root: Path) -> dict:
    head = _head(root)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() if head else ""
    return {
        "head": head,
        "branch": branch,
        "paths": {p: _hash(root / Path(*PurePosixPath(p).parts)) for p in _status_paths(root)},
    }


def snapshot(args: argparse.Namespace) -> tuple[int, dict]:
    root = repo_root(Path(args.repo))
    out = Path(args.out).resolve()
    if out == root or root in out.parents:
        raise ConfigError(
            "snapshot file must live outside the repository, or it changes the state it records"
        )
    record = {"schema": SNAPSHOT_SCHEMA, "repo": root.as_posix(), **_state(root)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0, {
        "snapshot": out.as_posix(),
        "head": record["head"],
        "dirty_paths": len(record["paths"]),
    }


def _load_snapshot(path: str, root: Path) -> dict:
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read snapshot {path}: {exc}") from exc
    if not isinstance(record, dict) or record.get("schema") != SNAPSHOT_SCHEMA:
        raise ConfigError(f"snapshot {path} is not a {SNAPSHOT_SCHEMA} record")
    if record.get("repo") != root.as_posix():
        raise ConfigError(f"snapshot {path} records {record.get('repo')}, not {root.as_posix()}")
    return record


def verify(args: argparse.Namespace) -> tuple[int, dict]:
    root = repo_root(Path(args.repo))
    check_root(root, args.output_root)
    before = _load_snapshot(args.snapshot, root)
    after = _state(root)
    prefix = PurePosixPath(args.output_root.replace("\\", "/").strip("/"))
    allowed = {prefix / name for name in (args.name or [])}
    violations = []
    for key in ("head", "branch"):
        if before[key] != after[key]:
            violations.append(
                {"kind": f"{key}-changed", "before": before[key], "after": after[key]}
            )
    changed = []
    for path in sorted(set(before["paths"]) | set(after["paths"])):
        if before["paths"].get(path) == after["paths"].get(path):
            continue
        changed.append(path)
        posix = PurePosixPath(path)
        if not any(posix == skill or skill in posix.parents for skill in allowed):
            violations.append({"kind": "outside-boundary", "path": path})
    return (1 if violations else 0), {"changed": changed, "violations": violations}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap_boundary", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan", help="validate the output root and proposed names")
    p_plan.add_argument("--repo", default=".")
    p_plan.add_argument("--output-root", required=True, help="one of: " + ", ".join(ALLOWED_ROOTS))
    p_plan.add_argument("--name", action="append", help="proposed skill name (repeatable)")
    p_plan.add_argument(
        "--update", action="append", help="existing skill the run may modify (repeatable)"
    )
    p_plan.add_argument("--project", help="require the <project>-<lens> prefix")

    p_snap = sub.add_parser("snapshot", help="record repository state before writing")
    p_snap.add_argument("--repo", default=".")
    p_snap.add_argument("--out", required=True, help="snapshot file outside the repository")

    p_verify = sub.add_parser("verify", help="compare repository state with a snapshot")
    p_verify.add_argument("--repo", default=".")
    p_verify.add_argument("--snapshot", required=True)
    p_verify.add_argument("--output-root", required=True)
    p_verify.add_argument("--name", action="append", help="authorized skill directory (repeatable)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {"plan": plan, "snapshot": snapshot, "verify": verify}
    try:
        code, payload = handlers[args.command](args)
    except ConfigError as exc:
        print(json.dumps({"error": "config", "message": str(exc)}))
        return 2
    except GitError as exc:
        print(json.dumps({"error": "git", "message": str(exc)}))
        return 3
    print(json.dumps(payload, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
