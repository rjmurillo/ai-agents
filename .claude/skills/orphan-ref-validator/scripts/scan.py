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

# Mirrors COUNT_PATTERN and LABEL_MAP from
# build/scripts/validate_marketplace_counts.py (canonical). Per
# .claude/rules/canonical-source-mirror.md, the canonical contract is:
#
#     COUNT_PATTERN = re.compile(
#         r"(\d+)\s+"
#         r"(specialized\s+agent\s+definition"
#         r"|agent\s+definition"
#         r"|agent"
#         r"|slash\s+command"
#         r"|lifecycle\s+hook"
#         r"|reusable\s+skill)"
#         r"s?"
#     )
#     LABEL_MAP = {
#         "specialized agent definition": "agent",
#         "agent definition": "agent",
#         "agent": "agent",
#         "slash command": "slash command",
#         "lifecycle hook": "lifecycle hook",
#         "reusable skill": "reusable skill",
#     }
#
# Stricter/looser/different than canonical: same pattern source bytes;
# orphan-ref-validator does not implement the canonical's --fix path or
# YAML-driven per-plugin exclude resolution. Detection only.
COUNT_CLAIM_RE = re.compile(
    r"(\d+)\s+"
    r"(specialized\s+agent\s+definition"
    r"|agent\s+definition"
    r"|agent"
    r"|slash\s+command"
    r"|lifecycle\s+hook"
    r"|reusable\s+skill)"
    r"s?"
)
COUNT_LABEL_MAP = {
    "specialized agent definition": "agent",
    "agent definition": "agent",
    "agent": "agent",
    "slash command": "slash command",
    "lifecycle hook": "lifecycle hook",
    "reusable skill": "reusable skill",
}
IGNORE_DIRECTIVE_RE = re.compile(r"<!--\s*orphan-ref-ignore\s*-->")
FILE_IGNORE_DIRECTIVE_RE = re.compile(r"<!--\s*orphan-ref-ignore-file\s*-->")

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from filters import is_known_kebab_word
else:
    from .filters import is_known_kebab_word

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
    """Yield candidate files under target (or just the target if it is a file).

    Recurses with ``iterdir`` and prunes ``EXCLUDE_DIR_NAMES`` at directory
    level rather than ``rglob('*')`` + post-filter, so excluded subtrees
    (``node_modules``, ``.git``, ``references``, ``templates``,
    ``__pycache__``) are never entered.
    """
    if target.is_file():
        if _is_secret_path(target):
            return
        if target.stat().st_size > MAX_FILE_BYTES:
            LOGGER.warning("skipping %s: exceeds %d bytes", target, MAX_FILE_BYTES)
            return
        yield target
        return
    yield from _iter_dir_pruned(target)


def _iter_dir_pruned(directory: Path) -> Iterable[Path]:
    """Walk ``directory`` recursively, pruning excluded directory names."""
    try:
        entries = list(directory.iterdir())
    except (OSError, PermissionError) as exc:
        LOGGER.warning("could not iterate %s: %s", directory, exc)
        return
    for entry in entries:
        if entry.is_dir():
            if entry.name in EXCLUDE_DIR_NAMES:
                continue
            yield from _iter_dir_pruned(entry)
            continue
        if not entry.is_file():
            continue
        if entry.suffix not in SCAN_FILE_SUFFIXES:
            continue
        if _is_secret_path(entry):
            continue
        try:
            size = entry.stat().st_size
        except OSError as exc:
            LOGGER.warning("could not stat %s: %s", entry, exc)
            continue
        if size > MAX_FILE_BYTES:
            LOGGER.warning("skipping %s: exceeds %d bytes", entry, MAX_FILE_BYTES)
            continue
        yield entry


def enumerate_skills(repo_root: Path) -> set[str] | None:
    """Return the set of skill names found at ``.claude/skills/<name>/SKILL.md``.

    Returns ``None`` when ``.claude/skills/`` is absent so callers can
    distinguish "no directory" (undeterminable) from "directory with zero
    skills" (deterministic count of zero).
    """
    skills_dir = repo_root / ".claude" / "skills"
    if not skills_dir.exists():
        return None
    return {
        d.name
        for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    }


_COUNT_CACHE: dict[tuple[str, str], int | None] = {}


