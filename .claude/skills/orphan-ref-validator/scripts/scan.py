#!/usr/bin/env python3
"""Orphan-ref validator: detect references to absent entities in structured artifacts.

Scans target paths for references to skill names, script paths, and count claims
that do not match working-tree state. Emits ADR-056 envelope plus final
``VERDICT: PASS|WARN|CRITICAL_FAIL`` line. Exit code per ADR-035.

Reference: REQ-008, DESIGN-008, issue #1939, epic #1933.

Exit codes:
    0 - PASS or WARN (no critical findings)
    1 - CRITICAL_FAIL (one or more critical findings)
    2 - Configuration error (bad CLI args, missing repo root)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Literal

VERSION = "1.0.0"

DEFAULT_TARGETS = (
    ".agents/specs",
    "tests/evals",
    ".claude/.claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".github/plugin/marketplace.json",
)

OPT_IN_ADR_TARGETS = (
    ".agents/architecture",
    "docs",
)

OPT_IN_SKILL_TARGETS = (
    ".claude/skills/*/SKILL.md",
)

SCAN_FILE_SUFFIXES = (".md", ".json", ".yaml", ".yml")

EXCLUDE_DIR_NAMES = frozenset({
    "__pycache__",
    ".git",
    "node_modules",
    "references",
    "templates",
})

SECRET_DENYLIST_PATTERNS = (
    re.compile(r"^\.env"),
    re.compile(r"^secrets\."),
    re.compile(r"\.key$"),
    re.compile(r"\.pem$"),
)

MAX_FILE_BYTES = 5 * 1024 * 1024

SKILL_REF_RE = re.compile(r"`([a-z][a-z0-9]*(?:-[a-z0-9]+)+)`")
SCRIPT_REF_RE = re.compile(r"`((?:build/scripts|scripts/validation|scripts)/[a-zA-Z0-9_/-]+\.py)`")
COUNT_CLAIM_RE = re.compile(r"\b(\d+)\s+(skills|agents|commands|hooks)\b", re.IGNORECASE)
IGNORE_DIRECTIVE_RE = re.compile(r"<!--\s*orphan-ref-ignore\s*-->")
FILE_IGNORE_DIRECTIVE_RE = re.compile(r"<!--\s*orphan-ref-ignore-file\s*-->")

try:
    from .filters import is_known_kebab_word
except ImportError:
    from filters import is_known_kebab_word  # type: ignore[no-redef]

LOGGER = logging.getLogger("orphan_ref_validator")

Severity = Literal["critical", "warn"]
Kind = Literal["skill_name", "script_path", "count_claim", "parse_error"]
Verdict = Literal["PASS", "WARN", "CRITICAL_FAIL"]


@dataclass(frozen=True)
class Finding:
    kind: Kind
    severity: Severity
    target_file: str
    line: int
    referenced_entity: str
    recommendation: str
    expected: str | None = None
    actual: str | None = None

    def to_dict(self) -> dict:
        d = {
            "kind": self.kind,
            "severity": self.severity,
            "target_file": self.target_file,
            "line": self.line,
            "referenced_entity": self.referenced_entity,
            "recommendation": self.recommendation,
        }
        if self.expected is not None:
            d["expected"] = self.expected
        if self.actual is not None:
            d["actual"] = self.actual
        return d


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    files_scanned: int = 0
    refs_checked: int = 0

    @property
    def verdict(self) -> Verdict:
        if any(f.severity == "critical" for f in self.findings):
            return "CRITICAL_FAIL"
        if self.findings:
            return "WARN"
        return "PASS"


def _is_secret_path(path: Path) -> bool:
    name = path.name
    return any(p.search(name) for p in SECRET_DENYLIST_PATTERNS)


def _walk_targets(target: Path) -> Iterable[Path]:
    """Yield candidate files under target (or just the target if it is a file)."""
    if target.is_file():
        if _is_secret_path(target):
            return
        if target.stat().st_size > MAX_FILE_BYTES:
            LOGGER.warning("skipping %s: exceeds %d bytes", target, MAX_FILE_BYTES)
            return
        yield target
        return
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in SCAN_FILE_SUFFIXES:
            continue
        if _is_secret_path(path):
            continue
        if any(part in EXCLUDE_DIR_NAMES for part in path.parts):
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            LOGGER.warning("skipping %s: exceeds %d bytes", path, MAX_FILE_BYTES)
            continue
        yield path


def enumerate_skills(repo_root: Path) -> set[str]:
    skills_dir = repo_root / ".claude" / "skills"
    if not skills_dir.exists():
        return set()
    return {
        d.name
        for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    }


def enumerate_count(repo_root: Path, kind: str) -> int | None:
    """Return count for the given resource kind, or None if undeterminable."""
    kind = kind.lower()
    if kind == "skills":
        return len(enumerate_skills(repo_root))
    if kind == "agents":
        agents_dir = repo_root / ".claude" / "agents"
        if not agents_dir.exists():
            return None
        return sum(1 for f in agents_dir.glob("*.md") if f.is_file())
    if kind == "commands":
        commands_dir = repo_root / ".claude" / "commands"
        if not commands_dir.exists():
            return None
        return sum(1 for f in commands_dir.glob("*.md") if f.is_file())
    if kind == "hooks":
        hooks_dir = repo_root / ".claude" / "hooks"
        if not hooks_dir.exists():
            return None
        return sum(1 for f in hooks_dir.rglob("*.py") if f.is_file())
    return None


def is_manifest_file(path: Path) -> bool:
    name = path.name
    return name in {"plugin.json", "marketplace.json"}


def extract_skill_refs(text: str) -> Iterable[tuple[int, str]]:
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _line_has_ignore_directive(line):
            continue
        for match in SKILL_REF_RE.finditer(line):
            yield lineno, match.group(1)


def extract_script_refs(text: str) -> Iterable[tuple[int, str]]:
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _line_has_ignore_directive(line):
            continue
        for match in SCRIPT_REF_RE.finditer(line):
            yield lineno, match.group(1)


def extract_count_claims(text: str) -> Iterable[tuple[int, int, str]]:
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _line_has_ignore_directive(line):
            continue
        for match in COUNT_CLAIM_RE.finditer(line):
            yield lineno, int(match.group(1)), match.group(2).lower()


def _path_under(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


_is_known_kebab_word = is_known_kebab_word


def _line_has_ignore_directive(line: str) -> bool:
    """Return True if the line carries an <!-- orphan-ref-ignore --> directive."""
    return bool(IGNORE_DIRECTIVE_RE.search(line))


def scan_file(
    target_path: Path,
    repo_root: Path,
    known_skills: set[str],
) -> tuple[list[Finding], int]:
    """Scan one file. Returns findings and count of refs checked."""
    findings: list[Finding] = []
    refs_checked = 0
    rel = _path_under(repo_root, target_path)

    try:
        text = target_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        LOGGER.warning("could not read %s: %s", target_path, exc)
        return findings, refs_checked

    head = "\n".join(text.splitlines()[:50])
    if FILE_IGNORE_DIRECTIVE_RE.search(head):
        LOGGER.info("file-scope ignore directive in %s; skipping", rel)
        return findings, refs_checked

    for lineno, ref in extract_skill_refs(text):
        if _is_known_kebab_word(ref):
            continue
        refs_checked += 1
        if ref not in known_skills:
            findings.append(
                Finding(
                    kind="skill_name",
                    severity="critical",
                    target_file=rel,
                    line=lineno,
                    referenced_entity=ref,
                    recommendation=(
                        f"Skill `{ref}` not present at .claude/skills/. "
                        "Update reference, restore the skill, or remove the mention."
                    ),
                )
            )

    for lineno, script_ref in extract_script_refs(text):
        refs_checked += 1
        candidate = repo_root / script_ref
        if not candidate.exists():
            findings.append(
                Finding(
                    kind="script_path",
                    severity="critical",
                    target_file=rel,
                    line=lineno,
                    referenced_entity=script_ref,
                    recommendation=(
                        f"Script `{script_ref}` not present on disk. "
                        "Update reference or restore the script."
                    ),
                )
            )

    if is_manifest_file(target_path):
        for lineno, claimed, kind in extract_count_claims(text):
            refs_checked += 1
            actual = enumerate_count(repo_root, kind)
            if actual is None:
                findings.append(
                    Finding(
                        kind="count_claim",
                        severity="warn",
                        target_file=rel,
                        line=lineno,
                        referenced_entity=f"{claimed} {kind}",
                        recommendation=(
                            f"Cannot enumerate {kind} (target directory absent). "
                            "Verify count manually or restore the directory."
                        ),
                        expected=str(claimed),
                        actual=None,
                    )
                )
                continue
            if actual != claimed:
                findings.append(
                    Finding(
                        kind="count_claim",
                        severity="critical",
                        target_file=rel,
                        line=lineno,
                        referenced_entity=f"{claimed} {kind}",
                        recommendation=(
                            f"Manifest claims {claimed} {kind}; actual count is {actual}. "
                            "Update manifest or use a count-validating generator."
                        ),
                        expected=str(claimed),
                        actual=str(actual),
                    )
                )

    return findings, refs_checked


def _expand_target(target: Path, repo_root: Path) -> list[Path]:
    """Expand a target into concrete paths.

    Supports literal files, directories, and glob patterns containing ``*`` or
    ``?``. Glob patterns are resolved relative to repo_root.
    """
    target_str = str(target)
    if "*" in target_str or "?" in target_str:
        rel = target_str
        if Path(rel).is_absolute():
            return []
        return sorted(repo_root.glob(rel))
    abs_target = target if target.is_absolute() else (repo_root / target)
    return [abs_target] if abs_target.exists() else []


def scan(targets: list[Path], repo_root: Path) -> ScanResult:
    """Scan all targets relative to repo_root."""
    repo_root = repo_root.resolve()
    known_skills = enumerate_skills(repo_root)
    result = ScanResult()
    for target in targets:
        expanded = _expand_target(target, repo_root)
        if not expanded:
            LOGGER.info("skipping %s: not present", target)
            continue
        for resolved in expanded:
            try:
                resolved.resolve().relative_to(repo_root)
            except ValueError:
                LOGGER.warning("skipping %s: outside repo root", resolved)
                continue
            for path in _walk_targets(resolved):
                findings, refs_checked = scan_file(path, repo_root, known_skills)
                result.findings.extend(findings)
                result.refs_checked += refs_checked
                result.files_scanned += 1
    return result


def render_envelope(result: ScanResult, output: str) -> str:
    envelope = {
        "Success": result.verdict != "CRITICAL_FAIL",
        "Data": {
            "findings": [f.to_dict() for f in result.findings],
            "verdict": result.verdict,
            "counts": {
                "files_scanned": result.files_scanned,
                "refs_checked": result.refs_checked,
                "findings_total": len(result.findings),
            },
        },
        "Error": None,
        "Metadata": {
            "Script": "scan.py",
            "Version": VERSION,
            "Timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }
    if output == "human":
        lines = [
            f"orphan-ref-validator {VERSION}",
            f"  files_scanned: {result.files_scanned}",
            f"  refs_checked:  {result.refs_checked}",
            f"  findings:      {len(result.findings)}",
        ]
        for f in result.findings:
            lines.append(
                f"  [{f.severity}] {f.target_file}:{f.line} {f.kind} `{f.referenced_entity}` -- {f.recommendation}"
            )
        return "\n".join(lines) + f"\nVERDICT: {result.verdict}"
    return json.dumps(envelope, indent=2) + f"\nVERDICT: {result.verdict}"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect orphan refs in structured artifacts (REQ-008)."
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=None,
        help="Target paths to scan (files or directories). Defaults to standard repo paths.",
    )
    parser.add_argument(
        "--include-adrs",
        action="store_true",
        default=False,
        help="Also scan .agents/architecture/ and docs/ (opt-in; high-noise historical surface).",
    )
    parser.add_argument(
        "--include-skill-descriptions",
        action="store_true",
        default=False,
        help="Also scan .claude/skills/*/SKILL.md (opt-in until preexisting drift is cleaned).",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root. Defaults to git rev-parse --show-toplevel or CWD.",
    )
    parser.add_argument(
        "--output",
        choices=("json", "human"),
        default="json",
        help="Output format. Default: json (ADR-056 envelope).",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Logging level. Default: WARNING.",
    )
    return parser.parse_args(argv)


def _resolve_repo_root(supplied: str | None) -> Path:
    if supplied is not None:
        return Path(supplied).resolve()
    candidate = Path.cwd()
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    return Path.cwd()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    try:
        repo_root = _resolve_repo_root(args.repo_root)
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("could not resolve repo root: %s", exc)
        return 2
    if args.targets:
        target_strs = list(args.targets)
    else:
        target_strs = list(DEFAULT_TARGETS)
        if args.include_adrs:
            target_strs.extend(OPT_IN_ADR_TARGETS)
        if args.include_skill_descriptions:
            target_strs.extend(OPT_IN_SKILL_TARGETS)
    targets = [Path(t) for t in target_strs]
    result = scan(targets, repo_root)
    print(render_envelope(result, args.output))
    if result.verdict == "CRITICAL_FAIL":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
