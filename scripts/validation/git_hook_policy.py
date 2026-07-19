#!/usr/bin/env python3
"""Narrow Git policies that Lefthook cannot express declaratively."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TextIO

from scripts.validation.sha_pinning import LOCAL_ACTION_PATTERN, VERSION_TAG_PATTERN

REPO_ROOT = Path(__file__).resolve().parents[2]
ZERO_SHA_LENGTHS = (40, 64)
PROHIBITED_DASHES = ("\N{EN DASH}", "\N{EM DASH}")
SESSION_PATH_RE = re.compile(r"^\.agents/sessions/\d{4}-\d{2}-\d{2}-session-\d+.*\.json$")
EPISODE_PATH_RE = re.compile(r"^\.agents/memory/episodes/episode-[A-Za-z0-9._-]+\.json$")
EPISODE_ID_RE = re.compile(r"^episode-[A-Za-z0-9._-]+$")
SECURITY_SUPPRESSION_RE = re.compile(
    r"#\s*(?:lgtm\[|nosec|nosem(?:grep)?|noqa:\s*S|type:\s*ignore\[|cwe-suppress)"
)
SEMGREP_SUFFIXES = frozenset({".js", ".ps1", ".psm1", ".py", ".ts", ".yaml", ".yml"})
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
    return env


def _run_command(
    args: Sequence[str],
    repo_root: Path,
    *,
    input_text: str | None = None,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = _clean_git_env()
    if extra_env is not None:
        env.update(extra_env)
    return subprocess.run(
        list(args),
        cwd=repo_root,
        env=env,
        input=input_text,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )


def _run_command_bytes(
    args: Sequence[str],
    repo_root: Path,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(args),
        cwd=repo_root,
        env=_clean_git_env(),
        capture_output=True,
        check=False,
    )


def _run_git(
    repo_root: Path,
    args: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    return _run_command(["git", *args], repo_root)


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
    paths.extend(
        pattern.split("*", 1)[0].rstrip("/")
        for pattern in GENERATED_GLOBS.get(kind, ())
    )
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
    message = message_path.read_text(encoding="utf-8")
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


def stage_generated(kind: str, repo_root: Path) -> int:
    safety_result = check_generated_paths(kind, repo_root)
    if safety_result != 0:
        return safety_result
    candidates = _generated_candidates(kind, repo_root)
    relative_paths: list[str] = []
    for candidate in candidates:
        if not candidate.exists():
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
    snapshot = graph_path.read_bytes() if graph_path.is_file() else None
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
    failed = False
    for invocation, needs_validation_path in _mypy_invocations(checked_paths):
        result = _invoke_mypy(invocation, repo_root, needs_validation_path)
        _print_process_output(result)
        failed |= result.returncode != 0
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
    )


def _push_updates(stream: TextIO, repo_root: Path) -> list[PushUpdate] | None:
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
        if Path(path).suffix.lower() not in {".py", ".ps1", ".psm1"}:
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
            "--diff-filter=ACMR",
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
        scan_paths = [
            path for path in paths if Path(path).suffix.lower() in SEMGREP_SUFFIXES
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
        result = _run_semgrep_tree(tree, repo_root)
        _print_process_output(result)
        return result.returncode


def _materialize_commit_tree(
    head: str,
    destination: Path,
    repo_root: Path,
    paths: Sequence[str] | None = None,
) -> int:
    archive_args = ["git", "archive", "--format=tar", head]
    if paths:
        archive_args.extend(["--", *paths])
    archive = _run_command_bytes(
        archive_args,
        repo_root,
    )
    if archive.returncode != 0:
        print(archive.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        return 2
    try:
        _extract_safe_archive(archive.stdout, destination)
    except (OSError, tarfile.TarError, ValueError) as error:
        print(f"ERROR: unsafe pushed archive: {error}", file=sys.stderr)
        return 2
    if paths and not _materialized_paths_complete(destination, paths):
        return 2
    return 0


def _materialized_paths_complete(destination: Path, paths: Sequence[str]) -> bool:
    for raw_path in paths:
        path = _safe_relative_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe requested archive path: {raw_path}", file=sys.stderr)
            return False
        output = destination / path
        try:
            mode = output.lstat().st_mode
        except OSError as error:
            print(f"ERROR: pushed archive omitted {path}: {error}", file=sys.stderr)
            return False
        if not stat.S_ISREG(mode):
            print(f"ERROR: pushed archive path is not a regular file: {path}", file=sys.stderr)
            return False
    return True


def _extract_safe_archive(archive_bytes: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        destinations: set[Path] = set()
        for member in archive.getmembers():
            output = _safe_archive_member(member, destination)
            if output in destinations:
                raise ValueError(f"duplicate archive destination: {member.name}")
            destinations.add(output)
            _extract_safe_member(archive, member, output)


def _extract_safe_member(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    output: Path,
) -> None:
    if member.isdir():
        output.mkdir(parents=True, exist_ok=True)
        return
    if member.issym():
        return
    if not member.isfile():
        raise ValueError(f"unsupported archive member: {member.name}")
    source = archive.extractfile(member)
    if source is None:
        raise ValueError(f"unreadable archive member: {member.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(source.read())


def _safe_archive_member(member: tarfile.TarInfo, destination: Path) -> Path:
    path = _safe_relative_path(member.name)
    if path is None:
        raise ValueError(f"unsafe archive path: {member.name}")
    output = destination / path
    output.resolve(strict=False).relative_to(destination.resolve())
    if member.issym():
        target = PurePosixPath(path).parent / member.linkname
        normalized_target = _safe_relative_path(target.as_posix())
        if normalized_target is None:
            raise ValueError(f"unsafe symlink target: {member.name}")
    if member.islnk():
        raise ValueError(f"hard link not allowed: {member.name}")
    return output


def _run_semgrep_tree(
    tree: Path,
    repo_root: Path,
) -> subprocess.CompletedProcess[str]:
    try:
        return _run_command(
            [
                "semgrep",
                "scan",
                "--config",
                "auto",
                "--error",
                "--severity",
                "ERROR",
                "--disable-nosem",
                "--no-git-ignore",
                str(tree),
            ],
            repo_root,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess([], 2, "", "semgrep executable not found\n")


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
        _fetch_origin_main(repo_root)
    updates = [resolve_push_update(push_ref, repo_root) for push_ref in active_refs]
    return _check_push_updates(updates, repo_root)


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
        result = _run_command(
            [
                sys.executable,
                ".claude/skills/SkillForge/scripts/validate-skill.py",
                str(Path(path).parent),
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


def run_adr_reminder(repo_root: Path) -> int:
    result = _run_command(
        [
            sys.executable,
            ".claude/skills/adr-review/scripts/detect_adr_changes.py",
            "--base-path",
            str(repo_root),
        ],
        repo_root,
    )
    _print_process_output(result)
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
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        env.pop(key, None)
    env["CLAUDE_PLUGIN_ROOT"] = str(repo_root / "src/copilot-cli")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(repo_root / "tests")],
        cwd=repo_root,
        env=env,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    _print_process_output(result)
    return result.returncode


def run_workflow_local(paths: Sequence[str], repo_root: Path) -> int:
    result = _run_command(
        [
            sys.executable,
            "scripts/validation/run_workflow_local_test.py",
            "--files",
            *paths,
            "--repo-root",
            str(repo_root),
        ],
        repo_root,
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
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-v"],
        cwd=repo_root,
        env=env,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
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


def _handle_adr_reminder(args: argparse.Namespace) -> int:
    return run_adr_reminder(_repo_root(args))


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
    )
    simple_commands = (
        ("branch", _handle_branch),
        ("planning", _handle_planning),
        ("adr-reminder", _handle_adr_reminder),
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
