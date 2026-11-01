#!/usr/bin/env python3
"""Locate catalog flags, list pytest markers, and check retired flags stay gone.

  flag_locator.py --repo . locate <id|name>  print file:line for each attributed file
  flag_locator.py --repo . locate --list   print the known ids
  flag_locator.py --repo . markers         list pytest markers from pyproject.toml
  flag_locator.py --repo . retired         confirm retired flags are absent

locate takes a kebab id or the exact flag name (case-sensitive match on the
needle, for example AI_AGENTS_PYTEST_WORKERS). It exits 1 when an attributed file is missing or has no hit for the needle.
markers reads [tool.pytest.ini_options].markers with tomllib. retired exits 1
when a retired flag name reappears in CONTRIBUTING.md or scripts/validation/pre_pr.py.
It does not search other files: a retired name left in a docstring elsewhere is
out of scope.

Exit codes: 0 ok, 1 findings, 2 bad arguments or unreadable configuration,
3 external failure (a file cannot be read).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import tomllib

_ORPHAN = ".claude/skills/orphan-ref-validator/scripts"

# id -> needle searched for, and the files the catalog attributes the flag to.
FLAGS: dict[str, dict[str, Any]] = {
    "git-config-count": {"needle": "GIT_CONFIG_COUNT", "files": ["tests/conftest.py"]},
    "push-lock-skip": {
        "needle": "SKIP_PUSH_LOCK_COMMIT_GUARD",
        "files": ["scripts/validation/check_push_lock_before_commit.py", "lefthook.yml"],
    },
    "pytest-full-suite": {
        "needle": "AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY",
        "files": ["scripts/validation/git_hook_policy.py"],
    },
    "pytest-workers": {
        "needle": "AI_AGENTS_PYTEST_WORKERS",
        "files": ["scripts/validation/git_hook_policy.py"],
    },
    "size-exception": {
        "needle": "size-exception",
        "files": [
            "scripts/validation/skill_size.py",
            ".claude/skills/taste-lints/scripts/taste_lints.py",
        ],
    },
    "orphan-ref-ignore": {
        "needle": "IGNORE_DIRECTIVE_RE = re.compile",
        "files": [f"{_ORPHAN}/patterns.py"],
    },
    "orphan-ref-ignore-file": {
        "needle": "FILE_IGNORE_DIRECTIVE_RE = re.compile",
        "files": [f"{_ORPHAN}/patterns.py"],
    },
    "orphan-ref-window": {"needle": "splitlines()[:50]", "files": [f"{_ORPHAN}/scan.py"]},
    "qa-docs-only": {
        "needle": "SKIPPED: docs-only",
        "files": ["scripts/validate_session_json.py", "CONTRIBUTING.md"],
    },
    "qa-investigation-only": {
        "needle": "SKIPPED: investigation-only",
        "files": ["scripts/validate_session_json.py"],
    },
    "env-example-keys": {"needle": "API_KEY", "files": [".env.example"]},
}

RETIRED = ["SKIP_PREPUSH", "SKIP_TESTS"]
RETIRED_FILES = ["CONTRIBUTING.md", "scripts/validation/pre_pr.py"]


def _hits(path: Path, needle: str) -> list[int]:
    text = path.read_text(encoding="utf-8")
    return [i for i, line in enumerate(text.splitlines(), 1) if needle in line]


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def cmd_locate(repo: Path, flag_id: str | None, list_only: bool) -> int:
    if list_only:
        _emit({"ids": sorted(FLAGS), "examined": len(FLAGS)})
        return 0
    if flag_id not in FLAGS:
        flag_id = next((k for k, v in FLAGS.items() if v["needle"] == flag_id), flag_id)
    if flag_id not in FLAGS:
        print(
            json.dumps({"error": f"unknown id: {flag_id}", "known": sorted(FLAGS)}), file=sys.stderr
        )
        return 2
    spec = FLAGS[flag_id]
    results, findings = [], 0
    for rel in spec["files"]:
        path = repo / rel
        if not path.is_file():
            results.append({"file": rel, "exists": False, "lines": []})
            findings += 1
            continue
        try:
            lines = _hits(path, spec["needle"])
        except (OSError, UnicodeDecodeError) as exc:
            print(json.dumps({"error": f"cannot read {rel}: {exc}"}), file=sys.stderr)
            return 3
        findings += 0 if lines else 1
        results.append(
            {
                "file": rel,
                "exists": True,
                "lines": lines,
                "locations": [f"{rel}:{n}" for n in lines],
            }
        )
    _emit({"id": flag_id, "needle": spec["needle"], "results": results, "examined": len(results)})
    return 1 if findings else 0


def cmd_markers(repo: Path) -> int:
    path = repo / "pyproject.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        print(json.dumps({"error": f"cannot read pyproject.toml: {exc}"}), file=sys.stderr)
        return 2
    raw = data.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("markers")
    if not isinstance(raw, list) or not raw:
        print(json.dumps({"error": "no [tool.pytest.ini_options].markers list"}), file=sys.stderr)
        return 2
    markers = []
    for item in raw:
        name, _, desc = str(item).partition(":")
        markers.append({"name": name.strip(), "description": desc.strip()})
    _emit({"markers": markers, "examined": len(markers)})
    return 0


def cmd_retired(repo: Path) -> int:
    reappeared, examined = [], 0
    for rel in RETIRED_FILES:
        path = repo / rel
        if not path.is_file():
            print(json.dumps({"error": f"missing file: {rel}"}), file=sys.stderr)
            return 2
        for name in RETIRED:
            examined += 1
            try:
                reappeared += [f"{rel}:{n} {name}" for n in _hits(path, name)]
            except (OSError, UnicodeDecodeError) as exc:
                print(json.dumps({"error": f"cannot read {rel}: {exc}"}), file=sys.stderr)
                return 3
    _emit(
        {"retired": RETIRED, "files": RETIRED_FILES, "reappeared": reappeared, "examined": examined}
    )
    return 1 if reappeared else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", default=".")
    sub = parser.add_subparsers(dest="cmd", required=True)
    loc = sub.add_parser("locate")
    loc.add_argument("id", nargs="?")
    loc.add_argument("--list", action="store_true", dest="list_only")
    sub.add_parser("markers")
    sub.add_parser("retired")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code in (0, None) else 2
    repo = Path(args.repo)
    if args.cmd == "locate":
        if not args.list_only and not args.id:
            print(json.dumps({"error": "locate needs an id or --list"}), file=sys.stderr)
            return 2
        return cmd_locate(repo, args.id, args.list_only)
    if args.cmd == "markers":
        return cmd_markers(repo)
    return cmd_retired(repo)


if __name__ == "__main__":
    sys.exit(main())
