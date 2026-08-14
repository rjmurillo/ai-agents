#!/usr/bin/env python3
"""Documentation Accuracy Scanner - Phases 1-3.

Treats code as the source of truth and documentation as the subject under test.
Produces JSON artifacts for downstream LLM-based verification (Phases 4-6).

Phase 1: Assessment - enumerate docs/source, extract symbols, build mapping
Phase 2: Claim Extraction - parse markdown for verifiable claims
Phase 3: Compilability - verify code example symbols exist in codebase

Exit Codes:
    0: No findings at or above severity threshold
    1: Error or inconclusive run, including no source symbols for Phase 3
    2: Configuration error, including an invalid --diff-base
    3: External dependency failure, including unavailable or failed Git
    10: Findings at or above severity threshold
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "signature": self.signature,
            "visibility": self.visibility,
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file": self.file,
            "line": self.line,
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
    severity: str  # critical, high, medium, low
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

_GIT_TIMEOUT = 60  # seconds, applied to every git subprocess call

# Environment variables that can redirect git to a foreign repository,
# inject configuration, or alter revision/object resolution.
# Sanitized from every git subprocess to ensure -C <repo_root> is authoritative.
# Source: `git rev-parse --local-env-vars` plus all GIT_CONFIG_* variables.
_GIT_ENV_DENY_EXACT = frozenset((
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
))

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
        if (
            normalized in _GIT_ENV_DENY_EXACT
            or any(normalized.startswith(p) for p in _GIT_ENV_DENY_PREFIXES)
        ):
            del env[key]
    env.update(_GIT_ENV_FORCE)
    return env


def _git_command(repo_root: Path, *args: str) -> list[str]:
    """Build a Git command with executable config and replacements disabled."""
    return [
        "git",
        "--no-replace-objects",
        "-c", "core.fsmonitor=false",
        "-C", str(repo_root),
        *args,
    ]


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


def _iter_git_files(repo_root: Path, *, require_git: bool = False):
    """Yield ``Path`` objects for every file tracked by git in ``repo_root``.

    Uses ``git ls-files -z --cached --others --exclude-standard`` with
    NUL-separated output so that paths containing newlines or special
    characters are handled correctly. Falls back to ``repo_root.rglob("*")``
    when the directory is not inside a git repository and *require_git* is
    ``False``.

    When *require_git* is ``True`` (diff-base/Git-scoped mode), a
    ``_GitError(3)`` is raised instead of falling back, because rglob
    would silently bypass the Git-backed scoping contract.
    """
    try:
        result = subprocess.run(
            _git_command(
                repo_root,
                "ls-files", "-z", "--cached", "--others", "--exclude-standard",
            ),
            capture_output=True,
            check=True,
            timeout=_GIT_TIMEOUT,
            env=_git_env(),
        )
        for rel_bytes in result.stdout.split(b"\x00"):
            if rel_bytes:
                rel = os.fsdecode(rel_bytes)
                yield repo_root / rel
        return
    except subprocess.CalledProcessError as exc:
        if require_git:
            raise _GitError(
                3, f"ls-files: git index error: "
                f"{_decode_stderr(exc.stderr)}",
            ) from exc
    except FileNotFoundError:
        if require_git:
            raise _GitError(3, "ls-files: git binary not found") from None
    yield from repo_root.rglob("*")


def _should_exclude(path: Path, repo_root: Path | None = None) -> bool:
    """Check if path is in an excluded directory.

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
        if part in EXCLUDE_DIRS:
            return True
    return False


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

    for i, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue

        if match.group(1):
            # Type declaration
            kind = match.group(1)
            name = match.group(2)
            sig = line.strip()
        else:
            # Method or property
            name = match.group(3)
            kind = "method" if "(" in line else "property"
            sig = line.strip()

        symbols.append(SourceSymbol(
            name=name,
            kind=kind,
            file=file_path,
            line=i + 1,
            signature=sig,
        ))

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
        symbols.append(SourceSymbol(
            name=name,
            kind=kind,
            file=file_path,
            line=i + 1,
            signature=line.strip(),
        ))

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
        symbols.append(SourceSymbol(
            name=name,
            kind=kind,
            file=file_path,
            line=i + 1,
            signature=stripped,
        ))

    return symbols


