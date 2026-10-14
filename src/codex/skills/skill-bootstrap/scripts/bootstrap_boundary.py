#!/usr/bin/env python3
"""Check the write boundary of a skill-bootstrap run.

A bootstrap run may write only inside one skills root of the consumer
repository (`.claude/skills` or `.github/skills`), and only into the skill
directories it named. Paths the user authorized beyond that root, such as a
canonical skill template, are passed with `--also-allow`. This script makes
the boundary checkable on Linux, macOS, and Windows.

Subcommands:

    plan      Validate the output root and the proposed skill names. Report
              each name as new, an authorized update, invalid, or a conflict.
    snapshot  Record HEAD, the branch, the existing skill directories, and a
              content hash of every dirty or untracked path. Write the record
              outside the repository.
    verify    Compare the repository with a snapshot. Report each changed
              path outside the authorized skill directories, each change to a
              pre-existing skill not passed with `--update`, and any change to
              HEAD or the branch.

Exit codes:

    0  The plan has no conflict, or verify found no violation.
    1  The plan has a conflict or an invalid name, or verify found a
       violation.
    2  Configuration error: bad arguments, an output root outside the allowed
       set or ignored by git, a snapshot inside the repository, or an
       unreadable snapshot.
    3  External error: git is missing, a git command failed, or a file could
       not be read.

Limits: verify compares the working tree, HEAD, the branch name, the index
flags that hide changes (assume-unchanged, skip-worktree), and
`info/exclude`. It does not see other ref changes (tags, other branches,
config, push), other writes inside `.git/`, or gitignored paths, so an
ignored output root, skill directory, or `--also-allow` path is refused. It
catches accidental writes by a cooperating run; it is not a sandbox, and a
snapshot taken after the writes proves nothing, so snapshot refuses to
overwrite an existing file. Empty directories are invisible to git and to
verify. A symlinked output root or skill directory fails with exit 3. Stdlib only, so the script runs from any plugin root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

# Consumer-workspace locations: the skills directory of the repository being
# bootstrapped, not a path into this plugin's own tree.
ALLOWED_ROOTS = (".claude/skills", ".github/skills")
NAME_RE = re.compile(r"^[a-z](?:[a-z0-9-]*[a-z0-9])?$")
MAX_NAME = 64
SNAPSHOT_SCHEMA = "skill-bootstrap-snapshot/3"
IGNORE_PROBE = "skill-bootstrap-probe/SKILL.md"
IGNORE_CHILD = "skill-bootstrap-probe.md"

Payload = dict[str, Any]


class ConfigError(Exception):
    """Bad input: exit 2."""


class GitError(Exception):
    """git is missing or failed: exit 3."""


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc


def _git(repo: Path, *args: str) -> str:
    proc = _run_git(repo, *args)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def repo_root(path: Path) -> Path:
    """Return the work-tree root that contains `path`."""
    if not path.is_dir():
        raise ConfigError(f"repository path is not a directory: {path}")
    return Path(_git(path, "rev-parse", "--show-toplevel").strip()).resolve()


def _posix(value: str) -> PurePosixPath:
    return PurePosixPath(value.replace("\\", "/").strip("/"))


def check_root(root: Path, output_root: str) -> PurePosixPath:
    """Return the output root as a repo-relative path, or raise when not allowed."""
    rel = _posix(output_root)
    if str(rel) not in ALLOWED_ROOTS:
        raise ConfigError(f"output root {output_root!r} is not one of {', '.join(ALLOWED_ROOTS)}")
    target = (root / Path(*rel.parts)).resolve()
    if root != target and root not in target.parents:
        raise ConfigError(f"output root {output_root!r} resolves outside the repository")
    proc = _run_git(root, "check-ignore", "-q", f"{rel}/{IGNORE_PROBE}")
    if proc.returncode == 0:
        raise ConfigError(
            f"output root {output_root!r} is ignored by git, so verify cannot see writes there"
        )
    if proc.returncode != 1:
        raise GitError(f"git check-ignore failed: {proc.stderr.strip()}")
    return rel


def require_visible(root: Path, paths: list[str]) -> None:
    """Raise when git ignores any path, because verify cannot see writes there."""
    if not paths:
        return
    probes = [probe for path in paths for probe in (path, f"{path}/{IGNORE_CHILD}")]
    proc = _run_git(root, "check-ignore", "--no-index", "--", *probes)
    if proc.returncode == 0:
        hidden = ", ".join(proc.stdout.split())
        raise ConfigError(f"git ignores {hidden}, so verify cannot see writes there")
    if proc.returncode != 1:
        raise GitError(f"git check-ignore failed: {proc.stderr.strip()}")


def name_defects(name: str, project: str | None = None) -> list[str]:
    """Return the reasons a skill name is invalid."""
    defects = []
    if len(name) > MAX_NAME:
        defects.append(f"longer than {MAX_NAME} characters")
    if not NAME_RE.match(name) or "--" in name:
        defects.append("not lowercase hyphen-case")
    if project and not name.startswith(f"{project}-"):
        defects.append(f"does not use the <project>-<lens> form for project {project!r}")
    return defects


def _skill_dirs(root: Path, rel: str) -> list[str]:
    path = root / Path(*PurePosixPath(rel).parts)
    return sorted(p.name for p in path.iterdir() if p.is_dir()) if path.is_dir() else []


def _plan_entry(
    name: str, project: str | None, updates: set[str], here: list[str], other: dict[str, list[str]]
) -> Payload:
    """Classify one proposed name. An update keeps its existing name, so no prefix check."""
    defects = name_defects(name, None if name in updates else project)
    shadowed = [r for r, names in other.items() if name in names]
    if defects:
        status = "invalid"
    elif name in updates and name in here:
        status = "update"
    elif name in updates:
        status, defects = "invalid", ["--update names no existing skill in the output root"]
    elif name in here:
        status, defects = "conflict", ["skill exists; pass --name and --update to modify it"]
    elif shadowed:
        status, defects = "conflict", [f"same name exists under {', '.join(shadowed)}"]
    else:
        status = "new"
    return {"name": name, "status": status, "defects": defects}


def plan(args: argparse.Namespace) -> tuple[int, Payload]:
    root = repo_root(Path(args.repo))
    rel = check_root(root, args.output_root)
    if args.project and name_defects(args.project):
        raise ConfigError(f"--project {args.project!r} is not lowercase hyphen-case")
    names = args.name or []
    updates = set(args.update or [])
    here = _skill_dirs(root, str(rel))
    other = {r: _skill_dirs(root, r) for r in ALLOWED_ROOTS if r != str(rel)}
    require_visible(root, [f"{rel}/{n}" for n in names if not name_defects(n)])
    entries = [_plan_entry(n, args.project, updates, here, other) for n in names]
    entries += [
        {"name": n, "status": "invalid", "defects": ["--update without a matching --name"]}
        for n in sorted(updates - set(names))
    ]
    blocking = any(e["status"] in ("invalid", "conflict") for e in entries)
    return (1 if blocking else 0), {
        "repo": root.as_posix(),
        "output_root": str(rel),
        "existing_skills": here,
        "proposed": entries,
    }


def _status_codes(root: Path) -> dict[str, str]:
    """Map every path git reports as changed or untracked to its two-letter status.

    `--no-renames` reports each side of a rename as its own entry, so a
    deleted source path is never folded into the destination.
    `--ignore-submodules=none` overrides config that hides submodule writes.
    The status code is kept so a staging change counts as a change.
    """
    raw = _git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--no-renames",
        "--ignore-submodules=none",
    )
    return {e[3:].rstrip("/"): e[:2] for e in raw.split("\0") if len(e) > 3}


def _hash(path: Path) -> str:
    if path.is_symlink():
        return "symlink:" + str(path.readlink())
    if not path.exists():
        return "absent"
    if path.is_dir():
        return "dir:" + _hash_tree(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return f"{digest.hexdigest()}:{path.stat().st_mode & 0o777:o}"


def _hash_tree(path: Path) -> str:
    """Hash a directory git reports as one entry, such as a nested repo or submodule."""
    digest = hashlib.sha256()
    for child in sorted(path.rglob("*")):
        if ".git" in child.relative_to(path).parts or child.is_dir():
            continue
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update(_hash(child).encode("utf-8"))
    return digest.hexdigest()


def _index_hidden(root: Path) -> list[str]:
    """Return tracked paths flagged assume-unchanged or skip-worktree, which status skips."""
    listed = _git(root, "ls-files", "-v", "-z").split("\0")
    return sorted(e[2:] for e in listed if len(e) > 2 and (e[0].islower() or e[0] == "S"))


def _git_flags(root: Path, hidden: list[str]) -> Payload:
    """Record git state that can hide a working-tree write from `git status`."""
    exclude = root / _git(root, "rev-parse", "--git-path", "info/exclude").strip()
    return {"index_hidden": hidden, "info_exclude": _hash(exclude)}


def _head(root: Path) -> str:
    """Return the HEAD commit, or an empty string in a repository with no commit."""
    proc = _run_git(root, "rev-parse", "--verify", "--quiet", "HEAD")
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _state(root: Path) -> Payload:
    head = _head(root)
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip() if head else ""
    hidden = _index_hidden(root)
    codes = _status_codes(root)
    codes.update({p: "H " for p in hidden if p not in codes})
    return {
        "head": head,
        "branch": branch,
        "paths": {
            p: f"{code}|{_hash(root / Path(*PurePosixPath(p).parts))}" for p, code in codes.items()
        },
        "git_flags": _git_flags(root, hidden),
    }


def snapshot(args: argparse.Namespace) -> tuple[int, Payload]:
    root = repo_root(Path(args.repo))
    rel = check_root(root, args.output_root)
    out = Path(args.out).resolve()
    if out == root or root in out.parents:
        raise ConfigError(
            "snapshot file must live outside the repository, or it changes the state it"
            " records; use the system temp directory or a session scratch directory"
        )
    record = {
        "schema": SNAPSHOT_SCHEMA,
        "repo": root.as_posix(),
        "output_root": str(rel),
        "existing_skills": _skill_dirs(root, str(rel)),
        **_state(root),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    except FileExistsError as exc:
        raise ConfigError(
            f"snapshot {out} already exists; keep the Phase 1 snapshot, or pick a new path"
            " only before any write"
        ) from exc
    return 0, {
        "snapshot": out.as_posix(),
        "head": record["head"],
        "existing_skills": len(record["existing_skills"]),
        "dirty_paths": len(record["paths"]),
    }


def _load_snapshot(path: str, root: Path, rel: PurePosixPath) -> Payload:
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read snapshot {path}: {exc}") from exc
    if not isinstance(record, dict) or record.get("schema") != SNAPSHOT_SCHEMA:
        raise ConfigError(f"snapshot {path} is not a {SNAPSHOT_SCHEMA} record")
    if record.get("repo") != root.as_posix():
        raise ConfigError(f"snapshot {path} records {record.get('repo')}, not {root.as_posix()}")
    if record.get("output_root") != str(rel):
        raise ConfigError(f"snapshot {path} records output root {record.get('output_root')}")
    return record


def _also_allowed(root: Path, values: list[str]) -> list[PurePosixPath]:
    allowed = []
    for value in values:
        rel = _posix(value)
        target = (root / Path(*rel.parts)).resolve()
        if not rel.parts or ".." in rel.parts or root not in target.parents:
            raise ConfigError(f"--also-allow {value!r} is not a path inside the repository")
        if rel.parts[0] == ".git":
            raise ConfigError(f"--also-allow {value!r} names git internals")
        for skills_root in map(PurePosixPath, ALLOWED_ROOTS):
            if rel == skills_root or rel in skills_root.parents or skills_root in rel.parents:
                raise ConfigError(
                    f"--also-allow {value!r} overlaps {skills_root}; use --name or --update"
                )
        allowed.append(rel)
    return allowed


def _classify(path: str, rel: PurePosixPath, grants: Payload) -> str | None:
    """Return the violation kind for one changed path, or None when authorized."""
    posix = PurePosixPath(path)
    if any(posix == extra or extra in posix.parents for extra in grants["also_allow"]):
        return None
    if rel not in posix.parents or len(posix.relative_to(rel).parts) < 2:
        return "outside-boundary"
    skill = posix.relative_to(rel).parts[0]
    if skill in grants["updates"]:
        return None
    if skill in grants["existing"]:
        return "unauthorized-update"
    return None if skill in grants["names"] else "outside-boundary"


def verify(args: argparse.Namespace) -> tuple[int, Payload]:
    root = repo_root(Path(args.repo))
    rel = check_root(root, args.output_root)
    names, updates = set(args.name or []), set(args.update or [])
    bad = sorted(n for n in names | updates if name_defects(n))
    if bad:
        raise ConfigError(f"invalid skill names: {', '.join(bad)}")
    before = _load_snapshot(args.snapshot, root, rel)
    also_allow = _also_allowed(root, args.also_allow or [])
    require_visible(
        root,
        [f"{rel}/{n}" for n in sorted(names | updates)] + [str(a) for a in also_allow],
    )
    grants = {
        "names": names,
        "updates": updates,
        "existing": set(before["existing_skills"]),
        "also_allow": also_allow,
    }
    after = _state(root)
    violations: list[Payload] = [
        {"kind": f"{key}-changed", "before": before[key], "after": after[key]}
        for key in ("head", "branch", "git_flags")
        if before[key] != after[key]
    ]
    examined = sorted(set(before["paths"]) | set(after["paths"]))
    changed = [p for p in examined if before["paths"].get(p) != after["paths"].get(p)]
    for path in changed:
        kind = _classify(path, rel, grants)
        if kind:
            violations.append({"kind": kind, "path": path})
    return (1 if violations else 0), {
        "examined": len(examined),
        "changed": changed,
        "violations": violations,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bootstrap_boundary", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)
    roots = "one of: " + ", ".join(ALLOWED_ROOTS)

    p_plan = sub.add_parser("plan", help="validate the output root and proposed names")
    p_plan.add_argument("--repo", default=".")
    p_plan.add_argument("--output-root", required=True, help=roots)
    p_plan.add_argument("--name", action="append", help="proposed skill name (repeat per name)")
    p_plan.add_argument(
        "--update", action="append", help="existing skill the run may modify (repeat per name)"
    )
    p_plan.add_argument("--project", help="require the <project>-<lens> prefix on new names")

    p_snap = sub.add_parser("snapshot", help="record repository state before writing")
    p_snap.add_argument("--repo", default=".")
    p_snap.add_argument("--output-root", required=True, help=roots)
    p_snap.add_argument("--out", required=True, help="snapshot file outside the repository")

    p_verify = sub.add_parser("verify", help="compare repository state with a snapshot")
    p_verify.add_argument("--repo", default=".")
    p_verify.add_argument("--snapshot", required=True)
    p_verify.add_argument("--output-root", required=True, help=roots)
    p_verify.add_argument("--name", action="append", help="new skill directory (repeat per name)")
    p_verify.add_argument(
        "--update", action="append", help="authorized existing skill (repeat per name)"
    )
    p_verify.add_argument(
        "--also-allow", action="append", help="user-authorized repo path outside the root"
    )
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
    except OSError as exc:
        print(json.dumps({"error": "io", "message": str(exc)}))
        return 3
    print(json.dumps(payload, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
