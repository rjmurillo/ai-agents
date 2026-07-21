#!/usr/bin/env python3
r"""Block staged ADR governance changes without fresh review evidence.

Canonical source:
`.claude/hooks/PreToolUse/invoke_adr_review_guard.py`

Verbatim trigger contract:

    _ADR_PATTERN = re.compile(r"(?:^|[\\/])ADR-\d+(?:-\w+)*\.md$", re.IGNORECASE)
    _CANONICAL_SOURCE_PATTERN = re.compile(r"SESSION-PROTOCOL\.md$", re.IGNORECASE)

Verbatim review-evidence contract:

    _REVIEW_PATTERNS = [
        re.compile(r"/adr-review"),
        re.compile(r"adr-review skill"),
        re.compile(r"ADR Review Protocol"),
        re.compile(r"multi-agent consensus.{0,200}\bADR\b", re.DOTALL),
        re.compile(r"\barchitect\b.{0,80}\bplanner\b.{0,80}\bqa\b", re.DOTALL),
    ]

Verbatim artifact check replaced by this helper:

    debate_logs = list(analysis_dir.glob("*debate*.md"))

Stricter/looser/different than canonical:
REQ-5 accepts a debate artifact only when its UTC mtime is today or git log
shows it changed after the current branch diverged from origin/main. This closes
the stale-artifact bypass in the canonical check. REQ-5 also gates every staged
path matching either quoted regex, so this helper does not retain the source
hook's later frontmatter-only metadata exemption.
"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

_ADR_PATTERN = re.compile(r"(?:^|[\\/])ADR-\d+(?:-\w+)*\.md$", re.IGNORECASE)
_CANONICAL_SOURCE_PATTERN = re.compile(r"SESSION-PROTOCOL\.md$", re.IGNORECASE)
_REVIEW_PATTERNS = [
    re.compile(r"/adr-review"),
    re.compile(r"adr-review skill"),
    re.compile(r"ADR Review Protocol"),
    re.compile(r"multi-agent consensus.{0,200}\bADR\b", re.DOTALL),
    re.compile(r"\barchitect\b.{0,80}\bplanner\b.{0,80}\bqa\b", re.DOTALL),
]
_GIT_TIMEOUT_SECONDS = 5


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=repo_root,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None


def _repo_root() -> Path | None:
    result = _run_git(Path.cwd(), "rev-parse", "--show-toplevel")
    if result is None or result.returncode != 0:
        return None
    root = result.stdout.strip()
    return Path(root) if root else None


def _today_session_log(repo_root: Path) -> Path | None:
    sessions_dir = repo_root / ".agents" / "sessions"
    if not sessions_dir.is_dir():
        return None
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    newest: tuple[float, Path] | None = None
    try:
        candidates = sessions_dir.glob(f"{today}-session-*.json")
        for candidate in candidates:
            try:
                item = (candidate.stat().st_mtime, candidate)
            except OSError:
                continue
            if newest is None or item[0] > newest[0]:
                newest = item
    except OSError:
        return None
    return newest[1] if newest else None


def _is_gated_file(path: str) -> bool:
    return bool(_ADR_PATTERN.search(path) or _CANONICAL_SOURCE_PATTERN.search(path))


def _staged_gated_files(repo_root: Path) -> list[str] | None:
    result = _run_git(repo_root, "diff", "--cached", "--name-only")
    if result is None or result.returncode != 0:
        return None
    return [path for path in result.stdout.splitlines() if _is_gated_file(path)]


def _has_review_evidence(session_log: Path) -> bool:
    try:
        content = session_log.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    return any(pattern.search(content) for pattern in _REVIEW_PATTERNS)


def _modified_today(path: Path) -> bool:
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).date()
    except (OSError, ValueError, OverflowError):
        return False
    return modified == datetime.now(tz=UTC).date()


def _modified_on_current_branch(repo_root: Path, path: Path) -> bool:
    merge_base = _run_git(repo_root, "merge-base", "HEAD", "origin/main")
    if merge_base is None or merge_base.returncode != 0:
        return False
    base = merge_base.stdout.strip()
    if not base:
        return False
    relative_path = path.relative_to(repo_root)
    history = _run_git(
        repo_root,
        "log",
        "--format=%H",
        f"{base}..HEAD",
        "--",
        str(relative_path),
    )
    return bool(history and history.returncode == 0 and history.stdout.strip())


def _has_fresh_debate_artifact(repo_root: Path) -> bool:
    analysis_dir = repo_root / ".agents" / "analysis"
    if not analysis_dir.is_dir():
        return False
    try:
        candidates = analysis_dir.glob("*debate*.md")
        return any(
            _modified_today(path) or _modified_on_current_branch(repo_root, path)
            for path in candidates
        )
    except OSError:
        return False


def check_adr_review_evidence(repo_root: Path) -> int:
    staged_files = _staged_gated_files(repo_root)
    if staged_files is None:
        print("ERROR: unable to inspect staged ADR governance files", file=sys.stderr)
        return 2
    if not staged_files:
        return 0
    session_log = _today_session_log(repo_root)
    if session_log is None:
        print("ERROR: ADR changes require today's session log", file=sys.stderr)
        return 2
    if not _has_review_evidence(session_log):
        print(
            f"ERROR: ADR changes lack adr-review evidence in {session_log.name}",
            file=sys.stderr,
        )
        return 2
    if not _has_fresh_debate_artifact(repo_root):
        print(
            "ERROR: ADR changes require a same-day or current-branch "
            "*debate*.md artifact",
            file=sys.stderr,
        )
        return 2
    return 0


def main() -> int:
    repo_root = _repo_root()
    return check_adr_review_evidence(repo_root) if repo_root is not None else 0


if __name__ == "__main__":
    sys.exit(main())
