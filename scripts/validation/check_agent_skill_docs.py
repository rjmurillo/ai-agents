#!/usr/bin/env python3
"""Gate: every agent and skill has a reference page and a README row.

Rule: ``templates/rules/agent-skill-docs.md``. PR #7416 shipped ``sol-loop``
and ``llm-council`` with no page, and PR #7424 shipped ``technical-writing``
with no page and no README row. Nothing compared the pages to their sources.

Blocking checks (MUST 1 and 3 of the rule):

- A skill has no ``docs/skills/<name>.md``. A skill is a direct child of
  ``src/claude/skills/`` or ``.claude/skills/`` that holds a ``SKILL.md``;
  a symlink in both trees counts once.
- An agent (``templates/agents/<name>.shared.md``) has no ``docs/agents/<name>.md``.
- A page exists for a skill or agent that does not.
- A page has no row in its ``README.md`` table, or a row links a missing page.
- A page lacks one of the seven sibling sections, or has them out of order.
  Other ``##`` headings may sit between them.

Advisory check (MUST 2, ``--freshness``): for each skill that existed at the
base ref, warn when a fact-bearing part of it changed and its page did not.
Facts compared: frontmatter ``name`` and ``argument-hint``, quoted trigger
phrases in ``description``, the file names under ``scripts/``, the lines of
an ``Exit Codes`` section, and backticked paths in ``SKILL.md``.

The blocking check reads the working tree, so an unstaged page counts. The
freshness check compares the working tree with the base ref.

CLI::

    uv run python scripts/validation/check_agent_skill_docs.py [<repo-root>]
    uv run python scripts/validation/check_agent_skill_docs.py --freshness [--base-ref REF]

Exit codes (ADR-035):
    0 - Success (no findings)
    1 - Logic error (a finding; for --freshness, a stale page)
    2 - Config error (invalid root, or a docs README is missing)
    3 - External error (git could not read the base ref)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks_common import _resolve_default_base_ref
from evidence import (
    REASON_ADVISORY_FINDINGS,
    REASON_BASE_REF_UNRESOLVED,
    REASON_DIFF_FAILED,
    REASON_TREE_ABSENT,
    REASON_VIOLATIONS_FOUND,
    CheckOutcome,
)
from skill_frontmatter import parse_frontmatter

SKILL_TREES = ("src/claude/skills", ".claude/skills")
AGENT_TREE = "templates/agents"
AGENT_SUFFIX = ".shared.md"
DOCS = {"skills": "docs/skills", "agents": "docs/agents"}
SECTIONS = (
    "When to use it",
    "When not to use it",
    "Quick start",
    "What you get",
    "Advanced use",
    "Where it runs",
    "Related",
)
_BLOCKING = "validate_agent_skill_docs"
_FRESHNESS = "validate_skill_page_freshness"
_SCOPE = "docs/skills, docs/agents"
_ROW_LINK = re.compile(r"\]\((?:\./)?([A-Za-z0-9_.-]+)\.md\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_QUOTED = re.compile(r'"([^"\n]+)"|`([^`\n]+)`')
_BACKTICK_PATH = re.compile(r"`([^`\s]*/[^`\s]*)`")


@dataclass(frozen=True, slots=True)
class Finding:
    """One problem with one file, as a repo-relative path and a message."""

    path: str
    message: str


@dataclass(frozen=True, slots=True)
class Report:
    """What a check examined and what it found."""

    examined: int
    findings: list[Finding] = field(default_factory=list)


class ConfigError(Exception):
    """The repository lacks a file the check needs."""


def skill_names(repo_root: Path) -> set[str]:
    """Return every skill name across both skill trees."""
    names: set[str] = set()
    for tree in SKILL_TREES:
        root = repo_root / tree
        if root.is_dir():
            names.update(entry.name for entry in root.iterdir() if (entry / "SKILL.md").is_file())
    return names


def agent_names(repo_root: Path) -> set[str]:
    """Return every agent name from the shared agent templates."""
    root = repo_root / AGENT_TREE
    if not root.is_dir():
        return set()
    return {p.name[: -len(AGENT_SUFFIX)] for p in root.glob(f"*{AGENT_SUFFIX}")}


def _page_names(docs_dir: Path) -> set[str]:
    return {p.stem for p in docs_dir.glob("*.md") if p.name != "README.md"}


def readme_rows(readme_text: str) -> set[str]:
    """Return page names linked from Markdown table rows."""
    rows: set[str] = set()
    for line in readme_text.splitlines():
        if line.lstrip().startswith("|"):
            rows.update(_ROW_LINK.findall(line))
    return rows


def section_problem(page_text: str) -> str | None:
    """Return why the page breaks the sibling section order, or None."""
    matches = (_HEADING.match(line) for line in page_text.splitlines())
    present = [m.group(2) for m in matches if m and m.group(1) == "##" and m.group(2) in SECTIONS]
    missing = [s for s in SECTIONS if s not in present]
    if missing:
        return f"missing section(s): {', '.join(missing)}"
    if present != list(SECTIONS):
        return f"sections out of order: {', '.join(present)}"
    return None


def _kind_findings(repo_root: Path, kind: str, sources: set[str], label: str) -> list[Finding]:
    docs_rel = DOCS[kind]
    docs_dir = repo_root / docs_rel
    readme = docs_dir / "README.md"
    if not readme.is_file():
        raise ConfigError(f"missing {docs_rel}/README.md")
    pages = _page_names(docs_dir)
    rows = readme_rows(readme.read_text(encoding="utf-8"))
    findings = [
        Finding(f"{docs_rel}/{n}.md", f"{label} '{n}' has no page") for n in sorted(sources - pages)
    ]
    findings += [
        Finding(f"{docs_rel}/{n}.md", f"page has no {label} '{n}'") for n in sorted(pages - sources)
    ]
    findings += [
        Finding(f"{docs_rel}/README.md", f"no table row links {n}.md") for n in sorted(pages - rows)
    ]
    findings += [
        Finding(f"{docs_rel}/README.md", f"row links missing page {n}.md")
        for n in sorted(rows - pages)
    ]
    for name in sorted(pages):
        problem = section_problem((docs_dir / f"{name}.md").read_text(encoding="utf-8"))
        if problem:
            findings.append(Finding(f"{docs_rel}/{name}.md", problem))
    return findings


def find_page_findings(repo_root: Path) -> Report:
    """Return missing, orphaned, unlisted, and misshapen pages.

    Raises ConfigError when a docs README is missing.
    """
    skills = skill_names(repo_root)
    agents = agent_names(repo_root)
    findings = _kind_findings(repo_root, "skills", skills, "skill")
    findings += _kind_findings(repo_root, "agents", agents, "agent")
    return Report(examined=len(skills) + len(agents), findings=findings)


# Freshness (advisory)


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def _skill_dir(repo_root: Path, name: str) -> str:
    """Return the tree that holds the real files for ``name``, not a symlink."""
    for tree in SKILL_TREES:
        path = repo_root / tree / name
        if path.is_dir() and not path.is_symlink():
            return f"{tree}/{name}"
    return f"{SKILL_TREES[0]}/{name}"


def _changed_paths(repo_root: Path, base_ref: str) -> set[str] | None:
    diff = _git(repo_root, "diff", "--name-only", base_ref, "--")
    untracked = _git(repo_root, "ls-files", "--others", "--exclude-standard")
    if diff.returncode != 0 or untracked.returncode != 0:
        return None
    return set(diff.stdout.splitlines()) | set(untracked.stdout.splitlines())


def _frontmatter(text: str) -> dict[object, object]:
    typed = parse_frontmatter(text).typed
    return typed if isinstance(typed, dict) else {}


def _triggers(description: object) -> set[str]:
    if not isinstance(description, str):
        return set()
    return {a or b for a, b in _QUOTED.findall(description)}


def exit_code_lines(text: str) -> list[str]:
    """Return the non-blank lines under any ``Exit Codes`` heading."""
    lines: list[str] = []
    level = 0
    for line in text.splitlines():
        match = _HEADING.match(line)
        if match:
            depth = len(match.group(1))
            if "exit code" in match.group(2).lower():
                level = depth
                continue
            if level and depth <= level:
                level = 0
        if level and line.strip():
            lines.append(line.strip())
    return lines


def _script_names(repo_root: Path, base_ref: str | None, skill_rel: str) -> set[str]:
    """Return file names under ``scripts/`` at ``base_ref``, or now when None."""
    prefix = f"{skill_rel}/scripts/"
    if base_ref is None:
        listing = _git(
            repo_root, "ls-files", "--cached", "--others", "--exclude-standard", "--", prefix
        )
        present = {line for line in listing.stdout.splitlines() if (repo_root / line).exists()}
    else:
        listing = _git(repo_root, "ls-tree", "-r", "--name-only", base_ref, "--", prefix)
        present = set(listing.stdout.splitlines())
    return {line[len(prefix) :] for line in present if line.startswith(prefix)}


def fact_changes(old: str, new: str) -> list[str]:
    """Return the fact kinds that differ between two ``SKILL.md`` texts."""
    old_fm, new_fm = _frontmatter(old), _frontmatter(new)
    changes = [key for key in ("name", "argument-hint") if old_fm.get(key) != new_fm.get(key)]
    if _triggers(old_fm.get("description")) != _triggers(new_fm.get("description")):
        changes.append("trigger phrases")
    if exit_code_lines(old) != exit_code_lines(new):
        changes.append("Exit Codes")
    if set(_BACKTICK_PATH.findall(old)) != set(_BACKTICK_PATH.findall(new)):
        changes.append("path references")
    return changes


def _stale_finding(repo_root: Path, base_ref: str, name: str, changed: set[str]) -> Finding | None:
    page_rel = f"{DOCS['skills']}/{name}.md"
    if page_rel in changed:
        return None
    skill_rel = _skill_dir(repo_root, name)
    old = _git(repo_root, "show", f"{base_ref}:{skill_rel}/SKILL.md")
    if old.returncode != 0:
        return None  # New skill: the blocking check owns it.
    new = (repo_root / skill_rel / "SKILL.md").read_text(encoding="utf-8")
    changes = fact_changes(old.stdout, new)
    before = _script_names(repo_root, base_ref, skill_rel)
    after = _script_names(repo_root, None, skill_rel)
    if before != after:
        changes.append(f"scripts/ file names ({', '.join(sorted(before ^ after))})")
    if not changes:
        return None
    return Finding(page_rel, f"skill '{name}' changed {'; '.join(changes)} and its page did not")


def find_stale_pages(repo_root: Path, base_ref: str) -> Report | None:
    """Return skills whose facts changed since ``base_ref`` with no page edit.

    Returns None when git cannot resolve ``base_ref`` or list changes.
    """
    if (
        _git(repo_root, "rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}").returncode
        != 0
    ):
        return None
    changed = _changed_paths(repo_root, base_ref)
    if changed is None:
        return None
    prefixes = {f"{tree}/{name}/": name for name in skill_names(repo_root) for tree in SKILL_TREES}
    touched = sorted(
        {name for path in changed for prefix, name in prefixes.items() if path.startswith(prefix)}
    )
    findings = [f for name in touched if (f := _stale_finding(repo_root, base_ref, name, changed))]
    return Report(examined=len(touched), findings=findings)


# Reporting and entry points

_PAGE_FIX = (
    "add, rename, or remove the page and its README row in this change, and keep "
    "the seven sibling sections in order. See templates/rules/agent-skill-docs.md."
)
_FRESH_FIX = "read each page named above and update the facts that changed (rule MUST 2)."


def _print_findings(header: str, report: Report, fix: str) -> None:
    print(f"[FAIL] {header}:", file=sys.stderr)
    for finding in report.findings:
        print(f"  {finding.path}: {finding.message}", file=sys.stderr)
    print(f"\nFix: {fix}", file=sys.stderr)


def _page_summary(report: Report) -> str:
    count = len(report.findings)
    return f"agent-skill-docs: {count} finding(s) in {report.examined} agent(s) and skill(s)"


def _fresh_summary(report: Report, ref: str) -> str:
    count, examined = len(report.findings), report.examined
    return f"skill-page-freshness: {count} stale page(s) in {examined} changed skill(s) vs {ref}"


def run_pages(repo_root: Path) -> int:
    """Run the blocking check and return an exit code."""
    try:
        report = find_page_findings(repo_root)
    except ConfigError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    print(_page_summary(report))
    if report.findings:
        _print_findings("agent and skill reference pages", report, _PAGE_FIX)
        return 1
    return 0


def run_freshness(repo_root: Path, base_ref: str | None) -> int:
    """Run the advisory check and return an exit code."""
    ref = base_ref or _resolve_default_base_ref(repo_root)
    if ref is None:
        print("[SKIP] skill-page-freshness: no base ref resolved; nothing to diff against")
        return 0
    report = find_stale_pages(repo_root, ref)
    if report is None:
        print(f"[FAIL] git could not read changes against {ref}", file=sys.stderr)
        return 3
    print(_fresh_summary(report, ref))
    if report.findings:
        _print_findings("skill facts changed with no page edit", report, _FRESH_FIX)
        return 1
    return 0


def validate_agent_skill_docs(repo_root: Path) -> CheckOutcome:
    """Blocking pre-PR gate: a typed outcome from the page check."""
    try:
        report = find_page_findings(repo_root)
    except ConfigError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return CheckOutcome.blocked(
            _BLOCKING, reason=REASON_TREE_ABSENT, scope=_SCOPE, detail=str(exc)
        )
    print(_page_summary(report))
    if report.findings:
        _print_findings("agent and skill reference pages", report, _PAGE_FIX)
        return CheckOutcome.failed(
            _BLOCKING,
            reason=REASON_VIOLATIONS_FOUND,
            scope=_SCOPE,
            examined=report.examined,
            findings=len(report.findings),
        )
    return CheckOutcome.passed(
        _BLOCKING, revision="working-tree", scope=_SCOPE, examined=report.examined
    )


def validate_skill_page_freshness(repo_root: Path) -> CheckOutcome:
    """Advisory pre-PR gate. ``pre_pr_policy`` licenses its FAIL and BLOCKED states."""
    ref = _resolve_default_base_ref(repo_root)
    if ref is None:
        return CheckOutcome.skipped(_FRESHNESS, reason=REASON_BASE_REF_UNRESOLVED, scope=_SCOPE)
    report = find_stale_pages(repo_root, ref)
    if report is None:
        return CheckOutcome.blocked(
            _FRESHNESS, reason=REASON_DIFF_FAILED, scope=_SCOPE, detail=f"git failed on {ref}"
        )
    print(_fresh_summary(report, ref))
    if report.findings:
        _print_findings("skill facts changed with no page edit (advisory)", report, _FRESH_FIX)
        return CheckOutcome.failed(
            _FRESHNESS,
            reason=REASON_ADVISORY_FINDINGS,
            revision=ref,
            scope=_SCOPE,
            examined=report.examined,
            findings=len(report.findings),
        )
    return CheckOutcome.passed(_FRESHNESS, revision=ref, scope=_SCOPE, examined=report.examined)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    parser = argparse.ArgumentParser(description="Check agent and skill reference pages.")
    parser.add_argument(
        "repo_root", nargs="?", type=Path, default=Path(__file__).resolve().parents[2]
    )
    parser.add_argument(
        "--freshness", action="store_true", help="run the advisory page freshness check"
    )
    parser.add_argument(
        "--base-ref", help="base ref for --freshness (default: the PR or default branch)"
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    if args.freshness:
        return run_freshness(repo_root, args.base_ref)
    return run_pages(repo_root)


if __name__ == "__main__":
    sys.exit(main())
