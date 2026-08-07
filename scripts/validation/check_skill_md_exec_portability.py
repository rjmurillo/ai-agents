#!/usr/bin/env python3
# taste-lint: ignore file-size, exec portability checker owns scan, parse, baseline, marker policy.
"""Exec-path vendor-portability ratchet for skill instruction files (issue #2838).

Counts bare ``.claude/skills/...`` executable invocations in skill Markdown.
In a vendored install the skill tree is at the plugin root, not ``./.claude``,
so bare paths break. The portable form uses the harness env var fallback:
``${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/...``.

Opt-out: ``<!-- vendor-portability-exec: <reason> -->`` suppresses a file.

Baseline ratchet: fails when a file exceeds its baseline or a clean file
introduces a new invocation. Use ``--update-baseline`` to tighten after fixes.

Scope: SKILL.md, references/**/*.md, scripts/README-*.md under .claude/skills/
and src/copilot-cli/skills/. Missing roots are skipped.

Exit codes (ADR-035): 0=clean, 1=drift, 2=config error.
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.validation.portability_common import (
    build_portability_parser,
    read_previous_sections,
    refuse_symlinked_scan_root,
    refuse_unsafe_baseline_write,
    write_baseline_json,
)
from scripts.validation.portability_common import (
    resolve_checked_baseline as _resolve_checked_baseline,
)

# Shipped skill trees to scan. Both carry SKILL.md files that agents execute:
# .claude/skills is the canonical tree; src/copilot-cli/skills holds the
# generated twins plus copilot-cli-native skills (e.g. pr-autofix).
SCAN_ROOTS: tuple[tuple[str, ...], ...] = (
    (".claude", "skills"),
    ("src", "copilot-cli", "skills"),
)

# Bare .claude/skills, build, and scripts invocations fail in vendored installs.
# The lead-in keeps prose mentions exempt; line continuations are normalized
# before matching so split commands still count.
EXEC_PATTERN = re.compile(
    r"(?<![\w.])(?:(?:python3?|bash|sh)[ \t]+(?:-\S+[ \t]+)*|\./)"
    r"[\"']?(?:\.claude/skills/|build/|scripts/)\S+\.(?:py|sh)(?!\.\w)[\"']?"
)

# Skill-relative script invocations: ``python3 scripts/foo.py`` (issue #3916).
_SKILL_REL_SCRIPT_PAT = re.compile(
    r"(?<![\w.])(?:python3?|bash|sh)[ \t]+(?:-\S+[ \t]+)*"
    r"[\"']?([a-zA-Z0-9_][a-zA-Z0-9_./-]*/[a-zA-Z0-9_./-]*\.(?:py|sh))[\"']?(?!\.\w)"
)

# Shell line-continuation: a backslash immediately before a newline splices the
# next line onto the current command. Collapse to a single space (what the shell
# does) so `python3 \<newline>  .claude/...` is seen as one invocation.
# The \r? handles CRLF line endings (backslash-CR-LF) as well as LF-only.
_CONTINUATION_PATTERN = re.compile(r"\\\r?\n[ \t]*")

# A skill self-declares an intentional bare invocation with this HTML comment.
# When present, the file's invocations are suppressed (the escape hatch). This
# marker is intentionally distinct from the prose guard's `vendor-portability`
# marker: declaring a prose path dependency does not exempt executable
# invocations, which migrate independently (issue #2838).
_MARKER_PATTERN = re.compile(
    r"<!--\s*vendor-portability-exec\s*:.*?-->",
    re.IGNORECASE | re.DOTALL,
)

_DEFAULT_BASELINE_NAME = "skill_md_exec_portability_baseline.json"

SKILL_FILE_NAME = "SKILL.md"
SCAN_FILE_PATTERNS: tuple[str, ...] = (
    SKILL_FILE_NAME,
    "references/**/*.md",
    "scripts/README-*.md",
)


def _repo_root(start: Path) -> Path:
    """Walk up from ``start`` to the repo root (the dir containing .claude/skills)."""
    base = start if start.is_dir() else start.parent
    for ancestor in (base, *base.parents):
        if (ancestor / ".claude" / "skills").is_dir():
            return ancestor
    return base


def has_portability_marker(text: str) -> bool:
    """Return True if the file self-declares an intentional bare invocation."""
    return _MARKER_PATTERN.search(text) is not None


def find_skill_relative_scripts(text: str) -> list[str]:
    """Return skill-relative script paths; empty when portability-exec marker present."""
    if has_portability_marker(text):
        return []
    joined = _CONTINUATION_PATTERN.sub(" ", text)
    return _SKILL_REL_SCRIPT_PAT.findall(joined)


def _scan_skill_for_dangling(
    paths: list[Path],
    skill_root: Path,
    repo_root: Path,
    seen: set[tuple[str, str]],
) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for path in paths:
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise OSError(f"Failed to read {path}: {exc}") from exc
        rel = path.relative_to(repo_root).as_posix()
        for script_path in find_skill_relative_scripts(text):
            if (skill_root / script_path).is_file() or (repo_root / script_path).is_file():
                continue
            key = (rel, script_path)
            if key not in seen:
                seen.add(key)
                result.append(key)
    return result


def scan_dangling_skill_relative_scripts(repo_root: Path) -> list[tuple[str, str]]:
    """Return ``[(file_rel_path, script_path)]`` for unresolvable script refs."""
    seen: set[tuple[str, str]] = set()
    dangling: list[tuple[str, str]] = []
    for parts in SCAN_ROOTS:
        root = repo_root.joinpath(*parts)
        if not root.is_dir():
            continue
        valid = (
            p
            for p in root.iterdir()
            if p.is_dir() and "__pycache__" not in p.parts and (p / SKILL_FILE_NAME).is_file()
        )
        for skill_root in sorted(valid):
            paths = sorted(
                set(itertools.chain.from_iterable(skill_root.glob(p) for p in SCAN_FILE_PATTERNS))
            )
            dangling.extend(_scan_skill_for_dangling(paths, skill_root, repo_root, seen))
    return dangling


def count_exec_invocations(text: str) -> int:
    """Count bare ``.claude/skills`` executable invocations in a SKILL.md."""
    joined = _CONTINUATION_PATTERN.sub(" ", text)
    return len(EXEC_PATTERN.findall(joined))


def count_file_invocations(text: str) -> int:
    """Marker-aware per-file count: 0 when self-declared, else the count."""
    if has_portability_marker(text):
        return 0
    return count_exec_invocations(text)


def count_marker_suppressed_invocations(text: str) -> int:
    """Count invocations hidden by a ``vendor-portability-exec`` marker."""
    if not has_portability_marker(text):
        return 0
    text_without_markers = _MARKER_PATTERN.sub("", text)
    return count_exec_invocations(text_without_markers)


def _iter_skill_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for skill_root in sorted(p for p in root.iterdir() if p.is_dir()):
        if "__pycache__" in skill_root.parts:
            continue
        if not (skill_root / SKILL_FILE_NAME).is_file():
            continue
        for pattern in SCAN_FILE_PATTERNS:
            paths.extend(
                p
                for p in sorted(skill_root.glob(pattern))
                if p.is_file() and "__pycache__" not in p.parts
            )
    return sorted(dict.fromkeys(paths))


def scan_all(repo_root: Path) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """Scan all skill Markdown files in one traversal.

    Returns (exec_counts, marker_counts, files_by_root). A single walk ensures
    the coverage decision and the baseline contents come from the same snapshot,
    so a concurrent tree mutation cannot produce a short baseline that passes the
    coverage check.

    Scan roots symlinked outside the repository are refused with OSError (issue
    #4212). A symlinked root would scan files git does not track; coverage checks
    based on those files can be satisfied while real shipped content is ignored.
    """
    exec_counts: dict[str, int] = {}
    marker_counts: dict[str, int] = {}
    files_by_root: dict[str, int] = {}
    for parts in SCAN_ROOTS:
        root_name = "/".join(parts)
        root = repo_root.joinpath(*parts)
        if not root.is_dir():
            files_by_root[root_name] = 0
            continue
        if refuse_symlinked_scan_root(repo_root, root):
            raise OSError(f"Scan root {root} resolves outside the repository root")
        files = _iter_skill_files(root)
        files_by_root[root_name] = len(files)
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise OSError(f"Failed to read skill file {path}: {exc}") from exc
            rel = path.relative_to(repo_root).as_posix()
            n = count_file_invocations(text)
            if n > 0:
                exec_counts[rel] = n
            m = count_marker_suppressed_invocations(text)
            if m > 0:
                marker_counts[rel] = m
    return exec_counts, marker_counts, files_by_root


def scan_skill_execs(repo_root: Path) -> dict[str, int]:
    """Return {relative_posix_path: count} for skill Markdown with >0 invocations."""
    exec_counts, _, _ = scan_all(repo_root)
    return exec_counts


def scanned_files_by_root(repo_root: Path) -> dict[str, int]:
    """Return per-root skill-file counts, absent roots as zero."""
    _, _, files_by_root = scan_all(repo_root)
    return files_by_root


def scan_marker_suppressions(repo_root: Path) -> dict[str, int]:
    """Return marker-suppressed invocation counts across every scan root."""
    _, marker_counts, _ = scan_all(repo_root)
    return marker_counts


def _load_baseline(path: Path) -> dict[str, int]:
    if not path.is_file():
        raise FileNotFoundError(f"Baseline file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Baseline must be a JSON object")
    files = data["files"] if "files" in data else data
    if not isinstance(files, dict):
        raise ValueError("Baseline 'files' must be a JSON object")

    baseline: dict[str, int] = {}
    for key, value in files.items():
        if value is None:
            raise ValueError(f"Baseline count for {key!r} is null")
        try:
            baseline[str(key)] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Baseline count for {key!r} is not an integer") from exc
    return baseline


def _load_marker_baseline(path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Baseline must be a JSON object")
    marker_files = data.get("marker_files", {})
    if not isinstance(marker_files, dict):
        raise ValueError("Baseline 'marker_files' must be a JSON object")
    baseline: dict[str, int] = {}
    for key, value in marker_files.items():
        try:
            baseline[str(key)] = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Marker baseline count for {key!r} is not an integer") from exc
    return baseline


def diff_against_baseline(
    current: dict[str, int], baseline: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Return (regressions, improvements) comparing current to baseline."""
    regressions: list[str] = []
    for rel, n in sorted(current.items()):
        allowed = baseline.get(rel, 0)
        if n > allowed:
            regressions.append(
                f"{rel}: {n} bare '.claude/skills/...' or 'scripts/...' invocation(s) "
                f"(baseline {allowed}). For a '.claude/skills/...' invocation, resolve "
                "the script root via a plugin-root env var "
                'with a source fallback, e.g. SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:'
                '-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/..." then invoke '
                "\"$SCRIPTS_DIR/script.py\". A 'scripts/...' invocation has no such "
                "resolved form: that tree is upstream-only and ships in neither "
                "plugin root, so drop the invocation instead. Either kind may be "
                "declared as an intentional dependency "
                "with '<!-- vendor-portability-exec: ... -->' (issue #2838, #4013)."
            )
    improvements: list[str] = []
    for rel, allowed in sorted(baseline.items()):
        n = current.get(rel, 0)
        if n < allowed:
            improvements.append(f"{rel}: {n} invocations (baseline {allowed})")
    return regressions, improvements


def diff_marker_baseline(
    current: dict[str, int], baseline: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Return exact-count marker drift."""
    regressions: list[str] = []
    for rel in sorted(set(current) | set(baseline)):
        count = current.get(rel, 0)
        allowed = baseline.get(rel, 0)
        if count != allowed:
            regressions.append(
                f"{rel}: vendor-portability-exec marker suppresses {count} invocations "
                f"(baseline {allowed}). Update the marker or regenerate the marker baseline."
            )
    return regressions, []


def build_parser() -> argparse.ArgumentParser:
    """Delegate to the shared parser; both ratchets take the same flags."""
    parser = build_portability_parser(__doc__, _DEFAULT_BASELINE_NAME)
    parser.add_argument(
        "--allow-marker-grow",
        action="store_true",
        default=False,
        help=(
            "Allow the total marker_files suppressed-invocation count to increase "
            "during --update-baseline. Required when deliberately adding a new "
            "vendor-portability-exec marker or expanding an existing one (issue #4204)."
        ),
    )
    return parser


def _resolve_root(repo_root: Path | None) -> Path:
    if repo_root:
        return repo_root.expanduser().resolve()
    return _repo_root(Path(__file__).resolve())


def _resolve_baseline_path(root: Path, baseline: Path | None) -> Path | None:
    """Locate the baseline, refusing anything out of root or hidden from review."""
    return _resolve_checked_baseline(root, baseline, _DEFAULT_BASELINE_NAME)


def _refuse_marker_files_growth(
    root: Path,
    baseline_path: Path,
    marker_current: dict[str, int],
    *,
    allow_marker_grow: bool,
) -> bool:
    """Refuse when the total marker_files count has grown.

    A vendor-portability-exec marker declares that a file's bare invocations
    are intentional. Once a file carries the marker every future invocation
    added to that file inherits the exemption automatically. Treating growth
    in the total suppressed-invocation count as a ratchet regression makes that
    growth visible at review time instead of silently absorbed into the next
    baseline regeneration (issue #4204).

    Pass allow_marker_grow=True (via --allow-marker-grow) to acknowledge a
    deliberate expansion, for example when adding a new marked file.

    Returns True when the write should be refused.
    """
    if allow_marker_grow:
        return False
    previous, problem = read_previous_sections(root, baseline_path)
    if problem or previous is None:
        return False
    committed_marker = previous.get("marker_files", {})
    committed_total = sum(
        v for v in committed_marker.values() if isinstance(v, int)
    )
    current_total = sum(marker_current.values())
    if current_total > committed_total:
        print(
            f"Refusing --update-baseline: marker_files total grew from "
            f"{committed_total} to {current_total}. "
            "A vendor-portability-exec marker now suppresses more invocations "
            "than before. "
            "If this is deliberate, pass --allow-marker-grow.",
            file=sys.stderr,
        )
        return True
    return False


def _write_baseline(
    root: Path,
    baseline_path: Path,
    current: dict[str, int],
    marker_current: dict[str, int],
    allow_shrink: bool,
) -> int:
    total = sum(current.values())
    marker_total = sum(marker_current.values())
    entries = dict(sorted(current.items()))
    marker_entries = dict(sorted(marker_current.items()))
    rc = write_baseline_json(
        root,
        baseline_path,
        {
            "_comment": (
                "Exec-path vendor-portability ratchet baseline for skill "
                "Markdown files (issues #2838, #4013, #4156). files counts bare "
                "'.claude/skills/...', 'build/...', or 'scripts/...' executable "
                "invocations per file. marker_files records invocations suppressed "
                "by '<!-- vendor-portability-exec: ... -->' markers. Generated by "
                "check_skill_md_exec_portability.py --update-baseline. Lower files "
                "values are better; migrate '.claude/skills/...' offenders to "
                "'${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}' and "
                "tighten. 'build/'/'scripts/' are upstream-only: drop or declare."
            ),
            "files": entries,
            "marker_files": marker_entries,
        },
        {"files": entries, "marker_files": marker_entries},
        "skill files",
        allow_shrink,
    )
    if rc:
        return rc
    print(
        f"Baseline written: {len(current)} files, {total} invocations; "
        f"{len(marker_current)} marker files, {marker_total} suppressed invocations."
    )
    return 0


def _has_scan_root(root: Path) -> bool:
    return any(root.joinpath(*parts).is_dir() for parts in SCAN_ROOTS)


def _print_report(
    output_format: str,
    regressions: list[str],
    improvements: list[str],
    dangling: list[tuple[str, str]],
    current: dict[str, int],
    baseline: dict[str, int],
) -> None:
    if output_format == "json":
        print(
            json.dumps(
                {
                    "regressions": regressions,
                    "improvements": improvements,
                    "current_total": sum(current.values()),
                    "baseline_total": sum(baseline.values()),
                    "dangling": dangling,
                },
                indent=2,
            )
        )
        return

    if improvements:
        print("Portability improved (tighten the baseline with --update-baseline):")
        for line in improvements:
            print(f"  [IMPROVED] {line}")
    if regressions:
        print("Skill exec-path vendor-portability drift detected (issue #2838, #4013):")
        for line in regressions:
            print(f"  [DRIFT] {line}")
        return
    if dangling:
        print(
            "Skill-relative scripts resolving nowhere (#3916).\n"
            "Suppress with '<!-- vendor-portability-exec: ... -->' if intentional:"
        )
        for rel_file, script in dangling:
            print(f"  [DANGLING] {rel_file}: {script!r}")
        return
    print(
        f"No skill exec-path vendor-portability drift. "
        f"{sum(current.values())} grandfathered invocations across "
        f"{len(current)} files (baseline {sum(baseline.values())})."
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = _resolve_root(args.repo_root)

    if not _has_scan_root(root):
        print(
            f"No skill scan roots found under {root} "
            f"({', '.join('/'.join(p) for p in SCAN_ROOTS)}).",
            file=sys.stderr,
        )
        return 2

    baseline_path = _resolve_baseline_path(root, args.baseline)
    if baseline_path is None:
        return 2

    try:
        current, marker_current, scanned_by_root = scan_all(root)
        dangling = scan_dangling_skill_relative_scripts(root)
    except OSError as exc:
        print(f"Could not scan skill files under {root}: {exc}", file=sys.stderr)
        return 2

    if args.update_baseline:
        if refuse_unsafe_baseline_write(
            root,
            scanned_by_root,
            baseline_path,
            {"files": current, "marker_files": marker_current},
            "skill files",
            args.allow_baseline_shrink,
        ):
            return 2
        if _refuse_marker_files_growth(
            root,
            baseline_path,
            marker_current,
            allow_marker_grow=args.allow_marker_grow,
        ):
            return 2
        return _write_baseline(
            root, baseline_path, current, marker_current, args.allow_baseline_shrink
        )

    try:
        baseline = _load_baseline(baseline_path)
        marker_baseline = _load_marker_baseline(baseline_path)
    except (OSError, ValueError) as exc:
        print(f"Could not read baseline {baseline_path}: {exc}", file=sys.stderr)
        return 2

    regressions, improvements = diff_against_baseline(current, baseline)
    marker_regressions, marker_improvements = diff_marker_baseline(
        marker_current, marker_baseline
    )
    regressions.extend(marker_regressions)
    improvements.extend(marker_improvements)
    _print_report(args.output_format, regressions, improvements, dangling, current, baseline)

    return 1 if (regressions or dangling) else 0


if __name__ == "__main__":
    sys.exit(main())
