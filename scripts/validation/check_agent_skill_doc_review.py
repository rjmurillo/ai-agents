#!/usr/bin/env python3
"""Gate: a changed skill or agent needs a page edit or a review trailer.

Rule: ``templates/rules/agent-skill-docs.md`` MUST 2. A script cannot tell
whether a page's prose is still true, so this gate asks for proof that a
person or agent read it. PR #7572 moved PR creation from ``ship`` to
``push-pr`` and left ``docs/skills/ship.md`` describing the old flow. The
advisory fact check in ``check_agent_skill_docs.py`` did not flag it.

A source counts as changed when its text differs from the fork point,
ignoring whitespace and blank lines. A source file added or removed for a
skill or agent whose page already exists counts as changed too. Sources:

- ``src/claude/skills/<name>/SKILL.md`` or ``.claude/skills/<name>/SKILL.md``
- ``templates/skills/<name>.SKILL.md.tmpl``
- ``templates/agents/<name>.shared.md`` and its host templates
- ``src/claude/agents/<name>.md`` and ``src/copilot-cli/agents/<name>.agent.md``,
  the rendered agents, so an edit to a shared or host-only agent partial
  counts for every agent it renders into

A changed source passes when every one of its changes since the fork point
has a review that descends from it. A review is either:

- its page (``docs/skills/<name>.md`` or ``docs/agents/<name>.md``) changed
  since the fork point beyond whitespace, in the same or a later commit than
  that change, or in the working tree, or
- a commit in ``<base-ref>..HEAD`` at or after that change carries a
  ``Docs-Reviewed:`` trailer that names it. Names are separated by commas
  or spaces. Use ``skills/<name>`` or ``agents/<name>`` when a skill
  and an agent share the name. A source with uncommitted changes passes only
  on an uncommitted page edit; commit it first to clear it with a trailer.

Only commits that change a file beyond whitespace count as a change or as a
page edit. Merge commits are skipped for both, so sibling commits merged into
the branch each need a review. Trailers are read from every commit.

A whole skill or agent that is new or removed since the fork point is
skipped: the blocking page check in ``check_agent_skill_docs.py`` owns new
and removed pages.

CLI::

    uv run python scripts/validation/check_agent_skill_doc_review.py [<repo-root>] [--base-ref REF]

Exit codes (ADR-035):
    0 - Success (every changed source is reviewed)
    1 - Logic error (a changed source has no page edit and no trailer)
    2 - Config error (invalid root, option-shaped base ref, no base ref, or no git)
    3 - External error (git failed, including an unknown base ref, or timed out)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_DIR = Path(__file__).resolve().parent
for _path in (_PROJECT_ROOT, _SCRIPT_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from checks_common import _resolve_default_base_ref  # noqa: E402

from scripts.validation.check_agent_skill_docs import (  # noqa: E402
    AGENT_SUFFIX,
    AGENT_TREE,
    DOCS,
    SKILL_TREES,
    Finding,
    GitReadError,
    _changed_paths,
    _git,
)

TRAILER = "Docs-Reviewed"
_SOURCE = re.compile(
    r"^(?:(?:src/claude|\.claude)/skills/(?P<skill>[^/]+)/SKILL\.md"
    r"|templates/skills/(?P<template>[^/]+)\.SKILL\.md\.tmpl"
    r"|templates/agents/(?P<agent>[^/]+)\.(?:shared\.md|(?:claude|copilot)\.md\.tmpl)"
    r"|src/claude/agents/(?P<rendered>[^/]+)\.md"
    r"|src/copilot-cli/agents/(?P<copilot>[^/]+)\.agent\.md)$"
)
_NAME_SPLIT = re.compile(r"[,\s]+")


@dataclass(frozen=True, slots=True)
class Review:
    """What the gate examined, what it found, and the trailer names that clear it."""

    examined: int
    base: str = ""
    findings: list[Finding] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)


def changed_sources(changed: set[str]) -> dict[str, tuple[str, str]]:
    """Map each changed source path to its (docs kind, name)."""
    sources: dict[str, tuple[str, str]] = {}
    for path in changed:
        match = _SOURCE.match(path)
        if match is None:
            continue
        skill = match.group("skill") or match.group("template")
        if skill:
            sources[path] = ("skills", skill)
        else:
            agent = match.group("agent") or match.group("rendered") or match.group("copilot")
            sources[path] = ("agents", agent)
    return sources


def _failed(result: subprocess.CompletedProcess[str], what: str) -> GitReadError:
    detail = (result.stderr or "").strip().splitlines()
    return GitReadError(f"{what}: {detail[-1]}" if detail else what)


def _existed_at(repo_root: Path, fork: str, path: str) -> bool:
    result = _git(repo_root, "ls-tree", "--name-only", fork, "--", path)
    if result.returncode != 0:
        raise _failed(result, f"git ls-tree failed for {path} at {fork}")
    return path in result.stdout.splitlines()


def _substantive(repo_root: Path, fork: str, path: str) -> bool:
    """Return True when ``path`` differs from ``fork`` beyond whitespace.

    A file added or removed since ``fork`` always differs.
    """
    if (repo_root / path).is_file() != _existed_at(repo_root, fork, path):
        return True
    result = _git(repo_root, "diff", "--quiet", "-w", "--ignore-blank-lines", fork, "--", path)
    if result.returncode not in (0, 1):
        raise _failed(result, f"git diff failed for {path} against {fork}")
    return result.returncode == 1


def reviews(repo_root: Path, base_ref: str) -> list[tuple[str, set[str]]]:
    """Return (commit, names) for each commit in ``base_ref..HEAD`` with a trailer."""
    log = _git(
        repo_root,
        "log",
        f"--format=%H%x00%(trailers:key={TRAILER},valueonly)%x01",
        "--end-of-options",
        f"{base_ref}..HEAD",
    )
    if log.returncode != 0:
        raise _failed(log, f"git log failed for {base_ref}..HEAD")
    found = []
    for record in log.stdout.split("\x01"):
        sha, _, value = record.strip().partition("\x00")
        names = {name for name in _NAME_SPLIT.split(value) if name}
        if sha and names:
            found.append((sha, names))
    return found


_WORKTREE = "working tree"


def _quiet_diff(repo_root: Path, *revs: str, path: str) -> bool:
    """Return True when ``path`` differs between ``revs`` (or the tree) beyond whitespace."""
    result = _git(repo_root, "diff", "--quiet", "-w", "--ignore-blank-lines", *revs, "--", path)
    if result.returncode not in (0, 1):
        raise _failed(result, f"git diff failed for {path}")
    return result.returncode == 1


def _changes(repo_root: Path, base_ref: str, path: str) -> list[str]:
    """Return every branch commit that changed ``path`` beyond whitespace.

    Returns ``[_WORKTREE]`` when the working tree changes it beyond whitespace.
    Every such commit is returned, so sibling commits merged into the branch
    each need their own review. Merge commits are skipped, so a GitHub merge
    checkout where the base also changed ``path`` resolves to branch commits.
    """
    dirty = _git(repo_root, "status", "--porcelain", "--", path)
    if dirty.returncode != 0:
        raise _failed(dirty, f"git status failed for {path}")
    if dirty.stdout.strip():
        untracked = dirty.stdout.startswith("??")
        if untracked or _quiet_diff(repo_root, "HEAD", path=path):
            return [_WORKTREE]
    log = _git(
        repo_root,
        "log",
        "--no-merges",
        "--format=%H",
        "--end-of-options",
        f"{base_ref}..HEAD",
        "--",
        path,
    )
    if log.returncode != 0:
        raise _failed(log, f"git log failed for {path}")
    return [sha for sha in log.stdout.split() if _quiet_diff(repo_root, f"{sha}^", sha, path=path)]


def _not_older(repo_root: Path, change: str | None, review: str | None) -> bool:
    """Return True when ``review`` is at or after ``change`` in history."""
    if review == _WORKTREE or change is None:
        return review is not None
    if review is None or change == _WORKTREE:
        return False
    result = _git(repo_root, "merge-base", "--is-ancestor", change, review)
    if result.returncode not in (0, 1):
        raise _failed(result, f"git merge-base --is-ancestor {change} {review} failed")
    return result.returncode == 0


def _source_exists(repo_root: Path, kind: str, name: str) -> bool:
    if kind == "agents":
        return (repo_root / AGENT_TREE / f"{name}{AGENT_SUFFIX}").is_file()
    return any((repo_root / tree / name / "SKILL.md").is_file() for tree in SKILL_TREES)


def _review_token(repo_root: Path, kind: str, name: str) -> str:
    """Return the trailer name for a source, qualified when the name is shared."""
    other = "agents" if kind == "skills" else "skills"
    return f"{kind}/{name}" if (repo_root / DOCS[other] / f"{name}.md").is_file() else name


def find_unreviewed(repo_root: Path, base_ref: str) -> Review:
    """Return changed skills and agents with no page edit and no trailer.

    Raises GitReadError when git cannot find the fork point or read the history.
    """
    fork = _git(repo_root, "merge-base", "HEAD", "--end-of-options", base_ref)
    if fork.returncode != 0 or not fork.stdout.strip():
        raise _failed(fork, f"git merge-base HEAD {base_ref} failed")
    base = fork.stdout.strip()
    changed = _changed_paths(repo_root, base)
    if changed is None:
        raise GitReadError(f"git could not list changes against {base}")
    candidates: dict[tuple[str, str], list[str]] = {}
    for path, (kind, name) in sorted(changed_sources(changed).items()):
        page = f"{DOCS[kind]}/{name}.md"
        if (
            _source_exists(repo_root, kind, name)
            and _existed_at(repo_root, base, page)
            and _substantive(repo_root, base, path)
        ):
            candidates.setdefault((kind, name), []).append(path)
    trailers = reviews(repo_root, base_ref) if candidates else []
    findings: list[Finding] = []
    tokens: list[str] = []
    for (kind, name), paths in sorted(candidates.items()):
        page = f"{DOCS[kind]}/{name}.md"
        token = _review_token(repo_root, kind, name)
        changes: list[str | None] = [
            c for path in paths for c in _changes(repo_root, base_ref, path)
        ]
        named = [sha for sha, names in trailers if token in names or f"{kind}/{name}" in names]
        reviews_for: list[str | None] = list(named)
        if page in changed and _substantive(repo_root, base, page):
            reviews_for += _changes(repo_root, base_ref, page)
        if all(
            any(_not_older(repo_root, change, review) for review in reviews_for)
            for change in changes or [None]
        ):
            continue
        findings.append(
            Finding(
                page,
                f"{', '.join(paths)} changed with no page edit or trailer at or after it; "
                f"edit this page or name '{token}'",
            )
        )
        tokens.append(token)
    return Review(examined=len(candidates), base=base, findings=findings, tokens=sorted(tokens))


def print_report(review: Review, base_ref: str) -> None:
    """Print the summary, and for findings the exact fix."""
    count, examined = len(review.findings), review.examined
    print(
        f"agent-skill-doc-review: {count} unreviewed of {examined} changed "
        f"vs {base_ref} (merge base {review.base[:12]})"
    )
    if not review.findings:
        return
    print(
        "[FAIL] skill or agent changed with no page edit or review trailer at or after the change."
        "\nRead each page below. If a fact on it changed (what it does, triggers,"
        "\narguments, scripts, exit codes, outputs, when to use it), edit the page."
        "\nOnly if every page is still true, put this line in the final trailer block"
        "\nof a commit made after your last change to the source, beside Co-Authored-By:"
        f"\n\n  {TRAILER}: {', '.join(review.tokens)}"
        "\n\nCommit the source change first: a trailer never clears an uncommitted change."
        "\nThen amend the last commit if it is unpushed; otherwise add a new commit"
        " (git commit --allow-empty). Never force-push a shared branch."
        "\nRule: templates/rules/agent-skill-docs.md MUST 2.\n",
        file=sys.stderr,
    )
    for finding in review.findings:
        print(f"  {finding.path}: {finding.message}", file=sys.stderr)


def run(repo_root: Path, base_ref: str | None) -> int:
    """Run the gate and return an ADR-035 exit code."""
    ref = base_ref or _resolve_default_base_ref(repo_root)
    if ref is None:
        print(
            "[FAIL] agent-skill-doc-review: no base ref resolved; pass --base-ref", file=sys.stderr
        )
        return 2
    if ref.startswith("-"):
        print(f"[FAIL] agent-skill-doc-review: invalid base ref {ref!r}", file=sys.stderr)
        return 2
    try:
        review = find_unreviewed(repo_root, ref)
    except FileNotFoundError as exc:
        print(f"[FAIL] agent-skill-doc-review: git not found: {exc}", file=sys.stderr)
        return 2
    except (GitReadError, subprocess.SubprocessError, OSError) as exc:
        print(f"[FAIL] agent-skill-doc-review: {exc}", file=sys.stderr)
        return 3
    print_report(review, ref)
    return 1 if review.findings else 0


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
