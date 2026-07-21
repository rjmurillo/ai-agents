#!/usr/bin/env python3
r"""Block completion claims that lack successful verification evidence.

Canonical source:
`.claude/hooks/PreToolUse/invoke_false_completion_gate.py`

Verbatim completion contract:

    COMPLETION_SIGNALS = re.compile(
        r"\b(done|fixed|complete[ds]?|finished|resolved|merged|shipped|closes?\s+#\d+)\b",
        re.IGNORECASE,
    )

Verbatim heading contract:

    _HEADING_LINE = re.compile(r"^[#\-*\s]*\w+:?\s*$")

Verbatim verification command contract:

    VERIFICATION_PATTERNS = [
        re.compile(r"pytest", re.IGNORECASE),
        re.compile(r"npm\s+test", re.IGNORECASE),
        re.compile(r"npm\s+run\s+test", re.IGNORECASE),
        re.compile(r"pnpm\s+test", re.IGNORECASE),
        re.compile(r"yarn\s+test", re.IGNORECASE),
        re.compile(r"tsc\s+--noEmit", re.IGNORECASE),
        re.compile(r"dotnet\s+test", re.IGNORECASE),
        re.compile(r"go\s+test", re.IGNORECASE),
        re.compile(r"gh\s+pr\s+checks", re.IGNORECASE),
        re.compile(r"Invoke-Pester", re.IGNORECASE),
        re.compile(r"uv\s+run\s+pytest", re.IGNORECASE),
        re.compile(r"make\s+test", re.IGNORECASE),
    ]

Verbatim successful-result contract:

    VERIFICATION_RESULT_PATTERNS = [
        re.compile(r"\d+\s+passed", re.IGNORECASE),
        re.compile(r"\bPASSED\b"),
        re.compile(r"exit[_ ]code[:\s]+0\b", re.IGNORECASE),
        re.compile(r"exited with 0\b", re.IGNORECASE),
        re.compile(r"✓|✔"),
        re.compile(r"All checks have passed", re.IGNORECASE),
        re.compile(r"checks? passed", re.IGNORECASE),
    ]

Stricter/looser/different than canonical:
The git commit-msg hook supplies the final message file, so this helper removes
Bash command parsing, PR command detection, documentation-only detection, and
yesterday fallback. REQ-6 and REQ-7 require evidence in today's newest session
log; a missing log therefore blocks a completion claim instead of failing open.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

COMPLETION_SIGNALS = re.compile(
    r"\b(done|fixed|complete[ds]?|finished|resolved|merged|shipped|closes?\s+#\d+)\b",
    re.IGNORECASE,
)
_HEADING_LINE = re.compile(r"^[#\-*\s]*\w+:?\s*$")
VERIFICATION_PATTERNS = [
    re.compile(r"pytest", re.IGNORECASE),
    re.compile(r"npm\s+test", re.IGNORECASE),
    re.compile(r"npm\s+run\s+test", re.IGNORECASE),
    re.compile(r"pnpm\s+test", re.IGNORECASE),
    re.compile(r"yarn\s+test", re.IGNORECASE),
    re.compile(r"tsc\s+--noEmit", re.IGNORECASE),
    re.compile(r"dotnet\s+test", re.IGNORECASE),
    re.compile(r"go\s+test", re.IGNORECASE),
    re.compile(r"gh\s+pr\s+checks", re.IGNORECASE),
    re.compile(r"Invoke-Pester", re.IGNORECASE),
    re.compile(r"uv\s+run\s+pytest", re.IGNORECASE),
    re.compile(r"make\s+test", re.IGNORECASE),
]
VERIFICATION_RESULT_PATTERNS = [
    re.compile(r"\d+\s+passed", re.IGNORECASE),
    re.compile(r"\bPASSED\b"),
    re.compile(r"exit[_ ]code[:\s]+0\b", re.IGNORECASE),
    re.compile(r"exited with 0\b", re.IGNORECASE),
    re.compile(r"✓|✔"),
    re.compile(r"All checks have passed", re.IGNORECASE),
    re.compile(r"checks? passed", re.IGNORECASE),
]
_GIT_TIMEOUT_SECONDS = 5


def _run_git(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None


def _repo_root() -> Path | None:
    result = _run_git("rev-parse", "--show-toplevel")
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


def _strip_heading_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not _HEADING_LINE.match(line))


def is_completion_claim(text: str) -> bool:
    return bool(COMPLETION_SIGNALS.search(_strip_heading_lines(text)))


def _has_verification_evidence(session_log: Path) -> bool:
    found_command = False
    found_result = False
    try:
        with session_log.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                found_command = found_command or any(
                    pattern.search(line) for pattern in VERIFICATION_PATTERNS
                )
                found_result = found_result or any(
                    pattern.search(line) for pattern in VERIFICATION_RESULT_PATTERNS
                )
                if found_command and found_result:
                    return True
    except OSError:
        return False
    return False


def completion_block_reason(text: str, repo_root: Path) -> str | None:
    if os.environ.get("SKIP_COMPLETION_GATE", "").lower() == "true":
        return None
    if not is_completion_claim(text):
        return None
    session_log = _today_session_log(repo_root)
    if session_log is None:
        return "completion claim has no session log for today"
    if not _has_verification_evidence(session_log):
        return f"completion claim lacks successful verification evidence in {session_log.name}"
    return None


def check_message_file(message_file: Path, repo_root: Path) -> int:
    try:
        message = message_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    reason = completion_block_reason(message, repo_root)
    if reason is None:
        return 0
    print(f"ERROR: false completion gate: {reason}", file=sys.stderr)
    print(
        "  Run tests or checks successfully, then record command and result "
        "in today's session log.",
        file=sys.stderr,
    )
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        return 0
    message_file = Path(args[0])
    repo_root = _repo_root()
    return check_message_file(message_file, repo_root) if repo_root is not None else 0


if __name__ == "__main__":
    sys.exit(main())
