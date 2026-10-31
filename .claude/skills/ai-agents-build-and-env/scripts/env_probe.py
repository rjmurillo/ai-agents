#!/usr/bin/env python3
"""Read environment pins and local env state for the ai-agents repo.

Subcommands:
  pins     Read interpreter, lefthook, PyYAML, requires-python, Node major,
           hook syntax floor, and Serena memory count from their defining files.
  envfile  Check .env is untracked and list .env.example key names.
  smoke    Run the Phase 3 smoke commands and compare against the pins.

Exit codes: 0 ok, 1 findings, 2 configuration or bad arguments,
3 external failure (git or uv missing or failed).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

EXIT_OK, EXIT_FINDINGS, EXIT_CONFIG, EXIT_EXTERNAL = 0, 1, 2, 3


class ConfigError(Exception):
    """A defining file is missing or lacks the expected line."""


class ExternalError(Exception):
    """A required external tool is missing or failed to run."""


def _read(repo: Path, rel: str) -> str:
    path = repo / rel
    if not path.is_file():
        raise ConfigError(f"missing source file: {rel}")
    return path.read_text(encoding="utf-8")


def _find(text: str, pattern: str, rel: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ConfigError(f"pattern {pattern!r} not found in {rel}")
    return match.group(1)


def read_pins(repo: Path) -> dict[str, Any]:
    py = _read(repo, ".python-version").strip()
    pyproject = _read(repo, "pyproject.toml")
    bootstrap = _read(repo, "scripts/bootstrap-vm.sh")
    syntax = _read(repo, "scripts/validation/validate_python_syntax.py")
    floor_m = re.search(r"^_SUPPORT_FLOOR\s*=\s*\((\d+),\s*(\d+)\)", syntax, re.MULTILINE)
    if floor_m is None:
        raise ConfigError("_SUPPORT_FLOOR not found in validate_python_syntax.py")
    memories = repo / ".serena" / "memories"
    memory_count = (
        sum(1 for p in memories.iterdir() if not p.name.startswith(".")) if memories.is_dir() else 0
    )
    return {
        "python": py,
        "requires_python": _find(pyproject, r'^requires-python\s*=\s*"([^"]+)"', "pyproject.toml"),
        "pyyaml": _find(pyproject, r'"PyYAML==([^"]+)"', "pyproject.toml"),
        "lefthook": _find(pyproject, r'"lefthook==([^"]+)"', "pyproject.toml"),
        "node_major": _find(bootstrap, r"NODE_MAJOR=(\d+)", "scripts/bootstrap-vm.sh"),
        "syntax_floor": f"{floor_m.group(1)}.{floor_m.group(2)}",
        "serena_memory_entries": memory_count,
    }


def _git_ls_files(repo: Path, rel: str) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "--", rel],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExternalError(f"git unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise ExternalError(f"git ls-files failed: {proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line]


def read_envfile(repo: Path) -> dict[str, Any]:
    example = repo / ".env.example"
    if not example.is_file():
        raise ConfigError("missing source file: .env.example")
    keys: list[str] = []
    commented: list[str] = []
    for line in example.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*(#\s*)?([A-Z][A-Z0-9_]*)=", line)
        if not match:
            continue
        bucket = commented if match.group(1) else keys
        if match.group(2) not in bucket:
            bucket.append(match.group(2))
    return {
        "env_exists": (repo / ".env").is_file(),
        "tracked_env": bool(_git_ls_files(repo, ".env")),
        "example_keys": keys,
        "commented_keys": commented,
    }


def _run(cmd: list[str], repo: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExternalError(f"cannot start {cmd[0]}: {exc}") from exc


def run_smoke(repo: Path) -> dict[str, Any]:
    pins = read_pins(repo)
    results = []
    ver = _run(["uv", "run", "--frozen", "lefthook", "version"], repo)
    got = ver.stdout.strip()
    results.append(
        {
            "cmd": "lefthook version",
            "rc": ver.returncode,
            "value": got,
            "ok": ver.returncode == 0 and got == pins["lefthook"],
        }
    )
    chk = _run(["uv", "run", "--frozen", "lefthook", "check-install"], repo)
    results.append(
        {"cmd": "lefthook check-install", "rc": chk.returncode, "ok": chk.returncode == 0}
    )
    col = _run(["uv", "run", "pytest", "tests/test_paths.py", "--collect-only", "-q"], repo)
    count = re.search(r"(\d+) tests? collected", col.stdout)
    results.append(
        {
            "cmd": "pytest tests/test_paths.py --collect-only",
            "rc": col.returncode,
            "value": int(count.group(1)) if count else None,
            "ok": col.returncode == 0 and count is not None,
        }
    )
    return {"results": results, "examined": len(results)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--repo", default=".", help="repository root (default: .)")
    parser.add_argument("command", choices=["pins", "envfile", "smoke"])
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code in (0, None) else EXIT_CONFIG
    repo = Path(args.repo)
    if not repo.is_dir():
        print(json.dumps({"error": f"not a directory: {repo}", "examined": 0}))
        return EXIT_CONFIG
    out: dict[str, Any]
    try:
        if args.command == "pins":
            pins = read_pins(repo)
            out = {"pins": pins, "examined": 7}
            code = EXIT_OK
        elif args.command == "envfile":
            info = read_envfile(repo)
            out = {**info, "examined": 2 + len(info["example_keys"]) + len(info["commented_keys"])}
            code = EXIT_FINDINGS if info["tracked_env"] else EXIT_OK
        else:
            out = run_smoke(repo)
            code = EXIT_OK if all(r["ok"] for r in out["results"]) else EXIT_FINDINGS
    except ConfigError as exc:
        print(json.dumps({"error": str(exc), "examined": 0}))
        return EXIT_CONFIG
    except ExternalError as exc:
        print(json.dumps({"error": str(exc), "examined": 0}))
        return EXIT_EXTERNAL
    print(json.dumps(out, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
