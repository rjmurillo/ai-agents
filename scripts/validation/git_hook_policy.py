#!/usr/bin/env python3
"""Narrow Git policies that Lefthook cannot express declaratively."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath
from typing import TextIO, cast

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from scripts.validation.sha_pinning import LOCAL_ACTION_PATTERN, VERSION_TAG_PATTERN

REPO_ROOT = Path(__file__).resolve().parents[2]
ZERO_SHA_LENGTHS = (40, 64)
PROHIBITED_DASHES = ("\N{EN DASH}", "\N{EM DASH}")
SESSION_PATH_RE = re.compile(r"^\.agents/sessions/\d{4}-\d{2}-\d{2}-session-\d+.*\.json$")
EPISODE_PATH_RE = re.compile(r"^\.agents/memory/episodes/episode-[A-Za-z0-9._-]+\.json$")
EPISODE_ID_RE = re.compile(r"^episode-[A-Za-z0-9._-]+$")
ADR_REVIEW_PATH_RE = re.compile(
    r"(?:^|[\\/])ADR-\d+(?:-\w+)*\.md$|SESSION-PROTOCOL\.md$",
    re.IGNORECASE,
)
ADR_PATH_RE = re.compile(r"(?:^|[\\/])ADR-\d+(?:-\w+)*\.md$", re.IGNORECASE)
ADR_ID_RE = re.compile(r"ADR-\d+", re.IGNORECASE)
FRONTMATTER_FIELD_RE = re.compile(r"^([A-Za-z0-9_-]+):(.*)$")
ADR_REVIEW_PATTERNS = (
    re.compile(r"/adr-review"),
    re.compile(r"adr-review skill"),
    re.compile(r"ADR Review Protocol"),
    re.compile(r"multi-agent consensus.{0,200}\bADR\b", re.DOTALL),
    re.compile(r"\barchitect\b.{0,80}\bplanner\b.{0,80}\bqa\b", re.DOTALL),
)
RETROSPECTIVE_EVIDENCE_PATTERNS = (
    re.compile(r"(?i)(##\s*retrospective|retrospective\s*section|learnings?\s*captured)"),
    re.compile(r"(?i)(\.agents/retrospective/|retrospective[-_]?file|retro[-_]?\d{4})"),
)
DOCUMENTATION_PATTERNS = (
    re.compile(r"\.md$"),
    re.compile(r"\.txt$"),
    re.compile(r"(^|/)README$"),
    re.compile(r"(^|/)LICENSE$"),
    re.compile(r"(^|/)CHANGELOG$"),
    re.compile(r"\.gitignore$"),
    re.compile(r"\.editorconfig$"),
)
TRIVIAL_SESSION_SECONDS = 10 * 60
SECURITY_SUPPRESSION_RE = re.compile(
    r"(?:#|//|/\*)\s*"
    r"(?:lgtm\[|nosec|nosem(?:grep)?|noqa:\s*S|type:\s*ignore\[|cwe-suppress)"
)
SEMGREP_SUFFIXES = frozenset({".js", ".ps1", ".psm1", ".py", ".ts", ".yaml", ".yml"})
SEMGREP_POWERSHELL_RULES = frozenset(
    {
        "yaml.github-actions.security.curl-eval.curl-eval",
        "yaml.github-actions.security.gha-curl-pipe-shell.gha-curl-pipe-shell",
    },
)
SEMGREP_POWERSHELL_ERROR_MARKER = (
    "metavariable-pattern failed when parsing $SHELL's content as Bash:"
)
SEMGREP_PARTIAL_RULE_RE = re.compile(
    r"When parsing a snippet as Bash for metavariable-pattern "
    r"in rule '([^'\r\n]+)'(?:,|$)"
)
POWERSHELL_SHELL_RE = re.compile(r"^\s*(?:pwsh|powershell)(?:\s|$)", re.IGNORECASE)
SEMGREP_TRUNCATION_RE = re.compile(r"\.\.\. \(truncated \d+ more characters\)$")
SEMGREP_MIN_TRUNCATED_SNIPPET_LENGTH = 80
SEMGREP_BATCH_TARGET_LIMIT = 100
SEMGREP_COMMAND_LENGTH_LIMIT = 24_000
# Lefthook owns the outer deadline; these child-process budgets must finish first.
DEFAULT_SUBPROCESS_TIMEOUT_SECONDS = 90
SEMGREP_TIMEOUT_SECONDS = 840
MYPY_TIMEOUT_SECONDS = 840
WORKFLOW_LOCAL_TIMEOUT_SECONDS = 1_740
# Scope the workflow-local gate to workflows this push changed versus the
# origin/main merge base (three-dot diff). Lefthook's {push_files} is a
# two-dot tree diff against the stale remote tip, so a rebase or force-push
# imports every workflow main advanced past; those are not this branch's
# delta. Override the base ref for tests or non-standard remotes.
WORKFLOW_LOCAL_BASE_REF_ENV = "WORKFLOW_LOCAL_BASE_REF"
WORKFLOW_LOCAL_DEFAULT_BASE = "origin/main"
TEST_SUITE_TIMEOUT_SECONDS = 1_740
CLI_E2E_TIMEOUT_SECONDS = 1_140
SKIPPED_DASH_PREFIXES = (
    "node_modules/",
    ".venv/",
    ".serena/cache/",
    "tests/hooks/fixtures/",
)
GIT_ENV_KEYS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_GRAFT_FILE",
    "GIT_SHALLOW_FILE",
)
WINDOWS_FORBIDDEN_PATH_CHARS = frozenset('<>:"|?*')
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
    | {
        f"{prefix}{suffix}"
        for prefix in ("COM", "LPT")
        for suffix in (
            "\N{SUPERSCRIPT ONE}",
            "\N{SUPERSCRIPT TWO}",
            "\N{SUPERSCRIPT THREE}",
        )
    },
)
GENERATED_PATHS = {
    "mcp": (
        ".vscode/mcp.json",
        ".factory/mcp.json",
    ),
    "causal": (".agents/memory/causality/causal-graph.json",),
    "memory-index": (".serena/memories/memory-index.md",),
}
GENERATED_GLOBS = {
    "agents": (
        "src/copilot-cli/agents/*.agent.md",
        "src/vs-code-agents/*.agent.md",
        "docs/agent-catalog.md",
    ),
    "episodes": (".agents/memory/episodes/episode-*.json",),
    "memory": (".serena/memories/**/*.md",),
}


@dataclass(frozen=True, slots=True)
class PushRef:
    local_ref: str
    local_sha: str
    remote_ref: str
    remote_sha: str

    @property
    def is_deletion(self) -> bool:
        return _is_zero_sha(self.local_sha)

    @property
    def is_new(self) -> bool:
        return _is_zero_sha(self.remote_sha)


@dataclass(frozen=True, slots=True)
class PushUpdate:
    source: PushRef
    base: str
    head: str
    range_spec: str
    destination_branch: str | None


def _clean_git_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in GIT_ENV_KEYS:
        env.pop(key, None)
    for key in tuple(env):
        if key.startswith(("GIT_TEST_COMMIT_GRAPH", "SEMGREP_")):
            env.pop(key)
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["GIT_TEST_COMMIT_GRAPH"] = "0"
    return env


def _run_command(
    args: Sequence[str],
    repo_root: Path,
    *,
    input_text: str | None = None,
    extra_env: Mapping[str, str] | None = None,
    process_env: Mapping[str, str] | None = None,
    timeout_seconds: float = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    env = dict(process_env) if process_env is not None else _clean_git_env()
    if extra_env is not None:
        env.update(extra_env)
    command = list(args)
    try:
        return subprocess.run(
            command,
            cwd=repo_root,
            env=env,
            input=input_text,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        stdout = _timeout_text(error.stdout)
        stderr = _append_timeout_message(
            _timeout_text(error.stderr),
            _timeout_message(command, timeout_seconds),
        )
        return subprocess.CompletedProcess(command, 3, stdout, stderr)


def _run_command_bytes(
    args: Sequence[str],
    repo_root: Path,
    *,
    timeout_seconds: float = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[bytes]:
    command = list(args)
    try:
        return subprocess.run(
            command,
            cwd=repo_root,
            env=_clean_git_env(),
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        stdout = _timeout_bytes(error.stdout)
        stderr = _append_timeout_bytes(
            _timeout_bytes(error.stderr),
            _timeout_message(command, timeout_seconds).encode(),
        )
        return subprocess.CompletedProcess(command, 3, stdout, stderr)


def _timeout_text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _timeout_bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    if isinstance(value, str):
        return value.encode()
    return value


def _timeout_message(args: Sequence[str], timeout_seconds: float) -> str:
    subject = _timeout_subject(args)
    return f"ERROR: {subject} timed out after {timeout_seconds:g} seconds\n"


def _timeout_subject(args: Sequence[str]) -> str:
    if not args:
        return "subprocess"
    executable = Path(args[0]).name
    if executable.startswith("python"):
        return _python_timeout_subject(executable, args[1:])
    if executable == "git":
        return _git_timeout_subject(args[1:])
    if executable in {"gh", "lefthook", "uv"} and len(args) > 1:
        subcommand = _safe_timeout_token(args[1])
        if subcommand is not None:
            return f"{executable} {subcommand}"
    return executable


def _python_timeout_subject(executable: str, args: Sequence[str]) -> str:
    if len(args) >= 2 and args[0] == "-m":
        module = _safe_timeout_token(args[1])
        return f"{executable} -m {module}" if module is not None else executable
    if not args:
        return executable
    script = _safe_timeout_token(Path(args[0]).name)
    if script is None:
        return executable
    subject = f"{executable} {script}"
    if len(args) > 1:
        subcommand = _safe_timeout_token(args[1])
        if subcommand is not None:
            subject = f"{subject} {subcommand}"
    return subject


def _git_timeout_subject(args: Sequence[str]) -> str:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "-c":
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        subcommand = _safe_timeout_token(token)
        return f"git {subcommand}" if subcommand is not None else "git"
    return "git"


def _safe_timeout_token(token: str) -> str | None:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", token):
        return token
    return None


def _append_timeout_message(stderr: str, message: str) -> str:
    separator = "" if not stderr or stderr.endswith("\n") else "\n"
    return f"{stderr}{separator}{message}"


def _append_timeout_bytes(stderr: bytes, message: bytes) -> bytes:
    separator = b"" if not stderr or stderr.endswith(b"\n") else b"\n"
    return stderr + separator + message


def _run_git(
    repo_root: Path,
    args: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    return _run_command(_git_command(args), repo_root)


def _run_git_bytes(
    repo_root: Path,
    args: Sequence[str],
) -> subprocess.CompletedProcess[bytes]:
    return _run_command_bytes(_git_command(args), repo_root)


def _git_command(args: Sequence[str]) -> list[str]:
    return ["git", "-c", "core.commitGraph=false", *args]


def _safe_relative_path(raw_path: str) -> str | None:
    if "\\" in raw_path:
        return None
    path = PurePosixPath(raw_path)
    if not raw_path or path.is_absolute() or ".." in path.parts:
        return None
    return path.as_posix()


def _safe_output_path(repo_root: Path, relative_path: str) -> Path | None:
    safe_path = _safe_relative_path(relative_path)
    if safe_path is None:
        return None
    resolved_root = repo_root.resolve()
    candidate = repo_root / safe_path
    current = candidate
    while current != repo_root:
        if current.is_symlink():
            return None
        current = current.parent
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError:
        return None
    return candidate


def check_generated_paths(kind: str, repo_root: Path) -> int:
    paths = list(GENERATED_PATHS.get(kind, ()))
    paths.extend(pattern.split("*", 1)[0].rstrip("/") for pattern in GENERATED_GLOBS.get(kind, ()))
    for relative_path in paths:
        if _safe_output_path(repo_root, relative_path) is None:
            print(f"ERROR: unsafe generated output path: {relative_path}", file=sys.stderr)
            return 2
    return 0


def _read_index_blob(repo_root: Path, relative_path: str) -> bytes | None:
    result = _run_git(repo_root, ["show", f":{relative_path}"])
    if result.returncode != 0:
        return None
    return result.stdout.encode("utf-8")


def _read_head_blob(repo_root: Path, relative_path: str) -> bytes | None:
    result = _run_git(repo_root, ["show", f"HEAD:{relative_path}"])
    if result.returncode != 0:
        return None
    return result.stdout.encode("utf-8")


def check_branch(repo_root: Path) -> int:
    result = _run_git(repo_root, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if result.returncode == 1:
        return 0
    if result.returncode != 0:
        print("ERROR: could not determine the current branch", file=sys.stderr)
        return 2
    branch = result.stdout.strip()
    if branch not in {"main", "master"}:
        return 0
    print(f"ERROR: cannot commit or push directly to '{branch}'", file=sys.stderr)
    return 1


def _current_branch(repo_root: Path) -> str | None:
    """Return the current branch name, or None when it cannot be determined.

    Empty output is a detached HEAD; a nonzero exit means git could not
    answer. Both collapse to None so the caller fails open.
    """
    result = _run_git(repo_root, ["branch", "--show-current"])
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def _recent_date_prefixes() -> tuple[str, str]:
    """Return today's and yesterday's UTC date strings for cross-midnight tolerance."""
    from datetime import timedelta

    now = datetime.now(tz=UTC)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    return today, yesterday


def _recent_session_candidates(sessions_dir: Path) -> list[Path] | None:
    """Return today's and yesterday's session logs, or None if unreadable.

    The two-day window handles cross-midnight UTC sessions. Returning None
    rather than an empty list keeps "directory unreadable" distinguishable
    from "no logs today", because both callers fail open on the former.
    """
    if not sessions_dir.is_dir():
        return None
    today, yesterday = _recent_date_prefixes()
    candidates: list[Path] = []
    try:
        candidates.extend(sessions_dir.glob(f"{today}-session-*.json"))
        candidates.extend(sessions_dir.glob(f"{yesterday}-session-*.json"))
    except OSError:
        return None
    return candidates


def _session_log_for_branch(sessions_dir: Path, branch: str) -> Path | None:
    """Return a recent session log whose branch field is ``branch``."""
    candidates = _recent_session_candidates(sessions_dir)
    if candidates is None:
        return None
    for candidate in sorted(candidates):
        if _session_branch(candidate) == branch:
            return candidate
    return None


def _is_merged_history(repo_root: Path, path: Path) -> bool:
    """Return True when ``path`` already exists on the upstream default branch.

    A committed merge of main imports the previously merged branch's session
    log. That file is newer by mtime than anything the current branch owns, so
    it wins the recency comparison and names a branch this one has never been
    near (issue #3343). The MERGE_HEAD exemption cannot help: it expires when
    the merge commit is created, while the imported file stays forever.

    Existing on the upstream default branch is the discriminator. A log that
    merged is settled history, not a statement about what the developer is
    working on now. A log authored on some other local branch is not there, so
    the co-mingling case from issue #682 keeps its teeth.

    Fails closed on every indeterminate answer it can observe: a path outside
    the repo, no resolvable ``origin/HEAD``, or a failed probe all return False
    and the mismatch still blocks.

    It cannot fail closed on git being unavailable, and does not claim to.
    ``_run_command`` catches only ``TimeoutExpired``, so a missing git binary
    raises ``FileNotFoundError`` past this function into the blanket handler in
    ``check_branch_context``, which returns 0. That is the deliberate fail-open
    contract of the caller, not an exemption this function grants, and
    ``_current_branch`` would already have taken the same exit several lines
    earlier. Pinned by
    ``test_branch_context_fails_open_when_git_is_unavailable``.
    """
    try:
        relative = path.relative_to(repo_root).as_posix()
    except ValueError:
        return False
    head = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "origin/HEAD"])
    upstream = head.stdout.strip() if head.returncode == 0 else ""
    if not upstream:
        return False
    probe = _run_git(repo_root, ["cat-file", "-e", f"{upstream}:{relative}"])
    return probe.returncode == 0


def _today_session_log(sessions_dir: Path) -> Path | None:
    """Return the newest recent session log by mtime, or None.

    Checks both today's and yesterday's UTC dates to handle cross-midnight
    sessions gracefully. Follows hook_utilities.get_today_session_log selection
    semantics (newest UTC-dated session log by mtime) with the per-file stat
    resilience of hook_utilities._newest_by_mtime: a single unreadable candidate
    (deleted or renamed mid-scan, permission race) is skipped rather than
    blinding the check to every other valid log. An empty match or an unreadable
    directory yields None so branch-context checking fails open.
    """
    candidates = _recent_session_candidates(sessions_dir)
    if candidates is None:
        return None
    best: Path | None = None
    best_mtime = float("-inf")
    for candidate in candidates:
        try:
            mtime = candidate.stat().st_mtime
        except OSError as exc:
            warnings.warn(
                f"Skipping unreadable session log {candidate}: {exc}",
                stacklevel=2,
            )
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best = candidate
    return best


def _split_frontmatter(content: str) -> tuple[str, str]:
    lines = content.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return "", content
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "".join(lines[1:index]), "".join(lines[index + 1 :])
    return "", content


def _has_duplicate_frontmatter_keys(frontmatter: str) -> bool:
    seen: set[str] = set()
    for line in frontmatter.splitlines():
        if line.startswith((" ", "\t")):
            continue
        match = FRONTMATTER_FIELD_RE.match(line)
        if match is None:
            continue
        key = match.group(1)
        if key in seen:
            return True
        seen.add(key)
    return False


def _parse_frontmatter(frontmatter: str) -> dict[str, object] | None:
    if _has_duplicate_frontmatter_keys(frontmatter):
        return None
    try:
        loaded = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        return None
    if loaded is None:
        return {}
    return loaded if isinstance(loaded, dict) else None


def _only_implemented_field_changed(
    old_frontmatter: str,
    new_frontmatter: str,
) -> bool:
    old_fields = _parse_frontmatter(old_frontmatter)
    new_fields = _parse_frontmatter(new_frontmatter)
    if old_fields is None or new_fields is None:
        return False
    changed = {
        key
        for key in old_fields.keys() | new_fields.keys()
        if old_fields.get(key) != new_fields.get(key)
    }
    return bool(changed) and changed <= {"implemented"}


def _is_frontmatter_only_metadata_change(path: str, repo_root: Path) -> bool:
    old_blob = _read_head_blob(repo_root, path)
    new_blob = _read_index_blob(repo_root, path)
    if old_blob is None or new_blob is None:
        return False
    old_frontmatter, old_body = _split_frontmatter(old_blob.decode("utf-8", errors="replace"))
    new_frontmatter, new_body = _split_frontmatter(new_blob.decode("utf-8", errors="replace"))
    if not old_frontmatter or not new_frontmatter or old_body != new_body:
        return False
    return _only_implemented_field_changed(old_frontmatter, new_frontmatter)


def _is_skill_frontmatter_only_change(path: str, repo_root: Path) -> bool:
    """Return True for a staged SKILL.md ADR-080 model-pin-only frontmatter edit.

    SkillForge validation (``validate-skill.py``) checks both the body
    (Triggers, Process, Verification, Scripts sections) and the frontmatter
    (required and allowed keys). A body-unchanged edit cannot regress the
    structural verdict, but a frontmatter edit still can, so this exemption is
    deliberately narrow: it skips validation only when the body text is
    unchanged from HEAD (bodies decoded as UTF-8 with ``errors="replace"`` and
    compared as strings, not raw bytes) AND the sole changed frontmatter keys
    are the ADR-080 model-pin
    fields (``model``, ``model-rationale``). Any other frontmatter delta, for
    example deleting ``name``/``description`` or introducing an unexpected key,
    still runs the validator. Mirrors the field-scoped precedent in
    ``_only_implemented_field_changed``.

    Returns False for newly added skills (no HEAD blob) so genuinely new skills
    are always validated.
    """
    old_blob = _read_head_blob(repo_root, path)
    new_blob = _read_index_blob(repo_root, path)
    if old_blob is None or new_blob is None:
        return False
    old_frontmatter, old_body = _split_frontmatter(old_blob.decode("utf-8", errors="replace"))
    new_frontmatter, new_body = _split_frontmatter(new_blob.decode("utf-8", errors="replace"))
    if not old_frontmatter or not new_frontmatter or old_body != new_body:
        return False
    return _only_model_pin_fields_changed(old_frontmatter, new_frontmatter)


_ADR080_MODEL_PIN_FIELDS = frozenset({"model", "model-rationale"})


def _only_model_pin_fields_changed(
    old_frontmatter: str,
    new_frontmatter: str,
) -> bool:
    old_fields = _parse_frontmatter(old_frontmatter)
    new_fields = _parse_frontmatter(new_frontmatter)
    # Require both parsed dicts non-empty (falsy covers None and {}). Comment-only
    # or whitespace-only frontmatter yaml-loads to an empty dict; treating that as
    # a model-pin-only change would skip validation on a SKILL.md that effectively
    # has no frontmatter fields, which is invalid and must be validated.
    if not old_fields or not new_fields:
        return False
    changed = {
        key
        for key in old_fields.keys() | new_fields.keys()
        if old_fields.get(key) != new_fields.get(key)
    }
    return bool(changed) and changed <= _ADR080_MODEL_PIN_FIELDS


def _gated_adr_review_paths(paths: Sequence[str], repo_root: Path) -> list[str]:
    gated: list[str] = []
    for path in paths:
        if ADR_REVIEW_PATH_RE.search(path) is None:
            continue
        if ADR_PATH_RE.search(path) and _is_frontmatter_only_metadata_change(path, repo_root):
            continue
        gated.append(path)
    return gated


def _extract_adr_ids(paths: Sequence[str]) -> set[str]:
    return {
        match.group(0).upper()
        for path in paths
        if (match := ADR_ID_RE.search(Path(path).name)) is not None
    }


def _debate_references_adr(debate_path: Path, adr_ids: set[str]) -> bool:
    if debate_path.is_symlink():
        return False
    try:
        content = debate_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    referenced = {match.group(0).upper() for match in ADR_ID_RE.finditer(content)}
    return bool(referenced & adr_ids)


def _session_has_adr_review(session_log: Path) -> bool:
    if session_log.is_symlink():
        return False
    try:
        content = session_log.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(pattern.search(content) for pattern in ADR_REVIEW_PATTERNS)


def check_adr_review_policy(paths: Sequence[str], repo_root: Path) -> int:
    gated_paths = _gated_adr_review_paths(paths, repo_root)
    if not gated_paths:
        return 0

    session_log = _today_session_log(repo_root / ".agents" / "sessions")
    if session_log is None or not _session_has_adr_review(session_log):
        print(
            "ERROR: ADR changes require adr-review evidence in today's session log",
            file=sys.stderr,
        )
        return 1

    analysis_dir = repo_root / ".agents" / "analysis"
    try:
        debate_logs = list(analysis_dir.glob("*debate*.md"))
    except OSError:
        debate_logs = []
    if not debate_logs:
        print("ERROR: ADR changes require a debate log in .agents/analysis", file=sys.stderr)
        return 1

    adr_ids = _extract_adr_ids(gated_paths)
    if adr_ids and not any(_debate_references_adr(path, adr_ids) for path in debate_logs):
        names = ", ".join(sorted(adr_ids))
        print(f"ERROR: no debate log references the staged ADR IDs: {names}", file=sys.stderr)
        return 1
    return 0


def _session_has_retrospective_evidence(session_log: Path) -> bool:
    if session_log.is_symlink():
        return False
    try:
        content = session_log.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(pattern.search(content) for pattern in RETROSPECTIVE_EVIDENCE_PATTERNS)


def _today_retrospective_exists(repo_root: Path) -> bool:
    retro_dir = repo_root / ".agents" / "retrospective"
    if not retro_dir.is_dir():
        return False
    today, yesterday = _recent_date_prefixes()
    try:
        for prefix in (today, yesterday):
            if any(not path.is_symlink() for path in retro_dir.glob(f"{prefix}*.md")):
                return True
        return False
    except OSError:
        return False


def _documentation_only(paths: Sequence[str]) -> bool:
    return bool(paths) and all(
        any(pattern.search(path) for pattern in DOCUMENTATION_PATTERNS) for path in paths
    )


def _is_trivial_retrospective_session(
    session_log: Path | None,
    paths: Sequence[str],
    *,
    now_epoch: float | None = None,
) -> bool:
    if session_log is None or len(paths) != 1:
        return False
    try:
        created = session_log.stat().st_ctime
    except OSError:
        return False
    current = datetime.now(tz=UTC).timestamp() if now_epoch is None else now_epoch
    return current - created <= TRIVIAL_SESSION_SECONDS


def check_retrospective_evidence(paths: Sequence[str], repo_root: Path) -> int:
    if os.environ.get("SKIP_RETROSPECTIVE_GATE") == "true":
        print("Retrospective policy bypassed via SKIP_RETROSPECTIVE_GATE=true")
        return 0
    if not paths:
        print(
            "WARNING: {push_files} empty; cannot determine documentation-only or "
            "trivial-session bypass—retrospective evidence still required",
            file=sys.stderr,
        )
    if paths and _documentation_only(paths):
        return 0

    session_log = _today_session_log(repo_root / ".agents" / "sessions")
    if paths and _is_trivial_retrospective_session(session_log, paths):
        return 0
    if _today_retrospective_exists(repo_root):
        return 0
    if session_log is not None and _session_has_retrospective_evidence(session_log):
        return 0

    print("ERROR: git push requires retrospective evidence for this session", file=sys.stderr)
    return 1


def _session_branch(session_log: Path) -> str | None:
    """Extract the expected branch from a session log.

    Canonical logs nest the branch at ``session.branch`` (see
    .agents/schemas/session-log.schema.json); pre-schema logs carry a
    top-level ``branch``. The nested value wins, then the top level.
    """
    try:
        data = json.loads(session_log.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    candidates: list[object] = []
    session = data.get("session")
    if isinstance(session, dict):
        candidates.append(session)
    candidates.append(data)
    for container in candidates:
        if isinstance(container, dict):
            branch = container.get("branch")
            if isinstance(branch, str):
                return branch
    return None


def check_branch_context(repo_root: Path) -> int:
    """Block a commit or push when the branch contradicts today's session log.

    Ported from the retired Claude PreToolUse hook
    ``invoke_branch_context_guard.py`` so the branch-mismatch safety net
    survives the move to Lefthook. Root cause: PR co-mingling from the
    PR #669 retrospective (Issue #682).

    The check is deliberately fail-open: it returns 0 (pass) on every
    ambiguous input and only returns 1 (block) when it can prove a
    mismatch. Retired-hook contract preserved verbatim:

        # Skip if no sessions directory (consumer repo)
        # Cannot determine branch, fail open
        # No session log, let session_log_guard handle this
        # No branch in session log, skip check

    Only a determinate ``current_branch != session_branch`` blocks. Two
    exemptions. A merge in progress is exempt: a merge legitimately imports
    another branch's newer session log into the tree, which would otherwise
    read as a mismatch. A committed merge is exempt on the same grounds but
    needs a different test, because ``MERGE_HEAD`` is gone by then while the
    imported log stays and keeps winning the recency comparison forever. That
    case requires both that the branch owns a recent log and that the newest
    log already exists on the upstream default branch, which makes it settled
    history rather than a claim about current work (issue #3343). A log
    authored on another local branch is not upstream, so the co-mingling case
    from issue #682 still blocks.
    """
    try:
        if _merge_in_progress(repo_root):
            return 0
        sessions_dir = repo_root / ".agents" / "sessions"
        if not sessions_dir.is_dir():
            return 0
        current_branch = _current_branch(repo_root)
        if current_branch is None:
            return 0
        session_log = _today_session_log(sessions_dir)
        if session_log is None:
            return 0
        session_branch = _session_branch(session_log)
        if session_branch is None:
            return 0
        if current_branch == session_branch:
            return 0
        if _session_log_for_branch(sessions_dir, current_branch) is not None and _is_merged_history(
            repo_root, session_log
        ):
            return 0
        print(
            "ERROR: branch context mismatch: "
            f"current='{current_branch}', session='{session_branch}' "
            f"(log: {session_log.name})",
            file=sys.stderr,
        )
        print(
            "  Fix: switch to the expected branch, update the session log branch "
            "field, or run /session-init for the current branch.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        return 0


def check_handoff(paths: Sequence[str], repo_root: Path) -> int:
    del repo_root
    normalized = {_safe_relative_path(path) for path in paths}
    if ".agents/HANDOFF.md" not in normalized:
        return 0
    print("ERROR: .agents/HANDOFF.md is read-only", file=sys.stderr)
    return 1


def _merge_in_progress(repo_root: Path) -> bool:
    result = _run_git(repo_root, ["rev-parse", "--git-path", "MERGE_HEAD"])
    if result.returncode != 0:
        return False
    merge_head = Path(result.stdout.strip())
    if not merge_head.is_absolute():
        merge_head = repo_root / merge_head
    return merge_head.is_file()


def check_sessions(paths: Sequence[str], repo_root: Path) -> int:
    if _merge_in_progress(repo_root):
        return 0
    sessions = [
        path
        for raw_path in paths
        if (path := _safe_relative_path(raw_path)) and SESSION_PATH_RE.fullmatch(path)
    ]
    if not sessions:
        print("ERROR: staged .agents changes require a JSON session log", file=sys.stderr)
        return 1
    for session in sessions:
        result = _run_command(
            [
                sys.executable,
                "scripts/validate_session_json.py",
                session,
                "--pre-commit",
            ],
            repo_root,
        )
        if result.returncode != 0:
            _print_process_output(result)
            return result.returncode
    return 0


def check_commit_message(message_path: Path) -> int:
    if not message_path.is_file():
        return 0
    message = message_path.read_text(encoding="utf-8", errors="replace")
    if not any(dash in message for dash in PROHIBITED_DASHES):
        return 0
    print(
        "ERROR: commit message contains em-dash (U+2014) or en-dash (U+2013)",
        file=sys.stderr,
    )
    return 1


def check_staged_dashes(paths: Sequence[str], repo_root: Path) -> int:
    violations: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe staged path: {raw_path}", file=sys.stderr)
            return 2
        if path.startswith(SKIPPED_DASH_PREFIXES):
            continue
        content = _read_index_blob(repo_root, path)
        if content is None:
            continue
        text = content.decode("utf-8", errors="replace")
        if any(dash in text for dash in PROHIBITED_DASHES):
            violations.append(path)
    if not violations:
        return 0
    print("ERROR: staged markdown contains prohibited Unicode dashes:", file=sys.stderr)
    for path in violations:
        print(f"  {path}", file=sys.stderr)
    return 1


def check_staged_action_pins(paths: Sequence[str], repo_root: Path) -> int:
    violations: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            return 2
        content = _read_index_blob(repo_root, path)
        if content is None:
            continue
        violations.extend(_action_pin_violations(path, content))
    if not violations:
        return 0
    print("ERROR: GitHub Actions must be pinned to commit SHAs:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


def _action_pin_violations(path: str, content: bytes) -> list[str]:
    violations: list[str] = []
    for line_number, line in enumerate(
        content.decode("utf-8", errors="replace").splitlines(),
        start=1,
    ):
        if LOCAL_ACTION_PATTERN.search(line):
            continue
        if VERSION_TAG_PATTERN.match(line):
            violations.append(f"{path}:{line_number}")
    return violations


def check_github_bash_scripts(paths: Sequence[str], repo_root: Path) -> int:
    violations: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            return 2
        if not path.startswith(".github/scripts/"):
            continue
        content = _read_index_blob(repo_root, path)
        if content is None:
            continue
        first_line = content.splitlines()[0] if content else b""
        if Path(path).suffix in {".bash", ".sh"} or (
            first_line.startswith(b"#!") and b"bash" in first_line
        ):
            violations.append(path)
    if not violations:
        return 0
    print("ERROR: Bash scripts are prohibited under .github/scripts:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


def check_security_suppressions(paths: Sequence[str], repo_root: Path) -> int:
    violations: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe security-scan path: {raw_path}", file=sys.stderr)
            return 2
        full_path = repo_root / path
        if not full_path.is_file() or full_path.is_symlink():
            continue
        violations.extend(_security_suppression_violations(path, full_path))
    if not violations:
        return 0
    print("ERROR: security suppression comments detected:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


def _security_suppression_violations(path: str, full_path: Path) -> list[str]:
    violations: list[str] = []
    for line_number, line in enumerate(
        full_path.read_text(encoding="utf-8", errors="replace").splitlines(),
        start=1,
    ):
        if SECURITY_SUPPRESSION_RE.search(line):
            violations.append(f"{path}:{line_number}")
    return violations


def _generated_candidates(kind: str, repo_root: Path) -> list[Path]:
    candidates = [repo_root / path for path in GENERATED_PATHS.get(kind, ())]
    for pattern in GENERATED_GLOBS.get(kind, ()):
        candidates.extend(repo_root.glob(pattern))
    return sorted(set(candidates))


def _matches_generated_glob(relative_path: str, pattern: str) -> bool:
    path_parts = PurePosixPath(relative_path).parts
    pattern_parts = PurePosixPath(pattern).parts
    matches = [True]
    for pattern_part in pattern_parts:
        matches.append(matches[-1] and pattern_part == "**")
    for path_part in path_parts:
        next_matches = [False]
        for index, pattern_part in enumerate(pattern_parts, start=1):
            if pattern_part == "**":
                next_matches.append(next_matches[index - 1] or matches[index])
                continue
            next_matches.append(matches[index - 1] and fnmatch(path_part, pattern_part))
        matches = next_matches
    return matches[-1]


def _is_allowlisted_generated_path(kind: str, relative_path: str) -> bool:
    if relative_path in GENERATED_PATHS.get(kind, ()):
        return True
    return any(
        _matches_generated_glob(relative_path, pattern) for pattern in GENERATED_GLOBS.get(kind, ())
    )


def _deleted_generated_candidates(kind: str, repo_root: Path) -> list[Path] | None:
    result = _run_git_bytes(
        repo_root,
        ["diff", "--name-only", "--diff-filter=D", "-z", "--"],
    )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout.decode("utf-8", errors="replace"), end="")
        if result.stderr:
            print(
                result.stderr.decode("utf-8", errors="replace"),
                end="",
                file=sys.stderr,
            )
        return None

    candidates: list[Path] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        relative_path = os.fsdecode(raw_path)
        safe_path = _safe_relative_path(relative_path)
        candidate = _safe_output_path(repo_root, relative_path)
        if safe_path is None or candidate is None:
            print(
                f"ERROR: unsafe tracked deletion path: {relative_path}",
                file=sys.stderr,
            )
            return None
        if _is_allowlisted_generated_path(kind, safe_path):
            candidates.append(candidate)
    return candidates


def stage_generated(kind: str, repo_root: Path) -> int:
    safety_result = check_generated_paths(kind, repo_root)
    if safety_result != 0:
        return safety_result
    deleted_candidates = _deleted_generated_candidates(kind, repo_root)
    if deleted_candidates is None:
        return 2
    tracked_deletions = set(deleted_candidates)
    candidates = set(_generated_candidates(kind, repo_root))
    candidates.update(tracked_deletions)
    relative_paths: list[str] = []
    for candidate in sorted(candidates):
        if not candidate.exists() and candidate not in tracked_deletions:
            continue
        try:
            relative_path = candidate.relative_to(repo_root).as_posix()
        except ValueError:
            return 2
        if _safe_output_path(repo_root, relative_path) is None:
            print(f"ERROR: refusing to stage unsafe path: {relative_path}", file=sys.stderr)
            return 2
        relative_paths.append(relative_path)
    if not relative_paths:
        return 0
    result = _run_git(repo_root, ["add", "--", *relative_paths])
    if result.returncode != 0:
        _print_process_output(result)
    return result.returncode


def extract_session_episodes(paths: Sequence[str], repo_root: Path) -> int:
    if check_generated_paths("episodes", repo_root) != 0:
        return 2
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None or not SESSION_PATH_RE.fullmatch(path):
            print(f"ERROR: invalid session path: {raw_path}", file=sys.stderr)
            return 2
        result = _run_command(
            [
                sys.executable,
                ".claude/skills/memory/scripts/extract_session_episode.py",
                path,
                "--preserve",
                "--pending-stage",
            ],
            repo_root,
        )
        if result.returncode != 0:
            _print_advisory_failure("episode extraction", result)
            continue
        episode_id = _episode_id_from_output(result.stdout)
        if episode_id is None:
            print("WARNING: episode extraction returned no valid id", file=sys.stderr)
            continue
        stage_result = _stage_episode(episode_id, repo_root)
        if stage_result != 0:
            return stage_result
    return 0


def _episode_id_from_output(stdout: str) -> str | None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    episode_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(episode_id, str) or not EPISODE_ID_RE.fullmatch(episode_id):
        return None
    return episode_id


def _stage_episode(episode_id: str, repo_root: Path) -> int:
    relative_path = f".agents/memory/episodes/{episode_id}.json"
    episode_path = _safe_output_path(repo_root, relative_path)
    if episode_path is None:
        print(f"ERROR: unsafe generated episode path: {relative_path}", file=sys.stderr)
        return 2
    if not episode_path.is_file():
        print(f"WARNING: generated episode not found: {relative_path}", file=sys.stderr)
        return 0
    result = _run_git(repo_root, ["add", "--", relative_path])
    return result.returncode


def _staged_episode_paths(repo_root: Path, diff_filter: str) -> list[str] | None:
    result = _run_git(
        repo_root,
        [
            "diff",
            "--cached",
            "--name-only",
            "-z",
            f"--diff-filter={diff_filter}",
            "--",
            ".agents/memory/episodes",
        ],
    )
    if result.returncode != 0:
        return None
    return [
        path
        for raw_path in result.stdout.split("\0")
        if (path := _safe_relative_path(raw_path)) and EPISODE_PATH_RE.fullmatch(path)
    ]


def update_causal_graph(repo_root: Path) -> int:
    staged = _staged_episode_paths(repo_root, "ACMR")
    deleted = _staged_episode_paths(repo_root, "D")
    if staged is None or deleted is None:
        return 2
    if not staged and not deleted:
        return 0
    relative_graph = ".agents/memory/causality/causal-graph.json"
    graph_path = _safe_output_path(repo_root, relative_graph)
    if graph_path is None:
        print("ERROR: unsafe causal graph output path", file=sys.stderr)
        return 2
    try:
        snapshot = graph_path.read_bytes()
    except FileNotFoundError:
        snapshot = None
    except OSError as exc:
        print(f"ERROR: could not snapshot causal graph: {exc}", file=sys.stderr)
        return 2
    result = _apply_causal_graph_updates(staged, deleted, graph_path, repo_root)
    if result == 0:
        return _stage_causal_graph(graph_path, repo_root)
    _restore_file(graph_path, snapshot)
    print("WARNING: causal graph update failed; original graph restored", file=sys.stderr)
    return 0


def _apply_causal_graph_updates(
    staged: Sequence[str],
    deleted: Sequence[str],
    graph_path: Path,
    repo_root: Path,
) -> int:
    prune_result = _prune_deleted_episodes(deleted, graph_path, repo_root)
    if prune_result != 0:
        return prune_result
    with tempfile.TemporaryDirectory(prefix="lefthook-causal-") as temp_dir:
        return _apply_staged_episodes(
            staged,
            Path(temp_dir),
            graph_path,
            repo_root,
        )


def _apply_staged_episodes(
    staged: Sequence[str],
    temp_dir: Path,
    graph_path: Path,
    repo_root: Path,
) -> int:
    for index, relative_path in enumerate(staged):
        content = _read_index_blob(repo_root, relative_path)
        if content is None:
            return 1
        staged_path = temp_dir / f"{index}-{Path(relative_path).name}"
        staged_path.write_bytes(content)
        result = _run_causal_updater(staged_path, graph_path, repo_root)
        if result != 0:
            return result
    return 0


def _prune_deleted_episodes(
    deleted: Sequence[str],
    graph_path: Path,
    repo_root: Path,
) -> int:
    episode_ids = [_deleted_episode_id(path, repo_root) for path in deleted]
    if not episode_ids:
        return 0
    missing = repo_root / ".agents/memory/episodes/__prune_only__"
    result = _run_command(
        [
            sys.executable,
            ".claude/skills/memory/scripts/update_causal_graph.py",
            "--prune-episode-ids",
            ",".join(episode_ids),
            "--episode-path",
            str(missing),
            "--graph-path",
            str(graph_path),
        ],
        repo_root,
    )
    if result.returncode != 0:
        _print_process_output(result)
    return result.returncode


def _deleted_episode_id(relative_path: str, repo_root: Path) -> str:
    content = _read_head_blob(repo_root, relative_path)
    if content is not None:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = None
        episode_id = payload.get("id") if isinstance(payload, dict) else None
        if isinstance(episode_id, str):
            return episode_id
    return Path(relative_path).stem


def _run_causal_updater(
    episode_path: Path,
    graph_path: Path,
    repo_root: Path,
) -> int:
    result = _run_command(
        [
            sys.executable,
            ".claude/skills/memory/scripts/update_causal_graph.py",
            "--episode-path",
            str(episode_path),
            "--graph-path",
            str(graph_path),
        ],
        repo_root,
    )
    if result.returncode != 0:
        _print_process_output(result)
    return result.returncode


def _restore_file(path: Path, snapshot: bytes | None) -> None:
    if snapshot is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(snapshot)


def _stage_causal_graph(graph_path: Path, repo_root: Path) -> int:
    if not graph_path.is_file():
        return 0
    relative_path = graph_path.relative_to(repo_root).as_posix()
    result = _run_git(repo_root, ["add", "--", relative_path])
    return result.returncode


# --- mypy diff-line ratchet (issue #2993) --------------------------------
# The pre-push mypy gate used to block on ANY error mypy reported in a touched
# file, including pre-existing debt the current push never changed. That
# coupled unrelated shared-file edits to old type errors and blocked pushes.
# The ratchet below blocks only on errors whose line was added or modified
# versus the merge base, so a push is judged on the lines it actually changed.
#
# A stored per-file signature baseline was rejected: mypy's reported error set
# is invocation-dependent (the same file yields different errors checked alone
# versus batched with siblings, because module resolution changes). Diff
# locality is invocation-independent, so it survives the batch/isolation split
# that _mypy_invocations() creates.
MYPY_RATCHET_BASE_REF_ENV = "MYPY_RATCHET_BASE_REF"
MYPY_RATCHET_DEFAULT_BASE = "origin/main"
# mypy default output: "path:line: error: message  [code]"; the column is
# absent in this repo's config but tolerated. Only ``error`` severity blocks;
# ``note`` lines are advisory and ignored.
MYPY_ERROR_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+):(?:\d+:)?\s*error:")
# Unified diff (``--unified=0``) markers. ``+++ b/<path>`` names the file; the
# ``+c,d`` field of each hunk header is the changed-line span (post-image).
DIFF_ADDED_FILE_RE = re.compile(r"^\+\+\+ b/(?P<path>.+)$")
DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


def _normalize_ratchet_path(path: str) -> str:
    # mypy on Windows can echo OS-native backslash separators, while git diff
    # names and command-line inputs are forward-slash; normalize so the pushed
    # set, the changed-line map, and parsed mypy paths compare equal.
    cleaned = path.strip().replace("\\", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _mypy_ratchet_base_ref() -> str:
    raw = os.environ.get(MYPY_RATCHET_BASE_REF_ENV, "").strip()
    if raw and not _is_zero_sha(raw):
        return raw
    return MYPY_RATCHET_DEFAULT_BASE


def _parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    # Post-image line numbers touched per file: both added and modified lines
    # land in the ``+start,count`` span. Two hunk shapes intentionally
    # contribute nothing, so the ratchet never blocks mypy errors on them:
    #   * Deletion-only hunks (``+N,0``) touch no post-image line. Adding
    #     ``start`` here would flag errors on an unchanged neighboring line,
    #     reintroducing the false positives on untouched code that the
    #     per-file gate produced before this ratchet (issue #2993).
    #   * Pure renames carry no ``+++ b/`` hunk, so the renamed path stays
    #     absent from the map; unchanged content cannot add new type debt.
    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        file_match = DIFF_ADDED_FILE_RE.match(line)
        if file_match is not None:
            current = _normalize_ratchet_path(file_match.group("path"))
            changed.setdefault(current, set())
            continue
        hunk_match = DIFF_HUNK_RE.match(line)
        if hunk_match is None or current is None:
            continue
        start = int(hunk_match.group("start"))
        count_raw = hunk_match.group("count")
        count = int(count_raw) if count_raw is not None else 1
        changed[current].update(range(start, start + count))
    return changed


def _changed_line_map(
    paths: Sequence[str],
    repo_root: Path,
    base_ref: str,
) -> dict[str, set[int]] | None:
    """Return added or modified line numbers per path versus ``base_ref``.

    ``None`` signals that the diff base could not be resolved; callers then
    fall back to blocking on any error so the gate is never weaker than before.
    """
    if not paths:
        return {}
    result = _run_git(
        repo_root,
        ["diff", "--unified=0", "--no-color", f"{base_ref}...HEAD", "--", *paths],
    )
    if result.returncode != 0:
        return None
    return _parse_changed_lines(result.stdout)


def _parse_mypy_error_locations(stdout: str) -> list[tuple[str, int]]:
    locations: list[tuple[str, int]] = []
    for line in stdout.splitlines():
        match = MYPY_ERROR_RE.match(line)
        if match is None:
            continue
        locations.append(
            (_normalize_ratchet_path(match.group("path")), int(match.group("line"))),
        )
    return locations


def _mypy_result_blocks(
    result: subprocess.CompletedProcess[str],
    pushed: set[str],
    changed_lines: dict[str, set[int]] | None,
) -> bool:
    if result.returncode == 0:
        return False
    locations = _parse_mypy_error_locations(result.stdout)
    if not locations:
        # Non-zero exit with no parseable error line is a fatal invocation
        # failure (crash, bad package name, hyphenated dir); block it.
        return True
    if changed_lines is None:
        # Diff base unresolved: block on any error (pre-ratchet behavior).
        return True
    return any(
        path in pushed and line in changed_lines.get(path, frozenset()) for path, line in locations
    )


def run_mypy(paths: Sequence[str], repo_root: Path) -> int:
    checked_paths: list[str] = []
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe mypy path: {raw_path}", file=sys.stderr)
            return 2
        full_path = repo_root / path
        if not full_path.is_file():
            continue
        if full_path.is_symlink():
            print(f"ERROR: refusing to type-check symlink: {path}", file=sys.stderr)
            return 2
        checked_paths.append(path)
    if not checked_paths:
        return 0
    pushed = {_normalize_ratchet_path(path) for path in checked_paths}
    changed_lines = _changed_line_map(checked_paths, repo_root, _mypy_ratchet_base_ref())
    failed = False
    for invocation, needs_validation_path in _mypy_invocations(checked_paths):
        result = _invoke_mypy(invocation, repo_root, needs_validation_path)
        _print_process_output(result)
        if _mypy_result_blocks(result, pushed, changed_lines):
            failed = True
    return 1 if failed else 0


def _mypy_invocations(paths: Sequence[str]) -> list[tuple[list[str], bool]]:
    validation_paths: list[str] = []
    by_basename: dict[str, list[str]] = {}
    for path in paths:
        if path.startswith("scripts/validation/"):
            validation_paths.append(path)
            continue
        by_basename.setdefault(Path(path).name, []).append(path)
    unique: list[str] = []
    colliding: list[str] = []
    for basename_group in by_basename.values():
        if len(basename_group) == 1:
            unique.extend(basename_group)
        else:
            colliding.extend(basename_group)
    invocations: list[tuple[list[str], bool]] = []
    if unique:
        invocations.append((unique, False))
    invocations.extend(([path], False) for path in colliding)
    invocations.extend(([path], True) for path in validation_paths)
    return invocations


def _invoke_mypy(
    paths: Sequence[str],
    repo_root: Path,
    needs_validation_path: bool,
) -> subprocess.CompletedProcess[str]:
    extra_env = None
    if needs_validation_path:
        validation_path = str(repo_root / "scripts/validation")
        inherited = os.environ.get("MYPYPATH")
        value = f"{validation_path}{os.pathsep}{inherited}" if inherited else validation_path
        extra_env = {"MYPYPATH": value}
    return _run_command(
        [sys.executable, "-m", "mypy", "--", *paths],
        repo_root,
        extra_env=extra_env,
        timeout_seconds=MYPY_TIMEOUT_SECONDS,
    )


def _check_no_grafts(repo_root: Path) -> int:
    graft_path_result = _run_git(
        repo_root,
        ["rev-parse", "--git-path", "info/grafts"],
    )
    if graft_path_result.returncode != 0:
        print("ERROR: could not resolve the Git grafts path", file=sys.stderr)
        return 2
    graft_path_lines = graft_path_result.stdout.splitlines()
    if len(graft_path_lines) != 1 or not graft_path_lines[0]:
        print("ERROR: Git returned an invalid grafts path", file=sys.stderr)
        return 2
    grafts_path = Path(graft_path_lines[0])
    if not grafts_path.is_absolute():
        grafts_path = (repo_root / grafts_path).resolve()
    try:
        grafts = grafts_path.read_bytes()
    except FileNotFoundError:
        return 0
    except OSError as error:
        print(f"ERROR: could not read {grafts_path}: {error}", file=sys.stderr)
        return 2
    if not _has_graft_entries(grafts):
        return 0
    print(
        f"ERROR: active Git grafts are not allowed during push validation: {grafts_path}",
        file=sys.stderr,
    )
    return 2


def _check_history_integrity(repo_root: Path) -> int:
    shallow_result = _run_git(repo_root, ["rev-parse", "--is-shallow-repository"])
    if shallow_result.returncode != 0:
        print("ERROR: could not determine whether the repository is shallow", file=sys.stderr)
        return 2
    shallow_state = shallow_result.stdout.strip()
    if shallow_state not in {"false", "true"}:
        print(f"ERROR: unexpected shallow repository state: {shallow_state}", file=sys.stderr)
        return 2
    if shallow_state == "true":
        print(
            "ERROR: push validation requires complete Git history; fetch the full history",
            file=sys.stderr,
        )
        return 2
    return _check_no_grafts(repo_root)


def _has_graft_entries(grafts: bytes) -> bool:
    return any(
        line and not line.startswith(b"#")
        for raw_line in grafts.splitlines()
        if (line := raw_line.strip())
    )


def _push_updates(stream: TextIO, repo_root: Path) -> list[PushUpdate] | None:
    if _check_history_integrity(repo_root) != 0:
        return None
    try:
        push_refs = parse_push_refs(stream)
    except ValueError as error:
        print(f"ERROR: malformed pre-push input, {error}", file=sys.stderr)
        return None
    updates: list[PushUpdate] = []
    seen_heads: set[str] = set()
    for push_ref in push_refs:
        if push_ref.is_deletion or push_ref.local_sha in seen_heads:
            continue
        updates.append(resolve_push_update(push_ref, repo_root))
        seen_heads.add(push_ref.local_sha)
    return updates


def check_pushed_suppressions(stream: TextIO, repo_root: Path) -> int:
    updates = _push_updates(stream, repo_root)
    if updates is None:
        return 2
    violations: list[str] = []
    for update in updates:
        paths = _changed_commit_paths(update, repo_root)
        if paths is None:
            return 2
        head_violations = _head_suppression_violations(
            update.head,
            paths,
            repo_root,
        )
        if head_violations is None:
            return 2
        violations.extend(head_violations)
    if not violations:
        return 0
    print("ERROR: security suppression comments detected in pushed commits:", file=sys.stderr)
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    return 1


def _head_suppression_violations(
    head: str,
    paths: Sequence[str],
    repo_root: Path,
) -> list[str] | None:
    violations: list[str] = []
    for path in paths:
        if Path(path).suffix.lower() not in SEMGREP_SUFFIXES:
            continue
        content = _read_commit_blob(head, path, repo_root)
        if content is None:
            return None
        violations.extend(_suppression_violations_in_text(head, path, content))
    return violations


def _changed_commit_paths(
    update: PushUpdate,
    repo_root: Path,
) -> list[str] | None:
    if ".." not in update.range_spec:
        return _commit_paths(update.head, repo_root)
    result = _run_git(
        repo_root,
        [
            "diff",
            "--name-only",
            "--diff-filter=ACMRT",
            "-z",
            update.range_spec,
        ],
    )
    if result.returncode != 0:
        _print_process_output(result)
        return None
    paths: list[str] = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe path in pushed range: {raw_path}", file=sys.stderr)
            return None
        paths.append(path)
    return paths


def _commit_paths(head: str, repo_root: Path) -> list[str] | None:
    result = _run_git(repo_root, ["ls-tree", "-r", "-z", "--name-only", head])
    if result.returncode != 0:
        _print_process_output(result)
        return None
    paths: list[str] = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe path in pushed tree: {raw_path}", file=sys.stderr)
            return None
        paths.append(path)
    return paths


def _read_commit_blob(head: str, path: str, repo_root: Path) -> str | None:
    result = _run_git(repo_root, ["show", f"{head}:{path}"])
    if result.returncode != 0:
        _print_process_output(result)
        return None
    return result.stdout


def _suppression_violations_in_text(head: str, path: str, text: str) -> list[str]:
    return [
        f"{head[:12]}:{path}:{line_number}"
        for line_number, line in enumerate(text.splitlines(), start=1)
        if SECURITY_SUPPRESSION_RE.search(line)
    ]


def scan_pushed_heads(stream: TextIO, repo_root: Path) -> int:
    updates = _push_updates(stream, repo_root)
    if updates is None:
        return 2
    for update in updates:
        paths = _changed_commit_paths(update, repo_root)
        if paths is None:
            return 2
        tree_paths = _commit_paths(update.head, repo_root)
        if tree_paths is None or _validate_materialization_paths(tree_paths) is None:
            return 2
        scan_paths = [
            path for path in paths if PurePosixPath(path).suffix.lower() in SEMGREP_SUFFIXES
        ]
        if not scan_paths:
            continue
        result = _scan_pushed_head(update.head, scan_paths, repo_root)
        if result != 0:
            return result
    return 0


def _scan_pushed_head(
    head: str,
    paths: Sequence[str],
    repo_root: Path,
) -> int:
    with tempfile.TemporaryDirectory(prefix="lefthook-semgrep-") as temp_dir:
        tree = Path(temp_dir)
        materialized = _materialize_commit_tree(head, tree, repo_root, paths)
        if materialized != 0:
            return materialized
        result = _run_semgrep_tree(tree, paths, repo_root)
        _print_process_output(result)
        return result.returncode


def _materialize_commit_tree(
    head: str,
    destination: Path,
    repo_root: Path,
    paths: Sequence[str],
) -> int:
    validated_paths = _validate_materialization_paths(paths)
    if validated_paths is None:
        return 2
    for path in validated_paths:
        blob_id = _commit_blob_id(head, path, repo_root)
        if blob_id is None:
            return 2
        blob = _run_git_bytes(repo_root, ["cat-file", "blob", blob_id])
        if blob.returncode != 0:
            print(blob.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
            return 2
        output = destination / path
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("xb") as output_stream:
                output_stream.write(blob.stdout)
        except OSError as error:
            print(f"ERROR: cannot materialize pushed blob {path}: {error}", file=sys.stderr)
            return 2
    return 0


def _validate_materialization_paths(paths: Sequence[str]) -> list[str] | None:
    validated_paths: list[str] = []
    file_destinations: set[str] = set()
    directory_destinations: set[str] = set()
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe pushed blob path: {raw_path}", file=sys.stderr)
            return None
        destination_key = _filesystem_collision_key(path)
        if destination_key is None:
            print(f"ERROR: pushed path is not portable across filesystems: {path}", file=sys.stderr)
            return None
        destination_parts = destination_key.split("/")
        parent_destinations = {
            "/".join(destination_parts[:index]) for index in range(1, len(destination_parts))
        }
        if (
            destination_key in file_destinations
            or destination_key in directory_destinations
            or parent_destinations & file_destinations
        ):
            print(f"ERROR: pushed paths collide on disk: {path}", file=sys.stderr)
            return None
        file_destinations.add(destination_key)
        directory_destinations.update(parent_destinations)
        validated_paths.append(path)
    return validated_paths


def _commit_blob_id(head: str, path: str, repo_root: Path) -> str | None:
    result = _run_git_bytes(
        repo_root,
        ["ls-tree", "-z", head, "--", path],
    )
    if result.returncode != 0:
        print(result.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        return None
    records = [record for record in result.stdout.split(b"\0") if record]
    if len(records) != 1:
        print(
            f"ERROR: pushed tree does not contain exactly one entry for {path}",
            file=sys.stderr,
        )
        return None
    try:
        metadata, raw_name = records[0].split(b"\t", maxsplit=1)
        mode, object_type, object_id = metadata.decode("ascii").split()
    except (UnicodeDecodeError, ValueError):
        print(f"ERROR: malformed pushed tree entry for {path}", file=sys.stderr)
        return None
    if os.fsdecode(raw_name) != path:
        print(f"ERROR: pushed tree entry mismatch for {path}", file=sys.stderr)
        return None
    if object_type != "blob" or mode not in {"100644", "100755"}:
        print(f"ERROR: pushed tree entry is not a regular file: {path}", file=sys.stderr)
        return None
    return object_id


def _filesystem_collision_key(path: str) -> str | None:
    normalized_parts: list[str] = []
    for part in PurePosixPath(path).parts:
        normalized = unicodedata.normalize("NFC", part)
        trimmed = normalized.rstrip(" .")
        base_name = trimmed.split(".", maxsplit=1)[0].upper()
        if (
            trimmed != normalized
            or base_name in WINDOWS_RESERVED_NAMES
            or any(
                ord(character) < 32 or character in WINDOWS_FORBIDDEN_PATH_CHARS
                for character in normalized
            )
        ):
            return None
        normalized_parts.append(trimmed.casefold())
    return "/".join(normalized_parts)


def _run_semgrep_tree(
    tree: Path,
    paths: Sequence[str],
    repo_root: Path,
) -> subprocess.CompletedProcess[str]:
    targets = [str(tree / path) for path in paths]
    finding: subprocess.CompletedProcess[str] | None = None
    last_result: subprocess.CompletedProcess[str] | None = None
    try:
        for batch in _semgrep_target_batches(targets):
            result = _run_command(
                _semgrep_command("auto", batch),
                repo_root,
                timeout_seconds=SEMGREP_TIMEOUT_SECONDS,
            )
            if result.returncode not in {0, 1}:
                return result
            verified = _verify_semgrep_targets(result, batch, repo_root)
            if verified.returncode == 2:
                return verified
            last_result = verified
            if verified.returncode == 1 and finding is None:
                finding = verified
    except FileNotFoundError:
        return subprocess.CompletedProcess([], 2, "", "semgrep executable not found\n")
    except OSError as error:
        return subprocess.CompletedProcess([], 2, "", f"cannot execute semgrep: {error}\n")
    return finding or last_result or subprocess.CompletedProcess([], 0, "", "")


def _semgrep_command(config: str, targets: Sequence[str]) -> list[str]:
    return [
        "semgrep",
        "scan",
        "--config",
        config,
        "--error",
        "--severity",
        "ERROR",
        "--disable-nosem",
        "--no-git-ignore",
        "--x-ignore-semgrepignore-files",
        "--max-target-bytes=0",
        "--no-exclude-binary-files",
        "--json",
        "--",
        *targets,
    ]


def _semgrep_target_batches(targets: Sequence[str]) -> list[list[str]]:
    base_length = sum(len(argument) + 1 for argument in _semgrep_command("auto", []))
    batches: list[list[str]] = []
    batch: list[str] = []
    batch_length = base_length
    for target in targets:
        target_length = len(target) + 1
        if batch and (
            len(batch) >= SEMGREP_BATCH_TARGET_LIMIT
            or batch_length + target_length > SEMGREP_COMMAND_LENGTH_LIMIT
        ):
            batches.append(batch)
            batch = []
            batch_length = base_length
        batch.append(target)
        batch_length += target_length
    if batch:
        batches.append(batch)
    return batches


def _verify_semgrep_targets(
    result: subprocess.CompletedProcess[str],
    targets: Sequence[str],
    repo_root: Path,
) -> subprocess.CompletedProcess[str]:
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        return _semgrep_target_failure(result, f"invalid Semgrep JSON: {error}")
    if not isinstance(payload, dict):
        return _semgrep_target_failure(result, "Semgrep JSON root is not an object")
    path_data = payload.get("paths")
    scanned = path_data.get("scanned") if isinstance(path_data, dict) else None
    if not isinstance(scanned, list) or not all(isinstance(path, str) for path in scanned):
        return _semgrep_target_failure(result, "Semgrep JSON lacks scanned target paths")
    expected = {_resolved_target_path(path, repo_root) for path in targets}
    actual = {_resolved_target_path(path, repo_root) for path in scanned}
    missing = expected - actual
    if missing:
        omitted = ", ".join(sorted(str(path) for path in missing))
        return _semgrep_target_failure(result, f"Semgrep omitted requested targets: {omitted}")
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return _semgrep_target_failure(result, "Semgrep JSON lacks an error manifest")
    if any(not _is_known_powershell_semgrep_error(error, expected, repo_root) for error in errors):
        return _semgrep_target_failure(result, "Semgrep reported scan errors")
    return result


def _is_known_powershell_semgrep_error(
    error: object,
    targets: set[Path],
    repo_root: Path,
) -> bool:
    if not isinstance(error, dict):
        return False
    if error.get("level") != "warn":
        return False
    message = error.get("message")
    raw_path = error.get("path")
    if not isinstance(message, str) or not isinstance(raw_path, str):
        return False
    target = _resolved_target_path(raw_path, repo_root)
    if target not in targets:
        return False
    try:
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    scripts = _yaml_run_scripts(content)
    if (
        error.get("code") == 2
        and error.get("type") == "Internal matching error"
        and error.get("rule_id") in SEMGREP_POWERSHELL_RULES
        and SEMGREP_POWERSHELL_ERROR_MARKER in message
    ):
        return _message_matches_powershell_run(message, scripts)
    spans = _powershell_partial_parsing_spans(error, message, target, repo_root)
    return bool(spans) and all(_span_belongs_to_powershell_step(scripts, span) for span in spans)


def _yaml_run_scripts(content: str) -> list[tuple[str | None, str, ScalarNode]]:
    try:
        root = yaml.compose(content, Loader=yaml.BaseLoader)
    except yaml.YAMLError:
        return []
    if root is None:
        return []
    scripts: list[tuple[str | None, str, ScalarNode]] = []
    stack: list[Node] = [root]
    visited: set[int] = set()
    while stack:
        node = stack.pop()
        if id(node) in visited:
            continue
        visited.add(id(node))
        if isinstance(node, MappingNode):
            fields = {key.value: value for key, value in node.value if isinstance(key, ScalarNode)}
            shell_node = fields.get("shell")
            run_node = fields.get("run")
            if isinstance(run_node, ScalarNode):
                shell = shell_node.value if isinstance(shell_node, ScalarNode) else None
                scripts.append((shell, run_node.value, run_node))
            stack.extend(value for _, value in node.value)
        elif isinstance(node, SequenceNode):
            stack.extend(node.value)
    return scripts


def _message_matches_powershell_run(
    message: str,
    scripts: Sequence[tuple[str | None, str, ScalarNode]],
) -> bool:
    raw_snippet = message.partition(SEMGREP_POWERSHELL_ERROR_MARKER)[2]
    truncated = SEMGREP_TRUNCATION_RE.search(raw_snippet) is not None
    snippet = SEMGREP_TRUNCATION_RE.sub("", raw_snippet).strip()
    if truncated and len(snippet) < SEMGREP_MIN_TRUNCATED_SNIPPET_LENGTH:
        return False
    matching_shells = [
        shell
        for shell, run, _ in scripts
        if _semgrep_snippet_matches_run(snippet, run, truncated=truncated)
    ]
    return bool(matching_shells) and all(_is_powershell_shell(shell) for shell in matching_shells)


def _semgrep_snippet_matches_run(
    snippet: str,
    run: str,
    *,
    truncated: bool,
) -> bool:
    snippet_lines = snippet.splitlines()
    run_lines = run.splitlines()
    if not snippet_lines or len(snippet_lines) > len(run_lines):
        return False
    complete_lines = snippet_lines[:-1] if truncated else snippet_lines
    if not truncated and len(snippet_lines) != len(run_lines):
        return False
    if any(
        not _semgrep_line_matches_run_line(observed, expected)
        for observed, expected in zip(
            complete_lines,
            run_lines[: len(complete_lines)],
            strict=True,
        )
    ):
        return False
    if not truncated:
        return True
    final_run_line = run_lines[len(snippet_lines) - 1]
    return _semgrep_line_matches_run_prefix(snippet_lines[-1], final_run_line)


def _semgrep_line_matches_run_line(observed: str, expected: str) -> bool:
    return _semgrep_line_matches_pattern(
        observed,
        expected,
        allow_expected_suffix=False,
    )


def _semgrep_line_matches_run_prefix(observed: str, expected: str) -> bool:
    return _semgrep_line_matches_pattern(
        observed,
        expected,
        allow_expected_suffix=True,
    )


def _semgrep_line_matches_pattern(
    observed: str,
    expected: str,
    *,
    allow_expected_suffix: bool,
) -> bool:
    observed_index = 0
    expected_index = 0
    wildcard_expected_index: int | None = None
    wildcard_observed_end = 0
    while observed_index < len(observed):
        if (
            expected_index < len(expected)
            and expected[expected_index].isascii()
            and expected[expected_index] == observed[observed_index]
        ):
            observed_index += 1
            expected_index += 1
            continue
        if expected_index < len(expected) and not expected[expected_index].isascii():
            while expected_index < len(expected) and not expected[expected_index].isascii():
                expected_index += 1
            wildcard_expected_index = expected_index
            wildcard_observed_end = observed_index + 1
            observed_index = wildcard_observed_end
            continue
        if wildcard_expected_index is None or wildcard_observed_end >= len(observed):
            return False
        wildcard_observed_end += 1
        observed_index = wildcard_observed_end
        expected_index = wildcard_expected_index
    if allow_expected_suffix:
        return expected_index > 0 and expected[expected_index - 1].isascii()
    return expected_index == len(expected)


def _is_powershell_shell(shell: str | None) -> bool:
    return shell is not None and bool(POWERSHELL_SHELL_RE.match(shell))


def _powershell_partial_parsing_spans(
    error: dict[object, object],
    message: str,
    target: Path,
    repo_root: Path,
) -> list[tuple[int, int, int, int]]:
    error_type = error.get("type")
    rule_ids = SEMGREP_PARTIAL_RULE_RE.findall(message)
    if (
        error.get("code") != 3
        or not isinstance(error_type, list)
        or len(error_type) != 2
        or error_type[0] != "PartialParsing"
        or len(rule_ids) != 1
        or rule_ids[0] not in SEMGREP_POWERSHELL_RULES
    ):
        return []
    locations = error_type[1]
    if not isinstance(locations, list):
        return []
    spans: list[tuple[int, int, int, int]] = []
    for location in locations:
        if not isinstance(location, dict):
            return []
        location_path = location.get("path")
        start = location.get("start")
        end = location.get("end")
        if (
            not isinstance(location_path, str)
            or _resolved_target_path(location_path, repo_root) != target
            or not isinstance(start, dict)
            or not isinstance(end, dict)
        ):
            return []
        start_line = start.get("line")
        start_col = start.get("col")
        start_offset = start.get("offset")
        end_line = end.get("line")
        end_col = end.get("col")
        end_offset = end.get("offset")
        positions = (
            start_line,
            start_col,
            start_offset,
            end_line,
            end_col,
            end_offset,
        )
        if any(type(position) is not int for position in positions):
            return []
        (
            start_line,
            start_col,
            start_offset,
            end_line,
            end_col,
            end_offset,
        ) = (cast(int, position) for position in positions)
        if (
            start_line < 1
            or start_col < 1
            or start_offset < 0
            or end_line < start_line
            or end_col < 1
            or end_offset <= start_offset
            or (end_line == start_line and end_col < start_col)
        ):
            return []
        spans.append((start_line, end_line, start_offset, end_offset))
    return spans


def _span_belongs_to_powershell_step(
    scripts: Sequence[tuple[str | None, str, ScalarNode]],
    span: tuple[int, int, int, int],
) -> bool:
    start_line, end_line, start_offset, end_offset = span
    matching_shells = [
        shell
        for shell, _, node in scripts
        if _yaml_node_contains_span(
            node,
            start_line,
            end_line,
            start_offset,
            end_offset,
        )
    ]
    return bool(matching_shells) and all(_is_powershell_shell(shell) for shell in matching_shells)


def _yaml_node_contains_span(
    node: ScalarNode,
    start_line: int,
    end_line: int,
    start_offset: int,
    end_offset: int,
) -> bool:
    node_start_line = int(node.start_mark.line) + 1
    node_end_line = int(node.end_mark.line) + 1
    node_end_column = int(node.end_mark.column)
    node_start_offset = int(node.start_mark.index)
    node_end_offset = int(node.end_mark.index)
    node_last_line = node_end_line if node_end_column > 0 else node_end_line - 1
    lines_contained = node_start_line <= start_line <= end_line <= node_last_line
    return lines_contained and node_start_offset <= start_offset and end_offset <= node_end_offset


def _resolved_target_path(path: str, repo_root: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve(strict=False)


def _semgrep_target_failure(
    result: subprocess.CompletedProcess[str],
    message: str,
) -> subprocess.CompletedProcess[str]:
    stderr = f"{result.stderr.rstrip()}\nERROR: {message}\n".lstrip()
    return subprocess.CompletedProcess(result.args, 2, result.stdout, stderr)


def run_semgrep(repo_root: Path) -> int:
    result = _run_command(
        [
            sys.executable,
            "scripts/security/run_semgrep.py",
            "--config",
            "auto",
            "--severity",
            "error",
        ],
        repo_root,
        timeout_seconds=SEMGREP_TIMEOUT_SECONDS,
    )
    _print_process_output(result)
    return result.returncode


def parse_push_refs(stream: TextIO) -> list[PushRef]:
    refs: list[PushRef] = []
    for line_number, line in enumerate(stream, start=1):
        fields = line.split()
        if len(fields) != 4:
            raise ValueError(f"line {line_number}: expected four pre-push fields")
        push_ref = PushRef(*fields)
        _validate_push_ref(push_ref, line_number)
        refs.append(push_ref)
    return refs


def _validate_push_ref(push_ref: PushRef, line_number: int) -> None:
    for sha in (push_ref.local_sha, push_ref.remote_sha):
        if len(sha) not in ZERO_SHA_LENGTHS or not all(
            char in "0123456789abcdefABCDEF" for char in sha
        ):
            raise ValueError(f"line {line_number}: invalid object id")
    for ref in (push_ref.local_ref, push_ref.remote_ref):
        if ref.startswith("-") or any(char.isspace() for char in ref):
            raise ValueError(f"line {line_number}: invalid ref name")


def _is_zero_sha(sha: str) -> bool:
    return len(sha) in ZERO_SHA_LENGTHS and not sha.strip("0")


def _merge_base(repo_root: Path, base: str, head: str) -> str | None:
    result = _run_git(repo_root, ["merge-base", base, head])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def resolve_push_update(push_ref: PushRef, repo_root: Path) -> PushUpdate:
    if push_ref.is_deletion:
        raise ValueError("deletions do not have a push range")
    base = _merge_base(repo_root, "origin/main", push_ref.local_sha)
    if base is None and push_ref.is_new:
        base = _merge_base(repo_root, "main", push_ref.local_sha)
    if base is None and not push_ref.is_new:
        base = push_ref.remote_sha
    plugin_base = base or "origin/main"
    range_spec = f"{base}..{push_ref.local_sha}" if base else push_ref.local_sha
    destination = _branch_name(push_ref.remote_ref)
    return PushUpdate(
        source=push_ref,
        base=plugin_base,
        head=push_ref.local_sha,
        range_spec=range_spec,
        destination_branch=destination,
    )


def _branch_name(ref: str) -> str | None:
    prefix = "refs/heads/"
    return ref[len(prefix) :] if ref.startswith(prefix) else None


def _fetch_origin_main(repo_root: Path) -> None:
    result = _run_git(repo_root, ["fetch", "--no-tags", "--quiet", "origin", "main"])
    if result.returncode != 0:
        print("WARNING: could not refresh origin/main; using local ref", file=sys.stderr)


def _protected_push_destination(push_ref: PushRef) -> str | None:
    branch = _branch_name(push_ref.remote_ref)
    return branch if branch in {"main", "master"} else None


def check_push_refs(stream: TextIO, repo_root: Path) -> int:
    branch_result = check_branch(repo_root)
    if branch_result != 0:
        return branch_result
    history_result = _check_history_integrity(repo_root)
    if history_result != 0:
        return history_result
    try:
        refs = parse_push_refs(stream)
    except ValueError as error:
        print(f"ERROR: malformed pre-push input, {error}", file=sys.stderr)
        return 2
    protected = next(
        (branch for ref in refs if (branch := _protected_push_destination(ref))),
        None,
    )
    if protected is not None:
        print(f"ERROR: cannot delete or update protected branch '{protected}'", file=sys.stderr)
        return 1
    active_refs = [push_ref for push_ref in refs if not push_ref.is_deletion]
    if active_refs:
        warn_if_push_files_incomplete(active_refs, repo_root)
        _fetch_origin_main(repo_root)
    updates = [resolve_push_update(push_ref, repo_root) for push_ref in active_refs]
    return _check_push_updates(updates, repo_root)


def warn_if_push_files_incomplete(
    push_refs: Sequence[PushRef],
    repo_root: Path,
) -> None:
    """Warn when Lefthook cannot prove its file template matches the push."""
    head_result = _run_git(repo_root, ["rev-parse", "HEAD"])
    if head_result.returncode != 0:
        _print_process_output(head_result)
        print(
            "WARNING: could not compare pushed refs with checked-out HEAD; "
            "Lefthook {push_files} quality coverage is unknown",
            file=sys.stderr,
        )
        return
    checked_out_head = head_result.stdout.strip()
    push_base = _run_git(repo_root, ["rev-parse", "--verify", "@{push}"])
    if (
        len(push_refs) == 1
        and push_refs[0].local_sha == checked_out_head
        and push_base.returncode == 0
        and push_refs[0].remote_sha == push_base.stdout.strip()
    ):
        return
    print(
        "WARNING: Lefthook {push_files} quality coverage may be incomplete because "
        "the pushed ref set does not match checked-out HEAD and its configured push "
        "base. Every ref still receives immutable security and policy scans. Push "
        "each ref from its checked-out branch for full local quality validation.",
        file=sys.stderr,
    )


def _check_push_updates(updates: Sequence[PushUpdate], repo_root: Path) -> int:
    policy_failed = False
    config_failed = False
    for update in updates:
        destination = update.destination_branch
        if destination in {"main", "master"}:
            print(f"ERROR: cannot push directly to '{destination}'", file=sys.stderr)
            policy_failed = True
        count_result = _check_commit_limit(update, repo_root)
        marker_result = _check_review_marker(update, repo_root)
        plugin_result = _check_plugin_version(update, repo_root)
        policy_failed |= count_result == 1 or marker_result == 1 or plugin_result == 1
        config_failed |= count_result == 2 or marker_result == 2
    if policy_failed:
        return 1
    return 2 if config_failed else 0


def _contains_main_merge(update: PushUpdate, repo_root: Path) -> bool:
    result = _run_git(repo_root, ["rev-list", "--merges", update.range_spec])
    if result.returncode != 0:
        return False
    return any(
        _merge_has_main_parent(merge_sha, repo_root)
        for merge_sha in result.stdout.splitlines()
        if merge_sha
    )


def _merge_has_main_parent(merge_sha: str, repo_root: Path) -> bool:
    result = _run_git(repo_root, ["show", "-s", "--format=%P", merge_sha])
    if result.returncode != 0:
        return False
    parents = result.stdout.split()
    for parent in parents[1:]:
        ancestor = _run_git(
            repo_root,
            ["merge-base", "--is-ancestor", parent, "origin/main"],
        )
        if ancestor.returncode == 0:
            return True
    return False


def _check_commit_limit(update: PushUpdate, repo_root: Path) -> int:
    result = _run_git(repo_root, ["rev-list", "--count", update.range_spec])
    if result.returncode != 0:
        _print_process_output(result)
        return 2
    try:
        commit_count = int(result.stdout.strip())
    except ValueError:
        return 2
    limit = 40 if _contains_main_merge(update, repo_root) else 20
    if commit_count <= limit:
        return 0
    branch = update.destination_branch or _branch_name(update.source.local_ref)
    args = [sys.executable, "scripts/validation/check_pr_bypass_label.py"]
    if branch:
        args.extend(["--branch", branch])
    bypass = _run_command(args, repo_root)
    if bypass.returncode == 0:
        print(bypass.stdout, end="")
        return 0
    _print_process_output(bypass)
    print(f"ERROR: push has {commit_count} commits, limit is {limit}", file=sys.stderr)
    return 1


def _check_review_marker(update: PushUpdate, repo_root: Path) -> int:
    trailers = _run_git(
        repo_root,
        [
            "log",
            "-1",
            "--format=%(trailers:key=Reviewed-By,valueonly,unfold)",
            update.head,
        ],
    )
    if trailers.returncode != 0:
        _print_process_output(trailers)
        return 2
    if not any(line.startswith("/review@") for line in trailers.stdout.splitlines()):
        return 0
    result = _run_command(
        [
            sys.executable,
            "scripts/validation/validate_review_marker.py",
            "--ref",
            update.head,
            "--repo-root",
            str(repo_root),
        ],
        repo_root,
    )
    if result.returncode != 0:
        _print_process_output(result)
    return result.returncode


def _check_plugin_version(update: PushUpdate, repo_root: Path) -> int:
    result = _run_command(
        [
            sys.executable,
            "build/scripts/validate_plugin_version_bump.py",
            "--base",
            update.base,
            "--head",
            update.head,
            "--repo-root",
            str(repo_root),
        ],
        repo_root,
    )
    if result.returncode == 2:
        _print_advisory_failure("plugin version check", result)
        return 0
    if result.returncode != 0:
        _print_process_output(result)
    return result.returncode


def run_yamllint(paths: Sequence[str], repo_root: Path) -> int:
    if os.environ.get("SKIP_YAMLLINT") == "1":
        print("YAML lint skipped (SKIP_YAMLLINT=1)")
        return 0
    if not paths:
        return 0
    try:
        result = _run_command(["yamllint", "-f", "parsable", "--", *paths], repo_root)
    except FileNotFoundError:
        print("WARNING: yamllint not installed", file=sys.stderr)
        return 0
    _print_process_output(result)
    if result.returncode != 0:
        print("WARNING: YAML style findings are advisory", file=sys.stderr)
    return 0


def run_skillforge(paths: Sequence[str], repo_root: Path) -> int:
    failed = False
    for path in paths:
        if _skip_skillforge_path(path):
            continue
        if _is_skill_frontmatter_only_change(path, repo_root):
            continue
        result = _run_command(
            [
                sys.executable,
                ".claude/skills/SkillForge/scripts/validate-skill.py",
                Path(path).parent.as_posix(),
            ],
            repo_root,
        )
        _print_process_output(result)
        failed |= result.returncode != 0
    return 1 if failed else 0


def _skip_skillforge_path(path: str) -> bool:
    if path.startswith("evals/"):
        return True
    command_mirrors = {
        "spec",
        "plan",
        "build",
        "test",
        "ship",
        "checkpoint",
        "pr-review",
        "retro",
        "sync",
    }
    parts = PurePosixPath(path).parts
    return (
        len(parts) == 5
        and parts[:3] == ("src", "copilot-cli", "skills")
        and parts[3] in command_mirrors
        and parts[4] == "SKILL.md"
    )


def run_planning_advisory(repo_root: Path) -> int:
    result = _run_command(
        [
            sys.executable,
            "build/scripts/validate_planning_artifacts.py",
            "--path",
            str(repo_root),
        ],
        repo_root,
    )
    _print_process_output(result)
    if result.returncode != 0:
        print("WARNING: planning validation findings are advisory", file=sys.stderr)
    return 0


def run_taste_advisory(paths: Sequence[str], repo_root: Path) -> int:
    if not paths:
        return 0
    result = _run_command(
        [
            sys.executable,
            ".claude/skills/taste-lints/scripts/taste_lints.py",
            *paths,
        ],
        repo_root,
    )
    _print_process_output(result)
    if result.returncode != 0:
        print("WARNING: taste lint findings are advisory", file=sys.stderr)
    return 0


def generate_mcp_advisory(repo_root: Path) -> int:
    if check_generated_paths("mcp", repo_root) != 0:
        return 2
    result = _run_command(
        [
            sys.executable,
            "scripts/sync_mcp_config.py",
            "--sync-all",
            "--repo-root-override",
            str(repo_root),
        ],
        repo_root,
    )
    _print_process_output(result)
    if result.returncode != 0:
        print("ERROR: MCP generation failed; generated files were not staged", file=sys.stderr)
    return result.returncode


def generate_agents_advisory(repo_root: Path) -> int:
    if check_generated_paths("agents", repo_root) != 0:
        return 2
    result = _run_command([sys.executable, "build/generate_agents.py"], repo_root)
    _print_process_output(result)
    if result.returncode != 0:
        print("ERROR: agent generation failed; generated files were not staged", file=sys.stderr)
    return result.returncode


def update_memory_tokens(repo_root: Path) -> int:
    if check_generated_paths("memory-index", repo_root) != 0:
        return 2
    result = _run_command(
        [sys.executable, "scripts/update_memory_index_tokens.py"],
        repo_root,
    )
    _print_process_output(result)
    if result.returncode != 0:
        print("ERROR: memory token update failed; memory index was not staged", file=sys.stderr)
    return result.returncode


def validate_memory_sizes(repo_root: Path) -> int:
    validator = repo_root / ".claude/skills/memory/scripts/test_memory_size.py"
    if not validator.is_file() or validator.is_symlink():
        print(f"ERROR: unsafe or missing memory size validator: {validator}", file=sys.stderr)
        return 2

    new_paths = _staged_memory_paths(repo_root, "A")
    modified_paths = _staged_memory_paths(repo_root, "M")
    if new_paths is None or modified_paths is None:
        return 2

    new_failures = _validate_memory_path_set(
        new_paths,
        validator,
        repo_root,
        blocking=True,
    )
    _validate_memory_path_set(
        modified_paths,
        validator,
        repo_root,
        blocking=False,
    )
    return 1 if new_failures else 0


def _staged_memory_paths(repo_root: Path, diff_filter: str) -> list[str] | None:
    result = _run_git(
        repo_root,
        [
            "diff",
            "--cached",
            "--name-only",
            "-z",
            f"--diff-filter={diff_filter}",
            "--",
            ".serena/memories",
        ],
    )
    if result.returncode != 0:
        _print_process_output(result)
        return None
    paths: list[str] = []
    for raw_path in result.stdout.split("\0"):
        if not raw_path:
            continue
        path = _safe_relative_path(raw_path)
        if path is None or not path.endswith(".md"):
            print(f"ERROR: unsafe staged memory path: {raw_path}", file=sys.stderr)
            return None
        paths.append(path)
    return paths


def _validate_memory_path_set(
    paths: Sequence[str],
    validator: Path,
    repo_root: Path,
    *,
    blocking: bool,
) -> bool:
    failed = False
    for path in paths:
        memory_path = _safe_output_path(repo_root, path)
        if memory_path is None or not memory_path.is_file():
            print(f"ERROR: unsafe staged memory file: {path}", file=sys.stderr)
            failed = True
            continue
        result = _run_command(
            [sys.executable, str(validator), str(memory_path)],
            repo_root,
        )
        if result.returncode == 0:
            continue
        _print_process_output(result)
        label = "ERROR" if blocking else "WARNING"
        print(f"{label}: memory exceeds size thresholds: {path}", file=sys.stderr)
        failed = True
    return failed


def cross_reference_memories(paths: Sequence[str], repo_root: Path) -> int:
    if check_generated_paths("memory", repo_root) != 0:
        return 2
    result = _run_command(
        [
            sys.executable,
            ".claude/skills/memory/scripts/invoke_memory_cross_reference.py",
            "--files",
            *paths,
            "--output-json",
        ],
        repo_root,
    )
    _print_process_output(result)
    if result.returncode != 0:
        print(
            "ERROR: memory cross-reference failed; generated files were not staged",
            file=sys.stderr,
        )
        return result.returncode
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        print(f"ERROR: invalid memory cross-reference result: {error}", file=sys.stderr)
        return 2
    if payload.get("Success") is not True:
        print(
            "ERROR: memory cross-reference reported errors; generated files were not staged",
            file=sys.stderr,
        )
        return 1
    return 0


def run_memory_sync(repo_root: Path) -> int:
    if os.environ.get("SKIP_MEMORY_SYNC") == "1":
        print("Memory sync skipped (SKIP_MEMORY_SYNC=1)")
        return 0
    command = [sys.executable, "-m", "scripts.memory_sync.cli", "hook"]
    if os.environ.get("MEMORY_SYNC_IMMEDIATE") == "1":
        command.append("--immediate")
    result = _run_command(command, repo_root)
    _print_process_output(result)
    if result.returncode != 0:
        print("WARNING: memory sync failed without blocking", file=sys.stderr)
    return 0


def run_pytest(repo_root: Path) -> int:
    env = _clean_git_env()
    for key in (
        "CLAUDE_PROJECT_DIR",
        "CLAUDE_PLUGIN_ROOT",
        "COPILOT_PLUGIN_ROOT",
        "GIT_INDEX_FILE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "SKIP_RETROSPECTIVE_GATE",
    ):
        env.pop(key, None)
    env["CLAUDE_PLUGIN_ROOT"] = str(repo_root / "src/copilot-cli")
    result = _run_command(
        [sys.executable, "-m", "pytest", str(repo_root / "tests")],
        repo_root,
        process_env=env,
        timeout_seconds=TEST_SUITE_TIMEOUT_SECONDS,
    )
    _print_process_output(result)
    return result.returncode


def _workflow_local_base_ref() -> str:
    raw = os.environ.get(WORKFLOW_LOCAL_BASE_REF_ENV, "").strip()
    if raw and not _is_zero_sha(raw):
        return raw
    return WORKFLOW_LOCAL_DEFAULT_BASE


def _pushed_workflow_paths(
    paths: Sequence[str],
    repo_root: Path,
    base_ref: str,
) -> set[str] | None:
    """Return the workflow paths this branch changed versus ``base_ref``.

    Uses the three-dot diff ``base_ref...HEAD`` so only commits unique to this
    branch since the merge base count; workflows that main advanced past on a
    rebase or force-push are excluded. ``None`` signals that ``base_ref`` could
    not be resolved, so callers validate every provided path and the gate is
    never weaker than before.
    """
    if not paths:
        return set()
    result = _run_git(
        repo_root,
        ["diff", "--name-only", f"{base_ref}...HEAD", "--", *paths],
    )
    if result.returncode != 0:
        return None
    return {_normalize_ratchet_path(line) for line in result.stdout.splitlines() if line.strip()}


def _select_pushed_workflows(paths: Sequence[str], repo_root: Path) -> list[str]:
    base_ref = _workflow_local_base_ref()
    changed = _pushed_workflow_paths(paths, repo_root, base_ref)
    if changed is None:
        print(
            f"WARNING: workflow-local could not resolve {base_ref}; "
            "validating all provided workflows",
            file=sys.stderr,
        )
        return list(paths)
    return [path for path in paths if _normalize_ratchet_path(path) in changed]


def run_workflow_local(paths: Sequence[str], repo_root: Path) -> int:
    selected = _select_pushed_workflows(paths, repo_root)
    if not selected:
        print(
            "workflow-local: no workflow files changed versus "
            f"{_workflow_local_base_ref()}; skipping act "
            "(imported or unchanged workflows excluded)",
        )
        return 0
    result = _run_command(
        [
            sys.executable,
            "scripts/validation/run_workflow_local_test.py",
            "--files",
            *selected,
            "--repo-root",
            str(repo_root),
        ],
        repo_root,
        timeout_seconds=WORKFLOW_LOCAL_TIMEOUT_SECONDS,
    )
    _print_process_output(result)
    return 0 if result.returncode == 4 else result.returncode


def check_placeholder_identities(stream: TextIO, repo_root: Path) -> int:
    try:
        refs = parse_push_refs(stream)
    except ValueError as error:
        print(f"ERROR: malformed pre-push input, {error}", file=sys.stderr)
        return 2
    for push_ref in refs:
        if push_ref.is_deletion:
            continue
        update = resolve_push_update(push_ref, repo_root)
        result = _run_command(
            [
                sys.executable,
                "scripts/validation/check_placeholder_identity.py",
                "--push-range",
                update.range_spec,
                "--repo-root",
                str(repo_root),
            ],
            repo_root,
        )
        _print_process_output(result)
        if result.returncode != 0:
            return result.returncode
    return 0


def additions_advisory(repo_root: Path) -> int:
    result = _run_git(
        repo_root,
        ["diff", "--numstat", "origin/main...HEAD"],
    )
    if result.returncode != 0:
        _print_process_output(result)
        print("WARNING: could not calculate branch additions", file=sys.stderr)
        return 0
    additions = sum(
        int(fields[0])
        for line in result.stdout.splitlines()
        if len(fields := line.split("\t", 2)) == 3 and fields[0].isdigit()
    )
    if additions > 500:
        print(f"WARNING: branch adds {additions} lines (recommended maximum 500)")
    return 0


def run_cli_e2e(test_file: str, repo_root: Path) -> int:
    if os.environ.get("SKIP_CLI_E2E") == "true":
        print("CLI E2E skipped (SKIP_CLI_E2E=true)")
        return 0
    if shutil.which("copilot") is None and shutil.which("claude") is None:
        print("CLI E2E skipped (no supported CLI installed)")
        return 0
    env = _clean_git_env()
    for key in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT", "COPILOT_PLUGIN_ROOT"):
        env.pop(key, None)
    env["RUN_CLI_E2E"] = "1"
    result = _run_command(
        [sys.executable, "-m", "pytest", test_file, "-v"],
        repo_root,
        process_env=env,
        timeout_seconds=CLI_E2E_TIMEOUT_SECONDS,
    )
    _print_process_output(result)
    return result.returncode


def validate_branch_sessions(paths: Sequence[str], repo_root: Path) -> int:
    failed = False
    for path in paths:
        result = _run_command(
            [sys.executable, "scripts/validate_session_json.py", path],
            repo_root,
        )
        _print_process_output(result)
        failed |= result.returncode != 0
    return 1 if failed else 0


def sync_observations(paths: Sequence[str], repo_root: Path) -> int:
    for path in paths:
        result = _run_command(
            [
                sys.executable,
                ".serena/scripts/import_observations_to_forgetful.py",
                "--observation-file",
                path,
                "--confidence-levels",
                "HIGH",
                "MED",
            ],
            repo_root,
        )
        _print_process_output(result)
        if result.returncode != 0:
            print(f"WARNING: observation sync failed for {path}", file=sys.stderr)
    return 0


def bot_cascade_advisory(repo_root: Path) -> int:
    try:
        pr = _run_command(
            ["gh", "pr", "view", "--json", "number", "--jq", ".number"],
            repo_root,
        )
    except FileNotFoundError:
        print("Bot cascade check skipped (gh unavailable)")
        return 0
    if pr.returncode != 0 or not pr.stdout.strip():
        print("Bot cascade check skipped (no resolvable PR)")
        return 0
    pr_number = pr.stdout.strip()
    threads = _run_command(
        [
            sys.executable,
            ".claude/skills/github/scripts/pr/get_unresolved_review_threads.py",
            "--pull-request",
            pr_number,
        ],
        repo_root,
    )
    _print_process_output(threads)
    _warn_unresolved_threads(threads.stdout, pr_number)
    _warn_recent_bot_review(pr_number, repo_root)
    return 0


def _warn_unresolved_threads(stdout: str, pr_number: str) -> None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        print(f"Bot cascade check skipped for PR #{pr_number} (invalid JSON)")
        return
    complete = payload.get("fetched_pages_complete") is True
    count = payload.get("unresolved_count")
    if complete and isinstance(count, int) and not isinstance(count, bool) and count > 0:
        print(f"WARNING: PR #{pr_number} has {count} unresolved thread(s)")


def _warn_recent_bot_review(pr_number: str, repo_root: Path) -> None:
    reviews = _run_command(
        [
            "gh",
            "api",
            f"repos/{{owner}}/{{repo}}/pulls/{pr_number}/reviews",
            "--paginate",
            "--jq",
            '.[] | select(.user.type == "Bot") | .submitted_at',
        ],
        repo_root,
    )
    if reviews.returncode != 0:
        print(f"Bot cascade review query skipped for PR #{pr_number}")
        return
    timestamps = [line.strip().strip('"') for line in reviews.stdout.splitlines() if line.strip()]
    if not timestamps:
        return
    try:
        submitted = datetime.fromisoformat(max(timestamps).replace("Z", "+00:00"))
    except ValueError:
        print(f"Bot cascade timestamp parse skipped for PR #{pr_number}")
        return
    age = int((datetime.now(UTC) - submitted).total_seconds())
    if age < 120:
        print(f"WARNING: PR #{pr_number} last bot review is {age}s old (< 120s)")


def _print_process_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)


def _print_advisory_failure(
    label: str,
    result: subprocess.CompletedProcess[str],
) -> None:
    _print_process_output(result)
    print(f"WARNING: {label} failed without blocking", file=sys.stderr)


def _repo_root(args: argparse.Namespace) -> Path:
    return Path(args.repo_root).resolve()


def _handle_branch(args: argparse.Namespace) -> int:
    return check_branch(_repo_root(args))


def _handle_branch_context(args: argparse.Namespace) -> int:
    return check_branch_context(_repo_root(args))


def _handle_handoff(args: argparse.Namespace) -> int:
    return check_handoff(args.paths, _repo_root(args))


def _handle_session(args: argparse.Namespace) -> int:
    return check_sessions(args.paths, _repo_root(args))


def _handle_commit_message(args: argparse.Namespace) -> int:
    return check_commit_message(Path(args.message_path))


def _handle_staged_dashes(args: argparse.Namespace) -> int:
    return check_staged_dashes(args.paths, _repo_root(args))


def _handle_staged_action_pins(args: argparse.Namespace) -> int:
    return check_staged_action_pins(args.paths, _repo_root(args))


def _handle_github_bash(args: argparse.Namespace) -> int:
    return check_github_bash_scripts(args.paths, _repo_root(args))


def _handle_security_suppressions(args: argparse.Namespace) -> int:
    return check_security_suppressions(args.paths, _repo_root(args))


def _handle_mypy(args: argparse.Namespace) -> int:
    return run_mypy(args.paths, _repo_root(args))


def _handle_yamllint(args: argparse.Namespace) -> int:
    return run_yamllint(args.paths, _repo_root(args))


def _handle_skillforge(args: argparse.Namespace) -> int:
    return run_skillforge(args.paths, _repo_root(args))


def _handle_planning(args: argparse.Namespace) -> int:
    return run_planning_advisory(_repo_root(args))


def _handle_adr_review(args: argparse.Namespace) -> int:
    return check_adr_review_policy(args.paths, _repo_root(args))


def _handle_retrospective(args: argparse.Namespace) -> int:
    return check_retrospective_evidence(args.paths, _repo_root(args))


def _handle_taste(args: argparse.Namespace) -> int:
    return run_taste_advisory(args.paths, _repo_root(args))


def _handle_generate_mcp(args: argparse.Namespace) -> int:
    return generate_mcp_advisory(_repo_root(args))


def _handle_generate_agents(args: argparse.Namespace) -> int:
    return generate_agents_advisory(_repo_root(args))


def _handle_memory_tokens(args: argparse.Namespace) -> int:
    return update_memory_tokens(_repo_root(args))


def _handle_memory_size(args: argparse.Namespace) -> int:
    return validate_memory_sizes(_repo_root(args))


def _handle_memory_cross_reference(args: argparse.Namespace) -> int:
    return cross_reference_memories(args.paths, _repo_root(args))


def _handle_memory_sync(args: argparse.Namespace) -> int:
    return run_memory_sync(_repo_root(args))


def _handle_pytest(args: argparse.Namespace) -> int:
    return run_pytest(_repo_root(args))


def _handle_workflow_local(args: argparse.Namespace) -> int:
    return run_workflow_local(args.paths, _repo_root(args))


def _handle_placeholder_identity(args: argparse.Namespace) -> int:
    return check_placeholder_identities(sys.stdin, _repo_root(args))


def _handle_additions(args: argparse.Namespace) -> int:
    return additions_advisory(_repo_root(args))


def _handle_cli_hook_e2e(args: argparse.Namespace) -> int:
    return run_cli_e2e("tests/e2e/test_cli_hook_e2e.py", _repo_root(args))


def _handle_cli_plugin_e2e(args: argparse.Namespace) -> int:
    return run_cli_e2e("tests/e2e/test_plugin_load_smoke.py", _repo_root(args))


def _handle_sessions(args: argparse.Namespace) -> int:
    return validate_branch_sessions(args.paths, _repo_root(args))


def _handle_observations(args: argparse.Namespace) -> int:
    return sync_observations(args.paths, _repo_root(args))


def _handle_bot_cascade(args: argparse.Namespace) -> int:
    return bot_cascade_advisory(_repo_root(args))


def _handle_semgrep_push(args: argparse.Namespace) -> int:
    return scan_pushed_heads(sys.stdin, _repo_root(args))


def _handle_suppressions_push(args: argparse.Namespace) -> int:
    return check_pushed_suppressions(sys.stdin, _repo_root(args))


def _handle_stage_generated(args: argparse.Namespace) -> int:
    return stage_generated(args.kind, _repo_root(args))


def _handle_extract_episodes(args: argparse.Namespace) -> int:
    return extract_session_episodes(args.paths, _repo_root(args))


def _handle_update_causal_graph(args: argparse.Namespace) -> int:
    return update_causal_graph(_repo_root(args))


def _handle_semgrep(args: argparse.Namespace) -> int:
    return run_semgrep(_repo_root(args))


def _handle_pre_push(args: argparse.Namespace) -> int:
    return check_push_refs(sys.stdin, _repo_root(args))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    subparsers = parser.add_subparsers(required=True)
    path_commands = (
        ("handoff", _handle_handoff),
        ("session", _handle_session),
        ("staged-dashes", _handle_staged_dashes),
        ("staged-action-pins", _handle_staged_action_pins),
        ("github-bash", _handle_github_bash),
        ("security-suppressions", _handle_security_suppressions),
        ("mypy", _handle_mypy),
        ("yamllint", _handle_yamllint),
        ("skillforge", _handle_skillforge),
        ("taste", _handle_taste),
        ("memory-cross-reference", _handle_memory_cross_reference),
        ("workflow-local", _handle_workflow_local),
        ("sessions", _handle_sessions),
        ("observations", _handle_observations),
        ("extract-episodes", _handle_extract_episodes),
        ("adr-review", _handle_adr_review),
        ("retrospective", _handle_retrospective),
    )
    simple_commands = (
        ("branch", _handle_branch),
        ("branch-context", _handle_branch_context),
        ("planning", _handle_planning),
        ("generate-mcp", _handle_generate_mcp),
        ("generate-agents", _handle_generate_agents),
        ("memory-token-update", _handle_memory_tokens),
        ("memory-size", _handle_memory_size),
        ("memory-sync", _handle_memory_sync),
        ("pytest", _handle_pytest),
        ("placeholder-identity", _handle_placeholder_identity),
        ("additions", _handle_additions),
        ("cli-hook-e2e", _handle_cli_hook_e2e),
        ("cli-plugin-e2e", _handle_cli_plugin_e2e),
        ("bot-cascade", _handle_bot_cascade),
        ("update-causal-graph", _handle_update_causal_graph),
        ("semgrep", _handle_semgrep),
        ("semgrep-push", _handle_semgrep_push),
        ("security-suppressions-push", _handle_suppressions_push),
        ("pre-push", _handle_pre_push),
    )
    for name, handler in path_commands:
        _add_path_command(subparsers, name, handler)
    for name, handler in simple_commands:
        _add_simple_command(subparsers, name, handler)
    message = subparsers.add_parser("commit-message")
    message.add_argument("message_path")
    message.set_defaults(handler=_handle_commit_message)
    generated = subparsers.add_parser("stage-generated")
    generated.add_argument("kind", choices=sorted(GENERATED_PATHS | GENERATED_GLOBS))
    generated.set_defaults(handler=_handle_stage_generated)
    return parser


def _add_path_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    handler: object,
) -> None:
    command = subparsers.add_parser(name)
    command.add_argument("paths", nargs="*")
    command.set_defaults(handler=handler)


def _add_simple_command(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    handler: object,
) -> None:
    command = subparsers.add_parser(name)
    command.set_defaults(handler=handler)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
