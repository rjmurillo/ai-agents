#!/usr/bin/env python3
"""Detect Spec<->Code drift for the /sync command (issue #1997).

Forward path (`/spec` -> `/plan` -> `/build`) turns intent into code. There is
no clean reverse path: when code is hand-edited, the specification drifts and
the staleness surfaces only at `/review` time, late and misattributed. This
detector closes the gap by scanning the specification tier (REQ/DESIGN/TASK)
for references to code paths and artifacts that no longer exist in the working
tree. A stale reference is evidence the spec drifted from the code.

Scope of this slice: detection and reporting only. The detector reports drift;
it does NOT auto-rewrite specs. Patch proposal via the `spec-generator` agent is
tracked as a follow-up (see the `/sync` command file and issue #1997).

Output envelope mirrors the ADR-056 four-field shape
(`Success`, `Data`, `Error`, `Metadata`) used by
`.claude/skills/orphan-ref-validator/scripts/envelope.py`, followed by a final
`VERDICT: PASS|DRIFT|ERROR` line. The contract, copied verbatim from that
canonical envelope:

    envelope = {
        "Success": True,
        "Data": {...},
        "Error": None,
        "Metadata": {
            "Script": "detect_spec_drift.py",
            "Version": "1.0.0",
            "Timestamp": "2026-01-01T00:00:00+00:00",
        },
    }

Different than canonical: orphan-ref-validator emits the verdict set
`PASS|WARN|CRITICAL_FAIL` over skill-name / script-path / count-claim findings.
This detector emits `PASS|DRIFT` over spec-to-code reference findings only; a
broken reference is the single finding kind here. See
`.claude/rules/canonical-source-mirror.md`.

Exit codes (per ADR-035):
    0 - PASS (no drift detected)
    1 - DRIFT (one or more stale spec references)
    2 - Configuration error (bad CLI args, repo root not found)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

VERSION = "1.0.0"
SCRIPT = "detect_spec_drift.py"

LOGGER = logging.getLogger("detect_spec_drift")

# Specification tiers scanned for code references. Each is relative to the
# repo root. A tier absent on disk (vendored install) is skipped, not an error.
DEFAULT_SPEC_TARGETS: tuple[str, ...] = (
    ".agents/specs/requirements",
    ".agents/specs/design",
    ".agents/specs/tasks",
)

# Reference shapes a spec file uses to point at code or artifacts. Each pattern
# captures a path inside backticks. The detector resolves the captured path
# against the working tree; a miss is drift.
#
# Anchored to known code/artifact roots so prose like `the spec` or a bare
# word never matches. Trailing punctuation is excluded by the character class.
_REFERENCE_ROOTS = (
    "build/scripts",
    "scripts",
    r"\.claude/skills",
    r"\.claude/commands",
    r"\.claude/hooks",
    r"\.claude/agents",
    "templates",
    "src",
    "tests",
)
_PATH_BODY = r"[-A-Za-z0-9_./*]+"
REFERENCE_RE = re.compile(
    r"(?<![\w/])`(?P<path>(?:" + "|".join(_REFERENCE_ROOTS) + r")/" + _PATH_BODY + r")`(?!\w)",
    re.IGNORECASE,
)

# A reference path ending in a directory separator is treated as a directory
# reference. The detector accepts it when the directory exists.
_DIR_HINT_RE = re.compile(r"/$")

# Inline ignore directive: a spec author may mark a reference as intentionally
# absent (a planned path, an example) with a trailing HTML comment. Mirrors the
# orphan-ref-validator file/line ignore convention.
IGNORE_DIRECTIVE = "sync-drift-ignore"

Verdict = Literal["PASS", "DRIFT"]


class DriftScanError(Exception):
    """Configuration or read error that prevents a trustworthy drift result."""


@dataclass(frozen=True, slots=True)
class DriftFinding:
    """One stale spec reference: a code path named in a spec but absent on disk."""

    spec_file: str
    line: int
    referenced_path: str
    recommendation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "spec_file": self.spec_file,
            "line": self.line,
            "referenced_path": self.referenced_path,
            "recommendation": self.recommendation,
        }


@dataclass
class DriftResult:
    """Aggregate outcome of one drift scan."""

    findings: list[DriftFinding] = field(default_factory=list)
    files_scanned: int = 0
    refs_checked: int = 0

    @property
    def verdict(self) -> Verdict:
        return "DRIFT" if self.findings else "PASS"


def find_repo_root(start: Path) -> Path | None:
    """Walk upward from `start` to the directory holding `.agents`.

    Returns None when no repo root is found, so the caller can emit a config
    error rather than scan an arbitrary tree.
    """
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".agents").is_dir():
            return candidate
    return None


def iter_spec_files(repo_root: Path, targets: tuple[str, ...]) -> list[Path]:
    """Collect markdown spec files under each present target directory.

    A target absent on disk is logged at INFO and skipped (vendored-install
    tolerance), never raised.
    """
    spec_files: list[Path] = []
    for target in targets:
        target_dir = _safe_repo_path(repo_root, target)
        if target_dir is None:
            raise DriftScanError(f"unsafe target path: {target}")
        if not target_dir.is_dir():
            LOGGER.info("skipping %s: not present", target)
            continue
        for root, dirs, files in os.walk(target_dir, followlinks=False):
            root_path = Path(root)
            dirs[:] = [
                d
                for d in dirs
                if not (root_path / d).is_symlink()
                and _is_relative_to_repo(repo_root, root_path / d)
            ]
            for filename in sorted(files):
                if not filename.endswith(".md"):
                    continue
                candidate = root_path / filename
                if not _is_relative_to_repo(repo_root, candidate):
                    rel_candidate = _relative(repo_root, candidate)
                    raise DriftScanError(f"unsafe spec file path: {rel_candidate}")
                spec_files.append(candidate)
    return sorted(spec_files)


def _has_unsafe_path_parts(path_text: str) -> bool:
    parts = path_text.rstrip("/").split("/")
    return (
        path_text.startswith("/")
        or any(part in ("", ".", "..") for part in parts)
        or Path(path_text).is_absolute()
    )


def _is_relative_to_repo(repo_root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve(strict=False).relative_to(repo_root.resolve())
    except ValueError:
        return False
    return True


def _safe_repo_path(repo_root: Path, relative_path: str) -> Path | None:
    if _has_unsafe_path_parts(relative_path):
        return None
    candidate = (repo_root / relative_path.rstrip("/")).resolve(strict=False)
    if not _is_relative_to_repo(repo_root, candidate):
        return None
    return candidate


def _reference_exists(repo_root: Path, referenced_path: str) -> bool:
    """Return True when the referenced path resolves to a file or directory.

    Wildcard references (a glob like `.claude/skills/*/SKILL.md`) are accepted
    when at least one match exists. A trailing-slash reference is a directory.
    """
    if "*" in referenced_path:
        if _has_unsafe_path_parts(referenced_path):
            return False
        return any(
            _is_relative_to_repo(repo_root, match) and match.exists()
            for match in repo_root.glob(referenced_path)
        )
    candidate = _safe_repo_path(repo_root, referenced_path)
    if candidate is None:
        return False
    if _DIR_HINT_RE.search(referenced_path):
        return candidate.is_dir()
    return candidate.exists()


def scan_spec_file(spec_file: Path, repo_root: Path) -> tuple[list[DriftFinding], int]:
    """Scan one spec file for stale code references.

    Returns the findings and the count of references checked. Lines carrying
    the ignore directive are skipped. Unreadable files fail closed with
    ``DriftScanError`` so I/O failures cannot appear as clean scans.
    """
    try:
        text = spec_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise DriftScanError(f"unreadable spec file: {spec_file} ({exc})") from exc

    rel_spec = _relative(repo_root, spec_file)
    findings: list[DriftFinding] = []
    refs_checked = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if IGNORE_DIRECTIVE in line:
            continue
        for match in REFERENCE_RE.finditer(line):
            referenced_path = match.group("path")
            refs_checked += 1
            if _reference_exists(repo_root, referenced_path):
                continue
            findings.append(
                DriftFinding(
                    spec_file=rel_spec,
                    line=line_number,
                    referenced_path=referenced_path,
                    recommendation=(
                        f"Spec references `{referenced_path}` which is absent on disk. "
                        "Update the spec to the current path, or restore the code, "
                        f"or mark the reference intentional with <!-- {IGNORE_DIRECTIVE} -->."
                    ),
                )
            )
    return findings, refs_checked


def detect_drift(repo_root: Path, targets: tuple[str, ...]) -> DriftResult:
    """Scan every present spec tier and aggregate stale references."""
    result = DriftResult()
    for spec_file in iter_spec_files(repo_root, targets):
        findings, refs_checked = scan_spec_file(spec_file, repo_root)
        result.findings.extend(findings)
        result.files_scanned += 1
        result.refs_checked += refs_checked
    return result


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _metadata() -> dict[str, str]:
    return {
        "Script": SCRIPT,
        "Version": VERSION,
        "Timestamp": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 - Python 3.10
    }


def render_envelope(result: DriftResult, output: str) -> str:
    """Render the ADR-056 envelope plus the VERDICT line for a completed scan."""
    envelope = {
        "Success": True,
        "Data": {
            "findings": [f.to_dict() for f in result.findings],
            "verdict": result.verdict,
            "counts": {
                "files_scanned": result.files_scanned,
                "refs_checked": result.refs_checked,
                "drift": len(result.findings),
            },
        },
        "Error": None,
        "Metadata": _metadata(),
    }
    if output == "human":
        return _render_human(result)
    return json.dumps(envelope, indent=2) + f"\nVERDICT: {result.verdict}"


def _render_human(result: DriftResult) -> str:
    lines = [f"detect_spec_drift {VERSION}"]
    lines.append(
        f"  scanned {result.files_scanned} spec file(s), checked {result.refs_checked} reference(s)"
    )
    for finding in result.findings:
        lines.append(
            f"  DRIFT {finding.spec_file}:{finding.line} -> "
            f"`{finding.referenced_path}` absent on disk"
        )
    lines.append(f"VERDICT: {result.verdict}")
    return "\n".join(lines)


def render_error_envelope(message: str, output: str) -> str:
    """Render an ADR-056 error envelope for a configuration failure (exit 2)."""
    envelope = {
        "Success": False,
        "Data": None,
        "Error": {"Message": message, "Code": 2, "Type": "InvalidParams"},
        "Metadata": _metadata(),
    }
    if output == "human":
        return f"detect_spec_drift {VERSION}\n  ERROR: {message}\nVERDICT: ERROR"
    return json.dumps(envelope, indent=2) + "\nVERDICT: ERROR"


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect Spec<->Code drift: spec references to absent code paths."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repo root (defaults to walking upward from the current directory).",
    )
    parser.add_argument(
        "--target",
        action="append",
        dest="targets",
        default=None,
        help="Spec tier directory to scan (repeatable). Defaults to REQ/DESIGN/TASK.",
    )
    parser.add_argument(
        "--output-format",
        choices=("json", "human"),
        default="json",
        help="Output shape: json (ADR-056 envelope) or human.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args(argv)

    start = args.repo_root if args.repo_root is not None else Path.cwd()
    repo_root = find_repo_root(start)
    if repo_root is None:
        print(
            render_error_envelope(
                f"repo root not found from {start} (no .agents directory)",
                args.output_format,
            )
        )
        return 2

    targets = tuple(args.targets) if args.targets else DEFAULT_SPEC_TARGETS
    try:
        result = detect_drift(repo_root, targets)
    except DriftScanError as exc:
        print(render_error_envelope(str(exc), args.output_format))
        return 2
    if args.targets and result.files_scanned == 0:
        print(
            render_error_envelope(
                f"target(s) matched no spec files: {', '.join(targets)}",
                args.output_format,
            )
        )
        return 2
    print(render_envelope(result, args.output_format))
    return 1 if result.verdict == "DRIFT" else 0


if __name__ == "__main__":
    sys.exit(main())
