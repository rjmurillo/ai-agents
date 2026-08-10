"""Marker path-drift validation for vendor-portability markers (issue #4116).

Extracted from check_skill_md_portability.py to respect the 500-line file-size
ceiling. This module provides:
  - Path extraction from marker and prose text
  - Drift detection (stale declarations, undeclared references, existence misses)
  - Ratchet baseline comparison for non-regression gating
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from scripts.validation.tracked_paths import path_exists_in_repo

# Paths that legitimately do not exist in this repo because the skill WRITES
# them into a consumer workspace rather than reading them here. Exemption is
# checked on path COMPONENTS, not string prefixes, so .agents/sessions matches
# .agents/sessions/foo but never .agents/sessions-evil/bar.
_CONSUMER_WORKSPACE_PATHS: tuple[tuple[str, ...], ...] = (
    (".agents", "sessions"),
    (".agents", "analysis"),
    (".agents", "critique"),
    (".agents", "memory"),
)

# Generated artifacts named in prose that no clean checkout contains. Listed as
# exact paths, not a directory prefix, so a typo under the same directory is
# still reported as an existence miss.
_GENERATED_ARTIFACTS: frozenset[str] = frozenset(
    {"build/audit/GENERATION-AUDIT.md"}
)

# Regex for the vendor-portability HTML comment marker (same as main module).
_MARKER_PATTERN = re.compile(
    r"<!--\s*vendor-portability\s*:.*?-->",
    re.IGNORECASE | re.DOTALL,
)

# Matches all HTML comments EXCEPT the vendor-portability marker.
_HTML_COMMENT_PATTERN = re.compile(
    r"<!--(?!\s*vendor-portability\s*:).*?-->",
    re.IGNORECASE | re.DOTALL,
)


def _strip_html_comments(text: str) -> str:
    """Remove HTML comments from text, preserving the portability marker."""
    return _HTML_COMMENT_PATTERN.sub("", text)


# Pre-computed constants for _extract_paths_from_text (avoid per-call rebuild).
_PATH_CHAR = r"[\w./_\\-]"
_SIMPLE_ANCHOR = r"(?:^|(?<=[\s(\[\"'`|,;*]))"
_KNOWN_SUBDIRS = frozenset({
    "agents", "platforms", "lib", "review-axes",
    "skills", "commands", "hooks", "rules",
    "validation", "architecture", "sessions",
    "analysis", "retrospective", "security",
    "governance", "critique", "memory", "references",
    "scripts", "tests", "modules", "utils",
})


def _extract_paths_from_text(
    text: str, *, unsafe_collector: set[str] | None = None
) -> set[str]:
    """Return the set of upstream path strings found in text.

    Uses dedicated full-path regexes. Single-segment prefixes (build, scripts,
    .agents) require a separator plus continuation to avoid matching bare English
    words. Multi-segment prefixes (.claude/lib, templates/agents) can match alone.

    Slash-separated English phrases like 'build/buy/partner/defer' are rejected
    when ALL continuation segments are purely lowercase alpha (3+ chars each) and
    none match a known subdirectory name.

    Paths with '..' components or absolute paths (leading /) are collected into
    unsafe_collector (if provided) rather than silently dropped, so callers can
    report them as invalid declarations.
    """
    path_char = _PATH_CHAR
    simple_anchor = _SIMPLE_ANCHOR
    known_subdirs = _KNOWN_SUBDIRS

    paths: set[str] = set()

    def _clean_match(raw: str) -> str:
        cleaned = re.sub(r'^[\s(\[<>"\'`|,;*]+', "", raw)
        # Strip only leading './' (relative prefix), NOT bare '/' (absolute)
        cleaned = re.sub(r'^(?:\.[\\/])', "", cleaned)
        return cleaned.rstrip("/\\.")

    def _is_phrase(normalized: str) -> bool:
        """Return True if path looks like a slash-separated English phrase."""
        segments = normalized.split("/")
        if len(segments) <= 1:
            return False
        tail = [s for s in segments[1:] if s]
        if not tail:
            return False
        if all(s.isalpha() and s.islower() and len(s) >= 3 for s in tail):
            return not any(s in known_subdirs for s in tail)
        return False

    def _is_valid_path(normalized: str) -> bool:
        """Reject absolute paths, '..' traversal, and placeholder templates.

        If unsafe_collector is provided, rejected paths are added there
        so callers can report them as invalid declarations. Placeholder
        paths (containing < or >) are excluded silently: they are
        templates, not filesystem references.
        """
        # Angle-bracket placeholders like <skill_dir>/scripts/foo.py are
        # templates, not real paths. Exclude silently, not as "invalid".
        if "<" in normalized or ">" in normalized:
            return False
        if normalized.startswith("/"):
            if unsafe_collector is not None:
                unsafe_collector.add(normalized)
            return False
        parts = PurePosixPath(normalized).parts
        if ".." in parts:
            if unsafe_collector is not None:
                unsafe_collector.add(normalized)
            return False
        return True

    # Single-segment prefixes: require separator + content
    # The optional leading group captures any run of leading segments so the
    # whole path token is seen, not just the part starting at the recognized
    # prefix. Matching only a leading "../" left traversal that arrives later
    # invisible: "./../scripts/x.py" and "a/../scripts/x.py" were extracted as
    # if they began at "scripts", so _is_valid_path never saw the ".." and the
    # reference escaped the plugin unreported. Refs #4116.
    for prefix in (r"\.agents", r"build", r"scripts"):
        pat = re.compile(
            simple_anchor + r"[\\/]?(?:[\w.\-]+[\\/])*?"
            + prefix + r"[\\/]" + path_char + r"+",
            re.MULTILINE,
        )
        for m in pat.finditer(text):
            normalized = _clean_match(m.group(0)).replace("\\", "/")
            if normalized and not _is_phrase(normalized) and _is_valid_path(normalized):
                paths.add(normalized)

    # Multi-segment prefixes: can match alone
    for prefix in (
        r"\.claude[\\/]+lib",
        r"\.claude[\\/]+review-axes",
        r"templates[\\/]+agents",
        r"templates[\\/]+platforms",
    ):
        pat = re.compile(
            simple_anchor + r"[\\/]?(?:[\w.\-]+[\\/])*?"
            + prefix + r"(?:[\\/]" + path_char + r"*)?",
            re.MULTILINE,
        )
        for m in pat.finditer(text):
            normalized = _clean_match(m.group(0)).replace("\\", "/")
            if normalized and _is_valid_path(normalized):
                paths.add(normalized)

    return paths


def marker_declared_paths(
    text: str,
    strip_code_fn: Callable[[str], str],
    strip_inline_fn: Callable[[str], str],
    *,
    unsafe_collector: set[str] | None = None,
) -> set[str]:
    """Extract upstream paths declared inside the vendor-portability marker span.

    strip_code_fn and strip_inline_fn are injected from the main module to
    avoid duplicating the CommonMark stripping logic.
    """
    declared: set[str] = set()
    for m in _MARKER_PATTERN.finditer(strip_inline_fn(strip_code_fn(text))):
        marker_text = m.group(0)
        declared |= _extract_paths_from_text(
            marker_text, unsafe_collector=unsafe_collector
        )
    return declared


def prose_declared_paths(
    text: str,
    strip_code_fn: Callable[[str], str],
    strip_inline_fn: Callable[[str], str],
    *,
    unsafe_collector: set[str] | None = None,
) -> set[str]:
    """Extract upstream paths from prose with marker and HTML comments removed.

    The marker span is removed first (so its declared paths do not count as
    prose references). Then remaining HTML comments are stripped (so
    commented-out obsolete references do not keep stale declarations alive).
    """
    prose = strip_code_fn(text)
    prose_no_marker = _MARKER_PATTERN.sub("", prose)
    prose_clean = _strip_html_comments(prose_no_marker)
    return _extract_paths_from_text(
        prose_clean, unsafe_collector=unsafe_collector
    )


def _is_consumer_workspace_path(path: str) -> bool:
    """Return True if path matches or is under a consumer-workspace prefix.

    Matching is on path COMPONENTS, not string prefixes, so .agents/sessions
    matches .agents/sessions/x but never .agents/sessions-evil/x.
    """
    parts = PurePosixPath(path).parts
    for prefix_parts in _CONSUMER_WORKSPACE_PATHS:
        n = len(prefix_parts)
        if len(parts) >= n and parts[:n] == prefix_parts:
            return True
    return False


def marker_path_drift(
    text: str,
    repo_root: Path,
    rel_path: str,
    strip_code_fn: Callable[[str], str],
    strip_inline_fn: Callable[[str], str],
) -> list[str]:
    """Report path-drift failures for a file with a vendor-portability marker.

    Five failure classes:
      (a) stale declaration: path named in marker but absent from prose
          (a declared directory covers prose paths beneath it)
      (b) undeclared ref: path in prose not covered by any marker declaration
          (a declared prefix covers all its descendants)
      (c) existence miss: any path (declared or prose) that does not resolve
          under repo_root (exempt: consumer-workspace paths)
      (d) invalid path: absolute or containing '..' traversal. Reported as a
          distinct category but excluded from the existence check.
      (e) containment violation: a path that resolves outside the repository
          root after symlink resolution.

    Comparison is case-sensitive (Linux filesystem semantics).

    Returns a list of human-readable failure strings (empty means clean).
    """
    if not _MARKER_PATTERN.search(strip_inline_fn(strip_code_fn(text))):
        return []

    unsafe_paths: set[str] = set()
    declared = marker_declared_paths(
        text, strip_code_fn, strip_inline_fn, unsafe_collector=unsafe_paths
    )
    prose_paths = prose_declared_paths(
        text, strip_code_fn, strip_inline_fn, unsafe_collector=unsafe_paths
    )
    failures: list[str] = []
    resolved_root = repo_root.resolve()

    # (d) invalid paths: absolute or containing '..' traversal
    for p in sorted(unsafe_paths):
        failures.append(
            f"{rel_path}: invalid path: \'{p}\' is absolute or contains "
            f"\'..\' traversal and cannot be validated"
        )

    def _is_covered_by(path: str, declarations: set[str]) -> bool:
        """Return True if path equals or is under any declared prefix (components)."""
        path_parts = PurePosixPath(path).parts
        for d in declarations:
            d_parts = PurePosixPath(d).parts
            n = len(d_parts)
            if len(path_parts) >= n and path_parts[:n] == d_parts:
                return True
        return False

    # (a) stale: declared path not referenced in prose (even as a prefix)
    for d in sorted(declared):
        d_parts = PurePosixPath(d).parts
        # A declaration is used if ANY prose path equals or starts with it
        if not any(
            PurePosixPath(p).parts[:len(d_parts)] == d_parts
            for p in prose_paths
        ):
            failures.append(
                f"{rel_path}: stale marker declaration: '{d}' is declared in the "
                f"vendor-portability marker but no longer referenced in prose"
            )

    # (b) undeclared: prose path not covered by any declaration
    for p in sorted(prose_paths):
        if not _is_covered_by(p, declared):
            failures.append(
                f"{rel_path}: undeclared reference: '{p}' is referenced in prose "
                f"but not declared in the vendor-portability marker"
            )

    # (c) existence: check every path (declared and prose) for real resolution
    all_paths = declared | prose_paths
    for path_str in sorted(all_paths):
        if _is_consumer_workspace_path(path_str) or path_str in _GENERATED_ARTIFACTS:
            continue
        candidate = (repo_root / path_str).resolve()
        # Containment check: resolved path must be under the repo root
        if not _is_path_contained(candidate, resolved_root):
            failures.append(
                f"{rel_path}: containment violation: '{path_str}' resolves "
                f"outside the repository root"
            )
            continue
        if not path_exists_in_repo(repo_root, path_str):
            failures.append(
                f"{rel_path}: existence miss: '{path_str}' is declared and/or "
                f"referenced but does not exist under the repository root"
            )

    return failures


def _is_path_contained(candidate: Path, root: Path) -> bool:
    """Return True if candidate is under root (both must be resolved)."""
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _load_drift_baseline(path: Path) -> dict[str, int]:
    """Load the drift_files section from the baseline JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Baseline must be a JSON object")
    drift_files = data.get("drift_files", {})
    if not isinstance(drift_files, dict):
        return {}
    baseline: dict[str, int] = {}
    for key, value in drift_files.items():
        try:
            baseline[str(key)] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Drift baseline count for {key!r} is not an integer"
            ) from exc
    return baseline


