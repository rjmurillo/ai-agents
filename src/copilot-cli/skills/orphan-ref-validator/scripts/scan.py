#!/usr/bin/env python3
# taste-lint: ignore file-size
#
# file-size suppression rationale: scan.py groups the regex constants,
# extractors, enumerators, scan(), render_envelope() bridge, and main()
# entry point that together implement REQ-009 in a single auditable
# module. Splitting further would scatter the canonical-source-mirror
# contract (`.claude/rules/canonical-source-mirror.md`) across more
# files, multiplying the surfaces that must stay byte-for-byte aligned
# with `build/scripts/validate_marketplace_counts.py`. The extractor
# helpers already live in sibling modules (``filters.py``, ``envelope.py``,
# ``walking.py``); the residual size is the orchestration core.
"""Orphan-ref validator: detect references to absent entities in structured artifacts.

Scans target paths for references to skill names, script paths, and count claims
that do not match working-tree state. Emits ADR-056 envelope plus final
``VERDICT: PASS|WARN|CRITICAL_FAIL`` line. Exit code per ADR-035.

Reference: REQ-009, DESIGN-009, issue #1939, epic #1933.

Exit codes:
    0 - PASS or WARN (no critical findings)
    1 - CRITICAL_FAIL (one or more critical findings)
    2 - Configuration error (bad CLI args, missing repo root)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path

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

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from counts import (
        enumerate_count,
        enumerate_skills,
        is_manifest_file,
        is_marketplace_manifest,
        reset_count_cache,
    )
    from envelope import (
        Finding,
        ScanResult,
        Severity,
        render_envelope,
        render_error_envelope,
    )
    from filters import is_known_kebab_word
    from patterns import (
        FILE_IGNORE_DIRECTIVE_RE,
        extract_count_claims,
        extract_script_refs,
        extract_skill_refs,
        extract_skill_script_refs,
    )
    from walking import walk_targets
else:
    from .counts import (
        enumerate_count,
        enumerate_skills,
        is_manifest_file,
        is_marketplace_manifest,
        reset_count_cache,
    )
    from .envelope import (
        Finding,
        ScanResult,
        Severity,
        render_envelope,
        render_error_envelope,
    )
    from .filters import is_known_kebab_word
    from .patterns import (
        FILE_IGNORE_DIRECTIVE_RE,
        extract_count_claims,
        extract_script_refs,
        extract_skill_refs,
        extract_skill_script_refs,
    )
    from .walking import walk_targets

LOGGER = logging.getLogger("orphan_ref_validator")


def _path_under(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


_is_known_kebab_word = is_known_kebab_word


def scan_file(
    target_path: Path,
    repo_root: Path,
    known_skills: set[str],
    enforce_counts: bool = False,
    skill_catalog_present: bool = True,
) -> tuple[list[Finding], int]:
    """Scan one file. Returns findings and count of refs checked.

    Thin orchestrator: read text, check for the file-scope ignore directive,
    delegate the three reference checks to private helpers. Each helper is
    small enough to unit-test in isolation.

    ``enforce_counts`` is reserved for an opt-in single-plugin count_claim
    enforcement path. PR1 leaves it ``False`` and defers count enforcement
    to the canonical validator. ``skill_catalog_present`` distinguishes
    "no skills directory exists" (warn) from "empty catalog" (critical).
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

    skill_findings, skill_refs = _check_skill_refs(
        text, rel, known_skills, skill_catalog_present
    )
    findings.extend(skill_findings)
    refs_checked += skill_refs

    script_findings, script_refs = _check_script_refs(text, rel, repo_root)
    findings.extend(script_findings)
    refs_checked += script_refs

    skill_script_findings, skill_script_refs = _check_skill_script_refs(
        text, rel, repo_root
    )
    findings.extend(skill_script_findings)
    refs_checked += skill_script_refs

    if is_manifest_file(target_path):
        # Count enforcement is single-plugin scoped: enumerate_count only
        # enumerates the .claude/ tree. marketplace.json catalogs are
        # multi-plugin (or describe the copilot tree), so enforcing their
        # per-plugin claims against .claude/* yields false positives. Skip
        # emission for them; refs are still counted for coverage.
        file_enforce = enforce_counts and not is_marketplace_manifest(target_path)
        count_findings, count_refs = _check_count_claims(
            text, rel, repo_root, file_enforce
        )
        findings.extend(count_findings)
        refs_checked += count_refs

    return findings, refs_checked


