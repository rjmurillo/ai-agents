#!/usr/bin/env python3
# taste-lint: ignore file-size
#
# file-size suppression rationale: scan.py groups the regex constants,
# extractors, enumerator, scan(), render_envelope() bridge, and main()
# entry point that together implement REQ-009 in a single auditable
# module. The extractor helpers already live in sibling modules
# (``filters.py``, ``envelope.py``, ``walking.py``); the residual size is
# the orchestration core.
"""Orphan-ref validator: detect references to absent entities in structured artifacts.

Scans target paths for references to skill names and script paths that do
not match working-tree state. Emits ADR-056 envelope plus final
``VERDICT: PASS|WARN|CRITICAL_FAIL`` line. Exit code per ADR-035.

Reference: REQ-009, DESIGN-009, issue #1939, epic #1933.

Exit codes:
    0 - PASS or WARN (no critical findings)
    1 - CRITICAL_FAIL (one or more critical findings)
    2 - Configuration error (bad CLI args, missing repo root)
    3 - External error
    4 - Authentication/authorization error, including permission denied
"""

from __future__ import annotations

import argparse
import codecs
import json
import logging
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path

DOT_AGENTS = "." + "agents"

DEFAULT_TARGETS = (
    f"{DOT_AGENTS}/specs",
    "tests",
    ".claude/.claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".github/plugin/marketplace.json",
)
DEFAULT_TRACKED_PREFIXES = (
    f"{DOT_AGENTS}/specs/",
    ".claude/rules/",
    ".github/instructions/",
    "src/copilot-cli/instructions/",
    "tests/",
)
DEFAULT_EXACT_TARGETS = (
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
        enumerate_sibling_artifacts,
        enumerate_skills,
    )
    from envelope import (
        Finding,
        IncompleteScan,
        Kind,
        ScanResult,
        Severity,
        SuppressedReference,
        render_envelope,
        render_error_envelope,
        render_scan_error_envelope,
        scan_error_exit_code,
    )
    from filters import (
        is_known_kebab_skill,
        is_known_kebab_word,
        is_known_single_word_skill,
    )
    from patterns import (
        FILE_IGNORE_DIRECTIVE_RE,
        extract_all_reference_candidates,
        extract_directive_suppressed_refs,
        extract_instruction_refs,
        extract_rule_refs,
        extract_script_refs,
        extract_single_word_skill_refs,
        extract_skill_refs,
        extract_skill_script_refs,
        extract_typed_skill_refs,
    )
    from walking import collect_walk_targets
else:
    from .counts import (
        enumerate_sibling_artifacts,
        enumerate_skills,
    )
    from .envelope import (
        Finding,
        IncompleteScan,
        Kind,
        ScanResult,
        Severity,
        SuppressedReference,
        render_envelope,
        render_error_envelope,
        render_scan_error_envelope,
        scan_error_exit_code,
    )
    from .filters import (
        is_known_kebab_skill,
        is_known_kebab_word,
        is_known_single_word_skill,
    )
    from .patterns import (
        FILE_IGNORE_DIRECTIVE_RE,
        extract_all_reference_candidates,
        extract_directive_suppressed_refs,
        extract_instruction_refs,
        extract_rule_refs,
        extract_script_refs,
        extract_single_word_skill_refs,
        extract_skill_refs,
        extract_skill_script_refs,
        extract_typed_skill_refs,
    )
    from .walking import collect_walk_targets

LOGGER = logging.getLogger("orphan_ref_validator")


