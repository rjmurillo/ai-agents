#!/usr/bin/env python3
# taste-lint: ignore complexity -- pre-existing debt, unlinted before the ADR-119 source classification
# taste-lint: ignore file-size -- pre-existing debt, unlinted before the ADR-119 source classification
"""Documentation Accuracy Scanner - Phases 1-3.

Treats code as the source of truth and documentation as the subject under test.
Produces JSON artifacts for downstream LLM-based verification (Phases 4-6).

Phase 1: Assessment - enumerate docs/source, extract symbols, build mapping
Phase 2: Claim Extraction - parse markdown for verifiable claims
Phase 3: Compilability - verify code example symbols exist in codebase

Same-PR mode (--same-pr, requires --diff-base): also checks prose against code
changed in the same diff (see same_pr.py). Findings join the gate; --same-pr
without --diff-base exits 2.

Exit Codes:
    0: No findings at or above severity threshold
    1: Error or inconclusive run, including no source symbols for Phase 3
    2: Configuration error, including an invalid --diff-base
    3: External dependency failure, including unavailable or failed Git
    10: Findings at or above severity threshold
"""

import argparse
import ast
import builtins
import importlib
import io
import json
import logging
import os
import posixpath
import re
import shlex
import subprocess
import sys
import textwrap
import tokenize
import typing
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any, cast

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SourceSymbol:
    """A public symbol extracted from source code."""

    name: str
    kind: str  # class, method, property, constructor, function
    file: str
    line: int
    signature: str
    visibility: str = "public"
    declaring_type: str = ""
    partial_scope: str = ""
    parameter_names: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "signature": self.signature,
            "visibility": self.visibility,
            **({"declaring_type": self.declaring_type} if self.declaring_type else {}),
            **({"partial_scope": self.partial_scope} if self.partial_scope else {}),
            **(
                {"parameter_names": self.parameter_names}
                if self.parameter_names is not None
                else {}
            ),
        }


@dataclass
class DocFile:
    """A documentation file with metadata."""

    path: str
    size_bytes: int
    line_count: int
    code_blocks: int
    referenced_symbols: list[str]
    mapped_source_files: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "code_blocks": self.code_blocks,
            "referenced_symbols": self.referenced_symbols,
            "mapped_source_files": self.mapped_source_files,
        }


@dataclass
class Claim:
    """A verifiable claim extracted from documentation."""

    id: str
    file: str
    line: int
    claim_type: str  # code_example, method_signature, behavioral, quantitative
    language: str
    content: str
    symbols_referenced: list[str]
    mapped_source: str
    end_line: int = 0  # last source line of the claim; 0 means ``line``

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line or self.line,
            "type": self.claim_type,
            "language": self.language,
            "content": self.content,
            "symbols_referenced": self.symbols_referenced,
            "mapped_source": self.mapped_source,
        }


@dataclass
class Finding:
    """A compilability or accuracy finding."""

    id: str
    claim_id: str
    severity: str  # critical, high, medium, low; info = outside the diff
    category: str
    file: str
    line: int
    description: str
    evidence: dict[str, Any]
    suggested_fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "claim_id": self.claim_id,
            "severity": self.severity,
            "category": self.category,
            "file": self.file,
            "line": self.line,
            "description": self.description,
            "evidence": self.evidence,
            "suggested_fix": self.suggested_fix,
        }


# ---------------------------------------------------------------------------
# Phase 1: Assessment
# ---------------------------------------------------------------------------

# File extensions to language mapping
SOURCE_EXTENSIONS: dict[str, str] = {
    ".cs": "csharp",
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}

DOC_GLOBS = ["docs/**/*.md", "**/*.md"]

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "target",
    "dist",
    "build",
    "bin",
    "obj",
    ".doc-accuracy",
}

# In git mode `git ls-files --exclude-standard` already honors .gitignore, so a
# name-based filter would only drop tracked folders that happen to be called
# build, bin, obj, dist, or target (issue #6202). Keep the two directories
# that are never repository content.
_GIT_EXCLUDE_DIRS = frozenset({".git", ".doc-accuracy"})

_GIT_TIMEOUT = 60  # seconds, applied to every git subprocess call

# Environment variables that can redirect git to a foreign repository,
# inject configuration, or alter revision/object resolution.
# Sanitized from every git subprocess to ensure -C <repo_root> is authoritative.
# Source: `git rev-parse --local-env-vars` plus all GIT_CONFIG_* variables.
_GIT_ENV_DENY_EXACT = frozenset(
    (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_IMPLICIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_CEILING_DIRECTORIES",
        "GIT_GRAFT_FILE",
        "GIT_REPLACE_REF_BASE",
        "GIT_NO_REPLACE_OBJECTS",
        "GIT_SHALLOW_FILE",
        "GIT_PREFIX",
        "GIT_CONFIG",
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
    )
)

# Prefix patterns: any env var starting with these is stripped.
_GIT_ENV_DENY_PREFIXES = ("GIT_CONFIG_",)

# Force repository-contained graft, replace, and shallow metadata off. Also
# ignore user and system config, which can install an executable fsmonitor.
_GIT_ENV_FORCE = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_GRAFT_FILE": os.devnull,
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_SHALLOW_FILE": os.devnull,
}


def _git_env() -> dict[str, str]:
    """Return a sanitized copy of os.environ without git repo/config vars."""
    env = os.environ.copy()
    for key in tuple(env):
        normalized = key.upper()
        if normalized in _GIT_ENV_DENY_EXACT or any(
            normalized.startswith(p) for p in _GIT_ENV_DENY_PREFIXES
        ):
            del env[key]
    env.update(_GIT_ENV_FORCE)
    return env


def _git_command(repo_root: Path, *args: str) -> list[str]:
    """Build a Git command with executable config and replacements disabled."""
    return [
        "git",
        "--no-replace-objects",
        "-c",
        "core.fsmonitor=false",
        "-C",
        str(repo_root),
        *args,
    ]


def _read_doc_text(path: Path) -> str:
    """Read a doc with no newline translation, so line numbers match Git's.

    ``read_text`` applies universal newlines, which turns a lone ``\\r`` into
    an extra line that Git does not count. Callers split on ``"\\n"`` and
    strip one trailing ``\\r`` per line only where content parsing needs it.
    """
    return path.read_bytes().decode("utf-8", errors="replace")


def _repo_relative(path: Path, repo_root: Path) -> str:
    """Return a Git-compatible repository-relative path on every platform."""
    return path.relative_to(repo_root).as_posix()


class _GitError(Exception):
    """Classified git failure carrying an ADR-035 exit code."""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _decode_stderr(raw: bytes | str | None) -> str:
    """Decode subprocess stderr which may be bytes or str."""
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode(errors="replace").strip()
    return raw.strip()


def _list_git_files(repo_root: Path, *, require_git: bool = False) -> list[Path] | None:
    """Return every path git knows in ``repo_root``, or ``None`` outside git.

    Uses ``git ls-files -z --cached --others --exclude-standard`` with
    NUL-separated output so that paths containing newlines or special
    characters are handled correctly. Returns ``None`` when the directory is
    not inside a git repository and *require_git* is ``False``, so the caller
    can fall back to a directory walk.

    When *require_git* is ``True`` (diff-base/Git-scoped mode), a
    ``_GitError(3)`` is raised instead of returning ``None``, because a walk
    would silently bypass the Git-backed scoping contract.
    """
    try:
        result = subprocess.run(
            _git_command(
                repo_root,
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ),
            capture_output=True,
            check=True,
            timeout=_GIT_TIMEOUT,
            env=_git_env(),
        )
        return [repo_root / os.fsdecode(rel) for rel in result.stdout.split(b"\x00") if rel]
    except subprocess.CalledProcessError as exc:
        if require_git:
            raise _GitError(
                3,
                f"ls-files: git index error: {_decode_stderr(exc.stderr)}",
            ) from exc
    except FileNotFoundError:
        if require_git:
            raise _GitError(3, "ls-files: git binary not found") from None
    return None


def _repo_files(repo_root: Path, *, require_git: bool = False) -> list[Path]:
    """List the repository files the assessment may read.

    In git mode the list comes from ``git ls-files``, which already honors
    ``.gitignore``, so tracked folders named ``build`` or ``bin`` are kept and
    only ``.git`` and ``.doc-accuracy`` are dropped. Outside git, the walk has
    no ignore rules, so the name-based ``EXCLUDE_DIRS`` filter applies.
    """
    listed = _list_git_files(repo_root, require_git=require_git)
    if listed is not None:
        return [p for p in listed if not _should_exclude(p, repo_root, _GIT_EXCLUDE_DIRS)]
    return [p for p in repo_root.rglob("*") if not _should_exclude(p, repo_root)]


def _should_exclude(
    path: Path,
    repo_root: Path | None = None,
    exclude_dirs: frozenset[str] | set[str] = EXCLUDE_DIRS,
) -> bool:
    """Check if path is in an excluded directory (``EXCLUDE_DIRS`` by default).

    When repo_root is provided, only checks the repo-relative portion
    of the path to avoid false positives from parent directory names.
    """
    check_path = path
    if repo_root is not None:
        try:
            check_path = path.relative_to(repo_root)
        except ValueError:
            pass
    for part in check_path.parts:
        if part in exclude_dirs:
            return True
    return False


_CSHARP_NAMESPACE_RE = re.compile(r"\bnamespace\s+([\w.]+)\s*([;{])")
_CSHARP_PARAMETER_NAME_RE = re.compile(r"\b([A-Za-z_]\w*)\s*$")


def _csharp_parameter_names(
    view: str, opening: int, owners: list[int], ends: dict[int, int]
) -> list[str] | None:
    close = ends.get(opening)
    if close is None:
        return None
    names: list[str] = []
    start, generic_depth, default_at = opening + 1, 0, None
    for token in re.finditer(r"[<>=,)]", view[start : close + 1]):
        index = opening + 1 + token.start()
        if owners[index] != opening:
            continue
        match token[0]:
            case "<" if default_at is None:
                generic_depth += 1
            case ">" if generic_depth:
                generic_depth -= 1
            case "=" if not generic_depth and default_at is None:
                default_at = index
            case "," | ")" if not generic_depth:
                parameter = view[start : default_at if default_at is not None else index]
                if name := _CSHARP_PARAMETER_NAME_RE.search(parameter):
                    names.append(name[1])
                start, default_at = index + 1, None
    return names


def _extract_csharp_symbols(content: str, file_path: str) -> list[SourceSymbol]:
    """Extract public symbols from C# source."""
    symbols: list[SourceSymbol] = []
    lines = content.split("\n")

    pattern = re.compile(
        r"^\s*(?:\[[^\]]*\]\s*)*"
        r"public\s+"
        r"(?:(?:static|virtual|override|abstract|async|sealed|readonly|partial)\s+)*"
        r"(?:(class|struct|interface|enum|record)\s+(\w+)"
        r"|(?:[\w<>\[\],?\s]+)\s+(\w+)\s*[<(])"
    )

    view = _c_family_code_view(content, "csharp")
    owners, ends = _balanced_groups(view)
    namespaces = {m.end() - 1: m[1] for m in _CSHARP_NAMESPACE_RE.finditer(view) if m[2] == "{"}
    file_namespaces = [m[1] for m in _CSHARP_NAMESPACE_RE.finditer(view) if m[2] == ";"]
    type_bodies = {
        header.end() - 1: header["name"]
        for header in _CSHARP_TYPE_HEADER_RE.finditer(view)
        if header.end() - 1 in ends
    }
    offset = 0
    for i, (line, checked_line) in enumerate(zip(lines, view.split("\n"), strict=True)):
        start = offset
        offset += len(line) + 1
        match = pattern.match(line)
        if not match:
            continue

        declaring_type = ""
        partial_scope = ""
        parameter_names = None
        checked_match = pattern.match(checked_line)
        if match.group(1):
            # Type declaration
            kind = match.group(1)
            name = match.group(2)
            sig = line.strip()
            if checked_match and "partial" in checked_line[: match.start(1)].split():
                owner = owners[start + match.start(2)]
                if owner in namespaces and owners[owner] == -1:
                    partial_scope = f"{Path(file_path).parent}:{namespaces[owner]}"
                elif owner == -1 and len(file_namespaces) <= 1:
                    namespace = file_namespaces[0] if file_namespaces else ""
                    partial_scope = f"{Path(file_path).parent}:{namespace}"
                if checked_line[match.end(2) :].lstrip().startswith("<"):
                    partial_scope = ""
        else:
            # Method or property
            name = match.group(3)
            kind = "method" if "(" in line else "property"
            sig = line.strip()
            if checked_match and (position := start + match.start(3)) < len(view):
                declaring_type = type_bodies.get(
                    _csharp_type_body(position, owners, type_bodies), ""
                )
                if method := _CSHARP_METHOD_USE_RE.match(view, position + len(name)):
                    parameter_names = _csharp_parameter_names(view, method.end() - 1, owners, ends)

        symbols.append(
            SourceSymbol(
                name=name,
                kind=kind,
                file=file_path,
                line=i + 1,
                signature=sig,
                declaring_type=declaring_type,
                partial_scope=partial_scope,
                parameter_names=parameter_names,
            )
        )

    return symbols


def _extract_python_symbols(content: str, file_path: str) -> list[SourceSymbol]:
    """Extract public symbols from Python source."""
    symbols: list[SourceSymbol] = []
    lines = content.split("\n")
    pattern = re.compile(r"^(\s*)(def|class)\s+(\w+)")

    for i, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue

        kind_token = match.group(2)
        name = match.group(3)

        if name.startswith("_"):
            continue

        kind = "class" if kind_token == "class" else "function"
        symbols.append(
            SourceSymbol(
                name=name,
                kind=kind,
                file=file_path,
                line=i + 1,
                signature=line.strip(),
            )
        )

    return symbols


def _extract_js_symbols(content: str, file_path: str) -> list[SourceSymbol]:
    """Extract exported symbols from JavaScript/TypeScript source."""
    symbols: list[SourceSymbol] = []
    lines = content.split("\n")
    pattern = re.compile(
        r"^(?:export\s+)?"
        r"(?:(?:async|default)\s+)*"
        r"(?:function|class|const|let|var|interface|type)\s+"
        r"(\w+)"
    )

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith("export"):
            continue

        match = pattern.match(stripped)
        if not match:
            continue

        name = match.group(1)
        kind = "class" if "class " in line else "function"
        symbols.append(
            SourceSymbol(
                name=name,
                kind=kind,
                file=file_path,
                line=i + 1,
                signature=stripped,
            )
        )

    return symbols


SYMBOL_EXTRACTORS = {
    "csharp": _extract_csharp_symbols,
    "python": _extract_python_symbols,
    "javascript": _extract_js_symbols,
    "typescript": _extract_js_symbols,
}


def _find_referenced_symbols(doc_content: str, symbol_names: set[str]) -> list[str]:
    """Find source symbols referenced in documentation content."""
    found: list[str] = []
    for name in symbol_names:
        if name in doc_content:
            found.append(name)
    return sorted(set(found))


def _source_reference_index(
    source_files: dict[str, str],
    source_symbols: list[SourceSymbol],
) -> dict[str, set[str]]:
    """Index file names, qualified modules, and unambiguous public symbols."""
    references: dict[str, set[str]] = {}
    symbols: dict[str, set[str]] = {}
    for src_path in source_files:
        path = Path(src_path)
        references.setdefault(src_path, set()).add(src_path)
        references.setdefault(path.name, set()).add(src_path)
        if path.suffix == ".py":
            module = path.parent if path.stem == "__init__" else path.with_suffix("")
            for start in range(len(module.parts) - 1):
                name = ".".join(module.parts[start:])
                references.setdefault(name, set()).add(src_path)
    for symbol in source_symbols:
        symbols.setdefault(symbol.name, set()).add(symbol.file)
        path = Path(symbol.file)
        module_name = path.parent.name if path.stem == "__init__" else path.stem
        references.setdefault(f"{module_name}.{symbol.name}", set()).add(symbol.file)
    for name, paths in symbols.items():
        # Identical projections remain coupled. Distinct implementations need
        # a qualified reference, rather than guessing from words like "main".
        if len({source_files[path] for path in paths}) == 1:
            references.setdefault(name, set()).update(paths)
    return references


def _map_doc_to_source(
    doc_path: str,
    doc_content: str,
    source_references: dict[str, set[str]],
) -> list[str]:
    """Map explicit references without matching prose against bare file stems."""
    mapped: set[str] = set()
    for reference in re.findall(r"\w+(?:[./\\-]\w+)*", doc_content):
        reference = reference.replace("\\", "/")
        paths = source_references.get(reference)
        if not paths:
            paths = source_references.get(reference.rsplit("/", 1)[-1])
        if not paths and "/" not in reference:
            paths = source_references.get(reference.rsplit(".", 1)[-1])
        mapped.update(paths or ())
    return sorted(mapped)


def _count_code_blocks(content: str) -> int:
    """Count fenced code blocks in markdown."""
    return len(re.findall(r"^```\w*\s*$", content, re.MULTILINE))