def _check_skill_refs(
    text: str, rel: str, known_skills: set[str], skill_catalog_present: bool
) -> tuple[list[Finding], int]:
    """Emit skill_name findings for backticked kebab tokens that have no
    matching ``.claude/skills/<name>/`` directory."""
    findings: list[Finding] = []
    refs_checked = 0
    for lineno, ref in extract_skill_refs(text):
        if _is_known_kebab_word(ref):
            continue
        refs_checked += 1
        if ref in known_skills:
            continue
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
    return findings, refs_checked


def _check_script_refs(
    text: str, rel: str, repo_root: Path
) -> tuple[list[Finding], int]:
    """Emit script_path findings for backticked repo-relative ``.py`` paths
    that do not exist on disk."""
    findings: list[Finding] = []
    refs_checked = 0
    for lineno, script_ref in extract_script_refs(text):
        refs_checked += 1
        if (repo_root / script_ref).exists():
            continue
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
    return findings, refs_checked


def _check_skill_script_refs(
    text: str, rel: str, repo_root: Path
) -> tuple[list[Finding], int]:
    """Emit script_path findings for skill-script references (.claude/skills or
    the copilot mirror), backticked or bare, that do not exist on disk. This is
    the issue #1987 wrong-script-name class (e.g. get_unresolved_threads.py for
    get_unresolved_review_threads.py)."""
    findings: list[Finding] = []
    refs_checked = 0
    for lineno, script_ref in extract_skill_script_refs(text):
        refs_checked += 1
        if (repo_root / script_ref).exists():
            continue
        findings.append(
            Finding(
                kind="script_path",
                severity="critical",
                target_file=rel,
                line=lineno,
                referenced_entity=script_ref,
                recommendation=(
                    f"Skill script `{script_ref}` not present on disk. "
                    "Check the exact filename (a missing word like `review` is "
                    "the issue #1987 failure mode); update the reference or "
                    "restore the script."
                ),
            )
        )
    return findings, refs_checked


def _check_count_claims(
    text: str, rel: str, repo_root: Path, enforce_counts: bool
) -> tuple[list[Finding], int]:
    """Extract count_claim regex matches. Findings are emitted only when
    ``enforce_counts`` is True (PR2 path); PR1 delegates emission to
    ``build/scripts/validate_marketplace_counts.py`` per
    ``.claude/rules/canonical-source-mirror.md``.
    """
    findings: list[Finding] = []
    refs_checked = 0
    for lineno, claimed, kind in extract_count_claims(text):
        refs_checked += 1
        if not enforce_counts:
            continue
        actual = enumerate_count(repo_root, kind)
        if actual is None:
            findings.append(_count_warn_finding(rel, lineno, claimed, kind))
            continue
        if actual != claimed:
            findings.append(
                _count_critical_finding(rel, lineno, claimed, kind, actual)
            )
    return findings, refs_checked