def _path_under(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except (ValueError, OSError, RuntimeError):
        return str(path)


def _exists_under_repo(repo_root: Path, path: Path) -> bool:
    resolved_root = repo_root.expanduser().resolve()
    resolved_path = path.expanduser().resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except (ValueError, OSError, RuntimeError):
        return False
    return resolved_path.exists()


_is_known_kebab_word = is_known_kebab_word
_is_known_kebab_skill = is_known_kebab_skill
_is_known_single_word_skill = is_known_single_word_skill


@dataclass(frozen=True)
class FileScanOutcome:
    findings: list[Finding]
    refs_checked: int
    scan_error: str | None = None
    scan_error_type: str = "config"
    directive_suppressed: list[SuppressedReference] | None = None
    skipped: bool = False


def scan_file(
    target_path: Path,
    repo_root: Path,
    known_skills: set[str],
    skill_catalog_present: bool = True,
    sibling_names: frozenset[str] | None = None,
) -> FileScanOutcome:
    """Scan one file. Returns findings and count of refs checked.

    Thin orchestrator: read text, check for the file-scope ignore directive,
    delegate the three reference checks to private helpers. Each helper is
    small enough to unit-test in isolation.

    ``skill_catalog_present`` distinguishes "no skills directory exists"
    (warn) from "empty catalog" (critical).

    ``sibling_names`` holds non-skill artifact names (agents, commands,
    review axes, Serena memories) that a backticked token may legally
    reference; see ``enumerate_sibling_artifacts``. Defaults to empty so
    existing callers keep the previous behavior.
    """
    findings: list[Finding] = []
    refs_checked = 0
    rel = _path_under(repo_root, target_path)

    try:
        text = _read_supported_text(target_path)
    except UnicodeError as exc:
        LOGGER.warning("could not decode %s: %s", target_path, exc)
        return FileScanOutcome(
            findings, refs_checked, f"could not decode file: {exc}", "config"
        )
    except OSError as exc:
        LOGGER.warning("could not read %s: %s", target_path, exc)
        return FileScanOutcome(
            findings, refs_checked, f"could not read file: {exc}", _io_error_type(exc)
        )

    head = "\n".join(text.splitlines()[:50])
    if FILE_IGNORE_DIRECTIVE_RE.search(head):
        LOGGER.info("file-scope ignore directive in %s; skipping", rel)
        return FileScanOutcome(
            findings=[],
            refs_checked=0,
            directive_suppressed=_suppressed_refs_for_text(
                text, rel, "file ignore directive"
            ),
            skipped=True,
        )

    skill_findings, skill_refs = _check_skill_refs(
        text, rel, known_skills, skill_catalog_present, sibling_names
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

    rule_findings, rule_refs = _check_repo_path_refs(
        text,
        rel,
        repo_root,
        extract_rule_refs,
        "rule_path",
        "Rule",
    )
    findings.extend(rule_findings)
    refs_checked += rule_refs

    instruction_findings, instruction_refs = _check_repo_path_refs(
        text,
        rel,
        repo_root,
        extract_instruction_refs,
        "instruction_path",
        "Instruction mirror",
    )
    findings.extend(instruction_findings)
    refs_checked += instruction_refs

    return FileScanOutcome(findings, refs_checked)


def _read_supported_text(target_path: Path) -> str:
    data = target_path.read_bytes()
    bom_encodings = (
        (codecs.BOM_UTF32_LE, "utf-32"),
        (codecs.BOM_UTF32_BE, "utf-32"),
        (codecs.BOM_UTF16_LE, "utf-16"),
        (codecs.BOM_UTF16_BE, "utf-16"),
        (codecs.BOM_UTF8, "utf-8-sig"),
    )
    for bom, encoding in bom_encodings:
        if data.startswith(bom):
            return data.decode(encoding)
    return data.decode("utf-8")


def directive_suppressed_refs(target_path: Path, repo_root: Path) -> list[SuppressedReference]:
    """Return references suppressed by line-scope ignore directives."""
    rel = _path_under(repo_root, target_path)
    try:
        text = _read_supported_text(target_path)
    except (OSError, UnicodeError):
        return []
    return _suppressed_refs_for_text(text, rel, "line ignore directive")


def _suppressed_refs_for_text(
    text: str, rel: str, reason: str
) -> list[SuppressedReference]:
    extractor = (
        extract_all_reference_candidates
        if reason == "file ignore directive"
        else extract_directive_suppressed_refs
    )
    return [
        SuppressedReference(
            target_file=rel,
            line=lineno,
            referenced_entity=ref,
            reason=reason,
        )
        for lineno, ref in extractor(text)
    ]


def _io_error_type(exc: OSError) -> str:
    if isinstance(exc, PermissionError):
        return "auth"
    return "config"


def _check_skill_refs(
    text: str,
    rel: str,
    known_skills: set[str],
    skill_catalog_present: bool,
    sibling_names: frozenset[str] | None = None,
) -> tuple[list[Finding], int]:
    """Emit skill_name findings for orphaned skill references.

    Two reference shapes are checked, both under the same candidate rule: a
    backticked token is a skill reference candidate only when the document
    gives evidence it means a skill. Evidence is either a type claim in the
    prose ("the ``ship`` skill", ``skill="ship"``) or membership in the
    curated set of names this repository has actually used for a skill.

    - Hyphenated tokens (``alpha-skill``): candidate when typed or listed in
      ``KNOWN_KEBAB_SKILLS``, flagged when absent from ``.claude/skills/``.
    - Single-word tokens (``incoherence``): candidate when typed or listed in
      ``KNOWN_SINGLE_WORD_SKILLS``, flagged when absent.

    The hyphenated arm used to treat every backticked kebab token as a
    candidate. In prose that premise is wrong far more often than it is
    right: kebab-case is the ordinary spelling for Actions runners, model
    ids, HTTP headers, config keys, and hook lifecycle names. Measured on
    ``.serena/memories/`` it produced 183 findings and zero true positives
    (issue #3637). The single-word arm already carried the evidence rule for
    the same reason (issue #2679); this is that rule applied consistently.

    A token that resolves in ``sibling_names`` names a real non-skill
    artifact (agent, slash command, review axis, Serena memory) and is not
    an orphan. Without that check the scanner reported prose mentions of
    ``decision-rigor`` (a review axis) and
    ``testing-002-test-first-development`` (a memory) as deleted skills, and
    the only remedy was appending each token to ``KEBAB_DENYLIST`` by hand.
    Resolution replaces that unbounded denylist with a bounded lookup.

    Sibling resolution applies only to references that make no type claim.
    When the prose explicitly calls the token a skill ("the ``ship`` skill",
    ``skill=`ship` ``), REQ-009 AC-2 governs and the token must resolve
    against ``.claude/skills/`` alone: a same-named agent or memory does not
    make the sentence true. Skipping that distinction would trade a false
    positive for a wrong pass.

    A type claim only strengthens resolution for a token that is already a
    candidate, and both extractors require backticks. So a quoted
    ``skill="ship"`` with no backticked ``ship`` anywhere on the line is
    never checked at all; the same line written as
    ``Use `ship` (skill="ship")`` is, because the backticks supply the
    candidate and the quoted form supplies the type claim.
    """
    findings: list[Finding] = []
    refs_checked = 0
    siblings = sibling_names if sibling_names is not None else frozenset()
    typed = extract_typed_skill_refs(text)
    for lineno, ref in extract_skill_refs(text):
        if _is_known_kebab_word(ref):
            continue
        is_typed = (lineno, ref) in typed
        if ref in known_skills or (ref in siblings and not is_typed):
            refs_checked += 1
            continue
        if not is_typed and not _is_known_kebab_skill(ref):
            continue
        refs_checked += 1
        findings.append(
            _skill_ref_finding(ref, rel, lineno, skill_catalog_present)
        )
    for lineno, ref in extract_single_word_skill_refs(text):
        is_typed = (lineno, ref) in typed
        if ref in known_skills or (ref in siblings and not is_typed):
            refs_checked += 1
            continue
        if not is_typed and not _is_known_single_word_skill(ref):
            continue
        refs_checked += 1
        findings.append(
            _skill_ref_finding(ref, rel, lineno, skill_catalog_present)
        )
    return findings, refs_checked


def _skill_ref_finding(
    ref: str, rel: str, lineno: int, skill_catalog_present: bool
) -> Finding:
    """Build a ``skill_name`` finding for an orphaned skill reference.

    Severity is ``critical`` when the catalog is authoritative (present) and
    ``warn`` when ``.claude/skills/`` is absent (vendored install): an absent
    catalog cannot confirm the reference is genuinely orphaned.
    """
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
    return Finding(
        kind="skill_name",
        severity=severity,
        target_file=rel,
        line=lineno,
        referenced_entity=ref,
        recommendation=recommendation,
    )


def _script_ref_resolves(script_ref: str, rel: str, repo_root: Path) -> bool:
    """True when a script reference resolves on disk.

    Tries repo-root-relative first (the historical contract). For a reference
    inside a skill's ``SKILL.md``, ALSO tries the SKILL.md's own directory,
    because skill docs cite their bundled scripts skill-relative
    (``scripts/foo.py`` means the skill's own ``scripts/``). Resolving only
    repo-relative false-flagged every portable skill-relative ref (issue #2796);
    rewriting those to absolute paths would regress #2050 vendored portability,
    so resolve them in place instead. Scoped to SKILL.md targets so non-skill
    documents keep the original repo-relative-only contract.
    """
    if _exists_under_repo(repo_root, repo_root / script_ref):
        return True
    if Path(rel).name == "SKILL.md":
        skill_dir = Path(rel).parent
        if _exists_under_repo(repo_root, repo_root / skill_dir / script_ref):
            return True
    return False


def _check_script_refs(
    text: str, rel: str, repo_root: Path
) -> tuple[list[Finding], int]:
    """Emit script_path findings for backticked repo-relative ``.py`` paths
    that do not exist on disk."""
    findings: list[Finding] = []
    refs_checked = 0
    for lineno, script_ref in extract_script_refs(text):
        refs_checked += 1
        if _script_ref_resolves(script_ref, rel, repo_root):
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
        if _script_ref_resolves(script_ref, rel, repo_root):
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


def _check_repo_path_refs(
    text: str,
    rel: str,
    repo_root: Path,
    extractor: Callable[[str], Iterable[tuple[int, str]]],
    kind: Kind,
    label: str,
) -> tuple[list[Finding], int]:
    """Emit findings for scanned repo-relative path references."""
    findings: list[Finding] = []
    refs_checked = 0
    for lineno, path_ref in extractor(text):
        refs_checked += 1
        if _exists_under_repo(repo_root, repo_root / path_ref):
            continue
        findings.append(
            Finding(
                kind=kind,
                severity="critical",
                target_file=rel,
                line=lineno,
                referenced_entity=path_ref,
                recommendation=(
                    f"{label} `{path_ref}` not present on disk. "
                    "Update reference or restore the file."
                ),
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


def _default_tracked_text_targets(repo_root: Path) -> list[str]:
    """Return tracked markdown, JSON, and YAML files under policy roots."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        LOGGER.warning("git ls-files unavailable for default targets: %s", exc)
        return list(DEFAULT_TARGETS)
    targets: list[str] = []
    for line in completed.stdout.splitlines():
        path = Path(line)
        if path.suffix not in {".md", ".json", ".yaml", ".yml"}:
            continue
        if line not in DEFAULT_EXACT_TARGETS and not any(
            line.startswith(prefix) for prefix in DEFAULT_TRACKED_PREFIXES
        ):
            continue
        if any(part in {"references", "templates"} for part in path.parts):
            continue
        targets.append(line)
    return sorted(targets) if targets else list(DEFAULT_TARGETS)


def _missing_target_issue(target: Path, repo_root: Path) -> IncompleteScan:
    display = str(target)
    if not target.is_absolute():
        display = str(target)
    else:
        display = _path_under(repo_root, target)
    return IncompleteScan(display, "target does not exist or glob matched no files")


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
    baseline: set[str] | None = None,
    allow_missing_targets: bool = False,
) -> ScanResult:
    """Scan all targets relative to repo_root.

    ``max_findings`` bounds memory growth on pathologically large
    catalogs. When reached, scanning halts early and a synthetic warning
    finding records the truncation so the operator can re-scan with
    narrower targets.

    ``baseline`` is a set of known pre-existing finding keys
    (``target_file:line:kind:referenced_entity``, see ``Finding.key``). A
    finding whose key is in the baseline is marked ``suppressed`` and does
    not drive the verdict, so a default repo-wide scan does not fail on debt
    that predates the gate (issue #2371). A new finding not in the baseline
    still yields CRITICAL_FAIL.
    """
    repo_root = repo_root.resolve()
    skills = enumerate_skills(repo_root)
    skill_catalog_present = skills is not None
    known_skills: set[str] = skills if skills is not None else set()
    sibling_names = enumerate_sibling_artifacts(repo_root)
    result = ScanResult()
    for target in targets:
        expanded = _expand_target(target, repo_root)
        if not expanded:
            if allow_missing_targets:
                LOGGER.info("skipping optional %s: not present", target)
                continue
            LOGGER.warning("incomplete scan for %s: not present", target)
            result.incomplete_scans.append(_missing_target_issue(target, repo_root))
            continue
        for resolved in expanded:
            try:
                resolved.resolve().relative_to(repo_root)
            except (OSError, ValueError) as exc:
                LOGGER.warning("incomplete scan for %s: outside repo root", resolved)
                result.incomplete_scans.append(
                    IncompleteScan(_path_under(repo_root, resolved), f"outside repo root: {exc}")
                )
                continue
            paths, walk_problems = collect_walk_targets(resolved, repo_root)
            result.incomplete_scans.extend(
                IncompleteScan(
                    _path_under(repo_root, problem.target),
                    problem.reason,
                    problem.error_type,
                )
                for problem in walk_problems
            )
            for path in paths:
                # Re-check containment after symlink resolution. A symlink
                # inside an allowed directory can point outside the repo.
                try:
                    path.resolve().relative_to(repo_root)
                except (OSError, ValueError) as exc:
                    LOGGER.warning(
                        "incomplete scan for %s: resolves outside repo root", path
                    )
                    result.incomplete_scans.append(
                        IncompleteScan(
                            _path_under(repo_root, path),
                            f"resolves outside repo root: {exc}",
                        )
                    )
                    continue
                outcome = scan_file(
                    path,
                    repo_root,
                    known_skills,
                    skill_catalog_present=skill_catalog_present,
                    sibling_names=sibling_names,
                )
                if outcome.directive_suppressed is not None:
                    result.directive_suppressed.extend(outcome.directive_suppressed)
                else:
                    result.directive_suppressed.extend(
                        directive_suppressed_refs(path, repo_root)
                    )
                if outcome.scan_error is not None:
                    result.incomplete_scans.append(
                        IncompleteScan(
                            _path_under(repo_root, path),
                            outcome.scan_error,
                            outcome.scan_error_type,
                        )
                    )
                    continue
                if outcome.skipped:
                    result.files_skipped += 1
                    continue
                findings = outcome.findings
                refs_checked = outcome.refs_checked
                if baseline:
                    findings = _suppress_baselined(findings, baseline)
                result.findings.extend(findings)
                result.refs_checked += refs_checked
                result.files_scanned += 1
    _prioritize_findings(result.findings)
    if len(result.findings) > max_findings:
        keep = max(0, max_findings - 1)
        result.findings[:] = result.findings[:keep]
        result.findings.append(
            Finding(
                kind="scan_truncated",
                severity="warn",
                target_file="<scanner>",
                line=0,
                referenced_entity=f"{max_findings} findings",
                recommendation=(
                    f"Scan reached {max_findings} findings before all findings could "
                    "be returned. Treat this scan as incomplete and re-scan with "
                    "narrower --targets to inspect the hidden findings."
                ),
            )
        )
        result.incomplete_scans.append(
            IncompleteScan(
                "<scanner>",
                f"scan truncated at {max_findings} findings",
                "logic",
            )
        )
    return result


def _prioritize_findings(findings: list[Finding]) -> None:
    findings.sort(
        key=lambda f: (
            f.suppressed,
            f.target_file,
            f.line,
            f.kind,
            f.referenced_entity,
        )
    )


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
        "--allow-missing-targets",
        action="store_true",
        default=False,
        help=(
            "Treat missing scan targets as optional vendored-install paths. "
            "Explicit targets are strict by default."
        ),
    )
    parser.add_argument(
        "--allow-empty-scan",
        action="store_true",
        default=False,
        help="Permit a completed scan to pass after scanning zero files.",
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
        target_strs = _default_tracked_text_targets(repo_root)
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
            baseline=baseline,
            allow_missing_targets=args.allow_missing_targets,
        )
        if result.incomplete_scans:
            message = (
                "scan incomplete: one or more requested targets could not be scanned"
            )
            print(render_scan_error_envelope(result, message, args.output))
            return int(scan_error_exit_code(result))
        if result.files_scanned == 0 and result.files_skipped == 0 and not args.allow_empty_scan:
            result.incomplete_scans.append(
                IncompleteScan(
                    "<scanner>",
                    "zero files scanned; pass --allow-empty-scan for explicit empty scope",
                )
            )
            print(render_scan_error_envelope(result, "scan completed zero files", args.output))
            return 2
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
