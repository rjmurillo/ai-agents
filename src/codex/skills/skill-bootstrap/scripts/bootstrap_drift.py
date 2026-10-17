#!/usr/bin/env python3
"""Re-verify the provenance of generated skills against the repository.

A generated skill may carry `reverify.json` at its skill root. Each check
states a fact the skill depends on, so a later run can see which skills have
drifted from the working tree and need an update.

Check kinds (each has a unique `id`):

    path_exists          {"path": ...}                 the path exists
    absent               {"path": ...}                 the path does not exist
    contains             {"path": ..., "text": ...}    the file holds the text
    line_count_at_least  {"path": ..., "min": N}       the file has >= N lines
    command              {"argv": [...], "expect_exit": 0}
                         run the argv, no shell, cwd=repo, 120 s timeout

Subcommand:

    check --repo PATH --skills-root DIR [--name SKILL]... [--allow-commands]
          [--require]

Paths must be relative, must not contain `..`, and must resolve inside the
repository (a symlink that escapes is rejected); otherwise the check is
`invalid`. A `command` check runs only with `--allow-commands`; without it the
check is `skipped`. A command is an argument list run without a shell, so a
repository file cannot inject shell syntax, but it does run code the skill
author chose: pass the flag only for skills you trust.

Per-check status: pass, fail, skipped, invalid. Per-skill status: `pass` when
every non-skipped check passes, `fail` when any check fails or is invalid,
`skipped` when every check was skipped (nothing was verified; not a failure,
and `--require` still counts the skill as having provenance), `no-provenance` when `reverify.json` is absent, and `malformed` when the JSON
or schema is bad (unknown kind, missing field, duplicate id, empty check
list).

The payload lists `update_candidates` (failing or malformed skills) and
`update_args`, a JSON list of argv tokens (`--name`, X, `--update`, X, ...)
for `bootstrap_boundary.py`. A skill directory whose name does not match
`[a-z](?:[a-z0-9-]*[a-z0-9])?`, is longer than 64 characters, or holds `--` is
`malformed` (detail `invalid skill name`),
so it is a candidate but never reaches `update_args`.

Exit codes:

    0  No skill failed or is malformed (and, with `--require`, every skill has
       provenance).
    1  A skill failed or is malformed, or `--require` found a skill without
       provenance.
    2  Configuration error: bad arguments, a repo or skills root that is not a
       directory, or a `--name` with no matching skill directory.

The payload carries `examined` (skills and checks, zero included). The script
never writes into the repository. Stdlib only, so it runs from any plugin
root.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

PROVENANCE_FILE = "reverify.json"
COMMAND_TIMEOUT_S = 120
PATH_KINDS = frozenset({"path_exists", "absent", "contains", "line_count_at_least"})
KINDS = PATH_KINDS | {"command"}
MAX_READ_BYTES = 5 * 1024 * 1024
SKILL_NAME_RE = re.compile(r"[a-z](?:[a-z0-9-]*[a-z0-9])?")
# Same rule as `bootstrap_boundary.name_defects`: at most 64 characters, no `--`.
# Skill scripts do not import each other, so the rule is repeated here and a
# test asserts the three scripts agree.
MAX_SKILL_NAME = 64
# The only parent variables a `command` check sees, so secrets do not leak to it.
COMMAND_ENV_KEYS = ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "TEMP", "TMP")

Payload = dict[str, Any]


class ConfigError(Exception):
    """Bad input: exit 2."""


class SchemaError(Exception):
    """A reverify.json that violates the schema: the skill is `malformed`."""


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_fields(check: Payload, label: str) -> None:
    kind = check["kind"]
    if kind in PATH_KINDS and not _text(check.get("path")):
        raise SchemaError(f"{label}: path must be a non-empty string")
    if kind == "contains" and not _text(check.get("text")):
        raise SchemaError(f"{label}: text must be a non-empty string")
    if kind == "line_count_at_least" and (not _int(check.get("min")) or check["min"] < 0):
        raise SchemaError(f"{label}: min must be a non-negative integer")
    if kind == "command":
        argv = check.get("argv")
        if not isinstance(argv, list) or not argv or not all(_text(a) for a in argv):
            raise SchemaError(f"{label}: argv must be a non-empty list of strings")
        if "expect_exit" in check and not _int(check["expect_exit"]):
            raise SchemaError(f"{label}: expect_exit must be an integer")


def validate_schema(data: Any) -> list[Payload]:
    """Return the checks of a parsed reverify.json, or raise SchemaError."""
    if not isinstance(data, dict) or not isinstance(data.get("checks"), list):
        raise SchemaError("top level must be an object with a checks list")
    checks: list[Payload] = data["checks"]
    if not checks:
        raise SchemaError("checks must not be empty")
    seen: set[str] = set()
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise SchemaError(f"checks[{index}] must be an object")
        if not _text(check.get("id")):
            raise SchemaError(f"checks[{index}]: id must be a non-empty string")
        label = f"check {check['id']}"
        if check["id"] in seen:
            raise SchemaError(f"{label}: duplicate id")
        seen.add(check["id"])
        kind = check.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            raise SchemaError(f"{label}: unknown kind {check.get('kind')!r}")
        _require_fields(check, label)
    return checks


def _safe_path(repo: Path, raw: str) -> Path | None:
    """Return the repo path, or None when it is absolute, climbs, or resolves outside the repo."""
    text = raw.strip()
    if not text or PurePosixPath(text).is_absolute() or PureWindowsPath(text).is_absolute():
        return None
    if ".." in PurePosixPath(text.replace("\\", "/")).parts:
        return None
    lexical = repo / Path(*PurePosixPath(text.replace("\\", "/")).parts)
    resolved = lexical.resolve()
    if resolved != repo and repo not in resolved.parents:
        return None
    # Return the unresolved path: `absent` must see a dangling symlink as present.
    return lexical


def valid_skill_name(name: str) -> bool:
    if len(name) > MAX_SKILL_NAME or "--" in name:
        return False
    return SKILL_NAME_RE.fullmatch(name) is not None


def _result(check: Payload, status: str, detail: str) -> Payload:
    return {"id": check["id"], "kind": check["kind"], "status": status, "detail": detail}


def _read_text(target: Path) -> str | None:
    if not target.is_file():
        return None
    size = target.stat().st_size
    if size > MAX_READ_BYTES:
        raise OSError(f"file is {size} bytes, over the {MAX_READ_BYTES} byte read cap")
    return target.read_text(encoding="utf-8", errors="replace")


def _unreadable(check: Payload, exc: OSError) -> Payload:
    return _result(check, "fail", f"cannot read {check['path']}: {exc}")


def _eval_contains(check: Payload, target: Path) -> Payload:
    try:
        content = _read_text(target)
    except OSError as exc:
        return _unreadable(check, exc)
    if content is None:
        return _result(check, "fail", f"{check['path']} is not a file")
    if check["text"] in content:
        return _result(check, "pass", "text found")
    return _result(check, "fail", f"text not found in {check['path']}")


def _eval_line_count(check: Payload, target: Path) -> Payload:
    try:
        content = _read_text(target)
    except OSError as exc:
        return _unreadable(check, exc)
    if content is None:
        return _result(check, "fail", f"{check['path']} is not a file")
    count = len(content.splitlines())
    status = "pass" if count >= check["min"] else "fail"
    return _result(check, status, f"{count} lines, need at least {check['min']}")


def _eval_path(check: Payload, repo: Path) -> Payload:
    target = _safe_path(repo, check["path"])
    if target is None:
        return _result(check, "invalid", f"path {check['path']!r} is not inside the repository")
    kind = check["kind"]
    if kind == "path_exists":
        present = target.exists()
        return _result(check, "pass" if present else "fail", "exists" if present else "missing")
    if kind == "absent":
        # lexists: a dangling symlink is still present.
        present = os.path.lexists(target)
        return _result(check, "fail" if present else "pass", "present" if present else "absent")
    if kind == "contains":
        return _eval_contains(check, target)
    return _eval_line_count(check, target)


def _eval_command(check: Payload, repo: Path, allow: bool) -> Payload:
    if not allow:
        return _result(check, "skipped", "command checks need --allow-commands")
    expected = check.get("expect_exit", 0)
    try:
        returncode = _run_argv(check["argv"], repo)
    except subprocess.TimeoutExpired:
        return _result(check, "fail", f"timed out after {COMMAND_TIMEOUT_S} s")
    except (OSError, ValueError) as exc:
        return _result(check, "fail", f"could not run {check['argv'][0]}: {exc}")
    status = "pass" if returncode == expected else "fail"
    return _result(check, status, f"exit {returncode}, expected {expected}")


def _run_argv(argv: list[str], repo: Path) -> int:
    """Run argv in its own session; on timeout kill the whole process group."""
    # Output is discarded on purpose: untrusted command output never reaches the agent.
    proc = subprocess.Popen(
        argv,
        cwd=repo,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={k: os.environ[k] for k in COMMAND_ENV_KEYS if k in os.environ},
        start_new_session=True,
    )
    try:
        return proc.wait(timeout=COMMAND_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        raise


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    if hasattr(os, "killpg"):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass  # group already gone
    proc.kill()
    proc.wait()


def evaluate_check(check: Payload, repo: Path, allow_commands: bool) -> Payload:
    """Evaluate one schema-valid check against the working tree."""
    if check["kind"] == "command":
        return _eval_command(check, repo, allow_commands)
    return _eval_path(check, repo)


def _skill_status(results: list[Payload]) -> str:
    if any(r["status"] in ("fail", "invalid") for r in results):
        return "fail"
    if all(r["status"] == "skipped" for r in results):
        return "skipped"  # nothing was verified, so do not report a pass
    return "pass"


def evaluate_skill(skill_dir: Path, repo: Path, allow_commands: bool) -> Payload:
    """Load a skill's reverify.json and evaluate every check."""
    entry: Payload = {"name": skill_dir.name, "status": "", "checks": []}
    if not valid_skill_name(skill_dir.name):
        entry["status"] = "malformed"
        entry["detail"] = "invalid skill name"
        return entry
    source = skill_dir / PROVENANCE_FILE
    if not source.is_file():
        entry["status"] = "no-provenance"
        return entry
    try:
        checks = validate_schema(json.loads(source.read_text(encoding="utf-8")))
    except (OSError, ValueError, RecursionError, SchemaError) as exc:
        entry["status"] = "malformed"
        entry["detail"] = str(exc)
        return entry
    entry["checks"] = [evaluate_check(c, repo, allow_commands) for c in checks]
    entry["status"] = _skill_status(entry["checks"])
    return entry


