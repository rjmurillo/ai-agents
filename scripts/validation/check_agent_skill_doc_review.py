#!/usr/bin/env python3
"""Gate: a changed skill or agent needs a page edit or a review trailer.

Rule: ``templates/rules/agent-skill-docs.md`` MUST 2. A script cannot tell
whether a page's prose is still true, so this gate asks for proof that a
person or agent read it. PR #7572 moved PR creation from ``ship`` to
``push-pr`` and left ``docs/skills/ship.md`` describing the old flow. The
advisory fact check in ``check_agent_skill_docs.py`` did not flag it.

A source counts as changed when its text differs from the fork point,
ignoring whitespace and blank lines. Source additions and removals for an
existing page count too. Sources:

- ``src/claude/skills/<name>/SKILL.md`` or ``.claude/skills/<name>/SKILL.md``
- ``templates/skills/<name>.SKILL.md.tmpl``
- ``templates/agents/<name>.shared.md`` and its host templates

A changed source passes when either holds:

- its page (``docs/skills/<name>.md`` or ``docs/agents/<name>.md``) also
  changed since the fork point, or
- a commit in ``<base-ref>..HEAD`` carries a ``Docs-Reviewed:`` trailer that
  names it. Names are separated by commas or spaces. Use ``skills/<name>``
  or ``agents/<name>`` to distinguish names shared by both kinds.

A source new since the fork point is skipped: the blocking page check in
``check_agent_skill_docs.py`` owns new and removed pages.

CLI::

    uv run python scripts/validation/check_agent_skill_doc_review.py [<repo-root>] [--base-ref REF]

Exit codes (ADR-035):
    0 - Success (every changed source is reviewed)
    1 - Logic error (a changed source has no page edit and no trailer)
    2 - Config error (invalid root, or no base ref resolved)
    3 - External error (git could not read the base ref or the history)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_DIR = Path(__file__).resolve().parent
for _path in (_PROJECT_ROOT, _SCRIPT_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from checks_common import _resolve_default_base_ref  # noqa: E402

from scripts.validation.check_agent_skill_docs import (  # noqa: E402
    DOCS,
    SKILL_TREES,
    Finding,
    Report,
    _changed_paths,
    _git,
)

TRAILER = "Docs-Reviewed"
_SOURCE = re.compile(
    r"^(?:(?:src/claude|\.claude)/skills/(?P<skill>[^/]+)/SKILL\.md"
    r"|templates/skills/(?P<template>[^/]+)\.SKILL\.md\.tmpl"
    r"|templates/agents/(?P<agent>[^/]+)\.(?:shared\.md|(?:claude|copilot)\.md\.tmpl))$"
)
_NAME_SPLIT = re.compile(r"[,\s]+")


class GitError(Exception):
    """git could not read the history or a diff the gate needs."""


def changed_sources(changed: set[str]) -> dict[str, tuple[str, str]]:
    """Map each changed source path to its (docs kind, name)."""
    sources: dict[str, tuple[str, str]] = {}
    for path in changed:
        match = _SOURCE.match(path)
        if match is None:
            continue
        if skill := match.group("skill") or match.group("template"):
            sources[path] = ("skills", skill)
        else:
            sources[path] = ("agents", match.group("agent"))
    return sources


def _existed_at(repo_root: Path, fork: str, path: str) -> bool:
    result = _git(repo_root, "ls-tree", "--name-only", fork, "--", path)
    if result.returncode != 0:
        raise GitError(f"git ls-tree failed for {path} at {fork}")
    return path in result.stdout.splitlines()


def _substantive(repo_root: Path, fork: str, path: str) -> bool:
    """Return True when ``path`` differs from ``fork`` beyond whitespace."""
    if (repo_root / path).is_file() and not _existed_at(repo_root, fork, path):
        return True
    result = _git(repo_root, "diff", "--quiet", "-w", "--ignore-blank-lines", fork, "--", path)
    if result.returncode not in (0, 1):
        raise GitError(f"git diff failed for {path} against {fork}")
    return result.returncode == 1


def reviewed_names(repo_root: Path, base_ref: str) -> set[str]:
    """Return every name a ``Docs-Reviewed:`` trailer in ``base_ref..HEAD`` lists."""
    log = _git(
        repo_root,
        "log",
        f"--format=%(trailers:key={TRAILER},valueonly)",
        f"{base_ref}..HEAD",
    )
    if log.returncode != 0:
        raise GitError(f"git log failed for {base_ref}..HEAD")
    return {name for name in _NAME_SPLIT.split(log.stdout) if name}


def find_unreviewed(repo_root: Path, base_ref: str) -> Report:
    """Return changed skills and agents with no page edit and no trailer.

    Raises GitError when git cannot find the fork point or read the history.
    """
    fork = _git(repo_root, "merge-base", "HEAD", base_ref)
    if fork.returncode != 0 or not fork.stdout.strip():
        raise GitError(f"git merge-base HEAD {base_ref} failed")
    base = fork.stdout.strip()
    changed = _changed_paths(repo_root, base)
    if changed is None:
        raise GitError(f"git could not list changes against {base}")
    candidates: dict[tuple[str, str], list[str]] = {}
    for path, (kind, name) in sorted(changed_sources(changed).items()):
        page = f"{DOCS[kind]}/{name}.md"
        if (
            _source_exists(repo_root, kind, name)
            and _existed_at(repo_root, base, page)
            and _substantive(repo_root, base, path)
        ):
            candidates.setdefault((kind, name), []).append(path)
    reviewed = reviewed_names(repo_root, base_ref) if candidates else set()
    findings = []
    for (kind, name), paths in sorted(candidates.items()):
        page = f"{DOCS[kind]}/{name}.md"
        token = _review_token(repo_root, kind, name)
        if page in changed or token in reviewed or f"{kind}/{name}" in reviewed:
            continue
        findings.append(
            Finding(page, f"{', '.join(paths)} changed; edit this page or name '{token}'")
        )
    return Report(examined=len(candidates), findings=findings)


def _source_exists(repo_root: Path, kind: str, name: str) -> bool:
    if kind == "agents":
        return (repo_root / "templates" / "agents" / f"{name}.shared.md").is_file()
    return any((repo_root / tree / name / "SKILL.md").is_file() for tree in SKILL_TREES)


def _review_token(repo_root: Path, kind: str, name: str) -> str:
    other = "agents" if kind == "skills" else "skills"
    return f"{kind}/{name}" if (repo_root / DOCS[other] / f"{name}.md").is_file() else name


def print_report(repo_root: Path, report: Report, base_ref: str) -> None:
    """Print the summary, and for findings the exact fix."""
    count, examined = len(report.findings), report.examined
    print(f"agent-skill-doc-review: {count} unreviewed of {examined} changed vs {base_ref}")
    if not report.findings:
        return
    print("[FAIL] skill or agent changed with no page edit and no review trailer:", file=sys.stderr)
    for finding in report.findings:
        print(f"  {finding.path}: {finding.message}", file=sys.stderr)
    tokens = sorted(
        _review_token(repo_root, Path(f.path).parent.name, Path(f.path).stem)
        for f in report.findings
    )
    print(
        "\nFix: read each page above. If a fact on it changed (what it does, triggers,"
        "\narguments, scripts, exit codes, outputs, when to use it), edit the page."
        "\nIf the page is still true, add this trailer to a commit on this branch:"
        f"\n\n  {TRAILER}: {', '.join(tokens)}"
        "\n\nRule: templates/rules/agent-skill-docs.md MUST 2.",
        file=sys.stderr,
    )


def run(repo_root: Path, base_ref: str | None) -> int:
    """Run the gate and return an ADR-035 exit code."""
    ref = base_ref or _resolve_default_base_ref(repo_root)
    if ref is None:
        print(
            "[FAIL] agent-skill-doc-review: no base ref resolved; pass --base-ref", file=sys.stderr
        )
        return 2
    try:
        report = find_unreviewed(repo_root, ref)
    except GitError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 3
    print_report(repo_root, report, ref)
    return 1 if report.findings else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns an ADR-035 exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo_root", nargs="?", type=Path, default=_PROJECT_ROOT)
    parser.add_argument("--base-ref", help="base ref (default: the PR or default branch)")
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    if not repo_root.is_dir():
        print(f"[FAIL] Invalid repository root: {repo_root}", file=sys.stderr)
        return 2
    return run(repo_root, args.base_ref)


if __name__ == "__main__":
    sys.exit(main())