SYMBOL_EXTRACTORS = {
    "csharp": _extract_csharp_symbols,
    "python": _extract_python_symbols,
    "javascript": _extract_js_symbols,
    "typescript": _extract_js_symbols,
}


def _find_referenced_symbols(
    doc_content: str, symbol_names: set[str]
) -> list[str]:
    """Find source symbols referenced in documentation content."""
    found: list[str] = []
    for name in symbol_names:
        if name in doc_content:
            found.append(name)
    return sorted(set(found))


def _map_doc_to_source(
    doc_path: str,
    doc_content: str,
    source_files: dict[str, str],
) -> list[str]:
    """Map a documentation file to relevant source files."""
    mapped: list[str] = []
    doc_lower = doc_content.lower()

    for src_path in source_files:
        src_name = Path(src_path).stem.lower()
        if src_name in doc_lower:
            mapped.append(src_path)

    return sorted(set(mapped))


def _count_code_blocks(content: str) -> int:
    """Count fenced code blocks in markdown."""
    return len(re.findall(r"^```\w*\s*$", content, re.MULTILINE))


def _get_changed_files(diff_base: str, repo_root: Path) -> set[str]:
    """Get files changed between diff_base and HEAD (committed changes only).

    Uses a deterministic validation sequence:

    1. Verify git work-tree environment (sanitized env, ``-C repo_root``).
    2. Resolve each revision to an OID and verify object accessibility.
    3. Resolve ``<revision>^{commit}``; non-commit bases are config exit 2.
    4. Diff by resolved commit OIDs using NUL-separated output (``-z``).

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

    # Phase 1: verify git environment
    try:
        wt_result = subprocess.run(
            _git_command(repo_root, "rev-parse", "--is-inside-work-tree"),
            capture_output=True, check=True,
            timeout=_GIT_TIMEOUT, env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise _GitError(
            3, f"rev-parse: not a git repository: "
            f"{_decode_stderr(exc.stderr)}",
        ) from exc
    if wt_result.stdout.strip().lower() != b"true":
        raise _GitError(
            3, "rev-parse: not inside a git work tree",
        )

    def resolve_commit(ref: str, *, invalid_exit: int) -> str:
        try:
            raw_result = subprocess.run(
                _git_command(
                    repo_root,
                    "rev-parse", "--verify", "--quiet", "--end-of-options",
                    ref,
                ),
                capture_output=True, check=True,
                timeout=_GIT_TIMEOUT, env=env,
            )
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 1:
                raise _GitError(
                    invalid_exit, f"rev-parse: unknown revision '{ref}'",
                ) from exc
            raise _GitError(
                3, f"rev-parse: failed to resolve '{ref}' "
                f"(rc {exc.returncode}): {_decode_stderr(exc.stderr)}",
            ) from exc

        raw_oid_bytes = raw_result.stdout.strip()
        if re.fullmatch(
            rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", raw_oid_bytes
        ) is None:
            raise _GitError(
                3, f"rev-parse: malformed object ID for '{ref}'",
            )
        raw_oid = raw_oid_bytes.decode("ascii")

        try:
            subprocess.run(
                _git_command(repo_root, "cat-file", "-e", raw_oid),
                capture_output=True, check=True,
                timeout=_GIT_TIMEOUT, env=env,
            )
        except subprocess.CalledProcessError as exc:
            raise _GitError(
                3, f"cat-file: object {raw_oid[:12]} not accessible "
                f"(rc {exc.returncode}): {_decode_stderr(exc.stderr)}",
            ) from exc

        try:
            commit_result = subprocess.run(
                _git_command(
                    repo_root,
                    "rev-parse", "--verify", "--quiet", "--end-of-options",
                    f"{ref}^{{commit}}",
                ),
                capture_output=True, check=True,
                timeout=_GIT_TIMEOUT, env=env,
            )
        except subprocess.CalledProcessError as exc:
            if exc.returncode == 1:
                try:
                    subprocess.run(
                        _git_command(repo_root, "cat-file", "-e", raw_oid),
                        capture_output=True, check=True,
                        timeout=_GIT_TIMEOUT, env=env,
                    )
                except subprocess.CalledProcessError as missing_exc:
                    raise _GitError(
                        3, f"cat-file: object {raw_oid[:12]} not accessible "
                        f"(rc {missing_exc.returncode}): "
                        f"{_decode_stderr(missing_exc.stderr)}",
                    ) from missing_exc
                raise _GitError(
                    invalid_exit,
                    f"rev-parse: invalid commit revision '{ref}'",
                ) from exc
            raise _GitError(
                3, f"rev-parse: failed to peel '{ref}' to a commit "
                f"(rc {exc.returncode}): {_decode_stderr(exc.stderr)}",
            ) from exc

        oid_bytes = commit_result.stdout.strip()
        if re.fullmatch(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})", oid_bytes) is None:
            raise _GitError(
                3, f"rev-parse: malformed commit ID for '{ref}'",
            )
        oid = oid_bytes.decode("ascii")

        try:
            subprocess.run(
                _git_command(repo_root, "cat-file", "-e", f"{oid}^{{commit}}"),
                capture_output=True, check=True,
                timeout=_GIT_TIMEOUT, env=env,
            )
        except subprocess.CalledProcessError as exc:
            raise _GitError(
                3, f"cat-file: commit {oid[:12]} not accessible "
                f"(rc {exc.returncode}): {_decode_stderr(exc.stderr)}",
            ) from exc
        return oid

    # Phases 2-3: resolve and verify immutable commit IDs.
    oid = resolve_commit(diff_base, invalid_exit=2)
    head_oid = resolve_commit("HEAD", invalid_exit=3)

    # Phase 4: diff by resolved OIDs, NUL-separated output.
    try:
        result = subprocess.run(
            _git_command(
                repo_root,
                "diff", "--no-ext-diff", "--name-only", "-z",
                oid, head_oid, "--",
            ),
            capture_output=True, check=True,
            timeout=_GIT_TIMEOUT, env=env,
        )
    except subprocess.CalledProcessError as exc:
        raise _GitError(
            3, f"diff: git failed after ref validation: "
            f"{_decode_stderr(exc.stderr)}",
        ) from exc
    return {
        os.fsdecode(f) for f in result.stdout.split(b"\x00") if f
    }


def run_assessment(
    repo_root: Path,
    doc_globs: list[str] | None = None,
    diff_base: str | None = None,
) -> dict[str, Any]:
    """Phase 1: Build assessment of documentation and source files."""
    if doc_globs is None:
        doc_globs = DOC_GLOBS

    changed_files: set[str] | None = None
    if diff_base:
        changed_files = _get_changed_files(diff_base, repo_root)

    # Enumerate documentation files
    doc_files_set: set[Path] = set()
    for glob_pattern in doc_globs:
        for p in repo_root.glob(glob_pattern):
            if p.is_file() and not _should_exclude(p, repo_root):
                doc_files_set.add(p)

    # Enumerate source files
    source_files: dict[str, str] = {}  # path -> content
    source_symbols: list[SourceSymbol] = []
    symbol_names: set[str] = set()

    for p in _iter_git_files(repo_root, require_git=diff_base is not None):
        if not p.is_file() or _should_exclude(p, repo_root):
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

    # Build doc file inventory
    doc_inventory: list[DocFile] = []
    for doc_path in sorted(doc_files_set):
        rel_path = _repo_relative(doc_path, repo_root)
        # When diff_base is set, only process documentation files that were
        # changed since that base. Source files are always fully indexed so
        # symbol resolution works across the whole repo.
        if changed_files is not None and rel_path not in changed_files:
            continue
        try:
            content = doc_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Failed to read doc file %s: %s", rel_path, exc)
            continue

        refs = _find_referenced_symbols(content, symbol_names)
        mapped = _map_doc_to_source(rel_path, content, source_files)

        doc_inventory.append(DocFile(
            path=rel_path,
            size_bytes=doc_path.stat().st_size,
            line_count=content.count("\n") + 1,
            code_blocks=_count_code_blocks(content),
            referenced_symbols=refs,
            mapped_source_files=mapped,
        ))

    # Build coverage summary
    documented_symbols = set()
    for doc in doc_inventory:
        documented_symbols.update(doc.referenced_symbols)

    public_count = len(source_symbols)
    documented_count = len(documented_symbols & symbol_names)
    coverage_pct = (documented_count / public_count * 100) if public_count else 100.0

    # Find benchmark files
    benchmark_files = []
    for p in _iter_git_files(repo_root, require_git=diff_base is not None):
        if not p.is_file() or _should_exclude(p, repo_root):
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


def _extract_identifiers(code: str) -> list[str]:
    """Extract potential identifiers from a code snippet."""
    # Match CamelCase and snake_case identifiers (3+ chars)
    identifiers = re.findall(r"\b([A-Z][a-zA-Z0-9]+)\b", code)
    # Also match method calls
    identifiers.extend(re.findall(r"\.([A-Za-z]\w+)\s*\(", code))
    # Named parameters (C# style)
    identifiers.extend(re.findall(r"(\w+)\s*:", code))
    return sorted(set(identifiers))


def _extract_quantitative_claims(line: str) -> list[str]:
    """Find quantitative claims in a line of text."""
    patterns = [
        r"[<>~]\s*\d+[%]",           # <5%, >90%, ~10%
        r"\d+-\d+\s*(?:ns|ms|us|s)\b",  # 15-40ns
        r"\d+\s*(?:ns|ms|us|s)\b",    # 100ns
        r"\d+(?:\.\d+)?%",            # 33.4%
        r"\+\d+(?:\.\d+)?%",          # +93.1%
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

    # Build symbol -> source file mapping
    symbol_to_source: dict[str, str] = {}
    for sym in assessment.get("source_symbols", []):
        symbol_to_source[sym["name"]] = sym["file"]

    for doc_info in assessment.get("documentation_files", []):
        doc_path = repo_root / doc_info["path"]
        try:
            content = doc_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning(
                "Failed to read doc file %s: %s", doc_info["path"], exc
            )
            continue

        lines = content.split("\n")
        mapped_sources = doc_info.get("mapped_source_files", [])
        default_source = mapped_sources[0] if mapped_sources else ""

        i = 0
        while i < len(lines):
            line = lines[i]

            # Detect fenced code blocks
            fence_match = re.match(r"^```(\w*)", line)
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

                identifiers = _extract_identifiers(code_content)
                # Map identifiers to source files
                mapped = default_source
                for ident in identifiers:
                    if ident in symbol_to_source:
                        mapped = symbol_to_source[ident]
                        break

                claim_counter += 1
                claims.append(Claim(
                    id=f"claim-{claim_counter:04d}",
                    file=doc_info["path"],
                    line=block_start,
                    claim_type="code_example",
                    language=lang,
                    content=code_content,
                    symbols_referenced=identifiers,
                    mapped_source=mapped,
                ))
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
                claims.append(Claim(
                    id=f"claim-{claim_counter:04d}",
                    file=doc_info["path"],
                    line=i + 1,
                    claim_type="behavioral",
                    language="",
                    content=line.strip(),
                    symbols_referenced=[method_name],
                    mapped_source=mapped,
                ))

            # Detect quantitative claims
            quant_claims = _extract_quantitative_claims(line)
            if quant_claims:
                claim_counter += 1
                claims.append(Claim(
                    id=f"claim-{claim_counter:04d}",
                    file=doc_info["path"],
                    line=i + 1,
                    claim_type="quantitative",
                    language="",
                    content=line.strip(),
                    symbols_referenced=quant_claims,
                    mapped_source=default_source,
                ))

            # Detect method signature claims
            sig_match = re.search(
                r"(?:constructor|method|function)\s+(?:accepts?|takes?|requires?)\s+"
                r"`([^`]+)`",
                line,
                re.IGNORECASE,
            )
            if sig_match:
                claim_counter += 1
                claims.append(Claim(
                    id=f"claim-{claim_counter:04d}",
                    file=doc_info["path"],
                    line=i + 1,
                    claim_type="method_signature",
                    language="",
                    content=line.strip(),
                    symbols_referenced=_extract_identifiers(sig_match.group(1)),
                    mapped_source=default_source,
                ))

            i += 1

    return {"claims": [c.to_dict() for c in claims]}


# ---------------------------------------------------------------------------
# Phase 3: Compilability Check
# ---------------------------------------------------------------------------

def run_compilability_check(
    assessment: dict[str, Any],
    claims_data: dict[str, Any],
) -> dict[str, Any]:
    """Phase 3: Verify symbols in code examples exist in the codebase."""
    source_symbols = assessment.get("source_symbols", [])
    if not source_symbols:
        return {
            "status": "DID_NOT_RUN",
            "reason": (
                "No source symbols found; Phase 3 cannot verify "
                "documentation references."
            ),
            "findings": [],
        }

    findings: list[Finding] = []
    finding_counter = 0

    # Build symbol index from assessment
    symbol_index: dict[str, SourceSymbol] = {}
    for sym_dict in source_symbols:
        sym = SourceSymbol(**sym_dict)
        symbol_index[sym.name] = sym

    # Build a set of all known symbol names for quick lookup
    known_names = set(symbol_index.keys())

    for claim_dict in claims_data.get("claims", []):
        if claim_dict["type"] not in ("code_example", "method_signature"):
            continue

        content = claim_dict["content"]
        lang = claim_dict.get("language", "")

        # Skip non-code languages
        if lang in ("bash", "shell", "yaml", "yml", "json", "xml", "markdown", ""):
            if claim_dict["type"] == "code_example":
                continue

        symbols_ref = claim_dict.get("symbols_referenced", [])
        if not symbols_ref:
            continue

        for sym_name in symbols_ref:
            if sym_name in known_names:
                # Symbol exists, check for parameter accuracy
                actual = symbol_index[sym_name]
                if actual.kind == "method" and "(" in content:
                    # Check named parameters in the code example
                    named_params = re.findall(
                        rf"{re.escape(sym_name)}\s*\([^)]*?(\w+)\s*:",
                        content,
                    )
                    for param in named_params:
                        pattern = rf"\b{re.escape(param)}\b"
                        # nosemgrep: skill-ldap-injection
                        if not re.search(pattern, actual.signature):
                            finding_counter += 1
                            findings.append(Finding(
                                id=f"compile-{finding_counter:04d}",
                                claim_id=claim_dict["id"],
                                severity="critical",
                                category="phantom_parameter",
                                file=claim_dict["file"],
                                line=claim_dict["line"],
                                description=(
                                    f"Parameter '{param}' does not exist in "
                                    f"{sym_name}(). "
                                    f"Actual signature: {actual.signature}"
                                ),
                                evidence={
                                    "documented": content[:200],
                                    "actual_signature": actual.signature,
                                    "source_file": actual.file,
                                    "source_line": actual.line,
                                },
                                suggested_fix=(
                                    f"Remove or rename parameter '{param}'. "
                                    f"Check {actual.file}:{actual.line} for "
                                    f"correct signature."
                                ),
                            ))
            else:
                # Symbol not found in codebase
                # Only flag CamelCase identifiers (likely type/method names)
                if not re.match(r"^[A-Z][a-zA-Z0-9]+$", sym_name):
                    continue

                # Skip common framework types
                framework_types = {
                    "String", "Int32", "Boolean", "Object", "Array",
                    "List", "Dictionary", "Task", "Action", "Func",
                    "IEnumerable", "IList", "Console", "Exception",
                    "Math", "DateTime", "TimeSpan", "Path", "File",
                    "Directory", "Type", "Attribute", "Nullable",
                    "True", "False", "None", "Error", "Promise",
                }
                if sym_name in framework_types:
                    continue

                finding_counter += 1
                findings.append(Finding(
                    id=f"compile-{finding_counter:04d}",
                    claim_id=claim_dict["id"],
                    severity="high",
                    category="unresolved_symbol",
                    file=claim_dict["file"],
                    line=claim_dict["line"],
                    description=(
                        f"Symbol '{sym_name}' referenced in documentation "
                        f"not found in codebase"
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
                ))

    return {
        "status": "COMPLETED",
        "findings": [f.to_dict() for f in findings],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


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

    if (
        compilability_data
        and compilability_data.get("status") == "DID_NOT_RUN"
    ):
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

    lines.append(
        f"**Gate: {gate_result['verdict']}** "
        f"(threshold: {gate_result['threshold']})"
    )
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

    if compilability_data and compilability_data["findings"]:
        lines.append("## Findings")
        lines.append("")
        lines.append(
            f"Total: {gate_result['total_findings']} "
            f"({gate_result['blocking_findings']} blocking)"
        )
        lines.append("")
        lines.append("| Severity | File | Line | Description |")
        lines.append("|----------|------|------|-------------|")
        for f in compilability_data["findings"]:
            desc = f["description"][:80]
            lines.append(
                f"| {f['severity']} | {f['file']} | {f['line']} | {desc} |"
            )
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
    if compilability_data:
        print(f"Findings: {gate_result['total_findings']} total")
        for sev in ("critical", "high", "medium", "low"):
            count = gate_result["by_severity"].get(sev, 0)
            if count:
                print(f"  {sev}: {count}")
    print(
        f"Gate: {gate_result['verdict']} "
        f"(threshold: {gate_result['threshold']})"
    )
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


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Documentation accuracy scanner (Phases 1-3)"
    )
    parser.add_argument(
        "--target", "-t", type=Path, required=True,
        help="Repository root to scan",
    )
    parser.add_argument(
        "--output-dir", "-o", type=Path, default=None,
        help="Output directory for JSON artifacts "
        "(default: <target>/.doc-accuracy)",
    )
    parser.add_argument(
        "--phases", type=str, default="1,2,3",
        help="Comma-separated phases to run (default: 1,2,3)",
    )
    parser.add_argument(
        "--diff-base", type=str, default=None,
        help="Git ref for incremental mode (only report changed files)",
    )
    parser.add_argument(
        "--severity-threshold", type=str, default="high",
        choices=["critical", "high", "medium", "low"],
        help="Minimum severity for non-zero exit code (default: high)",
    )
    parser.add_argument(
        "--format", "-f", type=str, default="json",
        choices=["json", "summary", "markdown"],
        help="Output format (default: json)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for doc-accuracy scanner."""
    parser = _build_parser()
    args = parser.parse_args(argv)

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
            assessment = _load_json_artifact(
                output_dir / "assessment.json", "assessment.json"
            )
            if assessment is None:
                return 1

        print("Phase 2: Claim Extraction...", file=sys.stderr)
        claims_data = run_claim_extraction(target, assessment)
        (output_dir / "claims.json").write_text(
            json.dumps(claims_data, indent=2), encoding="utf-8"
        )
        print(
            f"  Extracted {len(claims_data['claims'])} claims",
            file=sys.stderr,
        )

    # Phase 3: Compilability Check
    if 3 in phases:
        if assessment is None:
            assessment = _load_json_artifact(
                output_dir / "assessment.json", "assessment.json"
            )
            if assessment is None:
                return 1

        if claims_data is None:
            claims_data = _load_json_artifact(
                output_dir / "claims.json", "claims.json"
            )
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

    # Gate evaluation
    gate_result = check_gate(compilability_data, args.severity_threshold)

    # Write gate result
    (output_dir / "gate-result.json").write_text(
        json.dumps(gate_result, indent=2), encoding="utf-8"
    )

    # Output report
    if args.format == "summary":
        _print_summary(
            assessment, claims_data, compilability_data, gate_result
        )
    elif args.format == "markdown":
        report_path = output_dir / "report.md"
        generate_markdown_report(
            assessment, claims_data, compilability_data,
            gate_result, report_path,
        )
        print(f"Report written to {report_path}", file=sys.stderr)

    if gate_result["verdict"] == "FAIL":
        return 10
    if gate_result["verdict"] == "DID_NOT_RUN":
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