def _directory(value: str, label: str) -> Path:
    path = Path(value)
    if not path.is_dir():
        raise ConfigError(f"{label} is not a directory: {value}")
    return path.resolve()


def _select_skills(skills_root: Path, names: list[str]) -> list[Path]:
    try:
        available = {p.name: p for p in sorted(skills_root.iterdir()) if p.is_dir()}
    except OSError as exc:
        raise ConfigError(f"cannot list skills root {skills_root}: {exc}") from exc
    missing = [n for n in names if n not in available]
    if missing:
        raise ConfigError(f"no skill directory named {', '.join(missing)} in {skills_root}")
    if names:
        return [available[n] for n in dict.fromkeys(names)]
    return list(available.values())


def _update_args(names: list[str]) -> list[str]:
    return [token for n in names for token in ("--name", n, "--update", n)]


def check(args: argparse.Namespace) -> tuple[int, Payload]:
    repo = _directory(args.repo, "repo")
    skills_root = _directory(args.skills_root, "skills root")
    selected = _select_skills(skills_root, args.name or [])
    skills = [evaluate_skill(d, repo, args.allow_commands) for d in selected]
    candidates = [s["name"] for s in skills if s["status"] in ("fail", "malformed")]
    safe = [n for n in candidates if valid_skill_name(n)]
    missing = [s["name"] for s in skills if s["status"] == "no-provenance"]
    failed = bool(candidates) or (args.require and bool(missing))
    return (1 if failed else 0), {
        "skills": skills,
        "update_candidates": candidates,
        "update_args": _update_args(safe),
        "no_provenance": missing,
        "examined": {"skills": len(skills), "checks": sum(len(s["checks"]) for s in skills)},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        allow_abbrev=False, prog="bootstrap_drift", description=__doc__.split("\n\n")[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser(
        "check", allow_abbrev=False, help="re-verify skill provenance against the repository"
    )
    p_check.add_argument("--repo", required=True, help="repository working tree")
    p_check.add_argument("--skills-root", required=True, help="directory of skill directories")
    p_check.add_argument("--name", action="append", help="check only this skill (repeat per name)")
    p_check.add_argument(
        "--allow-commands", action="store_true", help="run `command` checks (trusted skills only)"
    )
    p_check.add_argument(
        "--require", action="store_true", help="fail when a skill has no reverify.json"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code, payload = check(args)
    except ConfigError as exc:
        print(json.dumps({"error": "config", "message": str(exc)}))
        return 2
    print(json.dumps(payload, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