def enumerate_count(repo_root: Path, kind: str) -> int | None:
    """Return count for the given canonical label, or ``None`` when absent.

    ``kind`` is one of the ``COUNT_LABEL_MAP`` values: ``"agent"``,
    ``"slash command"``, ``"lifecycle hook"``, ``"reusable skill"``. The
    legacy short forms ``"skills"``, ``"agents"``, ``"commands"``,
    ``"hooks"`` are accepted as aliases.

    Mirrors the project-toolkit ``.claude-plugin/marketplace.json``
    strategies declared in ``templates/marketplace-counters.yaml`` and
    implemented as ``md_agents``, ``commands``, ``hooks``, ``skill_dirs``
    in ``build/scripts/validate_marketplace_counts.py``. Per
    ``.claude/rules/canonical-source-mirror.md``:

        agent:           md_agents(.claude/agents, exclude={AGENTS.md, CLAUDE.md})
        slash command:   commands(.claude/commands, exclude={CLAUDE.md})
        lifecycle hook:  hooks(.claude/hooks)
        reusable skill:  skill_dirs(.claude/skills)

    Stricter/looser/different than canonical:

    - Pruning: canonical uses ``os.walk`` with ``_EXCLUDED_DIRS`` removed
      from ``dirs``; this uses ``Path.rglob``/``iterdir`` without that
      prune set. ``.claude/`` trees do not currently contain those names,
      so counts match in practice; if a future ``node_modules`` ever lands
      under ``.claude/hooks/`` the canonical will exclude it and this
      will not.
    - Per-plugin overrides: canonical reads
      ``templates/marketplace-counters.yaml`` for plugin-specific
      ``exclude`` lists; this hard-codes the project-toolkit excludes.
      Other plugins are not supported here; orphan-ref-validator scans
      manifests for general count drift, not per-plugin enforcement.
    - ``--fix``: canonical supports auto-fix; this is detection only.
    """
    canonical = {
        "agents": "agent",
        "commands": "slash command",
        "hooks": "lifecycle hook",
        "skills": "reusable skill",
    }.get(kind, kind)
    cache_key = (str(repo_root), canonical)
    if cache_key in _COUNT_CACHE:
        return _COUNT_CACHE[cache_key]
    result: int | None
    if canonical == "reusable skill":
        skills = enumerate_skills(repo_root)
        result = None if skills is None else len(skills)
    elif canonical == "agent":
        result = _count_md_agents(
            repo_root / ".claude" / "agents",
            exclude={"AGENTS.md", "CLAUDE.md"},
        )
    elif canonical == "slash command":
        result = _count_md_recursive(
            repo_root / ".claude" / "commands", exclude={"CLAUDE.md"}
        )
    elif canonical == "lifecycle hook":
        result = _count_py_recursive(repo_root / ".claude" / "hooks")
    else:
        result = None
    _COUNT_CACHE[cache_key] = result
    return result


def _reset_count_cache() -> None:
    """Clear the per-repo count cache. Test helper; not part of the CLI."""
    _COUNT_CACHE.clear()


def _count_md_agents(directory: Path, exclude: set[str]) -> int | None:
    """Count .md files; canonical _count_md_agents shape (excludes templates)."""
    if not directory.exists():
        return None
    return sum(
        1
        for f in directory.iterdir()
        if f.is_file()
        and f.suffix == ".md"
        and f.name not in exclude
        and "template" not in f.name
    )


def _count_md_recursive(directory: Path, exclude: set[str]) -> int | None:
    if not directory.exists():
        return None
    return sum(
        1
        for f in directory.rglob("*.md")
        if f.is_file() and f.name not in exclude
    )