def _merge_base(repo_root: Path, base_oid: str, head_oid: str, env: dict[str, str]) -> str:
    """Return the fork point of ``base_oid`` and ``head_oid``.

    Exit 2 when the two commits share no history (a config error: the
    base names an unrelated line). Exit 3 on any other git failure.
    """
    try:
        result = subprocess.run(
            _git_command(repo_root, "merge-base", base_oid, head_oid),
            capture_output=True,
            check=True,
            timeout=_GIT_TIMEOUT,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        if exc.returncode == 1 and not exc.stdout:
            raise _GitError(
                2,
                f"merge-base: {base_oid[:12]} and HEAD share no history",
            ) from exc
        raise _GitError(
            3,
            f"merge-base: failed (rc {exc.returncode}): {_decode_stderr(exc.stderr)}",
        ) from exc
    oid_bytes = result.stdout.strip()
    if re.fullmatch(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", oid_bytes) is None:
        raise _GitError(3, "merge-base: malformed commit ID")
    return oid_bytes.decode("ascii")


def _get_changed_diff(
    diff_base: str, repo_root: Path
) -> tuple[set[str], dict[str, list[list[int]]]]:
    """Return changed files still present at HEAD and their new-side line ranges.

    The first element is the ``_get_changed_files`` set. The second maps a
    changed file to ``[start, end]`` inclusive line ranges on the HEAD side,
    parsed from ``git diff --unified=0 --no-renames``. A changed
    file with no parsed hunk (binary, mode-only) is absent from the map; the
    caller treats an absent file as changed in full.
    """
    env = _git_env()
    fork_oid, head_oid = _resolve_fork_and_head(diff_base, repo_root, env)
    files = _diff_name_set(repo_root, fork_oid, head_oid, env)
    ranges = _diff_line_ranges(repo_root, fork_oid, head_oid, env)
    return files, ranges


def _get_changed_files(diff_base: str, repo_root: Path) -> set[str]:
    """Get files changed on HEAD since it forked from diff_base, minus deletions.

    The diff runs from ``merge-base(diff_base, HEAD)`` to HEAD, the same
    change set as ``git diff diff_base...HEAD``. Committed changes only.

    Uses a deterministic validation sequence:

    1. Verify git work-tree environment (sanitized env, ``-C repo_root``).
    2. Resolve each revision to an OID and verify object accessibility.
    3. Resolve ``<revision>^{commit}``; non-commit bases are config exit 2.
    4. Resolve the merge-base; unrelated histories are config exit 2.
    5. Diff by resolved commit OIDs using NUL-separated output (``-z``),
       dropping deleted paths (``--diff-filter=d``).

    All git commands use ``_git_env()`` to strip inherited repository-
    selection variables (GIT_DIR, GIT_WORK_TREE, etc.).

    Raises
    ------
    _GitError
        Classified failure (exit 2 = config, exit 3 = external).
    OSError
        When git binary is not found.
    subprocess.TimeoutExpired
        When any git call exceeds ``_GIT_TIMEOUT``.
    """
    env = _git_env()
    fork_oid, head_oid = _resolve_fork_and_head(diff_base, repo_root, env)
    return _diff_name_set(repo_root, fork_oid, head_oid, env)


def _resolve_fork_and_head(diff_base: str, repo_root: Path, env: dict[str, str]) -> tuple[str, str]:
    """Validate the repo and revisions; return ``(fork_oid, head_oid)``.

    Phases 1-4 of the sequence documented on ``_get_changed_files``.
    """
    # Phase 1: verify git environment
    try:
        wt_result = subprocess.run(
            _git_command(repo_root, "rev-parse", "--is-inside-work-tree"),
            capture_output=True,
            check=True,
            timeout=_GIT_TIMEOUT,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise _GitError(
            3,
            f"rev-parse: not a git repository: {_decode_stderr(exc.stderr)}",
        ) from exc
    if wt_result.stdout.strip().lower() != b"true":
        raise _GitError(
            3,
            "rev-parse: not inside a git work tree",
        )

    def resolve_commit(ref: str, *, invalid_exit: int) -> str:
        try:
            raw_result = subprocess.run(
                _git_command(
                    repo_root,
                    "rev-parse",
                    "--verify",
                    "--quiet",
                    "--end-of-options",
                    ref,
                ),
                capture_output=True,
                check=True,
                timeout=_GIT_TIMEOUT,
                env=env,
            )
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 1:
                raise _GitError(
                    invalid_exit,
                    f"rev-parse: unknown revision '{ref}'",
                ) from exc
            raise _GitError(
                3,
                f"rev-parse: failed to resolve '{ref}' "
                f"(rc {exc.returncode}): {_decode_stderr(exc.stderr)}",
            ) from exc

        raw_oid_bytes = raw_result.stdout.strip()
        if re.fullmatch(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", raw_oid_bytes) is None:
            raise _GitError(
                3,
                f"rev-parse: malformed object ID for '{ref}'",
            )
        raw_oid = raw_oid_bytes.decode("ascii")

        try:
            subprocess.run(
                _git_command(repo_root, "cat-file", "-e", raw_oid),
                capture_output=True,
                check=True,
                timeout=_GIT_TIMEOUT,
                env=env,
            )
        except subprocess.CalledProcessError as exc:
            raise _GitError(
                3,
                f"cat-file: object {raw_oid[:12]} not accessible "
                f"(rc {exc.returncode}): {_decode_stderr(exc.stderr)}",
            ) from exc

        try:
            commit_result = subprocess.run(
                _git_command(
                    repo_root,
                    "rev-parse",
                    "--verify",
                    "--quiet",
                    "--end-of-options",
                    f"{ref}^{{commit}}",
                ),
                capture_output=True,
                check=True,
                timeout=_GIT_TIMEOUT,
                env=env,
            )
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 1:
                try:
                    subprocess.run(
                        _git_command(repo_root, "cat-file", "-e", raw_oid),
                        capture_output=True,
                        check=True,
                        timeout=_GIT_TIMEOUT,
                        env=env,
                    )
                except subprocess.CalledProcessError as missing_exc:
                    raise _GitError(
                        3,
                        f"cat-file: object {raw_oid[:12]} not accessible "
                        f"(rc {missing_exc.returncode}): "
                        f"{_decode_stderr(missing_exc.stderr)}",
                    ) from missing_exc
                raise _GitError(
                    invalid_exit,
                    f"rev-parse: invalid commit revision '{ref}'",
                ) from exc
            raise _GitError(
                3,
                f"rev-parse: failed to peel '{ref}' to a commit "
                f"(rc {exc.returncode}): {_decode_stderr(exc.stderr)}",
            ) from exc

        oid_bytes = commit_result.stdout.strip()
        if re.fullmatch(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", oid_bytes) is None:
            raise _GitError(
                3,
                f"rev-parse: malformed commit ID for '{ref}'",
            )
        oid = oid_bytes.decode("ascii")

        try:
            subprocess.run(
                _git_command(repo_root, "cat-file", "-e", f"{oid}^{{commit}}"),
                capture_output=True,
                check=True,
                timeout=_GIT_TIMEOUT,
                env=env,
            )
        except subprocess.CalledProcessError as exc:
            raise _GitError(
                3,
                f"cat-file: commit {oid[:12]} not accessible "
                f"(rc {exc.returncode}): {_decode_stderr(exc.stderr)}",
            ) from exc
        return oid

    # Phases 2-3: resolve and verify immutable commit IDs.
    base_oid = resolve_commit(diff_base, invalid_exit=2)
    head_oid = resolve_commit("HEAD", invalid_exit=3)

    # Phase 4: diff from the fork point, not the base tip, so commits that
    # landed on the base after the fork are not counted as this branch's.
    oid = _merge_base(repo_root, base_oid, head_oid, env)
    return oid, head_oid


def _diff_name_set(repo_root: Path, fork_oid: str, head_oid: str, env: dict[str, str]) -> set[str]:
    """Phase 5: diff by resolved OIDs, NUL-separated output.

    ``--diff-filter=d`` drops deleted paths. A deleted file has no HEAD-side
    content to inventory, so listing it made a complete run read as a
    partial inventory to the review adapter, which then reported UNKNOWN.
    """
    oid = fork_oid
    try:
        # Not reachable as command injection: the refs are commit OIDs that
        # _resolve_fork_and_head validated as 40 or 64 lowercase hex
        # characters, argv is a list run without a shell, and _git_env strips
        # user and system git config from the inherited environment.
        result = subprocess.run(
            _git_command(
                repo_root,
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-renames",
                "--diff-filter=d",
                "--name-only",
                "-z",
                oid,
                head_oid,
                "--",
            ),
            capture_output=True,
            check=True,
            timeout=_GIT_TIMEOUT,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise _GitError(
            3,
            f"diff: git failed after ref validation: {_decode_stderr(exc.stderr)}",
        ) from exc
    return {os.fsdecode(f) for f in result.stdout.split(b"\x00") if f}


_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_C_ESCAPES = {
    "a": 7,
    "b": 8,
    "t": 9,
    "n": 10,
    "v": 11,
    "f": 12,
    "r": 13,
    '"': 34,
    "\\": 92,
}


def _norm_path(path: str) -> str:
    """Canonical repo-relative POSIX path used for every changed_lines key.

    A backslash is a path separator only on Windows. On POSIX it is a legal
    file name character, so ``a/b.md`` and ``a\\b.md`` must stay distinct.
    """
    if os.sep == "\\":
        path = path.replace("\\", "/")
    return posixpath.normpath(path)


def _unquote_c_path(quoted: str) -> str:
    """Decode a C-style quoted path as Git prints it in patch headers."""
    raw = bytearray()
    i = 1  # skip the opening quote
    end = len(quoted) - 1  # skip the closing quote
    while i < end:
        ch = quoted[i]
        if ch != "\\":
            raw.extend(ch.encode("utf-8"))
            i += 1
        elif quoted[i + 1].isdigit():
            raw.append(int(quoted[i + 1 : i + 4], 8))
            i += 4
        else:
            raw.append(_C_ESCAPES.get(quoted[i + 1], ord(quoted[i + 1])))
            i += 2
    return os.fsdecode(bytes(raw))


def _new_side_path(header_line: str) -> str | None:
    """Return the path from a ``+++ b/<path>`` header, or None for /dev/null."""
    value = header_line[4:].rstrip("\r\n")
    if "\t" in value and not value.startswith('"'):
        value = value.split("\t", 1)[0]
    if value == "/dev/null":
        return None
    if value.startswith('"'):
        value = _unquote_c_path(value)
    return value[2:] if value[:2] == "b/" else value


_WHOLE_FILE_END = 2**31 - 1
# An empty range list is never valid and means changed in full (fail closed).
# Rename detection is off, so a renamed doc is an added file: every line is
# in scope, and a carried-over claim cannot hide behind its old path.
_FENCE_LINE = re.compile(r"^ {0,3}(?:`{3,}|~{3,})")


def _hunk_range(start: int, count: int) -> list[int]:
    """Return the inclusive new-side range for one ``--unified=0`` hunk.

    A zero-length hunk is a pure deletion at line ``start``: the removed text
    sat between ``start`` and ``start + 1``, so both neighbors count as touched.
    """
    if count == 0:
        return [max(start, 1), start + 1]
    return [start, start + count - 1]


class _PatchParser:
    """Count-driven reader for ``git diff --unified=0`` output.

    Hunk bodies are consumed by the line counts in their ``@@`` header, so an
    added or removed line whose text looks like a file or hunk header is never
    interpreted as one. Anything inconsistent marks the file as changed in
    full (fail closed: every claim in it is in scope).
    """

    def __init__(self) -> None:
        self.ranges: dict[str, list[list[int]]] = {}
        self._fence_from: dict[str, int] = {}
        # Per file: parity of changed column-0 backtick fence lines so far, and
        # the first new-side line after the last hunk (start of the open gap).
        self._parity: dict[str, int] = {}
        self._gap_from: dict[str, int] = {}
        self._new_cursor = 0
        self._poisoned: set[str] = set()
        self._path: str | None = None
        self._current: list[list[int]] | None = None
        self._old_left = 0
        self._new_left = 0

    def feed(self, line: str) -> None:
        if self._old_left or self._new_left:
            if self._consume_body(line):
                return
            self._poison()
        self._header(line)

    def _consume_body(self, line: str) -> bool:
        kind = line[:1]
        if kind == "\\":
            return True  # "\ No newline at end of file" marker, uncounted
        if kind == "-" and self._old_left:
            self._old_left -= 1
            self._note_fence_text(line[1:])
        elif kind == "+" and self._new_left:
            self._new_left -= 1
            self._note_fence_text(line[1:])
            self._new_cursor += 1
        elif kind == " " and self._old_left and self._new_left:
            self._old_left -= 1
            self._new_left -= 1
            self._new_cursor += 1
        else:
            return False
        return True

    def _note_fence_text(self, text: str) -> None:
        """Classify one added or removed line by its fence effect.

        The claim extractor pairs fences by a toggle on lines that start with
        three backticks at column 0. Such a line flips the in-fence state of
        every unchanged line below it, so it only moves the parity that
        ``_close_gap`` reads. Any other fence-like shape (tildes, indented)
        stays fail closed through ``_note_fence``, because ``same_pr.py`` and
        the external-sdk scan read those shapes too.
        """
        if text.startswith("```"):
            if self._path is not None:
                self._parity[self._path] = self._parity.get(self._path, 0) ^ 1
        elif _FENCE_LINE.match(text):
            self._note_fence(self._new_cursor)

    def _close_gap(self, next_lo: int) -> None:
        """Emit the unchanged stretch before the next hunk when parity is odd.

        An odd count of changed column-0 fence lines above a stretch means its
        fence pairing flipped, so claims there are no longer the author's
        unchanged text. An even count leaves pairing as it was.
        """
        if self._path is None or self._current is None:
            return
        first = self._gap_from.get(self._path)
        if first is not None and self._parity.get(self._path, 0) and first < next_lo:
            self._current.append([first, next_lo - 1])

    def _note_fence(self, line_no: int) -> None:
        """Remember the earliest changed non-column-0 fence line.

        Editing a tilde or indented fence re-pairs every later fence for the
        readers that honor those shapes, so claims from that line to the end
        of the file are no longer the author's unchanged text.
        """
        if self._path is not None:
            known = self._fence_from.get(self._path, line_no)
            self._fence_from[self._path] = min(known, line_no)

    def _poison(self) -> None:
        self._old_left = self._new_left = 0
        if self._path is not None:
            self._poisoned.add(self._path)

    def _start_file(self, path: str | None) -> None:
        self._path = path
        self._current = [] if path is None else self.ranges.setdefault(path, [])

    def _header(self, line: str) -> None:
        if line.startswith("diff --git "):
            self._path, self._current = None, None
        elif line.startswith("+++ "):
            path = _new_side_path(line)
            path = None if path is None else _norm_path(path)
            self._start_file(path)
        elif line.startswith("@@"):
            self._hunk(line)

    def _hunk(self, line: str) -> None:
        match = _HUNK_HEADER.match(line)
        if self._current is None:
            raise ValueError("hunk header outside a file section")
        if match is None:
            self._poison_header()
            return
        old = 1 if match.group(1) is None else int(match.group(1))
        start = int(match.group(2))
        new = 1 if match.group(3) is None else int(match.group(3))
        span = _hunk_range(start, new)
        self._close_gap(span[0])
        self._current.append(span)
        if self._path is not None:
            self._gap_from[self._path] = span[1] + 1
        self._old_left, self._new_left = old, new
        # A deletion-only hunk (new == 0) removes text after line ``start``.
        self._new_cursor = start + 1 if new == 0 else start

    def _poison_header(self) -> None:
        if self._path is not None:
            self._poisoned.add(self._path)

    def finish(self) -> dict[str, list[list[int]]]:
        if self._old_left or self._new_left:
            self._poison()
        for path, found in self.ranges.items():
            if path in self._poisoned or not found:
                self.ranges[path] = [[1, _WHOLE_FILE_END]]
                continue
            if self._parity.get(path, 0) and path in self._gap_from:
                found.append([self._gap_from[path], _WHOLE_FILE_END])
            if path in self._fence_from:
                found.append([self._fence_from[path], _WHOLE_FILE_END])
        return self.ranges


def _parse_unified_zero(patch: str) -> dict[str, list[list[int]]]:
    """Map each patched file to its new-side changed line ranges.

    Splits on ``"\\n"`` only: ``str.splitlines`` also breaks on form feed,
    NEL and other separators that a doc line may legally contain.
    Raises ``ValueError`` when a hunk has no file section, which the caller
    treats as "no usable ranges" so every changed doc counts as changed in full.
    """
    parser = _PatchParser()
    for line in patch.split("\n"):
        parser.feed(line)
    return parser.finish()


def _diff_line_ranges(
    repo_root: Path, fork_oid: str, head_oid: str, env: dict[str, str]
) -> dict[str, list[list[int]]]:
    """Return changed new-side line ranges per file; renames count as adds."""
    try:
        # Not reachable as command injection: the refs are commit OIDs that
        # _resolve_fork_and_head validated as 40 or 64 lowercase hex
        # characters, argv is a list run without a shell, and _git_env strips
        # user and system git config from the inherited environment.
        result = subprocess.run(
            _git_command(
                repo_root,
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                "--unified=0",
                "--no-renames",
                "--src-prefix=a/",
                "--dst-prefix=b/",
                fork_oid,
                head_oid,
                "--",
            ),
            capture_output=True,
            check=True,
            timeout=_GIT_TIMEOUT,
            env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise _GitError(
            3,
            f"diff: git failed reading hunks: {_decode_stderr(exc.stderr)}",
        ) from exc
    try:
        return _parse_unified_zero(result.stdout.decode("utf-8", errors="replace"))
    except ValueError:
        return {}


def _has_symlink_part(path: Path, repo_root: Path) -> bool:
    """True when ``path`` or any parent below ``repo_root`` is a symlink."""
    current = repo_root
    for part in path.relative_to(repo_root).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _claim_in_ranges(claim: dict[str, Any], ranges: list[list[int]]) -> bool:
    """True when the claim's span overlaps any changed range.

    The span runs from ``line`` to ``end_line`` inclusive. For a fenced
    ``code_example`` that is the opening fence through the closing fence.
    """
    start = claim["line"]
    end = claim.get("end_line", start)
    return any(lo <= end and start <= hi for lo, hi in ranges)


def run_assessment(
    repo_root: Path,
    doc_globs: list[str] | None = None,
    diff_base: str | None = None,
) -> dict[str, Any]:
    """Phase 1: Build assessment of documentation and source files."""
    if doc_globs is None:
        doc_globs = DOC_GLOBS

    changed_files: set[str] | None = None
    changed_ranges: dict[str, list[list[int]]] = {}
    if diff_base:
        changed_files, changed_ranges = _get_changed_diff(diff_base, repo_root)

    repo_files = _repo_files(repo_root, require_git=diff_base is not None)
    allowed_files = set(repo_files)

    # Enumerate documentation files
    doc_files_set: set[Path] = set()
    for glob_pattern in doc_globs:
        for p in repo_root.glob(glob_pattern):
            if p.is_file() and p in allowed_files:
                doc_files_set.add(p)

    # Enumerate source files
    source_files: dict[str, str] = {}  # path -> content
    source_symbols: list[SourceSymbol] = []
    symbol_names: set[str] = set()

    for p in repo_files:
        if not p.is_file():
            continue

        ext = p.suffix.lower()
        lang = SOURCE_EXTENSIONS.get(ext)
        if not lang:
            continue

        rel_path = _repo_relative(p, repo_root)
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Failed to read source file %s: %s", rel_path, exc)
            continue

        source_files[rel_path] = content

        extractor = SYMBOL_EXTRACTORS.get(lang)
        if extractor:
            syms = extractor(content, rel_path)
            source_symbols.extend(syms)
            for s in syms:
                symbol_names.add(s.name)

    source_references = _source_reference_index(source_files, source_symbols)

    # Build doc file inventory
    doc_inventory: list[DocFile] = []
    changed_lines: dict[str, list[list[int]]] = {}
    for doc_path in sorted(doc_files_set):
        rel_path = _repo_relative(doc_path, repo_root)
        # When diff_base is set, only process documentation files that were
        # changed since that base. Source files are always fully indexed so
        # symbol resolution works across the whole repo.
        if changed_files is not None and rel_path not in changed_files:
            continue
        try:
            content = _read_doc_text(doc_path)
        except OSError as exc:
            logger.warning("Failed to read doc file %s: %s", rel_path, exc)
            continue

        refs = _find_referenced_symbols(content, symbol_names)
        mapped = _map_doc_to_source(rel_path, content, source_references)
        line_count = content.count("\n") + 1
        if changed_files is not None:
            # No parsed hunk, or a symlinked doc (git diffs only the link
            # text, not the content read here): changed in full.
            ranges = (
                None
                if _has_symlink_part(doc_path, repo_root)
                else changed_ranges.get(_norm_path(rel_path))
            ) or [[1, line_count]]
            # A key collision unions ranges, so it can only widen scope.
            changed_lines.setdefault(_norm_path(rel_path), []).extend(ranges)

        doc_inventory.append(
            DocFile(
                path=rel_path,
                size_bytes=doc_path.stat().st_size,
                line_count=line_count,
                code_blocks=_count_code_blocks(content),
                referenced_symbols=refs,
                mapped_source_files=mapped,
            )
        )

    # Build coverage summary
    documented_symbols = set()
    for doc in doc_inventory:
        documented_symbols.update(doc.referenced_symbols)

    public_count = len(source_symbols)
    documented_count = len(documented_symbols & symbol_names)
    coverage_pct = (documented_count / public_count * 100) if public_count else 100.0

    # Find benchmark files
    benchmark_files = []
    for p in repo_files:
        if not p.is_file():
            continue
        name = p.name.lower()
        rel = _repo_relative(p, repo_root)
        if "benchmark" in name:
            benchmark_files.append(rel)
        elif "bench" in name and p.suffix in (".json", ".csv", ".md"):
            if rel not in benchmark_files:
                benchmark_files.append(rel)

    return {
        "documentation_files": [d.to_dict() for d in doc_inventory],
        "source_symbols": [s.to_dict() for s in source_symbols],
        "benchmark_files": sorted(benchmark_files),
        "coverage_summary": {
            "public_symbols": public_count,
            "documented_symbols": documented_count,
            "coverage_pct": round(coverage_pct, 1),
        },
        "changed_files": sorted(changed_files) if changed_files is not None else None,
        "changed_lines": changed_lines if changed_files is not None else None,
    }


# ---------------------------------------------------------------------------
# Phase 2: Claim Extraction
# ---------------------------------------------------------------------------


def _detect_language(info_string: str) -> str:
    """Detect language from code fence info string."""
    lang_map = {
        "csharp": "csharp",
        "cs": "csharp",
        "c#": "csharp",
        "python": "python",
        "py": "python",
        "javascript": "javascript",
        "js": "javascript",
        "typescript": "typescript",
        "ts": "typescript",
        "bash": "bash",
        "sh": "bash",
        "shell": "bash",
        "powershell": "powershell",
        "ps1": "powershell",
        "pwsh": "powershell",
        "yaml": "yaml",
        "yml": "yaml",
        "json": "json",
        "xml": "xml",
        "go": "go",
        "rust": "rust",
        "rs": "rust",
        "java": "java",
    }
    token = info_string.strip().lower().split()[0] if info_string.strip() else ""
    return lang_map.get(token, token)


# Left-to-right scan so a quote inside a comment, or a '#' inside a string,
# is consumed by whichever construct opens first.
_TRIPLE_QUOTE = "\"\"\"|'''"
_PY_NON_CODE_RE = re.compile(
    r"(?s)(" + _TRIPLE_QUOTE + r").*?(?:\1|\Z)"
    r"|\"(?:\\.|[^\"\\\n])*(?:\"|(?=\n)|\Z)"
    r"|'(?:\\.|[^'\\\n])*(?:'|(?=\n)|\Z)"
    r"|\#[^\n]*"
)

_PY_NON_CODE_TOKENS = frozenset(
    {
        tokenize.STRING,
        tokenize.COMMENT,
        getattr(tokenize, "FSTRING_START", -1),
        getattr(tokenize, "FSTRING_MIDDLE", -1),
        getattr(tokenize, "FSTRING_END", -1),
        getattr(tokenize, "TSTRING_START", -1),
        getattr(tokenize, "TSTRING_MIDDLE", -1),
        getattr(tokenize, "TSTRING_END", -1),
    }
)


def _blank_python_non_code_by_tokens(code: str) -> str:
    """Blank STRING and COMMENT token spans, keeping all other columns.

    Raises tokenize.TokenError, IndentationError or SyntaxError when the
    snippet is not tokenizable.
    """
    lines = code.split("\n")
    chars = [list(line) for line in lines]
    readline = io.StringIO(code).readline
    for tok in tokenize.generate_tokens(readline):
        if tok.type == tokenize.ERRORTOKEN:
            # An unterminated single-line literal yields ERRORTOKEN instead
            # of raising; its words would leak, so take the regex fallback.
            raise tokenize.TokenError("unterminated literal", tok.start)
        if tok.type not in _PY_NON_CODE_TOKENS:
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        for row in range(srow, erow + 1):
            if row > len(chars):
                break
            line = chars[row - 1]
            start = scol if row == srow else 0
            end = ecol if row == erow else len(line)
            for col in range(start, min(end, len(line))):
                line[col] = " "
    return "\n".join("".join(line) for line in chars)


def _strip_python_non_code(code: str) -> str:
    """Remove strings, docstrings and comments from a Python snippet.

    Uses the stdlib tokenizer so f-string expressions stay visible. Snippets
    the tokenizer rejects (unterminated quotes, inconsistent dedent, as seen
    in excerpted doc examples) fall back to a conservative regex strip. The
    regex errs toward blanking: it can hide an identifier, never invent one.
    """
    try:
        return _blank_python_non_code_by_tokens(code)
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return _PY_NON_CODE_RE.sub(lambda m: " " * len(m.group(0)), code)


_PY_FROM_IMPORT_RE = re.compile(
    r"^[ \t]*from[ \t]+([\w.]+)[ \t]+import[ \t]+"
    r"(?:\(([^)]*)\)|([^\n(]+))",
    re.MULTILINE,
)


def _python_stdlib_imported_names(code: str) -> set[str]:
    """Names brought in by ``from <stdlib module> import ...`` lines.

    Includes both the imported name and its ``as`` alias (the bound name).

    Handles single-line and parenthesized multi-line imports. These names
    are defined by the standard library, not the repo, so Phase 3 must not
    look them up in the repo symbol index. Imports from any other module
    stay checkable. ``code`` must already be stripped of strings and
    comments.
    """
    names: set[str] = set()
    for module, grouped, plain in _PY_FROM_IMPORT_RE.findall(code):
        if module.split(".")[0] not in sys.stdlib_module_names:
            continue
        for part in (grouped or plain).split(","):
            # Both the imported name and its alias come from the stdlib.
            names.update(n.strip() for n in part.split(" as ") if n.strip())
    return names


def _python_example_definitions(code: str) -> set[str]:
    """Resolve top-level declarations without hiding imports or nested names."""
    try:
        tree = ast.parse(textwrap.dedent(code))
    except SyntaxError:
        return set()
    definitions = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    imports = {
        name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
        for name in (alias.name, alias.asname)
        if name
    }
    return definitions - imports


_PyPos = tuple[int, int]  # (line, character column) in the dedented example
_PyDef = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
_PY_DEF_NAME_RE = re.compile(r"\b(?:def|class)\s+(\w+)")
_WORD_RE = re.compile(r"\w+")
_PY_NESTED_SCOPES = (ast.Lambda, ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)
_PY_TERMINAL_STATEMENTS = (ast.Return, ast.Raise, ast.Break, ast.Continue)
# Bindings definitely made so far: a class scope, a stdlib module, or an untyped name.
_PyDefined = dict[str, "_PyScope | None"]


class _PyScope:
    """One Python scope in an example: module, class, function or comprehension.

    ``_local`` holds every name the scope binds anywhere, so a read of a local
    name never falls through to an enclosing scope. ``defined`` holds the
    names definitely bound at the current point of the flow analysis.
    ``_outer`` is what enclosing scopes had definitely bound when this scope
    was created. A plain class, not a dataclass: on Python 3.10 a dataclass
    resolves its self-referencing string annotations through ``sys.modules``,
    which a script loaded by file path may not be registered in.
    """

    def __init__(self, kind: str, parent: "_PyScope | None", local: set[str]) -> None:
        self._kind = kind
        self._local = local
        self.never: set[str] = set()
        self.defined: _PyDefined = {}
        self._outer: _PyDefined = {}
        if parent is not None:
            self._outer = dict(parent._outer)
            if parent._kind != "class":
                # Nested scopes never see a class body's names.
                for name in parent._local | parent.never:
                    self._outer.pop(name, None)
                self._outer.update(
                    (n, v) for n, v in parent.defined.items() if n not in parent.never
                )

    def lookup(self, name: str) -> tuple[bool, "_PyScope | None"]:
        """Whether ``name`` is definitely bound here and what it binds."""
        if name in self.never:
            return False, None
        table = self.defined if name in self._local else self._outer
        return (name in table), table.get(name)


_PyImportResolver = typing.Callable[[str, str], "_PyScope | None"]
_PY_STDLIB_MODULE = _PyScope("stdlib", None, set())


def _py_scope_locals(nodes: list[Any]) -> tuple[set[str], set[str]]:
    """Names a scope binds anywhere, and names it declares global or nonlocal.

    Nested function, class, lambda and comprehension bodies are not walked;
    only a nested definition's own name binds here.
    """
    local: set[str] = set()
    never: set[str] = set()
    stack = list(nodes)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            local.add(node.name)
            continue
        if isinstance(node, _PY_NESTED_SCOPES):
            continue
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            local.add(node.id)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            never.update(node.names)
        elif isinstance(node, ast.alias):
            local.add(node.asname or node.name.split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            local.add(node.name)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            local.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            local.add(node.rest)
        stack.extend(ast.iter_child_nodes(node))
    return local, never


class _PyBindingCollector(ast.NodeVisitor):
    """Record each name occurrence and whether it resolves within the example.

    A conservative definite-assignment pass. A read resolves only when every
    path reaching it binds the name: ``if`` needs both branches, ``try``
    needs the body and every handler, and a binding inside a loop body,
    ``with`` body or ``match`` case does not survive the statement. A short-
    circuit or conditional-expression walrus never binds definitely.
    Imports resolve only when an exact repository module proves a class
    binding. ``global``/``nonlocal``, ``except`` aliases and match captures
    stay checkable.
    """

    def __init__(
        self, lines: list[str], tree: ast.Module, resolve_import: _PyImportResolver | None = None
    ) -> None:
        self._lines = lines
        local, never = _py_scope_locals(tree.body)
        self._scope = _PyScope("module", None, local)
        self._scope.never = never
        self.uses: list[tuple[_PyPos, str, bool]] = []
        self.unproven_module_roots: set[_PyPos] = set()
        self._conditional = 0  # depth inside short-circuit or ternary operands
        self._halted = False  # the last statement left its block
        self._resolve_import = resolve_import

    def _pos(self, lineno: int, byte_col: int) -> _PyPos:
        line = self._lines[lineno - 1].encode("utf-8")
        return lineno, len(line[:byte_col].decode("utf-8", "replace"))

    def _bind(self, name: str, pos: _PyPos | None, class_scope: "_PyScope | None" = None) -> None:
        if pos is not None:
            self.uses.append((pos, name, True))
        if self._conditional == 0 and name not in self._scope.never:
            self._scope.defined[name] = class_scope

    def _visit_all(self, nodes: list[Any]) -> None:
        for child in nodes:
            if child is not None:
                self.visit(child)

    # --- expressions --------------------------------------------------------

    def visit_Name(self, node: ast.Name) -> None:
        pos = self._pos(node.lineno, node.col_offset)
        if isinstance(node.ctx, ast.Store):
            self._bind(node.id, pos)
        elif isinstance(node.ctx, ast.Load):
            self.uses.append((pos, node.id, self._scope.lookup(node.id)[0]))
        else:
            self.uses.append((pos, node.id, False))
            self._scope.defined.pop(node.id, None)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.visit(node.value)
        line, end = self._pos(cast(int, node.end_lineno), cast(int, node.end_col_offset))
        resolved = False
        if isinstance(node.value, ast.Name):
            found, class_scope = self._scope.lookup(node.value.id)
            resolved = found and class_scope is not None and node.attr in class_scope.defined
            if class_scope is not _PY_STDLIB_MODULE:
                self.unproven_module_roots.add(self._pos(node.value.lineno, node.value.col_offset))
        self.uses.append(((line, end - len(node.attr)), node.attr, resolved))

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self.visit(node.value)
        self.visit(node.target)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.visit(node.values[0])
        self._conditional += 1
        self._visit_all(node.values[1:])
        self._conditional -= 1

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.visit(node.test)
        self._conditional += 1
        self._visit_all([node.body, node.orelse])
        self._conditional -= 1

    # --- simple statements ----------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            name = alias.asname or root
            self._scope.defined.pop(name, None)
            if root in sys.stdlib_module_names:
                self._bind(name, None, _PY_STDLIB_MODULE)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            if name == "*":
                self._scope.defined.clear()
                continue
            # An unverified import still replaces any previous binding.
            self._scope.defined.pop(name, None)
            if self._resolve_import is None or node.module is None or node.level:
                continue
            class_scope = self._resolve_import(node.module, alias.name)
            if class_scope is None or name in self._scope.never:
                continue
            self.uses.append((self._pos(alias.lineno, alias.col_offset), alias.name, True))
            self._bind(name, None, class_scope)
            if alias.asname:
                end = cast(int, alias.end_col_offset) - len(name.encode("utf-8"))
                self.uses.append((self._pos(cast(int, alias.end_lineno), end), name, True))

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        self._visit_all(node.targets)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._visit_all([node.annotation, node.value])
        if node.value is None and isinstance(node.target, ast.Name):
            # ``NAME: int`` declares a type but binds nothing.
            pos = self._pos(node.target.lineno, node.target.col_offset)
            self.uses.append((pos, node.target.id, False))
            return
        self.visit(node.target)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            pos = self._pos(node.target.lineno, node.target.col_offset)
            self.uses.append((pos, node.target.id, self._scope.lookup(node.target.id)[0]))
        self.visit(node.value)
        self.visit(node.target)

    def generic_visit(self, node: ast.AST) -> None:
        super().generic_visit(node)
        if isinstance(node, _PY_TERMINAL_STATEMENTS):
            self._halted = True

    # --- control flow ---------------------------------------------------------

    def _run_block(self, stmts: list[ast.stmt], start: _PyDefined) -> _PyDefined | None:
        """Visit ``stmts`` from ``start``; the bindings at exit, or None if none falls out."""
        self._scope.defined = dict(start)
        self._halted = False
        for stmt in stmts:
            self.visit(stmt)
            if self._halted:
                self._halted = False
                return None
        return self._scope.defined

    def _merge(self, paths: list[_PyDefined | None], start: _PyDefined) -> None:
        """Keep only bindings every path that falls through has made."""
        live = [path for path in paths if path is not None]
        if not live:
            self._scope.defined = dict(start)
            self._halted = True
            return
        merged = {
            name: value for name, value in live[0].items() if all(name in path for path in live[1:])
        }
        for name in merged:
            if any(path[name] is not merged[name] for path in live[1:]):
                merged[name] = None
        self._scope.defined = merged
        self._halted = False

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        start = dict(self._scope.defined)
        body = self._run_block(node.body, start)
        orelse = self._run_block(node.orelse, start)
        self._merge([body, orelse], start)

    def _visit_loop(self, node: ast.For | ast.AsyncFor | ast.While) -> None:
        # The body may run zero times, so nothing it binds survives the loop.
        self.visit(node.iter if not isinstance(node, ast.While) else node.test)
        start = dict(self._scope.defined)
        if not isinstance(node, ast.While):
            self.visit(node.target)
        self._run_block(node.body, self._scope.defined)
        self._run_block(node.orelse, start)
        self._scope.defined = start
        self._halted = False

    def visit_For(self, node: ast.For) -> None:
        self._visit_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_loop(node)

    def visit_While(self, node: ast.While) -> None:
        self._visit_loop(node)

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        # A context manager may suppress an exception raised in the body.
        for item in node.items:
            self.visit(item.context_expr)
            self._visit_all([item.optional_vars])
        start = dict(self._scope.defined)
        self._run_block(node.body, start)
        self._scope.defined = start
        self._halted = False

    def visit_With(self, node: ast.With) -> None:
        self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with(node)

    def visit_Match(self, node: Any) -> None:
        self.visit(node.subject)
        start = dict(self._scope.defined)
        for case in node.cases:
            self._scope.defined = dict(start)
            self._visit_all([case.pattern, case.guard])
            self._run_block(case.body, self._scope.defined)
        self._scope.defined = start
        self._halted = False

    def _visit_try(self, node: Any) -> None:
        # An exception can leave the body before any binding in it.
        start = dict(self._scope.defined)
        body = self._run_block(node.body, start)
        if body is not None:
            body = self._run_block(node.orelse, body)
        paths = [body]
        for handler in node.handlers:
            self._scope.defined = dict(start)
            self._visit_all([handler.type])
            paths.append(self._run_block(handler.body, self._scope.defined))
        self._merge(paths, start)
        merged, halted = self._scope.defined, self._halted
        final = self._run_block(node.finalbody, start)
        if final is None:
            self._scope.defined, self._halted = merged, True
            return
        self._scope.defined = {**merged, **final}
        self._halted = halted

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_try(node)

    def visit_TryStar(self, node: Any) -> None:
        self._visit_try(node)

    # --- scopes ---------------------------------------------------------------

    def _bind_def_name(self, node: _PyDef, class_scope: "_PyScope | None" = None) -> None:
        lineno, col = self._pos(node.lineno, node.col_offset)
        match = _PY_DEF_NAME_RE.search(self._lines[lineno - 1], col)
        found = match is not None and match[1] == node.name
        pos = (lineno, cast(re.Match[str], match).start(1)) if found else None
        self._bind(node.name, pos, class_scope)

    def _enter(self, kind: str, local: set[str], never: set[str] | None = None) -> _PyScope:
        outer = self._scope
        self._scope = _PyScope(kind, outer, local)
        self._scope.never = never or set()
        return outer

    def _leave(self, outer: _PyScope) -> None:
        self._scope = outer
        self._halted = False

    def _bind_arguments(self, args: ast.arguments) -> None:
        every = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
        for arg in every:
            if arg is not None:
                self._bind(arg.arg, self._pos(arg.lineno, arg.col_offset))

    @staticmethod
    def _argument_names(args: ast.arguments) -> set[str]:
        every = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
        return {arg.arg for arg in every if arg is not None}

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        args = node.args
        every = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
        self._visit_all([*node.decorator_list, *args.defaults, *args.kw_defaults, node.returns])
        self._visit_all([arg.annotation for arg in every if arg is not None])
        self._bind_def_name(node)
        local, never = _py_scope_locals(node.body)
        outer = self._enter("function", local | self._argument_names(args), never)
        self._bind_arguments(args)
        self._run_block(node.body, self._scope.defined)
        self._leave(outer)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._visit_all([*node.args.defaults, *node.args.kw_defaults])
        outer = self._enter("function", self._argument_names(node.args))
        self._bind_arguments(node.args)
        self.visit(node.body)
        self._leave(outer)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_all([*node.decorator_list, *node.bases, *node.keywords])
        local, never = _py_scope_locals(node.body)
        outer = self._enter("class", local, never)
        class_scope = self._scope
        self._run_block(node.body, {})
        self._leave(outer)
        # A class name binds only after its body has run.
        self._bind_def_name(node, class_scope)

    def _visit_comprehension(self, node: Any) -> None:
        generators: list[ast.comprehension] = node.generators
        self.visit(generators[0].iter)
        local, _ = _py_scope_locals([generator.target for generator in generators])
        outer = self._enter("comprehension", local)
        for index, generator in enumerate(generators):
            self.visit(generator.target)
            if index:
                self.visit(generator.iter)
            self._visit_all(generator.ifs)
        self._visit_all([getattr(node, field, None) for field in ("elt", "key", "value")])
        self._leave(outer)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node)


def _python_example_bindings(
    code: str, resolve_import: _PyImportResolver | None
) -> tuple[set[str], str]:
    """Return excluded names and the code view after stdlib chain blanking.

    A read resolves only to a binding that every path reaching it has made,
    in a scope visible from the read; ``Owner.name`` resolves only when
    ``Owner`` is a declared or verified imported class whose body definitely
    binds ``name``. One unresolved occurrence keeps the name checkable, so this
    never hides a use before binding, out of scope, or on a path that skips
    the binding.
    """
    source = textwrap.dedent(code)
    view = _strip_python_non_code(source)
    imported_names = _python_stdlib_imported_names(view)
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return imported_names, _blank_stdlib_attribute_chains(view)
    collector = _PyBindingCollector(source.split("\n"), tree, resolve_import)
    collector.visit(tree)
    status: dict[tuple[_PyPos, str], bool] = {}
    for pos, name, resolved in collector.uses:
        key = (pos, name)
        status[key] = status.get(key, True) and resolved
    occurrences: dict[str, list[_PyPos]] = {}
    for lineno, line in enumerate(view.split("\n"), start=1):
        for word in _WORD_RE.finditer(line):
            occurrences.setdefault(word[0], []).append((lineno, word.start()))
    local_names = {
        name
        for name in {name for _, name in status}
        if name in occurrences and all(status.get((pos, name), False) for pos in occurrences[name])
    }
    view = _blank_stdlib_attribute_chains(view, collector.unproven_module_roots)
    return local_names | imported_names, view


def _python_import_resolver(
    repo_root: Path, source_symbols: list[dict[str, Any]]
) -> _PyImportResolver:
    """Resolve direct class bindings from an exact repo-root or src module.

    Read indexed Python source without importing it. Leave ambiguous modules,
    re-exports, and unindexed external modules checkable.
    """
    class_files = {
        (symbol["file"], symbol["name"])
        for symbol in source_symbols
        if symbol["kind"] == "class" and symbol["file"].endswith(".py")
    }

    @cache
    def resolve(module: str, name: str) -> _PyScope | None:
        qualified = module.replace(".", "/")
        paths = [
            path
            for prefix in ("", "src/")
            for path in (f"{prefix}{qualified}.py", f"{prefix}{qualified}/__init__.py")
            if (repo_root / path).is_file()
        ]
        if len(paths) != 1 or (paths[0], name) not in class_files:
            return None
        try:
            source = (repo_root / paths[0]).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, UnicodeError, SyntaxError, ValueError):
            return None
        collector = _PyBindingCollector(source.split("\n"), tree)
        collector.visit(tree)
        return collector._scope.lookup(name)[1]

    return resolve


_PY_PLAIN_IMPORT_RE = re.compile(r"^[ \t]*import[ \t]+([^\n]+)$", re.MULTILINE)
_PY_IMPORT_PART_RE = re.compile(r"([\w.]+)(?:\s+as\s+(\w+))?$")

_TYPING_NAMES = frozenset(typing.__all__)

_DECLARATION_RES: dict[str, re.Pattern[str]] = {
    "csharp": re.compile(r"\b(?:class|record|interface|struct|enum|delegate)\s+([A-Z]\w*)"),
    "typescript": re.compile(r"\b(?:interface|class|enum|type|const|function)\s+([A-Z]\w*)"),
    "javascript": re.compile(r"\b(?:interface|class|enum|type|const|function)\s+([A-Z]\w*)"),
}

_CSHARP_RECORD_PARAMS_RE = re.compile(r"\brecord\s+[A-Z]\w*\s*\(([^)]*)\)")
_CSHARP_RECORD_PROP_RE = re.compile(r"\b[\w<>\[\],.?]+\s+([A-Z]\w*)")

_JS_BUILTIN_TYPES = frozenset(
    {
        "Array",
        "ArrayBuffer",
        "BigInt",
        "Boolean",
        "DataView",
        "Date",
        "Error",
        "EvalError",
        "Float32Array",
        "Float64Array",
        "Function",
        "Generator",
        "Int16Array",
        "Int32Array",
        "Int8Array",
        "Intl",
        "JSON",
        "Map",
        "Math",
        "Number",
        "Object",
        "Promise",
        "Proxy",
        "RangeError",
        "ReferenceError",
        "Reflect",
        "RegExp",
        "Set",
        "String",
        "Symbol",
        "SyntaxError",
        "TypeError",
        "Uint16Array",
        "Uint32Array",
        "Uint8Array",
        "URIError",
        "WeakMap",
        "WeakSet",
        "AbortController",
        "Blob",
        "Document",
        "Element",
        "Event",
        "EventTarget",
        "FormData",
        "Headers",
        "HTMLElement",
        "Navigator",
        "Node",
        "Request",
        "Response",
        "Storage",
        "URL",
        "URLSearchParams",
        "Window",
    }
)

_CSHARP_FRAMEWORK_TYPES_EXTRA = frozenset(
    {
        "AggregateException",
        "AppDomain",
        "ArgumentException",
        "ArgumentNullException",
        "ArgumentOutOfRangeException",
        "BitConverter",
        "CancellationToken",
        "CancellationTokenSource",
        "Convert",
        "DateTimeOffset",
        "Delegate",
        "Enum",
        "Environment",
        "EventArgs",
        "FormatException",
        "GC",
        "Guid",
        "HashSet",
        "IComparable",
        "IDisposable",
        "InvalidCastException",
        "InvalidOperationException",
        "IOException",
        "KeyValuePair",
        "Lazy",
        "LinkedList",
        "NotImplementedException",
        "NotSupportedException",
        "NullReferenceException",
        "OperationCanceledException",
        "OverflowException",
        "Queue",
        "Random",
        "Stack",
        "StringBuilder",
        "SystemException",
        "Thread",
        "TimeoutException",
        "Tuple",
        "UnauthorizedAccessException",
        "Uri",
        "Version",
        "WeakReference",
    }
)


def _python_stdlib_module_aliases(code: str) -> set[str]:
    """Bound names of plain ``import x`` lines whose top-level module is stdlib.

    ``import xml.etree.ElementTree as ET`` binds ``ET``; ``import os, sys``
    binds ``os`` and ``sys``. Non-stdlib modules stay out so their attribute
    chains remain checkable. ``code`` must already be stripped of strings
    and comments.
    """
    aliases: set[str] = set()
    for imports in _PY_PLAIN_IMPORT_RE.findall(code):
        for part in imports.split(","):
            match = _PY_IMPORT_PART_RE.match(part.strip())
            if match and match.group(1).split(".")[0] in sys.stdlib_module_names:
                aliases.add(match.group(2) or match.group(1).split(".")[0])
    return aliases


def _blank_stdlib_attribute_chains(code: str, unproven_roots: set[_PyPos] | None = None) -> str:
    """Blank ``alias.attr`` chains for stdlib-imported aliases.

    ``argparse.ArgumentParser`` resolves through the standard library, not
    the repo, so the attribute name must not reach the identifier scan.
    Blanking is column-preserving and can only hide a name, never invent one.
    """
    aliases = _python_stdlib_module_aliases(code)
    if not aliases:
        return code
    joined = "|".join(sorted((re.escape(a) for a in aliases), key=len, reverse=True))
    pattern = re.compile(rf"\b(?:{joined})(?:\.\w+)+")
    roots = unproven_roots or set()

    def blank_line(line: int, text: str) -> str:
        return pattern.sub(lambda m: m[0] if (line, m.start()) in roots else " " * len(m[0]), text)

    return "\n".join(blank_line(line, text) for line, text in enumerate(code.split("\n"), start=1))


def _blank_stdlib_plain_import_lines(code: str) -> str:
    """Blank the stdlib parts of plain ``import`` lines, preserving columns.

    ``import xml.etree.ElementTree as ET`` contributes no repo symbol, so
    neither the module path nor the alias may reach the identifier scan.
    Non-stdlib parts stay visible so their names remain checkable.
    """

    def repl(match: re.Match[str]) -> str:
        prefix = match.group(0)[: match.start(1) - match.start(0)]
        parts: list[str] = []
        for part in match.group(1).split(","):
            part_match = _PY_IMPORT_PART_RE.match(part.strip())
            if part_match and part_match.group(1).split(".")[0] in sys.stdlib_module_names:
                parts.append(" " * len(part))
            else:
                parts.append(part)
        return prefix + ",".join(parts)

    return _PY_PLAIN_IMPORT_RE.sub(repl, code)


def _example_declaration_names(code: str, lang: str) -> set[str]:
    """Type and member names an example declares itself.

    References to a name the example declares (a class, a record and its
    positional properties, a method signature) are example-local, not repo
    symbol references.
    """
    if lang == "python":
        return _python_example_definitions(code)
    pattern = _DECLARATION_RES.get(lang)
    if pattern is None:
        return set()
    stripped = _try_c_family_code_view(code, lang)
    if stripped is None:
        # Unreadable literals: a declaration inside a string must not hide a
        # real-code name, so drop nothing.
        return set()
    names = set(pattern.findall(stripped))
    for body in re.findall(r"\benum\s+[A-Z]\w*\s*\{([^{}]*)\}", stripped):
        names.update(re.findall(r"(?:^|,)\s*([A-Za-z]\w*)", body))
    if lang == "csharp":
        for params in _CSHARP_RECORD_PARAMS_RE.findall(stripped):
            names.update(_CSHARP_RECORD_PROP_RE.findall(params))
    return names


_CSHARP_TOKENS_NO_BLOCK = r"""@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|//[^\r\n]*"""
_CSHARP_LINE_COMMENT_TOKENS = re.compile(_CSHARP_TOKENS_NO_BLOCK, re.DOTALL)
_CSHARP_COMMENT_TOKENS = re.compile(_CSHARP_TOKENS_NO_BLOCK + r"|/\*.*?(?:\*/|\Z)", re.DOTALL)


def _blank_csharp_comment_token(match: re.Match[str]) -> str:
    text = match[0]
    if text.startswith("/*") and (len(text) < 4 or not text.endswith("*/")):
        # An unclosed ``/*`` stays text. No later ``/*`` can close either, so
        # the rest is scanned for line comments only. Retrying every open
        # ``/*`` to the end of input made this pass quadratic.
        return text[:2] + _CSHARP_LINE_COMMENT_TOKENS.sub(_blank_csharp_comment_token, text[2:])
    if text.startswith(("//", "/*")):
        return re.sub(r"[^\r\n]", " ", text)
    return text


def _strip_csharp_comments(code: str) -> str:
    """Blank comments while preserving string literals and their delimiters."""
    return _CSHARP_COMMENT_TOKENS.sub(_blank_csharp_comment_token, code)


# (start, end) character spans of literal text or comment to blank.
_Spans = list[tuple[int, int]]
# The lookbehind lets a second ``$`` run follow only ``@``. Two free ``\$*``
# runs made a failed match quadratic in the length of a ``$`` run.
_CSHARP_STRING_PREFIX_RE = re.compile(r'(\$*)(@?)((?:(?<=@)\$+)?)("+)')
_CSHARP_CHAR_RE = re.compile(r"'(?:\\.[^'\n]{0,8}|[^'\\\n])'")
_BRACE_RUN_RE = re.compile(r"\{+")
# Scanner loop steps allowed per input character. A well-formed snippet
# needs at most about two; each hole that never closes rescans its text.
_SCAN_STEPS_PER_CHAR = 8


class _ScanBudgetError(Exception):
    """The C-family literal scan ran out of steps."""


class _ScanBudget:
    """Steps left for one C-family scan, so unclosed holes cannot rescan forever."""

    __slots__ = ("_steps",)

    def __init__(self, steps: int) -> None:
        self._steps = steps

    def spend(self) -> None:
        self._steps -= 1
        if self._steps < 0:
            raise _ScanBudgetError


def _c_family_code_view(code: str, lang: str, *, literal_ends: set[int] | None = None) -> str:
    """Blank C#, TypeScript, and JavaScript literal text and comments.

    Interpolation holes stay visible because they are code. A literal or
    comment whose terminator is missing stays visible too: blanking hides
    findings, so the view errs toward keeping text. Column preserving. A
    snippet the scanner cannot read in bounded work comes back unchanged.
    """
    view = _try_c_family_code_view(code, lang, literal_ends=literal_ends)
    return code if view is None else view


def _try_c_family_code_view(
    code: str, lang: str, *, literal_ends: set[int] | None = None
) -> str | None:
    """The literal-blanked view, or None when the scan gives up.

    Crafted nesting exhausts the step budget or the recursion limit. The
    caller then keeps the raw text, which can only report extra names.
    ``literal_ends`` is filled only on success.
    """
    try:
        spans = _scan_c_family(
            code, 0, lang, in_hole=False, budget=_ScanBudget(_SCAN_STEPS_PER_CHAR * len(code))
        )[1]
    except (_ScanBudgetError, RecursionError):
        logger.warning("C-family literal scan gave up on the snippet; keeping raw text")
        return None
    chars = list(code)
    for start, end in spans:
        if (
            literal_ends is not None
            and code[end - 1] != "{"
            and not code.startswith(("//", "/*"), start)
        ):
            literal_ends.add(end)
        for index in range(start, end):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


# Pseudo-token kinds the JavaScript scan emits in place of a raw token.
_JS_CONTROL_END = "control-end"
_JS_STATEMENT_END = "statement-end"
_JS_PROPERTY = "property"
_JS_NON_NULL = "non-null"


def _scan_c_family(
    code: str, i: int, lang: str, *, in_hole: bool, budget: _ScanBudget
) -> tuple[int, _Spans]:
    """Scan code from ``i``; inside a hole, stop at its unmatched ``}``."""
    spans: _Spans = []
    depth = 0
    previous = ""
    control_parens: list[bool] = []
    statement_braces: list[bool] = []
    while i < len(code):
        budget.spend()
        char = code[i]
        if code.startswith("//", i):
            end = code.find("\n", i)
            end = len(code) if end < 0 else end
            spans.append((i, end))
            i = end
            continue
        if code.startswith("/*", i):
            end = code.find("*/", i + 2)
            if end >= 0:
                spans.append((i, end + 2))
                i = end + 2
                continue
        regex_end = (
            _scan_js_regex(code, i) if lang != "csharp" and _js_regex_allowed(previous) else None
        )
        if regex_end is not None:
            spans.append((i, regex_end))
            i = regex_end
            previous = "literal"
            continue
        literal = _scan_c_family_literal(code, i, lang, budget)
        if literal is not None:
            i, literal_spans = literal
            spans.extend(literal_spans)
            previous = "literal"
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            if depth == 0 and in_hole:
                return i, spans
            depth = max(depth - 1, 0)
        if lang != "csharp" and not char.isspace():
            match = cast(re.Match[str], _JS_SCAN_TOKEN.match(code, i))
            token = match[0]
            if token == "(":
                control_parens.append(previous in _JS_CONTROL_HEADS)
            elif token == ")" and control_parens and control_parens.pop():
                token = _JS_CONTROL_END
            elif token == "{":
                statement_braces.append(previous in _JS_STATEMENT_BLOCK_PRECEDERS)
            elif token == "}" and statement_braces and statement_braces.pop():
                token = _JS_STATEMENT_END
            elif previous in (".", "?.") and token in _JS_KEYWORDS:
                token = _JS_PROPERTY
            elif token == "!" and lang == "typescript" and not _js_regex_allowed(previous):
                token = _JS_NON_NULL
            previous = token
            i = match.end()
            continue
        i += 1
    return i, spans


# Characters and keywords after which ``/`` starts a regex, not a division.
_JS_REGEX_PRECEDERS = frozenset("(,=:[!&|?{;+-*/%~^") | {"=>", _JS_CONTROL_END, _JS_STATEMENT_END}
_JS_REGEX_KEYWORDS = frozenset(
    {"return", "typeof", "instanceof", "in", "new", "delete", "void", "throw", "case", "do", "else"}
)
_JS_CONTROL_HEADS = frozenset({"if", "for", "while", "with", "switch", "catch"})
_JS_STATEMENT_BLOCK_PRECEDERS = frozenset(
    {"", _JS_CONTROL_END, _JS_STATEMENT_END, ";", "try", "else", "finally", "do"}
)
_JS_KEYWORDS = _JS_REGEX_KEYWORDS | _JS_CONTROL_HEADS | _JS_STATEMENT_BLOCK_PRECEDERS
_JS_SCAN_TOKEN = re.compile(r"[\w$]+|=>|\+\+|--|\?\.|[^\s]")


def _js_regex_allowed(previous: str) -> bool:
    """Whether the last significant token can precede a regex expression."""
    return not previous or previous in _JS_REGEX_PRECEDERS or previous in _JS_REGEX_KEYWORDS


def _scan_js_regex(code: str, i: int) -> int | None:
    """End index of a JavaScript regex literal at ``i``, or None.

    Escapes and ``[...]`` classes may hold ``/``. A body that reaches a line
    end is not a regex, so the ``/`` stays ordinary code.
    """
    if code[i] != "/" or code.startswith(("//", "/*"), i):
        return None
    j, in_class = i + 1, False
    while j < len(code) and code[j] not in "\r\n\u2028\u2029":
        char = code[j]
        if char == "\\":
            if j + 1 < len(code) and code[j + 1] in "\r\n\u2028\u2029":
                return None
            j += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            j += 1
            while j < len(code) and code[j].isalpha():
                j += 1
            return j
        j += 1
    return None


def _scan_c_family_literal(
    code: str, i: int, lang: str, budget: _ScanBudget
) -> tuple[int, _Spans] | None:
    """Return the end index and blank spans of a literal at ``i``, if terminated."""
    if lang == "csharp":
        if code[i] == "'":
            match = _CSHARP_CHAR_RE.match(code, i)
            return (match.end(), [(i, match.end())]) if match else None
        if i > 0 and code[i - 1] in "$@":
            return None
        prefix = _CSHARP_STRING_PREFIX_RE.match(code, i)
        if prefix is None or (prefix[1] and prefix[3]):
            return None
        dollars = len(prefix[1] or prefix[3])
        quotes = len(prefix[4])
        if quotes >= 3 and not prefix[2]:
            return _scan_quoted(code, i, prefix.end(), '"' * quotes, dollars, lang, "raw", budget)
        mode = "verbatim" if prefix[2] else "regular"
        return _scan_quoted(code, i, prefix.start(4) + 1, '"', dollars, lang, mode, budget)
    if code[i] in "\"'":
        return _scan_quoted(code, i, i + 1, code[i], 0, lang, "regular", budget)
    if code[i] == "`":
        return _scan_quoted(code, i, i + 1, "`", 1, lang, "template", budget)
    return None


def _scan_quoted(
    code: str,
    start: int,
    i: int,
    closer: str,
    holes: int,
    lang: str,
    mode: str,
    budget: _ScanBudget,
) -> tuple[int, _Spans] | None:
    """Scan a quoted body from ``i``; ``holes`` is the brace count opening a hole.

    ``mode`` is ``regular`` (backslash escapes, one line), ``verbatim``
    (``""`` escapes, multi-line), ``raw`` (no escapes, multi-line), or
    ``template`` (JavaScript backquote with ``${`` holes).
    """
    spans: _Spans = []
    text_start = start
    while i < len(code):
        budget.spend()
        if mode in ("regular", "template") and code[i] == "\\":
            i += 2
            continue
        if mode == "regular" and code[i] == "\n":
            return None
        if code.startswith(closer, i):
            if mode == "verbatim" and code.startswith('""', i):
                i += 2
                continue
            spans.append((text_start, i + len(closer)))
            return i + len(closer), spans
        opener = _hole_opener_length(code, i, holes, mode)
        if opener < 0:
            i += -opener
            continue
        if opener:
            spans.append((text_start, i + opener))
            end, hole_spans = _scan_c_family(code, i + opener, lang, in_hole=True, budget=budget)
            closing = "}" * (1 if mode == "template" else holes)
            if not code.startswith(closing, end):
                return None
            spans.extend(hole_spans)
            text_start = end
            i = end + len(closing)
            continue
        i += 1
    return None


def _hole_opener_length(code: str, i: int, holes: int, mode: str) -> int:
    """Characters opening a hole at ``i``; negative skips literal braces; 0 is text."""
    if not holes:
        return 0
    if mode == "template":
        return 2 if code.startswith("${", i) else 0
    if code[i] != "{":
        return 0
    run = cast(re.Match[str], _BRACE_RUN_RE.match(code, i)).end() - i
    if mode != "raw":
        # ``{{`` is an escaped brace in an ordinary interpolated string.
        return -2 if run >= 2 else 1
    if run < holes:
        return -run
    # The trailing ``holes`` braces open the hole; any before them are text.
    return run


_COMMON_FRAMEWORK_TYPES = frozenset(
    {
        "String",
        "Int32",
        "Boolean",
        "Object",
        "Array",
        "List",
        "Dictionary",
        "Task",
        "Action",
        "Func",
        "IEnumerable",
        "IList",
        "Console",
        "Exception",
        "Math",
        "DateTime",
        "TimeSpan",
        "Path",
        "File",
        "Directory",
        "Type",
        "Attribute",
        "Nullable",
        "True",
        "False",
        "None",
        "Error",
        "Promise",
    }
)
_CSHARP_KEYWORD_TYPES = frozenset(
    {"string", "int", "long", "short", "byte", "sbyte", "uint", "ulong", "ushort"}
    | {"bool", "double", "float", "decimal", "char", "object", "dynamic", "nint", "nuint"}
)
_TS_KEYWORD_TYPES = frozenset(
    {"string", "number", "boolean", "bigint", "symbol", "object", "any", "unknown", "void"}
)
# Receivers whose members are never repo claims: framework types per language.
_PROVEN_RECEIVER_TYPES: dict[str, frozenset[str]] = {
    "csharp": _COMMON_FRAMEWORK_TYPES
    | _CSHARP_FRAMEWORK_TYPES_EXTRA
    | _CSHARP_KEYWORD_TYPES
    | {"System"},
    "typescript": _COMMON_FRAMEWORK_TYPES | _JS_BUILTIN_TYPES | _TS_KEYWORD_TYPES,
    "javascript": _COMMON_FRAMEWORK_TYPES | _JS_BUILTIN_TYPES,
}
_TYPE_NAME_RE = re.compile(r"[A-Z][a-zA-Z0-9]+")
_MEMBER_ACCESS_RE = re.compile(r"(?<!\.)\??\.\s*([A-Za-z_$][\w$]*)")
_IDENTIFIER_BEFORE_RE = re.compile(r"(\w+)\s*$")
_NEW_BEFORE_RE = re.compile(r"\bnew\s*$")
_GROUP_OPENERS = {")": "(", "]": "[", ">": "<"}
# ``Type name`` declarations (C#) and ``name: Type`` annotations (TypeScript),
# plus ``name = new Type(`` in both, map a lowercase variable to its type.
_CSHARP_TYPED_NAME_RE = re.compile(
    r"\b(?!(?:return|throw|yield|case|new|in|is)\b)"
    r"([A-Za-z_]\w*(?:\.\w+)*)(?:\s*<[^<>;{}()]*>)?(?:\s*\[\s*\])?\??\s+([a-z_]\w*)\s*(?=[=;,)])"
)
_TS_TYPED_NAME_RE = re.compile(r"\b([a-z_$][\w$]*)\s*\??:\s*([A-Za-z_]\w*)")
_NEW_ASSIGNED_RE = re.compile(r"\b([a-z_]\w*)\s*=\s*new\s+((?:\w+\s*\.\s*)*[A-Z]\w*)")
_TS_VARIABLE_BEFORE_RE = re.compile(r"\b(?:const|let|var)\s*$")


_CSHARP_TYPE_PARAM = r"(?:\b(?:in|out)\s+)?\w+"
_CSHARP_TYPE_PARAMS = (
    rf"(?:\s*<(?P<params>\s*{_CSHARP_TYPE_PARAM}(?:\s*,\s*{_CSHARP_TYPE_PARAM})*\s*)>)?"
)
_CSHARP_TYPE_TOKEN = r"[A-Za-z_][\w.]*(?:\s*<[^;{}()=]*>)?(?:\s*\[\s*,*\s*\])*\??"
_CSHARP_DECL_START = r"(?:^|(?<=[{};]))\s*"
_CSHARP_DECL_MODIFIERS = (
    r"(?:(?:public|private|protected|internal|static|sealed|abstract|virtual|override"
    r"|async|extern|partial|unsafe|new|readonly)\s+)*"
)
_CSHARP_TYPE_HEADER_RE = re.compile(
    r"\b(?P<kind>class|struct|interface|enum|record(?:\s+(?:class|struct))?)\s+(?P<name>\w+)"
    + _CSHARP_TYPE_PARAMS
    + r"[^;{}]*\{"
)
_CSHARP_METHOD_HEAD_RE = re.compile(
    _CSHARP_DECL_START + rf"(?P<modifiers>{_CSHARP_DECL_MODIFIERS})"
    r"(?!(?:new|return|throw|yield|if|for|foreach|while|switch|catch|using|lock|var"
    r"|await|else|do|case|goto"
    r"|public|private|protected|internal|static|sealed|abstract|virtual|override"
    r"|async|extern|partial|unsafe|readonly|implicit|explicit|operator)\b)"
    rf"(?:ref\s+(?:readonly\s+)?)?{_CSHARP_TYPE_TOKEN}\s+(?P<name>\w+)"
    + _CSHARP_TYPE_PARAMS
    + r"\s*\(",
    re.MULTILINE,
)
_CSHARP_METHOD_TAIL_RE = re.compile(r"\s*(?:where\s+[^;{}=]*)?(?P<body>\{|=>|;|\Z)")
_CSHARP_METHOD_USE_RE = re.compile(r"\s*(?:<[^;{}()=]*>\s*)?\(")
_CSHARP_CONST_HEAD_RE = re.compile(
    _CSHARP_DECL_START
    + _CSHARP_DECL_MODIFIERS
    + rf"const\s+{_CSHARP_TYPE_TOKEN}\s+(\w+)\s*=(?!=|>)",
    re.MULTILINE,
)
_CSHARP_CONST_NEXT_RE = re.compile(r",\s*(\w+)\s*=(?!=|>)")
_CSHARP_NEW_RE = re.compile(rf"\bnew\b(?:\s+(?P<type>{_CSHARP_TYPE_TOKEN}))?\s*([({{])")
_CSHARP_TARGET_TYPED_NEW_RE = re.compile(r"(?:[=(\[{]|=>|\breturn)\s*$")
_CSHARP_INITIALIZER_KEY_RE = re.compile(r"[{,]\s*@?([A-Za-z_]\w*)\s*=(?!=|>)\s*")
_CSHARP_SEMICOLON_RE = re.compile(";")
_BALANCED_GROUP_OPENERS = {"}": "{", ")": "(", "]": "["}


def _balanced_groups(view: str) -> tuple[list[int], dict[int, int]]:
    """Innermost group at each character and closing indexes of balanced groups."""
    owners: list[int] = []
    ends: dict[int, int] = {}
    stack: list[int] = []
    for index, char in enumerate(view):
        parent = stack[-1] if stack else -1
        owners.append(parent)
        if char in "{([":
            stack.append(index)
        elif stack and _BALANCED_GROUP_OPENERS.get(char) == view[parent]:
            ends[stack.pop()] = index
    return owners, ends


def _csharp_type_parameters(header: re.Match[str]) -> set[str]:
    return {part.split()[-1] for part in (header["params"] or "").split(",") if part.strip()}


def _csharp_statement_end(view: str, owners: list[int], start: int, scope_end: int) -> int | None:
    owner = owners[start]
    return next(
        (
            m.start()
            for m in _CSHARP_SEMICOLON_RE.finditer(view, start, scope_end)
            if owners[m.start()] == owner
        ),
        None,
    )


def _csharp_initializer_keys(view: str, owners: list[int], ends: dict[int, int]) -> _Spans:
    """Recognize assignments at an object initializer's own depth."""
    pending: set[int] = set()
    for constructor in _CSHARP_NEW_RE.finditer(view):
        start = constructor.end() - 1
        if view[start] == "(" and start in ends:
            if not constructor["type"]:
                prefix = view[: constructor.start()].rstrip()
                parent = owners[start]
                in_arguments = parent != -1 and view[parent] in "([" and prefix.endswith(",")
                if not in_arguments and not _CSHARP_TARGET_TYPED_NEW_RE.search(prefix):
                    continue
            after_args = ends[start] + 1
            start = after_args + len(view[after_args:]) - len(view[after_args:].lstrip())
        if start in ends and view[start] == "{":
            pending.add(start)

    keys: _Spans = []
    visited: set[int] = set()
    while pending:
        start = pending.pop()
        if start in visited:
            continue
        visited.add(start)
        for match in _CSHARP_INITIALIZER_KEY_RE.finditer(view, start, ends[start]):
            delimiter = match.start()
            if delimiter != start and (view[delimiter] != "," or owners[delimiter] != start):
                continue
            keys.append(match.span(1))
            child = match.end()
            if child in ends and view[child] == "{":
                pending.add(child)
    return keys


def _csharp_method_bindings(
    view: str, owners: list[int], ends: dict[int, int], type_bodies: dict[int, str]
) -> _Spans:
    """Use balanced parameter lists and the declaration's own body and scope."""
    spans: _Spans = []
    for head in _CSHARP_METHOD_HEAD_RE.finditer(view):
        owner = owners[head.start("name")]
        if owner != -1 and (view[owner] != "{" or owner not in ends):
            continue
        close = ends.get(head.end() - 1)
        if close is None:
            continue
        tail = _CSHARP_METHOD_TAIL_RE.match(view, close + 1)
        if tail is None:
            continue
        body = tail["body"]
        body_start = tail.start("body")
        end = ends.get(body_start) if body == "{" else body_start
        modifiers = set(head["modifiers"].split())
        # A fragment can end at an explicitly declared method signature.
        if not body and (
            owner != -1 or not ({"public", "private", "protected", "internal"} & modifiers)
        ):
            continue
        if (
            body == ";"
            and type_bodies.get(owner) != "interface"
            and not ({"abstract", "extern", "partial"} & modifiers)
        ):
            continue
        scope_end = ends.get(owner, len(view))
        if body == "=>":
            end = _csharp_statement_end(view, owners, body_start, scope_end)
        if end is None:
            continue
        declaring_type = _csharp_type_body(owner, owners, type_bodies)
        spans.extend(
            span
            for span in _bare_binding_spans(view, owner + 1, scope_end, {head["name"]}, method=True)
            if _csharp_type_body(span[0], owners, type_bodies) == declaring_type
        )
        spans.extend(
            _bare_binding_spans(
                view, head.start(), end, _csharp_type_parameters(head), type_parameter=True
            )
        )
    return spans


def _bare_binding_spans(
    view: str,
    start: int,
    end: int,
    names: set[str],
    *,
    method: bool = False,
    type_parameter: bool = False,
) -> _Spans:
    if not names:
        return []
    spans: _Spans = []
    for word in _WORD_RE.finditer(view, start, end):
        if word[0] not in names:
            continue
        prefix = view[: word.start()].rstrip()
        if prefix.endswith((".", "::")):
            continue
        if not type_parameter and _NEW_BEFORE_RE.search(prefix):
            continue
        if method and not _CSHARP_METHOD_USE_RE.match(view, word.end()):
            continue
        spans.append(word.span())
    return spans


def _blank_example_spans(view: str, spans: _Spans) -> str:
    chars = list(view)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    return "".join(chars)


def _csharp_type_body(position: int, owners: list[int], type_bodies: dict[int, str]) -> int:
    while position != -1 and position not in type_bodies:
        position = owners[position]
    return position


def _csharp_binding_view(view: str) -> str:
    owners, ends = _balanced_groups(view)
    spans = _csharp_initializer_keys(view, owners, ends)
    type_bodies: dict[int, str] = {}
    for header in _CSHARP_TYPE_HEADER_RE.finditer(view):
        body = header.end() - 1
        if body not in ends or owners[body] != owners[header.start()]:
            continue
        type_bodies[body] = header["kind"]
        spans.extend(
            _bare_binding_spans(
                view,
                header.start(),
                ends[body],
                _csharp_type_parameters(header),
                type_parameter=True,
            )
        )
    spans.extend(_csharp_method_bindings(view, owners, ends, type_bodies))
    for constant in _CSHARP_CONST_HEAD_RE.finditer(view):
        start = constant.start(1)
        if owners[start] != -1:
            continue
        end = _csharp_statement_end(view, owners, start, len(view))
        if end is None:
            continue
        declarations = [
            constant,
            *(
                other
                for other in _CSHARP_CONST_NEXT_RE.finditer(view, constant.end(), end)
                if owners[other.start()] == -1
            ),
        ]
        for declaration in declarations:
            spans.extend(
                span
                for span in _bare_binding_spans(
                    view, declaration.start(1), len(view), {declaration[1]}
                )
                if _csharp_type_body(span[0], owners, type_bodies) == -1
            )
    return _blank_example_spans(view, spans)


_JS_EXPORT_NAMES_RE = re.compile(r"(?<![\w$.])export\b\s*(?:type\b\s*)?\{([^{}]*)\}(\s*from\b)?")
_JS_IMPORT_NAMES_RE = re.compile(r"(?<![\w$.])import\b\s*(?:[\w$]+\s*,\s*)?\{([^{}]*)\}\s*from\b")
_JS_NAMED_ALIAS_RE = re.compile(
    r"(?:^|(?<=,))\s*(?:(type)\s+)?[\w$]+\s+as\s+([A-Za-z_$][\w$]*)\s*(?=,|$)"
)
_JS_MODULE_SPECIFIER_RE = re.compile(
    r"(?:\s|//[^\r\n]*(?:\r\n?|\n)|/\*(?:[^*]|\*(?!/))*\*/)*"
    r"""(?:"(?:\\.|[^"\\\r\n])*"|'(?:\\.|[^'\\\r\n])*')"""
)


def _js_named_aliases(clause: re.Match[str], *, export: bool) -> _Spans:
    offset = clause.start(1)
    return [
        (offset + m.start(2), offset + m.end(2))
        for m in _JS_NAMED_ALIAS_RE.finditer(clause[1])
        if export or m[1] is None
    ]


def _js_binding_view(view: str, source: str) -> str:
    """An export alias labels an export. An import alias binds a local name."""
    if "export" not in view and "import" not in view:
        return view
    owners, _ = _balanced_groups(view)
    exports = [
        clause for clause in _JS_EXPORT_NAMES_RE.finditer(view) if owners[clause.start()] == -1
    ]
    imports = [
        clause
        for clause in _JS_IMPORT_NAMES_RE.finditer(view)
        if owners[clause.start()] == -1 and _JS_MODULE_SPECIFIER_RE.match(source, clause.end())
    ]
    aliases = [span for clause in imports for span in _js_named_aliases(clause, export=False)]
    names = {view[start:end] for start, end in aliases}
    uses = _bare_binding_spans(view, 0, len(view), names)
    clauses = [*imports, *(clause for clause in exports if clause[2])]
    spans = [span for span in uses if not any(c.start() <= span[0] < c.end() for c in clauses)]
    spans.extend(aliases)
    spans.extend(span for clause in exports for span in _js_named_aliases(clause, export=True))
    return _blank_example_spans(view, spans)


_TYPE_BODY_RE = re.compile(r"\b(?:class|struct|record|interface)\s+[A-Z]\w*[^{;]*\{")
# A field or property declared directly in a type body: ``int Total;``,
# ``decimal Total { get; set; }``, ``int Total => 1;`` or ``int Total = 0;``.
_CSHARP_MEMBER_DECL_RE = re.compile(
    r"(?:^|(?<=[{;}]))\s*(?:(?:public|private|protected|internal|static|readonly|const"
    r"|virtual|override|abstract|sealed|new|required|volatile|unsafe)\s+)*"
    r"(?!(?:return|throw|await|yield|var|using|case|goto|else|new|class|struct|record"
    r"|interface|enum)\b)"
    r"[A-Za-z_][\w.]*(?:\s*<[^<>;{}]*>)?(?:\s*\[\s*\])*\??\s+([A-Z]\w*)\s*(?=;|=(?!=)|\{|=>)",
    re.MULTILINE,
)
# A TypeScript or JavaScript class field or interface property: ``Total: number``.
_TS_MEMBER_DECL_RE = re.compile(
    r"(?:^|(?<=[{;,]))\s*(?:(?:public|private|protected|readonly|static|declare|abstract"
    r"|override)\s+)*([A-Z]\w*)\s*[?!]?\s*(?=:|=(?![=>])|;)",
    re.MULTILINE,
)


def _type_member_scopes(view: str, lang: str) -> list[tuple[int, int, set[str]]]:
    """Each declared type's body span and the fields and properties it declares.

    Only declarations at the body's own brace depth count, so a local
    variable inside a method is not a member. A type whose body never
    closes contributes nothing.
    """
    pattern = _CSHARP_MEMBER_DECL_RE if lang == "csharp" else _TS_MEMBER_DECL_RE
    scopes: list[tuple[int, int, set[str]]] = []
    for header in _TYPE_BODY_RE.finditer(view):
        start, depth = header.end(), 0
        depths: list[int] = []
        for index in range(start, len(view)):
            char = view[index]
            if char == "}" and depth == 0:
                body = view[start:index]
                members = {
                    match[1] for match in pattern.finditer(body) if depths[match.start(1)] == 0
                }
                scopes.append((start, index, members))
                break
            depths.append(depth)
            depth += {"{": 1, "}": -1}.get(char, 0)
    return scopes


def _blank_in_scope_members(view: str, scopes: list[tuple[int, int, set[str]]]) -> str:
    """Blank a declared member's own declaration and bare uses inside its type body.

    Outside the declaring body a bare name stays visible, so it is checked.
    """
    chars = list(view)
    for start, end, members in scopes:
        for word in _WORD_RE.finditer(view, start, end):
            if word[0] in members:
                chars[word.start() : word.end()] = " " * len(word[0])
    return "".join(chars)


def _skip_group_back(view: str, end: int) -> int | None:
    """Index of the opener matching the closer just before ``end``, or None."""
    closer = view[end - 1]
    opener = _GROUP_OPENERS[closer]
    depth = 0
    for index in range(end - 1, -1, -1):
        if view[index] == closer:
            depth += 1
        elif view[index] == opener:
            depth -= 1
            if depth == 0:
                return index
    return None


class _Receiver(typing.NamedTuple):
    name: str
    position: int
    constructed: bool
    direct: bool
    type_path: bool = False


def _member_receiver(view: str, dot: int) -> _Receiver:
    """Walk a chain back to its root and distinguish direct member access."""
    end = dot
    hops = 0
    groups: list[str] = []
    while True:
        end = len(view[:end].rstrip())
        while end and view[end - 1] in _GROUP_OPENERS:
            if view[end - 1] == ">" and view[:end].endswith("=>"):
                return _Receiver("", dot, False, False)
            opener = _skip_group_back(view, end)
            if opener is None:
                return _Receiver("", dot, False, False)
            groups.append(view[opener])
            end = len(view[:opener].rstrip())
        word = _IDENTIFIER_BEFORE_RE.search(view[:end])
        if word is None:
            return _Receiver("", dot, False, False)
        start = end - len(word[0].rstrip())
        head = view[:start].rstrip()
        if head.endswith("."):
            hops += 1
            end = len(head) - 1 - (1 if head.endswith("?.") else 0)
            continue
        constructed = bool(_NEW_BEFORE_RE.search(head))
        direct = hops == 0 and (not groups or (constructed and groups == ["("]))
        return _Receiver(word[1], start, constructed, direct, constructed and not groups)


def _receiver_root(view: str, dot: int) -> tuple[str, bool]:
    receiver = _member_receiver(view, dot)
    return receiver.name, receiver.constructed


def _receiver_bindings(view: str, lang: str) -> typing.Callable[[_Receiver], str]:
    """Find a receiver's preceding declaration in a visible lexical block."""
    owners, ends = _balanced_groups(view)
    declarations: dict[tuple[str, int], dict[int, str]] = {}

    def block(position: int) -> int:
        owner = owners[position]
        while owner != -1 and view[owner] != "{":
            owner = owners[owner]
        return owner

    def declare(
        match: re.Match[str], name_group: int, type_group: int, *, inferred: bool = False
    ) -> None:
        position = match.start(name_group)
        scope = block(position)
        group = owners[position]
        if group != -1 and view[group] == "(" and group in ends:
            after = ends[group] + 1
            tail = view[after:].lstrip()
            if tail.startswith("{"):
                scope = len(view) - len(tail)
        key = (match[name_group], scope)
        binding = declarations.setdefault(key, {})
        if inferred and not (
            binding.get(position) == "var"
            or (lang == "typescript" and _TS_VARIABLE_BEFORE_RE.search(view[:position]))
        ):
            return
        binding[position] = re.sub(r"\s+", "", match[type_group])

    if lang == "csharp":
        for match in _CSHARP_TYPED_NAME_RE.finditer(view):
            declare(match, 2, 1)
    else:
        for match in _TS_TYPED_NAME_RE.finditer(view):
            declare(match, 1, 2)
    for match in _NEW_ASSIGNED_RE.finditer(view):
        declare(match, 1, 2, inferred=True)

    def resolve(receiver: _Receiver) -> str:
        if receiver.constructed:
            return receiver.name
        scope = block(receiver.position)
        while True:
            local = declarations.get((receiver.name, scope), {})
            position = max((p for p in local if p < receiver.position), default=-1)
            if position != -1:
                return local[position]
            if scope == -1:
                return receiver.name
            scope = block(scope)

    return resolve


def _receiver_types(view: str, lang: str) -> dict[str, str]:
    """Lowercase variable name -> declared or constructed type in the example."""
    typed = (
        [(name, kind) for kind, name in _CSHARP_TYPED_NAME_RE.findall(view)]
        if lang == "csharp"
        else _TS_TYPED_NAME_RE.findall(view)
    )
    types = dict(typed)
    types.update(_NEW_ASSIGNED_RE.findall(view))
    return {name: kind.rsplit(".", 1)[-1].strip() for name, kind in types.items()}


def _proven_member_names(
    view: str, lang: str, local_types: set[str], unresolved_types: set[str]
) -> set[str]:
    """Member names whose every access has a receiver proven not to be repo API.

    A receiver is proven when its chain starts at a type the example
    declares, a framework type, a variable declared or constructed with one
    of those, or ``this``/``base`` inside an example that declares a type.
    A free variable, or one assigned from an unresolved call, proves
    nothing, so its members stay checkable.
    """
    proven_types = (local_types - unresolved_types) | _PROVEN_RECEIVER_TYPES.get(lang, frozenset())
    variables = _receiver_types(view, lang)
    proven: dict[str, bool] = {}
    for match in _MEMBER_ACCESS_RE.finditer(view):
        root, constructed = _receiver_root(view, match.start())
        if root in ("this", "base"):
            ok = bool(local_types - unresolved_types)
        else:
            receiver_type = root if constructed else variables.get(root, root)
            ok = bool(root) and receiver_type in proven_types
        proven[match[1]] = proven.get(match[1], True) and ok
    return {name for name, ok in proven.items() if ok}


_CSHARP_MEMBER_CALL_RE = re.compile(r"\s*(?:<[^;{}()]*?>\s*)?\(")
_NAMED_ARGUMENT_RE = re.compile(r"(?<=[(,])\s*(\w+)\s*:")
_RepoMethods = dict[tuple[str, str], list[SourceSymbol]]


def _qualified_member_checks(
    source: str,
    lexical: str,
    checked: str,
    lang: str,
    local_types: set[str],
    repo_methods: _RepoMethods,
    literal_ends: set[int],
) -> tuple[str, set[str], list[tuple[SourceSymbol, str]]]:
    """Consume member occurrences before bare names reach the global index."""
    resolve_receiver = _receiver_bindings(lexical, lang)
    concrete_types = local_types | _PROVEN_RECEIVER_TYPES[lang]
    unchecked_types = {"dynamic"} if lang == "csharp" else {"any", "unknown"}
    owners, ends = _balanced_groups(checked)
    spans: _Spans = []
    unresolved: set[str] = set()
    wrong_parameters: list[tuple[SourceSymbol, str]] = []
    for match in _MEMBER_ACCESS_RE.finditer(checked):
        name = match[1]
        receiver = _member_receiver(lexical, match.start())
        if receiver.type_path:
            continue
        receiver_type = resolve_receiver(receiver)
        call = _CSHARP_MEMBER_CALL_RE.match(checked, match.end())
        if lang == "csharp" and (
            not _TYPE_NAME_RE.fullmatch(name) or (not call and receiver_type not in unchecked_types)
        ):
            continue
        if lang == "typescript" and receiver.name[:1].isdigit():
            continue
        spans.append(match.span(1))
        if literal_ends and len(source[: match.start()].rstrip()) in literal_ends:
            continue
        if receiver_type in unchecked_types:
            unresolved.add(name)
            continue
        if receiver_type.rsplit(".", 1)[-1] in concrete_types or (
            receiver.name in {"this", "base"} and local_types
        ):
            continue

        methods = repo_methods.get((receiver_type, name), []) if receiver.direct else []
        static_access = not receiver.constructed and receiver.name == receiver_type
        methods = [
            method
            for method in methods
            if ("static" in method.signature.split("(", 1)[0].split()) == static_access
        ]
        if not methods or call is None:
            unresolved.add(name)
            continue
        opening = call.end() - 1
        params = [
            param[1]
            for param in _NAMED_ARGUMENT_RE.finditer(
                checked, opening + 1, ends.get(opening, opening)
            )
            if owners[param.start(1)] == opening
        ]
        if not params:
            continue
        methods = [method for method in methods if method.parameter_names is not None]
        if not methods:
            unresolved.add(name)
            continue
        missing_by_overload = [
            [param for param in params if param not in (method.parameter_names or [])]
            for method in methods
        ]
        best = min(range(len(methods)), key=lambda index: len(missing_by_overload[index]))
        wrong_parameters.extend((methods[best], param) for param in missing_by_overload[best])
    return _blank_example_spans(checked, spans), unresolved, wrong_parameters


# A C# preprocessor directive occupies its whole line, optionally indented,
# with optional whitespace after "#". Directive lines name build symbols
# (NETFRAMEWORK, NET472, DEBUG) or tooling text (#region, #pragma), never a
# repository declaration.
_CSHARP_DIRECTIVE_LINE_RE = re.compile(r"^[ \t]*#[ \t]*[a-z]+\b.*$", re.MULTILINE)


def _sibling_module(stem: str) -> ModuleType:
    """Import a sibling script module by name, as ``_same_pr_scan`` does."""
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    return importlib.import_module(stem)


def _extract_identifiers(
    code: str,
    lang: str = "",
    doc_definitions: frozenset[str] | set[str] = frozenset(),
    *,
    resolve_import: _PyImportResolver | None = None,
) -> list[str]:
    """Extract potential identifiers from a code snippet.

    For Python (``lang == "python"``) only code tokens count: strings,
    docstrings and comments are blanked first, names imported from the
    standard library, declarations within the example, and names whose every
    occurrence binds or resolves within the example are dropped, and
    attribute chains on stdlib-imported modules are blanked.

    f-string expressions stay visible only on Python 3.12+, where the
    tokenizer splits f-strings. On 3.10 and 3.11 the whole f-string is one
    STRING token and is blanked, which can only miss a symbol, never add a
    false finding. C#, TypeScript, and JavaScript comments are blanked,
    example-local declarations are dropped. TypeScript and JavaScript
    literal text is blanked by ``_c_family_code_view``; C# literal text by
    the steps below. Member calls stay visible for parameter checks against
    known methods. TypeScript object-literal keys are data, not named
    parameters.

    For C# (``lang == "csharp"``) preprocessor directive lines are blanked
    first, so ``#if NETFRAMEWORK`` does not report an unresolved symbol
    (issue #7453). Then string and char literal text is blanked, keeping
    interpolation holes, so ``[Conditional("DEBUG")]`` does not report
    ``DEBUG``. Named-argument names in attribute argument lists are blanked
    too, so ``EntryPoint`` in ``[DllImport("k32", EntryPoint = "Beep")]`` is
    not reported. The attribute name itself stays a checked code reference.
    When the literal scan cannot read the snippet, the raw code is scanned,
    which can only report extra names. Other languages keep lines starting with
    ``#``, because JavaScript and TypeScript private members use that prefix,
    and keep the language-agnostic scan.
    """
    ignored_names: set[str] = set(doc_definitions)
    if lang == "python":
        ignored_names.update(_python_example_definitions(code))
        excluded_names, code = _python_example_bindings(code, resolve_import)
        ignored_names.update(excluded_names)
        code = _blank_stdlib_plain_import_lines(code)
    elif lang in _DECLARATION_RES:
        if lang == "csharp":
            code = _CSHARP_DIRECTIVE_LINE_RE.sub("", code)
            blanked = _sibling_module("csharp_literals").blank_csharp_literals(code)
            if blanked is None:
                # An unclosed string, a multi-line verbatim string, or the
                # recursion limit stopped the scan. Scanning the unblanked code
                # can only report extra names, never hide one.
                logger.warning("C# literal scan could not read the snippet; scanning raw code")
            else:
                holes = _sibling_module("csharp_holes")
                code = holes.blank_csharp_attribute_named_args(blanked)
        ignored_names.update(_example_declaration_names(code, lang))
        code = _strip_csharp_comments(code) if lang == "csharp" else _c_family_code_view(code, lang)
    # Match CamelCase and snake_case identifiers (3+ chars)
    identifiers = re.findall(r"\b([A-Z][a-zA-Z0-9]+)\b", code)
    # Also match method calls
    identifiers.extend(re.findall(r"\.([A-Za-z]\w+)\s*\(", code))
    if lang == "typescript":
        identifiers.extend(_MEMBER_ACCESS_RE.findall(code))

    if lang not in ("typescript", "javascript"):
        # Named parameters (C# style)
        identifiers.extend(re.findall(r"(\w+)\s*:", code))
    return sorted(set(identifiers) - ignored_names)


def _doc_example_definitions(lines: list[str]) -> dict[str, set[str]]:
    """Type names declared by any fenced example in the document.

    Only declarations in fences of the same language resolve each other.
    """
    definitions: dict[str, set[str]] = {}
    i = 0
    while i < len(lines):
        fence_match = re.match(r"^```(\S*)", lines[i])
        if not fence_match:
            i += 1
            continue
        lang = _detect_language(fence_match.group(1))
        i += 1
        block: list[str] = []
        while i < len(lines) and not lines[i].startswith("```"):
            block.append(lines[i])
            i += 1
        definitions.setdefault(lang, set()).update(
            _example_declaration_names("\n".join(block), lang)
        )
        i += 1
    return definitions


# File-level opt-out for Markdown that documents another product's SDK:
#   <!-- doc-accuracy: external-sdk <name> -- <reason> -->
# A well-formed marker silences ``unresolved_symbol`` for the whole file.
# A marker whose SDK name is missing or not a real name (no letter or digit,
# starts with "-", or is the "<name>" placeholder) is reported as
# INVALID_SDK_MARKER_CLAIM and suppresses nothing.
#
# Fail closed, with no fence state. A marker is honored only when (a) its line
# starts with ``<!--`` at column 0, and (b) no EARLIER line contains a run of
# three backticks or three tildes anywhere on the line. Every fenced code
# block's opening line contains such a run, so a marker with none before it
# cannot be inside a fence. Tracking fences instead (top level only, or with
# container prefixes) inverts after a list item, blockquote, or HTML block that
# holds a fence-like line, and then honors a marker inside a later real fence.
# The cost: a marker placed below any code fence is not honored. Put it right
# after the H1.
_EXTERNAL_SDK_MARKER_RE = re.compile(
    r"<!--\s*doc-accuracy:\s*external-sdk(?=\s|-->)(?P<body>.*?)-->"
)
_FENCE_LIKE_RUNS = ("```", "~~~")
INVALID_SDK_MARKER_CLAIM = "invalid_external_sdk_marker"


def _parse_sdk_marker_body(body: str) -> tuple[str, str]:
    """Return ``(sdk name, reason)`` from a marker body; name is "" when absent.

    The name is the whitespace-separated tokens before the first ``--`` token,
    the reason is the tokens after it. One linear pass, no regex.
    """
    tokens = body.split()
    if "--" not in tokens:
        name, reason = " ".join(tokens), ""
    else:
        split_at = tokens.index("--")
        name, reason = " ".join(tokens[:split_at]), " ".join(tokens[split_at + 1 :])
    return (name if _is_valid_sdk_name(name) else ""), reason


def _is_valid_sdk_name(name: str) -> bool:
    """True when ``name`` names an SDK, not a typo or the template placeholder."""
    return (
        any(ch.isalnum() for ch in name)
        and not name.startswith("-")
        and not (name.startswith("<") and name.endswith(">"))
    )


def _find_external_sdk_markers(lines: list[str]) -> list[tuple[int, str, str]]:
    """Find honored markers as ``(1-based line, sdk name, reason)`` tuples.

    A marker counts only when ``<!--`` starts at column 0 and no earlier line
    contains three backticks or three tildes (see the module comment above).
    Scanning stops at the first line holding such a run. A marker after that
    line is ignored, whether well formed or nameless, because it may be example
    text inside a fence. ``sdk name`` is "" for a nameless marker, which the
    caller reports. A marker split across LF-terminated lines is not recognized.
    """
    stop = _sdk_marker_scan_stop(lines)
    scanned = lines if stop is None else lines[: stop + 1]
    markers: list[tuple[int, str, str]] = []
    for number, line in enumerate(scanned, start=1):
        marker = _EXTERNAL_SDK_MARKER_RE.match(line)
        if marker:
            name, reason = _parse_sdk_marker_body(marker.group("body"))
            markers.append((number, name, reason))
    return markers


def _sdk_marker_scan_stop(lines: list[str]) -> int | None:
    """0-based index of the first line holding a fence-like run, or None.

    The marker scan reads up to and including this line and no further.
    """
    for index, line in enumerate(lines):
        if any(run in line for run in _FENCE_LIKE_RUNS):
            return index
    return None


def _first_ignored_sdk_marker(lines: list[str]) -> dict[str, int] | None:
    """Locate the first well-formed marker the scan ignored, and the stop line.

    Returns 1-based ``{"line": marker, "stop_line": stop}`` or None. Lines
    above an unchanged marker keep their order, so the marker can only have
    been honored at the base when the diff changed the marker line or the
    stop line (the first fence-like line, which must then be new).
    """
    stop = _sdk_marker_scan_stop(lines)
    if stop is None:
        return None
    for number, line in enumerate(lines[stop + 1 :], start=stop + 2):
        marker = _EXTERNAL_SDK_MARKER_RE.match(line)
        if marker and _parse_sdk_marker_body(marker.group("body"))[0]:
            return {"line": number, "stop_line": stop + 1}
    return None


# Every pattern is anchored at the start of a line, so a declaration counts
# only where a statement begins. Text in the middle of a line, such as a regex
# literal or a string the blanking pass could not parse, declares nothing.
# Keyword and modifier runs stay on one line, and no two adjacent parts can
# share a run of spaces, so a crafted line costs linear time per line. The
# property pattern crosses line breaks on purpose, because a name, its ``{``
# and ``get`` often sit on separate lines. A declaration a pattern misses
# keeps its finding, which is the safe direction.
_CS_ATTRIBUTES = r"(?:\[[^\]\n]*\][ \t]*)*"
_CS_MODIFIERS = (
    r"(?:(?:public|private|protected|internal|static|sealed|abstract|partial"
    r"|readonly|unsafe|file|new|ref)[ \t]+)*"
)
_CS_METHOD_MODIFIER_WORDS = (
    r"public|private|protected|internal|static|virtual|override|abstract"
    r"|sealed|async|extern|unsafe|new|partial|readonly"
)
_CS_METHOD_MODIFIERS = r"(?:(?:" + _CS_METHOD_MODIFIER_WORDS + r")[ \t]+)*"
# A return type: no modifier or conversion keyword, then type characters. A
# comma inside a generic may be followed by one space (``Dictionary<string,
# int>``). The comma is only in the second branch, so each character has one
# parse. One space at most keeps that branch from sharing a run of spaces with
# the ``[ \t]+`` before the method name, which would make a match quadratic.
_CS_RETURN_TYPE = (
    r"(?!(?:" + _CS_METHOD_MODIFIER_WORDS + r"|implicit|explicit|operator)\b)"
    r"(?:[\w<>\[\].?]|,[ \t]?){1,200}"
)
_DECLARED_NAME_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "csharp": (
        re.compile(
            r"^[ \t]*" + _CS_ATTRIBUTES + _CS_MODIFIERS + r"(?:class|struct|interface|enum"
            r"|record(?:[ \t]+(?:class|struct))?|namespace)[ \t]+([A-Za-z_][\w.]*)",
            re.MULTILINE,
        ),
        re.compile(
            r"^[ \t]*(?:[\w<>\[\],.?]+[ \t]+)+([A-Za-z_]\w*)\s*\{\s*(?:get|set|init)\b",
            re.MULTILINE,
        ),
        # A method has a return type between its modifiers and its name. A
        # constructor (``protected internal Order(``) has none: it names a type
        # it does not declare. A modifier word is never a return type, so no
        # modifier can stand in for one. A conversion operator names its target
        # type the same way, so ``implicit``, ``explicit`` and ``operator`` are
        # never a return type either.
        re.compile(
            r"^[ \t]*"
            + _CS_ATTRIBUTES
            + r"(?:public|private|protected|internal)[ \t]+"
            + _CS_METHOD_MODIFIERS
            + _CS_RETURN_TYPE
            + r"[ \t]+([A-Za-z_]\w*)[ \t]*\(",
            re.MULTILINE,
        ),
    ),
    "python": (re.compile(r"^[ \t]*(?:async[ \t]+)?(?:class|def)[ \t]+(\w+)", re.MULTILINE),),
    "javascript": (
        re.compile(
            r"^[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?(?:declare[ \t]+)?(?:abstract[ \t]+)?"
            r"(?:async[ \t]+)?(?:class|interface|enum|function)[ \t]+([A-Za-z_$][\w$]*)",
            re.MULTILINE,
        ),
        # A type alias is ``type Name =`` or ``type Name<...> =``. Requiring the
        # ``=`` or ``<`` keeps ``import type X`` and a wrapped
        # ``import {\n  type X,\n}`` list as claims about the repository.
        re.compile(
            r"^[ \t]*(?:export[ \t]+)?(?:declare[ \t]+)?type[ \t]+([A-Za-z_$][\w$]*)[ \t]*[=<]",
            re.MULTILINE,
        ),
    ),
}
_DECLARED_NAME_PATTERNS["typescript"] = _DECLARED_NAME_PATTERNS["javascript"]

# Comments and string literals in C#, JavaScript, and TypeScript. Blanking errs
# toward hiding a declaration, which can only keep a finding, never drop one.
# A backslash always consumes the next character (or the end of the block), so
# each string body has one parse and every alternative ends without failing.
_C_LIKE_NON_CODE_RE = re.compile(
    r"(?s)/\*.*?(?:\*/|\Z)"
    r"|//[^\n]*"
    # C# raw strings (3 to 16 quotes, closed by the same run) and verbatim
    # strings span lines. The cap keeps the backreference check linear.
    r'|("{3,16}).*?(?:\1|\Z)'
    r'|(?:\$@|@\$?)"(?:""|[^"])*(?:"|\Z)'
    r"|\"(?:\\(?:.|\Z)|[^\"\\\n])*(?:\"|(?=\n)|\Z)"
    r"|'(?:\\(?:.|\Z)|[^'\\\n])*(?:'|(?=\n)|\Z)"
    r"|`(?:\\(?:.|\Z)|[^`\\])*(?:`|\Z)"
)


def _strip_non_code(code: str, lang: str) -> str:
    """Blank comments and strings so a keyword in them declares nothing."""
    if lang == "python":
        return _strip_python_non_code(code)
    return _C_LIKE_NON_CODE_RE.sub(lambda m: " " * len(m.group(0)), code)


def _declared_names(code: str, lang: str) -> set[str]:
    """Names a code block declares itself, so they are not repo symbol claims.

    Conservative on purpose: every pattern needs a declaration keyword, an
    access modifier, or a property accessor, so a plain use never counts.
    Comments and strings are blanked first, so ``// class Ghost`` declares
    nothing. Dotted namespaces such as ``Foo.Bar`` contribute each part.
    """
    patterns = _DECLARED_NAME_PATTERNS.get(lang, ())
    if not patterns:
        return set()
    code = _strip_non_code(code, lang)
    names: set[str] = set()
    for pattern in patterns:
        for found in pattern.findall(code):
            names.update(part for part in found.split(".") if part)
    return names


def _exemption_lines(
    claims_data: dict[str, Any] | None, compilability_data: dict[str, Any] | None
) -> list[str]:
    """One human-readable line per file exempted by an external-sdk marker."""
    exempt = (claims_data or {}).get("external_sdk_files", {})
    suppressed = (compilability_data or {}).get("external_sdk_suppressed", {})
    phase_three_ran = (
        compilability_data is not None and compilability_data.get("status") != "DID_NOT_RUN"
    )
    lines = []
    for path, info in sorted(exempt.items()):
        info = info if isinstance(info, dict) else {"sdk": str(info)}
        lines.append(
            f"External SDK exemption: {path} (SDK {info.get('sdk', '')}, "
            f"marker line {info.get('line', '?')}), "
            f"reason: {info.get('reason') or 'none given'}; "
            + (
                f"{suppressed.get(path, 0)} unresolved_symbol suppressed"
                if phase_three_ran
                else "unresolved_symbol not checked (phase 3 did not run)"
            )
        )
    return lines


def _declared_skip_lines(compilability_data: dict[str, Any] | None) -> list[str]:
    """One line per file whose examples declared names Phase 3 then skipped."""
    declared = (compilability_data or {}).get("declared_name_suppressed", {})
    return [
        f"{path}: {count} unresolved_symbol skipped because the same code example declares them"
        for path, count in sorted(declared.items())
    ]


def _extract_quantitative_claims(line: str) -> list[str]:
    """Find quantitative claims in a line of text."""
    patterns = [
        r"[<>~]\s*\d+[%]",  # <5%, >90%, ~10%
        r"\d+-\d+\s*(?:ns|ms|us|s)\b",  # 15-40ns
        r"\d+\s*(?:ns|ms|us|s)\b",  # 100ns
        r"\d+(?:\.\d+)?%",  # 33.4%
        r"\+\d+(?:\.\d+)?%",  # +93.1%
    ]
    claims = []
    for p in patterns:
        claims.extend(re.findall(p, line))
    return claims


def run_claim_extraction(
    repo_root: Path,
    assessment: dict[str, Any],
) -> dict[str, Any]:
    """Phase 2: Extract verifiable claims from documentation files."""
    claims: list[Claim] = []
    claim_counter = 0
    external_sdk_files: dict[str, dict[str, Any]] = {}
    external_sdk_ignored: dict[str, dict[str, int]] = {}

    # Build symbol -> source file mapping
    symbol_to_source: dict[str, str] = {}
    source_symbols = assessment.get("source_symbols", [])
    for sym in source_symbols:
        symbol_to_source[sym["name"]] = sym["file"]
    resolve_import = _python_import_resolver(repo_root, source_symbols)

    for doc_info in assessment.get("documentation_files", []):
        doc_path = repo_root / doc_info["path"]
        try:
            content = _read_doc_text(doc_path)
        except OSError as exc:
            logger.warning("Failed to read doc file %s: %s", doc_info["path"], exc)
            continue

        lines = [ln[:-1] if ln.endswith("\r") else ln for ln in content.split("\n")]
        mapped_sources = doc_info.get("mapped_source_files", [])
        default_source = mapped_sources[0] if mapped_sources else ""
        doc_definitions = _doc_example_definitions(lines)

        ignored_marker = _first_ignored_sdk_marker(lines)
        if ignored_marker is not None:
            external_sdk_ignored[doc_info["path"]] = ignored_marker

        for marker_line, sdk_name, reason in _find_external_sdk_markers(lines):
            if sdk_name:
                external_sdk_files.setdefault(
                    doc_info["path"], {"sdk": sdk_name, "reason": reason, "line": marker_line}
                )
                continue
            claim_counter += 1
            claims.append(
                Claim(
                    id=f"claim-{claim_counter:04d}",
                    file=doc_info["path"],
                    line=marker_line,
                    claim_type=INVALID_SDK_MARKER_CLAIM,
                    language="",
                    content=lines[marker_line - 1].strip(),
                    symbols_referenced=[],
                    mapped_source=default_source,
                )
            )

        i = 0
        while i < len(lines):
            line = lines[i]

            # Detect fenced code blocks
            fence_match = re.match(r"^```(\S*)", line)
            if fence_match:
                lang = _detect_language(fence_match.group(1))
                block_start = i + 1
                i += 1
                block_lines = []
                while i < len(lines) and not lines[i].startswith("```"):
                    block_lines.append(lines[i])
                    i += 1

                code_content = "\n".join(block_lines)
                if not code_content.strip():
                    i += 1
                    continue

                identifiers = _extract_identifiers(
                    code_content,
                    lang,
                    doc_definitions.get(lang, set()),
                    resolve_import=resolve_import,
                )
                # Map identifiers to source files
                mapped = default_source
                for ident in identifiers:
                    if ident in symbol_to_source:
                        mapped = symbol_to_source[ident]
                        break

                claim_counter += 1
                claims.append(
                    Claim(
                        id=f"claim-{claim_counter:04d}",
                        file=doc_info["path"],
                        line=block_start,
                        claim_type="code_example",
                        language=lang,
                        content=code_content,
                        symbols_referenced=identifiers,
                        mapped_source=mapped,
                        end_line=block_start + len(block_lines) + 1,  # closing fence
                    )
                )
                i += 1
                continue

            # Detect behavioral claims (sentences with method references)
            method_ref = re.search(
                r"`(\w+)\(\)`\s+(?:emits?|returns?|throws?|creates?|produces?)",
                line,
            )
            if method_ref:
                claim_counter += 1
                method_name = method_ref.group(1)
                mapped = symbol_to_source.get(method_name, default_source)
                claims.append(
                    Claim(
                        id=f"claim-{claim_counter:04d}",
                        file=doc_info["path"],
                        line=i + 1,
                        claim_type="behavioral",
                        language="",
                        content=line.strip(),
                        symbols_referenced=[method_name],
                        mapped_source=mapped,
                    )
                )

            # Detect quantitative claims
            quant_claims = _extract_quantitative_claims(line)
            if quant_claims:
                claim_counter += 1
                claims.append(
                    Claim(
                        id=f"claim-{claim_counter:04d}",
                        file=doc_info["path"],
                        line=i + 1,
                        claim_type="quantitative",
                        language="",
                        content=line.strip(),
                        symbols_referenced=quant_claims,
                        mapped_source=default_source,
                    )
                )

            # Detect method signature claims
            sig_match = re.search(
                r"(?:constructor|method|function)\s+(?:accepts?|takes?|requires?)\s+"
                r"`([^`]+)`",
                line,
                re.IGNORECASE,
            )
            if sig_match:
                claim_counter += 1
                claims.append(
                    Claim(
                        id=f"claim-{claim_counter:04d}",
                        file=doc_info["path"],
                        line=i + 1,
                        claim_type="method_signature",
                        language="",
                        content=line.strip(),
                        symbols_referenced=_extract_identifiers(sig_match.group(1)),
                        mapped_source=default_source,
                    )
                )

            i += 1

    return {
        "claims": [c.to_dict() for c in claims],
        "external_sdk_files": external_sdk_files,
        "external_sdk_ignored": external_sdk_ignored,
    }


# ---------------------------------------------------------------------------
# Phase 3: Compilability Check
# ---------------------------------------------------------------------------


def _marker_may_have_flipped(marker: dict[str, int], ranges: list[list[int]]) -> bool:
    """True when a changed range covers the ignored marker or the scan stop line."""
    watched = (marker["line"], marker["stop_line"])
    return any(lo <= line <= hi for lo, hi in ranges for line in watched)


def _scope_findings(
    findings: list[dict[str, Any]],
    claims_by_id: dict[str, dict[str, Any]],
    changed_lines: dict[str, list[list[int]]] | None,
    ignored_markers: dict[str, dict[str, int]] | None = None,
) -> list[dict[str, Any]]:
    """Mark findings in or out of the PR's changed lines (``--diff-base`` only).

    ``changed_lines`` is None without ``--diff-base``; findings are returned
    untouched so full-file gating is unchanged. Otherwise every finding gets
    ``in_diff``. One whose claim span misses every changed range is downgraded
    to ``info`` (``original_severity`` keeps the old value), so it stays
    visible but never reaches the gate.

    ``ignored_markers`` maps a file to its first well-formed external-sdk
    marker that the scan ignored, as ``{"line", "stop_line"}``. When the diff
    changed either line, the marker may have been honored at the base, so an
    ``unresolved_symbol`` finding in that file stays in scope.
    """
    if changed_lines is None:
        return findings
    markers = ignored_markers or {}
    for finding in findings:
        claim = claims_by_id[finding["claim_id"]]
        ranges = changed_lines.get(_norm_path(claim["file"]))
        # Fail closed: a file with no entry, or an empty list, is changed in
        # full.
        in_diff = not ranges or _claim_in_ranges(claim, ranges)
        marker = markers.get(claim["file"])
        if (
            not in_diff
            and marker is not None
            and finding["category"] == "unresolved_symbol"
            and _marker_may_have_flipped(marker, ranges or [])
        ):
            in_diff = True
            # The claim's own lines did not change, so say why it gates.
            finding["scope_reason"] = "ignored_external_sdk_marker"
            finding["scope_marker_line"] = marker["line"]
        finding["in_diff"] = in_diff
        if not in_diff:
            finding["original_severity"] = finding["severity"]
            finding["severity"] = "info"
    return findings


def _phantom_parameter_finding(
    number: int, claim: dict[str, Any], actual: SourceSymbol, param: str
) -> Finding:
    return Finding(
        id=f"compile-{number:04d}",
        claim_id=claim["id"],
        severity="critical",
        category="phantom_parameter",
        file=claim["file"],
        line=claim["line"],
        description=(
            f"Parameter '{param}' does not exist in {actual.name}(). "
            f"Actual signature: {actual.signature}"
        ),
        evidence={
            "documented": claim["content"][:200],
            "actual_signature": actual.signature,
            "source_file": actual.file,
            "source_line": actual.line,
        },
        suggested_fix=(
            f"Remove or rename parameter '{param}'. Check {actual.file}:{actual.line} for "
            f"correct signature."
        ),
    )


def run_compilability_check(
    assessment: dict[str, Any],
    claims_data: dict[str, Any],
) -> dict[str, Any]:
    """Phase 3: Verify symbols in code examples exist in the codebase."""
    source_symbols = assessment.get("source_symbols", [])
    if not source_symbols:
        return {
            "status": "DID_NOT_RUN",
            "reason": ("No source symbols found; Phase 3 cannot verify documentation references."),
            "findings": [],
        }

    findings: list[Finding] = []
    finding_counter = 0

    # Build symbol index from assessment
    symbol_index: dict[str, SourceSymbol] = {}
    csharp_types: dict[str, list[tuple[str, str]]] = {}
    repo_methods: _RepoMethods = {}
    for sym_dict in source_symbols:
        sym = SourceSymbol(**sym_dict)
        symbol_index[sym.name] = sym
        if sym.file.lower().endswith(".cs") and sym.kind in {
            "class",
            "struct",
            "record",
            "interface",
        }:
            csharp_types.setdefault(sym.name, []).append((sym.kind, sym.partial_scope))
        if sym.declaring_type and sym.kind == "method":
            repo_methods.setdefault((sym.declaring_type, sym.name), []).append(sym)
    unambiguous = {
        name
        for name, declarations in csharp_types.items()
        if len(declarations) == 1 or (declarations[0][1] and len(set(declarations)) == 1)
    }
    repo_methods = {key: methods for key, methods in repo_methods.items() if key[0] in unambiguous}

    # Build a set of all known symbol names for quick lookup
    known_names = set(symbol_index.keys())

    external_sdk_files: dict[str, Any] = claims_data.get("external_sdk_files", {})
    external_sdk_suppressed: dict[str, int] = {}
    declared_name_suppressed: dict[str, int] = {}

    for claim_dict in claims_data.get("claims", []):
        if claim_dict["type"] == INVALID_SDK_MARKER_CLAIM:
            finding_counter += 1
            findings.append(
                Finding(
                    id=f"compile-{finding_counter:04d}",
                    claim_id=claim_dict["id"],
                    severity="high",
                    category="invalid_external_sdk_marker",
                    file=claim_dict["file"],
                    line=claim_dict["line"],
                    description=(
                        "external-sdk marker names no SDK, so it suppresses nothing. "
                        "Expected: <!-- doc-accuracy: external-sdk <name> -- <reason> -->"
                    ),
                    evidence={"documented": claim_dict["content"][:200]},
                    suggested_fix="Add the SDK name and a reason after 'external-sdk'.",
                )
            )
            continue

        if claim_dict["type"] not in ("code_example", "method_signature"):
            continue

        content = claim_dict["content"]
        lang = claim_dict.get("language", "")
        # Literal text and comments are data; interpolation holes stay code.
        literal_ends: set[int] = set()
        lexical_content = (
            _c_family_code_view(content, lang, literal_ends=literal_ends)
            if lang in _DECLARATION_RES
            else content
        )
        checked_content = lexical_content
        if lang == "csharp":
            checked_content = _csharp_binding_view(lexical_content)
        elif lang in ("typescript", "javascript"):
            checked_content = _js_binding_view(lexical_content, content)
        symbols_ref = claim_dict.get("symbols_referenced", [])
        unresolved_members: set[str] = set()
        member_only: set[str] = set()
        if lang in _DECLARATION_RES:
            # Phase 2 omits example-local and doc-local type declarations.
            local_types = {
                word for word in _WORD_RE.findall(lexical_content) if _TYPE_NAME_RE.fullmatch(word)
            } - set(symbols_ref)
            if lang in {"csharp", "typescript"}:
                declared_types = set(_DECLARATION_RES[lang].findall(lexical_content))
                checked_content, unresolved_members, wrong_parameters = _qualified_member_checks(
                    content,
                    lexical_content,
                    checked_content,
                    lang,
                    declared_types | (local_types - known_names),
                    repo_methods if lang == "csharp" else {},
                    literal_ends,
                )
                for actual, param in wrong_parameters:
                    finding_counter += 1
                    findings.append(
                        _phantom_parameter_finding(finding_counter, claim_dict, actual, param)
                    )
            # Keep bare uses and constructors, even if a member shares the name.
            bare_content = re.sub(r"\.\s*[A-Za-z]\w*", lambda m: " " * len(m[0]), checked_content)
            member_scopes = _type_member_scopes(checked_content, lang)
            bare_content = _blank_in_scope_members(bare_content, member_scopes)
            bare_names = set(re.findall(r"\b([A-Z][a-zA-Z0-9]+)\b", bare_content))
            declared_members = {name for _, _, names in member_scopes for name in names}
            accessed_members = set(_MEMBER_ACCESS_RE.findall(checked_content))
            constructed = set(re.findall(r"\bnew\s+(?:\w+\s*\.\s*)*([A-Z]\w*)", checked_content))
            # A member the example declares and never reaches through an
            # unproven receiver is example-local; so is a proven access.
            member_only = (
                _proven_member_names(lexical_content, lang, local_types, known_names)
                | (declared_members - accessed_members)
            ) - (bare_names | constructed)

        # Skip languages without source-symbol extractors (e.g. text/ASCII
        # diagrams, PowerShell, bash).  Only languages present in
        # SYMBOL_EXTRACTORS can be meaningfully verified against the index.
        if lang not in SYMBOL_EXTRACTORS:
            if claim_dict["type"] == "code_example":
                continue

        # A code example may declare its own types, namespaces, properties and
        # methods. Those are not claims about the repository. Python examples
        # use AST scope analysis in Phase 2 instead of regex declaration matching.
        declared = (
            _declared_names(content, lang)
            if claim_dict["type"] == "code_example" and lang != "python"
            else set()
        )
        if declared and lang in _DECLARATION_RES:
            omitted_declared = (
                declared
                & local_types
                - known_names
                - _COMMON_FRAMEWORK_TYPES
                - set(symbols_ref)
                - unresolved_members
            )
            omitted_count = sum(
                1 for name in omitted_declared if re.match(r"^[A-Z][a-zA-Z0-9]+$", name)
            )
            if omitted_count:
                path = claim_dict["file"]
                declared_name_suppressed[path] = (
                    declared_name_suppressed.get(path, 0) + omitted_count
                )

        code_words = set(_WORD_RE.findall(checked_content))
        for sym_name in sorted(set(symbols_ref) | unresolved_members):
            visible = lang not in _DECLARATION_RES or sym_name in code_words
            if visible and sym_name in known_names:
                # Symbol exists, check for parameter accuracy
                actual = symbol_index[sym_name]
                if actual.kind == "method" and "(" in content:
                    # Check named parameters in the code example
                    named_params = re.findall(
                        rf"\b{re.escape(sym_name)}\s*\([^)]*?(\w+)\s*:",
                        checked_content,
                    )
                    for param in named_params:
                        pattern = rf"\b{re.escape(param)}\b"
                        # nosemgrep: skill-ldap-injection
                        if not re.search(pattern, actual.signature):
                            finding_counter += 1
                            findings.append(
                                _phantom_parameter_finding(
                                    finding_counter, claim_dict, actual, param
                                )
                            )

            if sym_name not in unresolved_members:
                if not visible or sym_name in known_names:
                    continue
                # The example declares this name itself; count the skip so the
                # report shows what this rule hid (even if also member-only).
                if (
                    sym_name in declared
                    and re.match(r"^[A-Z][a-zA-Z0-9]+$", sym_name)
                    and sym_name not in _COMMON_FRAMEWORK_TYPES
                ):
                    path = claim_dict["file"]
                    declared_name_suppressed[path] = declared_name_suppressed.get(path, 0) + 1
                    continue
                if sym_name in member_only:
                    continue
                # Symbol not found in codebase
                # Only flag CamelCase identifiers (likely type/method names)
                if not re.match(r"^[A-Z][a-zA-Z0-9]+$", sym_name):
                    continue

                # Skip common framework types
                if sym_name in _COMMON_FRAMEWORK_TYPES:
                    continue

                # Python builtins (ImportError, ValueError, ...) and typing
                # names (Any, Optional, ...) are never repo symbols.
                if lang == "python" and (hasattr(builtins, sym_name) or sym_name in _TYPING_NAMES):
                    continue

                # JavaScript and TypeScript built-ins are never repo symbols.
                if lang in ("javascript", "typescript") and sym_name in _JS_BUILTIN_TYPES:
                    continue

                # Common base class library types beyond the pinned set.
                if lang == "csharp" and sym_name in _CSHARP_FRAMEWORK_TYPES_EXTRA:
                    continue

            # The file declares itself documentation for another SDK, so a
            # symbol missing here is not a claim about this repository.
            if claim_dict["file"] in external_sdk_files:
                path = claim_dict["file"]
                external_sdk_suppressed[path] = external_sdk_suppressed.get(path, 0) + 1
                continue

            finding_counter += 1
            findings.append(
                Finding(
                    id=f"compile-{finding_counter:04d}",
                    claim_id=claim_dict["id"],
                    severity="high",
                    category="unresolved_symbol",
                    file=claim_dict["file"],
                    line=claim_dict["line"],
                    description=(
                        f"Symbol '{sym_name}' referenced in documentation not found in codebase"
                    ),
                    evidence={
                        "documented": content[:200],
                        "symbol": sym_name,
                        "search_scope": "all source files",
                    },
                    suggested_fix=(
                        f"Verify '{sym_name}' exists in the codebase. "
                        f"It may be misspelled, renamed, or removed."
                    ),
                )
            )

    claims_by_id = {c["id"]: c for c in claims_data.get("claims", [])}
    return {
        "status": "COMPLETED",
        "findings": _scope_findings(
            [f.to_dict() for f in findings],
            claims_by_id,
            assessment.get("changed_lines"),
            claims_data.get("external_sdk_ignored", {}),
        ),
        "external_sdk_suppressed": external_sdk_suppressed,
        "declared_name_suppressed": declared_name_suppressed,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# "info" ranks below every --severity-threshold choice, so it never blocks.
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def check_gate(
    compilability_data: dict[str, Any] | None,
    severity_threshold: str,
) -> dict[str, Any]:
    """Evaluate findings against severity threshold.

    Returns a gate_result dict with verdict and counts.
    """
    threshold_level = SEVERITY_ORDER.get(severity_threshold, 1)
    by_severity: dict[str, int] = {}
    blocking_count = 0

    if compilability_data and compilability_data.get("status") == "DID_NOT_RUN":
        return {
            "verdict": "DID_NOT_RUN",
            "reason": compilability_data["reason"],
            "threshold": severity_threshold,
            "blocking_findings": 0,
            "total_findings": 0,
            "by_severity": {},
        }

    if compilability_data:
        for finding in compilability_data["findings"]:
            sev = finding["severity"]
            by_severity[sev] = by_severity.get(sev, 0) + 1
            finding_level = SEVERITY_ORDER.get(sev, 3)
            if finding_level <= threshold_level:
                blocking_count += 1

    verdict = "FAIL" if blocking_count > 0 else "PASS"
    return {
        "verdict": verdict,
        "threshold": severity_threshold,
        "blocking_findings": blocking_count,
        "total_findings": sum(by_severity.values()),
        "by_severity": by_severity,
    }


def generate_markdown_report(
    assessment: dict[str, Any] | None,
    claims_data: dict[str, Any] | None,
    compilability_data: dict[str, Any] | None,
    gate_result: dict[str, Any],
    output_path: Path,
) -> None:
    """Write a markdown summary report to output_path."""
    lines: list[str] = []
    lines.append("# Documentation Accuracy Report")
    lines.append("")

    lines.append(f"**Gate: {gate_result['verdict']}** (threshold: {gate_result['threshold']})")
    lines.append("")
    if reason := gate_result.get("reason"):
        lines.append(f"**Reason:** {reason}")
        lines.append("")

    if assessment:
        cs = assessment["coverage_summary"]
        lines.append("## Coverage")
        lines.append("")
        lines.append(f"- Public symbols: {cs['public_symbols']}")
        lines.append(f"- Documented symbols: {cs['documented_symbols']}")
        lines.append(f"- Coverage: {cs['coverage_pct']}%")
        lines.append("")

    if claims_data:
        by_type: dict[str, int] = {}
        for c in claims_data["claims"]:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        lines.append("## Claims")
        lines.append("")
        lines.append(f"Total: {len(claims_data['claims'])}")
        lines.append("")
        for ct, count in sorted(by_type.items()):
            lines.append(f"- {ct}: {count}")
        lines.append("")

    if exemptions := _exemption_lines(claims_data, compilability_data):
        lines.append("## External SDK exemptions")
        lines.append("")
        lines.extend(f"- {text}" for text in exemptions)
        lines.append("")

    if declared_skips := _declared_skip_lines(compilability_data):
        lines.append("## Example-declared names")
        lines.append("")
        lines.extend(f"- {text}" for text in declared_skips)
        lines.append("")

    if compilability_data and compilability_data["findings"]:
        lines.append("## Findings")
        lines.append("")
        lines.append(
            f"Total: {gate_result['total_findings']} ({gate_result['blocking_findings']} blocking)"
        )
        lines.append("")
        lines.append("| Severity | File | Line | Description |")
        lines.append("|----------|------|------|-------------|")
        for f in compilability_data["findings"]:
            desc = f["description"][:80]
            lines.append(f"| {f['severity']} | {f['file']} | {f['line']} | {desc} |")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _print_summary(
    assessment: dict[str, Any] | None,
    claims_data: dict[str, Any] | None,
    compilability_data: dict[str, Any] | None,
    gate_result: dict[str, Any],
) -> None:
    """Print a text summary to stdout."""
    print("\n--- Documentation Accuracy Summary ---")
    if assessment:
        cs = assessment["coverage_summary"]
        print(
            f"Symbols: {cs['documented_symbols']}/{cs['public_symbols']} "
            f"({cs['coverage_pct']}% coverage)"
        )
    if claims_data:
        by_type: dict[str, int] = {}
        for c in claims_data["claims"]:
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        print(f"Claims: {len(claims_data['claims'])} total")
        for ct, count in sorted(by_type.items()):
            print(f"  {ct}: {count}")
    for text in _exemption_lines(claims_data, compilability_data):
        print(text)
    for text in _declared_skip_lines(compilability_data):
        print(f"Example-declared names: {text}")
    if compilability_data:
        print(f"Findings: {gate_result['total_findings']} total")
        for sev in ("critical", "high", "medium", "low", "info"):
            count = gate_result["by_severity"].get(sev, 0)
            if count:
                print(f"  {sev}: {count}")
    print(f"Gate: {gate_result['verdict']} (threshold: {gate_result['threshold']})")
    if reason := gate_result.get("reason"):
        print(f"Reason: {reason}")


def _load_json_artifact(path: Path, name: str) -> dict[str, Any] | None:
    """Load a JSON artifact file, returning None with error on failure."""
    if not path.exists():
        print(
            f"ERROR: {name} not found. Run the required phase first.",
            file=sys.stderr,
        )
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print(f"ERROR: {name} is not a JSON object.", file=sys.stderr)
        return None
    return cast(dict[str, Any], data)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


_HELP_EPILOG = """\
examples:
  %(prog)s --target .
  %(prog)s --target . --diff-base origin/main --format summary

exit codes:
  0  no findings at or above the severity threshold
  1  error or inconclusive run
  2  configuration error, such as an invalid --diff-base
  3  external dependency failure, such as git unavailable
  10  findings at or above the severity threshold
"""


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Documentation accuracy scanner (Phases 1-3)",
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--target",
        "-t",
        type=Path,
        required=True,
        help="Repository root to scan",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Output directory for JSON artifacts (default: <target>/.doc-accuracy)",
    )
    parser.add_argument(
        "--phases",
        type=str,
        default="1,2,3",
        help="Comma-separated phases to run (default: 1,2,3)",
    )
    parser.add_argument(
        "--diff-base",
        type=str,
        default=None,
        help="Git ref for incremental mode (only report files changed "
        "since HEAD forked from this ref, as in git diff REF...HEAD)",
    )
    parser.add_argument(
        "--same-pr",
        action="store_true",
        help="Check changed prose against code changed in the same diff and write "
        "same-pr-findings.json and same-pr-checklist.json (requires --diff-base)",
    )
    parser.add_argument(
        "--severity-threshold",
        type=str,
        default="high",
        choices=["critical", "high", "medium", "low"],
        help="Minimum severity for non-zero exit code (default: high)",
    )
    parser.add_argument(
        "--format",
        "-f",
        type=str,
        default="json",
        choices=["json", "gate", "summary", "markdown"],
        help=(
            "Output format (default: json). 'gate' emits the same JSON without "
            "the repository-wide source_symbols index, for callers that only "
            "consume the gate result."
        ),
    )
    return parser


def _same_pr_scan(target: Path, diff_base: str, output_dir: Path) -> dict[str, Any] | int:
    """Run the same-PR scan over the diff; return its result, or an exit code on failure."""
    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import same_pr

    try:
        files, ranges = _get_changed_diff(diff_base, target)
    except _GitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.exit_code
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: git failed reading the diff: {exc}", file=sys.stderr)
        return 3
    try:
        env = _git_env()
        fork_oid, head_oid = _resolve_fork_and_head(diff_base, target, env)
        # shlex.quote is a no-op on a hex id and stops the id, which came
        # from git stdout under a copied environment, from reaching argv.
        fork_token = shlex.quote(fork_oid)
        head_token = shlex.quote(head_oid)
        if fork_token != fork_oid or head_token != head_oid:
            print("ERROR: refusing a revision that is not one shell token", file=sys.stderr)
            return 3
        # Resolved commit IDs and these flags block a local diff driver.
        removed = subprocess.run(
            _git_command(
                target,
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                "--unified=0",
                "--end-of-options",
                fork_token,
                head_token,
                "--",
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=True,
            env=env,
        )
    except _GitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.exit_code
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: git failed reading removed symbols: {exc}", file=sys.stderr)
        return 3
    result: dict[str, Any] = same_pr.run_same_pr(
        target,
        files,
        ranges,
        normalize=_norm_path,
        is_unsafe=lambda path: _has_symlink_part(path, target),
        tracked_files=[_repo_relative(p, target) for p in _repo_files(target, require_git=True)],
        removed_symbols=same_pr.removed_references(removed.stdout),
    )
    # Repository pre-PR integration reuses the canonical cardinality detector.
    validation = Path(__file__).resolve().parents[5] / "scripts" / "validation"
    if (validation / "nl_cardinality.py").is_file():
        sys.path.insert(0, str(validation))
        try:
            # Installed plugins do not ship this module, so the import stays optional.
            try:
                import nl_cardinality
            except ImportError:
                nl_cardinality = None
            if nl_cardinality is not None:
                same_pr.add_cardinality(
                    result,
                    target,
                    files,
                    ranges,
                    nl_cardinality,
                    is_unsafe=lambda path: _has_symlink_part(path, target),
                )
        finally:
            sys.path.remove(str(validation))
    same_pr.write_artifacts(output_dir, result)
    return result


def main(argv: list[str] | None = None) -> int:
    """Entry point for doc-accuracy scanner."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.same_pr and not args.diff_base:
        print("ERROR: --same-pr requires --diff-base", file=sys.stderr)
        return 2

    # Validate target path (CWE-22 prevention)
    target = args.target.resolve()
    if not target.is_dir():
        print(f"ERROR: Target is not a directory: {target}", file=sys.stderr)
        return 1

    # Set up output directory
    output_dir = args.output_dir or (target / ".doc-accuracy")
    output_dir = output_dir.resolve()

    # Validate output_dir to prevent path traversal (CWE-22).
    # Absolute paths are allowed (e.g., /tmp for CI). Relative paths must
    # resolve within the target repository.
    if args.output_dir is not None and not args.output_dir.is_absolute():
        try:
            output_dir.relative_to(target)
        except ValueError:
            print(
                f"ERROR: Relative output directory '{args.output_dir}' resolves "
                f"outside the target repository '{target}'.",
                file=sys.stderr,
            )
            return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    phases = {int(p.strip()) for p in args.phases.split(",")}

    assessment = None
    claims_data = None
    compilability_data = None

    # Phase 1: Assessment
    if 1 in phases or 2 in phases or 3 in phases:
        print("Phase 1: Assessment...", file=sys.stderr)
        try:
            assessment = run_assessment(target, diff_base=args.diff_base)
        except _GitError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return exc.exit_code
        except OSError as exc:
            print(f"ERROR: git not available: {exc}", file=sys.stderr)
            return 3
        except subprocess.TimeoutExpired as exc:
            print(
                f"ERROR: git timed out ({_GIT_TIMEOUT}s): {exc.cmd}",
                file=sys.stderr,
            )
            return 3
        (output_dir / "assessment.json").write_text(
            json.dumps(assessment, indent=2), encoding="utf-8"
        )
        doc_count = len(assessment["documentation_files"])
        sym_count = len(assessment["source_symbols"])
        print(
            f"  Found {doc_count} doc files, {sym_count} source symbols",
            file=sys.stderr,
        )

    # Phase 2: Claim Extraction
    if 2 in phases or 3 in phases:
        if assessment is None:
            assessment = _load_json_artifact(output_dir / "assessment.json", "assessment.json")
            if assessment is None:
                return 1

        print("Phase 2: Claim Extraction...", file=sys.stderr)
        claims_data = run_claim_extraction(target, assessment)
        (output_dir / "claims.json").write_text(json.dumps(claims_data, indent=2), encoding="utf-8")
        print(
            f"  Extracted {len(claims_data['claims'])} claims",
            file=sys.stderr,
        )

    # Phase 3: Compilability Check
    if 3 in phases:
        if assessment is None:
            assessment = _load_json_artifact(output_dir / "assessment.json", "assessment.json")
            if assessment is None:
                return 1

        if claims_data is None:
            claims_data = _load_json_artifact(output_dir / "claims.json", "claims.json")
            if claims_data is None:
                return 1

        print("Phase 3: Compilability Check...", file=sys.stderr)
        compilability_data = run_compilability_check(assessment, claims_data)
        (output_dir / "compilability-findings.json").write_text(
            json.dumps(compilability_data, indent=2), encoding="utf-8"
        )
        if compilability_data["status"] == "DID_NOT_RUN":
            print(
                f"  Did not run: {compilability_data['reason']}",
                file=sys.stderr,
            )
        else:
            finding_count = len(compilability_data["findings"])
            print(
                f"  Found {finding_count} compilability issues",
                file=sys.stderr,
            )

    same_pr_result = None
    if args.same_pr:
        scan = _same_pr_scan(target, args.diff_base, output_dir)
        if isinstance(scan, int):
            return scan
        same_pr_result = scan

    # Gate evaluation
    gate_result = check_gate(compilability_data, args.severity_threshold)
    if same_pr_result:
        import same_pr

        gate_result = same_pr.fold_into_gate(
            gate_result,
            same_pr_result["findings"]["findings"],
            args.severity_threshold,
            SEVERITY_ORDER,
        )

    # Write gate result
    (output_dir / "gate-result.json").write_text(
        json.dumps(gate_result, indent=2), encoding="utf-8"
    )

    # Output report
    if args.format in ("json", "gate"):
        # `source_symbols` is the whole tracked-source index, and it is built
        # even for a diff-scoped run because claim checking needs it. Measured
        # on this repository with --diff-base origin/main: 8,561,547 bytes of
        # JSON, of which source_symbols is 8,456,923 (98.8%, 36,975 entries),
        # against 43,513 bytes of documentation_files. A caller that only reads
        # the gate result pays that whole cost, and a payload that large is
        # liable to be truncated in transit, which turns a completed scan into
        # a parse failure. 'gate' drops the index and nothing else.
        payload_assessment = assessment
        if args.format == "gate" and assessment is not None:
            payload_assessment = {k: v for k, v in assessment.items() if k != "source_symbols"}
        print(
            json.dumps(
                {
                    "assessment": payload_assessment,
                    "claims_data": claims_data,
                    "compilability_data": compilability_data,
                    "gate_result": gate_result,
                    **({"same_pr": same_pr_result} if same_pr_result else {}),
                },
                indent=2,
            )
        )
    elif args.format == "summary":
        if same_pr_result:
            import same_pr

            print("\n".join(same_pr.summary_lines(same_pr_result)))
        _print_summary(assessment, claims_data, compilability_data, gate_result)
    elif args.format == "markdown":
        report_path = output_dir / "report.md"
        generate_markdown_report(
            assessment,
            claims_data,
            compilability_data,
            gate_result,
            report_path,
        )
        print(f"Report written to {report_path}", file=sys.stderr)

    if gate_result["verdict"] == "FAIL":
        return 10
    if gate_result["verdict"] == "DID_NOT_RUN":
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
