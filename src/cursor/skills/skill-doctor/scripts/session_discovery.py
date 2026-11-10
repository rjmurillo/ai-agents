"""Local history and skill discovery for skill-doctor.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any

from session_common import record_collection_issue

CLAUDE_DIRECTORY = ".claude"
PROJECT_HARNESS_DIRS = (CLAUDE_DIRECTORY, ".codex", ".github", ".factory")


def resolve_repo(repo_arg: Any) -> Path:
    if repo_arg:
        return Path(repo_arg).expanduser().resolve()
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            return Path(res.stdout.strip()).resolve()
    except (subprocess.TimeoutExpired, OSError):
        pass
    return Path.cwd().resolve()


def resolve_repos(repo_args: Any) -> list[Path]:
    if not repo_args:
        return [resolve_repo(None)]
    return list(dict.fromkeys(resolve_repo(value) for value in repo_args))


def _skill_roots(
    repos: Any,
    codex_home: Path,
    extra_dirs: Any,
    include_global: bool,
    homes: tuple[Path | None, ...],
    copilot_home: Path | None,
) -> list[Path]:
    if isinstance(repos, Path):
        repos = [repos]
    roots = [repo / harness / "skills" for repo in repos for harness in PROJECT_HARNESS_DIRS]
    if include_global:
        roots.append(codex_home / "skills")
        roots.extend(Path(home) / "skills" for home in homes if home is not None)
        if copilot_home is not None:
            roots.append(copilot_home / "skills")
            roots.extend(sorted((copilot_home / "installed-plugins").glob("*/*/skills")))
    roots.extend(Path(directory).expanduser() for directory in extra_dirs)
    return roots


def _skill_metadata(skill_md: Path) -> dict[str, Any] | None:
    try:
        content = skill_md.read_bytes()
        text = content.decode("utf-8", errors="replace")
        stat = skill_md.stat()
    except OSError:
        record_collection_issue("skill_read_failures")
        return None
    match = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
    return {
        "name": skill_md.parent.name,
        "path": str(skill_md),
        "description": match.group(1).strip().strip("\"'")[:300] if match else "",
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def discover_skills(
    repos: Any,
    codex_home: Path,
    extra_dirs: Any,
    include_global: bool,
    pi_home: Path | None = None,
    grok_home: Path | None = None,
    zcode_home: Path | None = None,
    hermes_home: Path | None = None,
    copilot_home: Path | None = None,
    claude_home: Path | None = None,
    factory_home: Path | None = None,
) -> dict[str, Any]:
    roots = _skill_roots(
        repos,
        codex_home,
        extra_dirs,
        include_global,
        (
            claude_home or Path.home() / CLAUDE_DIRECTORY,
            pi_home,
            grok_home,
            zcode_home,
            hermes_home,
            factory_home,
        ),
        copilot_home,
    )
    skills: dict[str, dict[str, Any]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for skill_md in sorted(root.glob("*/SKILL.md")):
            metadata = _skill_metadata(skill_md)
            if metadata is not None:
                _add_definition(skills, metadata)
    return skills


def _add_definition(skills: dict[str, dict[str, Any]], metadata: dict[str, Any]) -> None:
    """Keep the first-seen copy as the edit target and group every copy by content.

    Roots are visited in `--repo` order, then global homes, so the first copy is
    the current checkout's. Usage detection never depends on that choice.
    """
    chosen = skills.setdefault(metadata["name"], metadata)
    if chosen is metadata:
        metadata["definitions"] = []
    for definition in chosen["definitions"]:
        if definition["sha256"] == metadata["sha256"]:
            break
    else:
        definition = {"sha256": metadata["sha256"], "paths": []}
        chosen["definitions"].append(definition)
    if metadata["path"] not in definition["paths"]:
        definition["paths"].append(metadata["path"])


def _recent_files(paths: Any, cutoff: datetime) -> list[tuple[datetime, Path]]:
    files = []
    for path in paths:
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime >= cutoff:
            files.append((mtime, path))
    return sorted(files, key=lambda item: item[0], reverse=True)


def find_codex_session_files(codex_home: Path, cutoff: datetime) -> Any:
    paths = (
        path
        for sub in ("sessions", "archived_sessions")
        for path in (codex_home / sub).rglob("rollout-*.jsonl")
    )
    return _recent_files(paths, cutoff)


def find_claude_session_files(claude_home: Path, cutoff: datetime, include_subagents: bool) -> Any:
    projects = claude_home / "projects"
    candidates = list(projects.glob("*/*.jsonl"))
    if include_subagents:
        candidates.extend(projects.glob("*/*/subagents/*.jsonl"))
    return _recent_files(candidates, cutoff)


def find_copilot_session_files(copilot_home: Path, cutoff: datetime) -> list[tuple[datetime, Path]]:
    return _recent_files((copilot_home / "session-state").glob("*/events.jsonl"), cutoff)


def find_pi_session_files(pi_home: Path, cutoff: datetime) -> Any:
    return _recent_files((pi_home / "sessions").glob("*/*.jsonl"), cutoff)


def find_grok_session_files(grok_home: Path, cutoff: datetime) -> Any:
    return _recent_files((grok_home / "sessions").glob("*/*/chat_history.jsonl"), cutoff)


def find_droid_session_files(factory_home: Path, cutoff: datetime) -> Any:
    """Session journals only: the ``*.settings.json`` sidecars never match ``*.jsonl``."""
    return _recent_files((factory_home / "sessions").glob("*/*.jsonl"), cutoff)


def find_zcode_session_files(zcode_home: Path, cutoff: datetime) -> Any:
    return _recent_files((zcode_home / "cli" / "rollout").glob("model-io-*.jsonl"), cutoff)


def warp_data_roots(data_dir: Any, platform: str, os_name: str, environ: Any) -> list[Path]:
    if data_dir:
        return [Path(data_dir).expanduser()]
    if platform == "darwin":
        return [
            Path.home()
            / "Library"
            / "Group Containers"
            / "2BBY89MBSN.dev.warp"
            / "Library"
            / "Application Support"
        ]
    if platform.startswith("linux"):
        xdg_data = Path(environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return [xdg_data / "warp-terminal", xdg_data / "warp"]
    if os_name == "nt" and environ.get("APPDATA"):
        return [Path(environ["APPDATA"]) / "Warp"]
    return []


def warp_database_candidates(explicit_paths: Any, roots: Any) -> list[Path]:
    candidates = [Path(value).expanduser() for value in explicit_paths]
    for root in roots:
        if root.is_file():
            candidates.append(root)
            continue
        candidates.append(root / "warp.sqlite")
        if root.is_dir():
            candidates.extend(root.glob("*/warp.sqlite"))
    databases = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.is_file():
            databases.add(resolved)
    return sorted(databases)


def _hermes_roots(explicit_path: Any, *, explicit_only: bool) -> list[Path]:
    if explicit_path and explicit_only:
        return [Path(explicit_path).expanduser()]
    roots = [Path(explicit_path).expanduser()] if explicit_path else []
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        roots.append(Path(env_home).expanduser())
    return roots + [Path.home() / ".hermes", Path.home()]


def _resolved_roots(roots: list[Path]) -> list[Path]:
    resolved_roots = []
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved not in resolved_roots:
            resolved_roots.append(resolved)
    return resolved_roots


def resolve_hermes_home(explicit_path: Any = None) -> Path:
    roots = _resolved_roots(_hermes_roots(explicit_path, explicit_only=False))
    for root in roots:
        if (root / "state.db").is_file():
            return root
    return roots[0] if roots else Path.home().resolve()


def discover_hermes_databases(explicit_path: Any = None) -> list[Path]:
    roots = _resolved_roots(_hermes_roots(explicit_path, explicit_only=True))
    return [root / "state.db" for root in roots if (root / "state.db").is_file()]


def session_cwd_within_repo(cwd: Any, repo: Path) -> bool:
    if not isinstance(cwd, str) or not cwd:
        return False
    if bool(PureWindowsPath(cwd).drive) != (os.name == "nt"):
        return False
    try:
        path = Path(cwd)
        return path.is_absolute() and path.resolve().is_relative_to(repo)
    except (OSError, ValueError):
        return False


def session_matches_repo(cwd: Any, repo: Path) -> bool:
    """Admit only native descendants of an explicitly selected repository."""
    if isinstance(cwd, os.PathLike):
        cwd = os.fspath(cwd)
    return session_cwd_within_repo(cwd, repo)


def session_matches_repos(cwd: Any, repos: Any) -> bool:
    return any(session_matches_repo(cwd, repo) for repo in repos)


def copilot_session_matches_repos(meta: dict[str, Any], repos: Any) -> bool:
    history = meta["cwd_history"]
    return session_matches_repos(meta.get("cwd"), repos) and all(
        session_matches_repos(cwd, repos) for cwd in history
    )


def infer_session_repos(sessions: Any) -> list[Path]:
    repos = []
    for session in sessions:
        cwd = session["meta"].get("cwd")
        if not cwd:
            continue
        path = Path(cwd).expanduser()
        if not path.is_dir():
            continue
        repo = _git_root(path)
        if repo is not None and repo not in repos:
            repos.append(repo)
    return repos


def _git_root(path: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve()


def parse_collector_args(description: str | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    _add_source_arguments(parser)
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="project to include (repeatable; default: git root of cwd, else cwd)",
    )
    parser.add_argument(
        "--no-worktrees",
        action="store_true",
        help="grade only the listed checkouts, not their registered worktrees",
    )
    parser.add_argument(
        "--all-conversations",
        action="store_true",
        help="score conversations from every project represented in local history",
    )
    parser.add_argument(
        "--include-global-skills",
        action="store_true",
        help="also discover skills in the supported harnesses' global skill directories",
    )
    _add_sampling_arguments(parser)
    parser.add_argument(
        "--skills-dir",
        action="append",
        default=[],
        help="extra skills directory to scan (repeatable)",
    )
    parser.add_argument(
        "--include-subagents", action="store_true", help="include subagent/child sessions"
    )
    parser.add_argument("--out", default="./skill-doctor-report")
    return parser.parse_args()


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--harness",
        choices=(
            "auto",
            "all",
            "claude",
            "codex",
            "copilot",
            "warp",
            "pi",
            "grok",
            "zcode",
            "hermes",
            "droid",
        ),
        default="auto",
        help="session source (default: auto; scans every locally available source)",
    )
    parser.add_argument(
        "--claude-home",
        default=os.environ.get("CLAUDE_CONFIG_DIR", "~/.claude"),
        help="Claude Code config directory (default: CLAUDE_CONFIG_DIR or ~/.claude)",
    )
    parser.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", "~/.codex"))
    parser.add_argument(
        "--copilot-home",
        default=os.environ.get("COPILOT_HOME", "~/.copilot"),
        help="Copilot CLI home containing session-state (default: COPILOT_HOME or ~/.copilot)",
    )
    parser.add_argument(
        "--pi-home", default="~/.pi/agent", help="Pi agent home (default: ~/.pi/agent)"
    )
    parser.add_argument("--grok-home", default="~/.grok", help="Grok Build home (default: ~/.grok)")
    parser.add_argument("--zcode-home", default="~/.zcode", help="ZCode home (default: ~/.zcode)")
    parser.add_argument(
        "--factory-home",
        default="~/.factory",
        help="Factory Droid home containing sessions (default: ~/.factory)",
    )
    parser.add_argument(
        "--hermes-home",
        default=None,
        help="Hermes Agent home containing state.db (default: HERMES_HOME, ~/.hermes, then ~)",
    )
    parser.add_argument(
        "--warp-db", action="append", default=[], help="explicit Warp warp.sqlite path (repeatable)"
    )
    parser.add_argument(
        "--warp-data-dir",
        default=os.environ.get("WARP_DATA_DIR"),
        help="directory containing Warp channel data directories",
    )


def _non_negative_minutes(value: str) -> float:
    try:
        minutes = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from None
    if minutes < 0 or minutes != minutes:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return minutes


def _add_sampling_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--min-idle-minutes",
        type=_non_negative_minutes,
        default=15.0,
        help="skip sessions whose last record is newer than N minutes, because they may "
        "still be running (default: 15; 0 keeps every session)",
    )
    parser.add_argument(
        "--days", type=int, default=45, help="only consider sessions modified in the last N days"
    )
    parser.add_argument(
        "--max-sessions", type=int, default=12, help="max sessions to sample for scoring"
    )
    parser.add_argument("--per-skill", type=int, default=3, help="max sampled sessions per skill")
    parser.add_argument(
        "--no-skill", type=int, default=4, help="max sampled sessions that used no skill"
    )