def _count_py_recursive(directory: Path) -> int | None:
    if not directory.exists():
        return None
    return sum(1 for f in directory.rglob("*.py") if f.is_file())


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
    """Yield ``(lineno, count, canonical_label)`` triples for each count claim.

    ``canonical_label`` is the ``COUNT_LABEL_MAP`` value (one of "agent",
    "slash command", "lifecycle hook", "reusable skill"); ``enumerate_count``
    consumes the same labels.
    """
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _line_has_ignore_directive(line):
            continue
        for match in COUNT_CLAIM_RE.finditer(line):
            label_text = re.sub(r"\s+", " ", match.group(2).lower())
            canonical = COUNT_LABEL_MAP.get(label_text)
            if canonical is None:
                continue
            yield lineno, int(match.group(1)), canonical


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
    enforce_counts: bool = False,
    skill_catalog_present: bool = True,
) -> tuple[list[Finding], int]:
    """Scan one file. Returns findings and count of refs checked.

    ``enforce_counts`` is reserved for an opt-in single-plugin count_claim
    enforcement path. PR1 leaves it ``False`` and defers count enforcement
    to the canonical validator (see header comment in the count_claim
    block).

    ``skill_catalog_present`` distinguishes "no skills directory exists"
    (downgrade skill_name findings to warn; we cannot say a backticked
    kebab token is orphaned because we do not know what's installed) from
    "directory exists with zero skills" (treat as authoritative empty set;
    every backticked kebab token is critical).
    """
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
            severity: Severity = "critical" if skill_catalog_present else "warn"
            recommendation = (
                f"Skill `{ref}` not present at .claude/skills/. "
                "Update reference, restore the skill, or remove the mention."
                if skill_catalog_present
                else (
                    f"Skill `{ref}` cannot be verified: .claude/skills/ "
                    "directory is absent (vendored install)."
                )
            )
            findings.append(
                Finding(
                    kind="skill_name",
                    severity=severity,
                    target_file=rel,
                    line=lineno,
                    referenced_entity=ref,
                    recommendation=recommendation,
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

    # Count_claim enforcement is delegated to
    # build/scripts/validate_marketplace_counts.py per
    # .claude/rules/canonical-source-mirror.md. The canonical validator
    # reads templates/marketplace-counters.yaml for per-plugin source
    # directories and exclude lists, supports auto-fix, and runs in CI.
    # orphan-ref-validator's regex still extracts claims (refs_checked
    # increments for visibility) but emits no Findings; ``--enforce-counts``
    # is the planned PR2 surface for opt-in single-plugin enforcement.
    if is_manifest_file(target_path):
        for lineno, claimed, kind in extract_count_claims(text):
            refs_checked += 1
            if enforce_counts:
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
    skills = enumerate_skills(repo_root)
    skill_catalog_present = skills is not None
    known_skills: set[str] = skills if skills is not None else set()
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
                # Re-check containment after symlink resolution. A symlink
                # inside an allowed directory can point outside the repo.
                try:
                    path.resolve().relative_to(repo_root)
                except ValueError:
                    LOGGER.warning(
                        "skipping %s: resolves outside repo root", path
                    )
                    continue
                findings, refs_checked = scan_file(
                    path,
                    repo_root,
                    known_skills,
                    skill_catalog_present=skill_catalog_present,
                )
                result.findings.extend(findings)
                result.refs_checked += refs_checked
                result.files_scanned += 1
    return result


def render_envelope(result: ScanResult, output: str) -> str:
    # Per ADR-056: Success reflects whether the scan ran successfully, not
    # whether findings exist. CRITICAL_FAIL is a successful scan that found
    # blocking issues; the verdict expresses that. Reserve Success=false +
    # populated Error{Message,Code} for configuration or runtime failures
    # (which exit code 2).
    envelope = {
        "Success": True,
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
        help=(
            "Repository root. Default: walk up from CWD looking for the nearest "
            ".git directory; fall back to CWD. A supplied path must exist and be "
            "a directory or the script exits with ADR-035 code 2."
        ),
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


class RepoRootError(ValueError):
    """Raised when ``--repo-root`` does not point at an existing directory."""


def _resolve_repo_root(supplied: str | None) -> Path:
    """Return the resolved repository root.

    Raises ``RepoRootError`` if a user-supplied path is missing or not a
    directory; ``main`` translates that into the ADR-035 configuration
    error exit code (``2``).
    """
    if supplied is not None:
        candidate = Path(supplied).resolve()
        if not candidate.exists():
            raise RepoRootError(f"--repo-root path does not exist: {candidate}")
        if not candidate.is_dir():
            raise RepoRootError(f"--repo-root path is not a directory: {candidate}")
        return candidate
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
    except RepoRootError as exc:
        LOGGER.error("%s", exc)
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