def diff_drift_baseline(
    current: dict[str, int], baseline: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Return (regressions, improvements) for drift counts.

    A regression is a file whose drift count rose above its baseline or a
    new file with drift not in the baseline. An improvement is a file whose
    drift count dropped.
    """
    regressions: list[str] = []
    improvements: list[str] = []
    for rel in sorted(set(current) | set(baseline)):
        count = current.get(rel, 0)
        allowed = baseline.get(rel, 0)
        if count > allowed:
            regressions.append(
                f"{rel}: {count} marker-drift findings (baseline {allowed}). "
                "Update the vendor-portability marker to declare all referenced "
                "paths, or regenerate the baseline with --update-baseline."
            )
        elif count < allowed:
            improvements.append(
                f"{rel}: drift dropped from {allowed} to {count}"
            )
    return regressions, improvements


def drift_counts_from_failures(drift_failures: list[str]) -> dict[str, int]:
    """Aggregate drift failures into per-file counts for baselining."""
    counts: dict[str, int] = {}
    for line in drift_failures:
        # Each failure starts with "rel_path: category: ..."
        file_key = line.split(":")[0].strip()
        counts[file_key] = counts.get(file_key, 0) + 1
    return counts


def report_drift_ratchet(
    drift_current: dict[str, int],
    drift_baseline: dict[str, int],
) -> tuple[list[str], list[str]]:
    """Compare current drift counts against baseline (issue #4116).

    Returns (regressions, improvements). A regression is a file whose drift
    count rose above baseline. Improvements report files where drift dropped.
    """
    regressions, improvements = diff_drift_baseline(drift_current, drift_baseline)
    if regressions:
        print("Marker path-drift regressions (issue #4116):")
        for line in regressions:
            print(f"  [DRIFT] {line}")
    if improvements:
        print("Marker path-drift improved (tighten baseline with --update-baseline):")
        for line in improvements:
            print(f"  [IMPROVED] {line}")
    return regressions, improvements