def _count_warn_finding(rel: str, lineno: int, claimed: int, kind: str) -> Finding:
    return Finding(
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


def _count_critical_finding(
    rel: str, lineno: int, claimed: int, kind: str, actual: int
) -> Finding:
    return Finding(
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


MAX_FINDINGS = 500


def _suppress_baselined(
    findings: list[Finding], baseline: set[str]
) -> list[Finding]:
    """Return findings with baselined keys marked ``suppressed``.

    A finding whose ``key`` is in the baseline is replaced by a suppressed
    copy. Non-baselined findings pass through unchanged.
    """
    return [
        replace(f, suppressed=True) if f.key in baseline else f for f in findings
    ]


class BaselineError(ValueError):
    """Raised when a ``--baseline`` file cannot be read or parsed."""


def load_baseline(path: Path) -> set[str]:
    """Load a set of baseline finding keys from a file.

    Two formats are accepted:

    - JSON: either a list of key strings (``["a:1:skill_name:x", ...]``) or a
      scan envelope (``{"Data": {"findings": [...]}}``) whose findings are
      reduced to keys.
    - Plain text: one ``target_file:line:kind:referenced_entity`` key per
      line; blank lines and ``#`` comment lines are ignored.

    Raises ``BaselineError`` on a missing file or unparseable content.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BaselineError(f"cannot read baseline file {path}: {exc}") from exc

    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return _load_baseline_json(stripped, path)
    return {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _load_baseline_json(stripped: str, path: Path) -> set[str]:
    json_text = _strip_verdict_suffix(stripped)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise BaselineError(f"baseline file {path} is not valid JSON: {exc}") from exc
    if isinstance(data, list):
        return {str(item) for item in data}
    if isinstance(data, dict):
        data_field = data.get("Data")
        findings = data_field.get("findings") if isinstance(data_field, dict) else None
        if isinstance(findings, list):
            keys: set[str] = set()
            for f in findings:
                if not isinstance(f, dict):
                    continue
                target_file = f.get("target_file")
                line = f.get("line")
                kind = f.get("kind")
                referenced_entity = f.get("referenced_entity")
                if (
                    target_file is None
                    or line is None
                    or kind is None
                    or referenced_entity is None
                ):
                    continue
                keys.add(
                    f"{target_file}:{line}:{kind}:{referenced_entity}"
                )
            return keys
    raise BaselineError(
        f"baseline file {path} JSON must be a list of keys or a scan "
        "envelope with Data.findings"
    )


def _strip_verdict_suffix(stripped: str) -> str:
    lines = stripped.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("VERDICT:"):
            return "\n".join(lines[:index]).strip()
    return stripped


def scan(
    targets: list[Path],
    repo_root: Path,
    max_findings: int = MAX_FINDINGS,
    enforce_counts: bool = False,
    baseline: set[str] | None = None,
) -> ScanResult:
    """Scan all targets relative to repo_root.

    Clears the per-process count cache at entry so programmatic use
    (multiple ``scan()`` calls in the same process) does not see stale
    enumerations after filesystem mutation. The CLI runs one scan per
    process so cache reset is also safe there.

    ``max_findings`` bounds memory growth on pathologically large
    catalogs. When reached, scanning halts early and a synthetic warning
    finding records the truncation so the operator can re-scan with
    narrower targets.

    ``enforce_counts`` opts into single-plugin count_claim emission. Default
    off keeps marketplace.json multi-plugin coverage delegated to the
    canonical ``build/scripts/validate_marketplace_counts.py`` per
    ``.claude/rules/canonical-source-mirror.md``.

    ``baseline`` is a set of known pre-existing finding keys
    (``target_file:line:kind:referenced_entity``, see ``Finding.key``). A
    finding whose key is in the baseline is marked ``suppressed`` and does
    not drive the verdict, so a default repo-wide scan does not fail on debt
    that predates the gate (issue #2371). A new finding not in the baseline
    still yields CRITICAL_FAIL.
    """
    reset_count_cache()
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
            for path in walk_targets(resolved, repo_root):
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
                    enforce_counts=enforce_counts,
                    skill_catalog_present=skill_catalog_present,
                )
                if baseline:
                    findings = _suppress_baselined(findings, baseline)
                    findings.sort(key=lambda f: f.suppressed)
                # Reserve one slot for the synthetic truncation finding so
                # the returned list never exceeds ``max_findings``.
                budget = max_findings - 1
                if len(findings) > 0 and len(result.findings) + len(findings) > budget:
                    keep = max(0, budget - len(result.findings))
                    result.findings.extend(findings[:keep])
                    result.refs_checked += refs_checked
                    result.files_scanned += 1
                    result.findings.append(
                        Finding(
                            kind="scan_truncated",
                            severity="warn",
                            target_file="<scanner>",
                            line=0,
                            referenced_entity=f"{max_findings} findings",
                            recommendation=(
                                f"Scan halted at {max_findings} findings to bound "
                                "memory; re-scan with narrower --targets to see "
                                "the remaining findings."
                            ),
                        )
                    )
                    return result
                result.findings.extend(findings)
                result.refs_checked += refs_checked
                result.files_scanned += 1
    return result


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect orphan refs in structured artifacts (REQ-009)."
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
        "--enforce-counts",
        action="store_true",
        default=False,
        help=(
            "Emit count_claim findings for plugin-manifest count claims that "
            "diverge from working-tree state (single-plugin scope). Default off: "
            "marketplace.json multi-plugin coverage is delegated to the canonical "
            "build/scripts/validate_marketplace_counts.py per "
            ".claude/rules/canonical-source-mirror.md."
        ),
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
        "--baseline",
        default=None,
        help=(
            "Path to a baseline file of known pre-existing finding keys "
            "(target_file:line:kind:referenced_entity). Matching findings are "
            "marked suppressed and do not fail the scan; new findings not in "
            "the baseline still exit 1. Accepts a JSON list of keys, a scan "
            "envelope (Data.findings), or one key per line (# comments allowed)."
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
    # argparse calls sys.exit(2) on unknown/invalid flags via SystemExit;
    # catch so the ADR-056 contract (Success=false, Error block, VERDICT:
    # ERROR) is honored even for typoed flags. The script's stderr already
    # carried argparse's "usage: ..." text by this point.
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        if exc.code in (None, 0):
            raise
        message = "invalid command-line arguments (see argparse usage on stderr)"
        # Default to JSON envelope on parse failure; --output is unknown here.
        print(render_error_envelope(message, "json"))
        return 2
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    try:
        repo_root = _resolve_repo_root(args.repo_root)
    except RepoRootError as exc:
        LOGGER.error("%s", exc)
        print(render_error_envelope(str(exc), args.output))
        return 2
    if args.targets:
        target_strs = list(args.targets)
        if args.include_adrs:
            print(
                "warning: --include-adrs ignored because --targets was specified "
                "explicitly. Add the ADR paths to --targets to scan them.",
                file=sys.stderr,
            )
        if args.include_skill_descriptions:
            print(
                "warning: --include-skill-descriptions ignored because --targets "
                "was specified explicitly. Add the skill paths to --targets to "
                "scan them.",
                file=sys.stderr,
            )
    else:
        target_strs = list(DEFAULT_TARGETS)
        if args.include_adrs:
            target_strs.extend(OPT_IN_ADR_TARGETS)
        if args.include_skill_descriptions:
            target_strs.extend(OPT_IN_SKILL_TARGETS)
    targets = [Path(t) for t in target_strs]
    baseline: set[str] | None = None
    if args.baseline:
        try:
            baseline_candidate = Path(args.baseline)
            baseline_path = (
                baseline_candidate
                if baseline_candidate.is_absolute()
                else repo_root / baseline_candidate
            ).resolve()
            try:
                baseline_path.relative_to(repo_root)
            except ValueError as exc:
                raise BaselineError(
                    f"baseline path escapes repository root: {baseline_path}"
                ) from exc
            baseline = load_baseline(baseline_path)
        except BaselineError as exc:
            LOGGER.error("%s", exc)
            print(render_error_envelope(str(exc), args.output))
            return 2
    try:
        result = scan(
            targets,
            repo_root,
            enforce_counts=args.enforce_counts,
            baseline=baseline,
        )
        print(render_envelope(result, args.output))
    except Exception as exc:
        # Catch-all so an unexpected runtime crash (filesystem races, encoding
        # surprises, etc.) still emits the ADR-056 envelope + VERDICT: ERROR
        # line. Without this guard the build gate parser sees a Python
        # traceback on stdout and a missing VERDICT line, which violates the
        # /build gate contract.
        LOGGER.exception("unhandled exception during scan")
        message = f"unhandled exception during scan: {type(exc).__name__}: {exc}"
        print(render_error_envelope(message, args.output, error_type="General"))
        return 2
    if result.verdict == "CRITICAL_FAIL":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
