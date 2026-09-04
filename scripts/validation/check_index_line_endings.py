#!/usr/bin/env python3
"""Block blobs whose line endings contradict their gitattributes.

A file declared `text ... eol=lf` is supposed to hold LF in its blob. A blob
that holds CRLF anyway is not a cosmetic problem: with `core.autocrlf=input`
the clean filter rewrites CRLF to LF on read, so the checked-out copy never
matches its own blob. Git's stat cache hides that right after checkout, then
reports the file modified the moment anything touches it, and any merge that
touches the path aborts with "Your local changes to the following files would
be overwritten by merge" in a worktree nobody edited.

Two such blobs reached `main` and broke merges in every worktree until
`git add --renormalize` cleaned them. Neither the clean filter nor any local
hook ran on them, because both commits were created through the GraphQL
`createCommitOnBranch` API, which uploads file contents verbatim. That path
stays available and is documented as the workaround when a sandbox cannot run
lefthook, so nothing upstream of the stored blob can be relied on to prevent a
repeat. This check reads the stored blobs, which is the one place the defect is
always visible.

Two scopes are read, because they answer different questions and can disagree:

- `HEAD`, through an isolated index, is what a push transmits. This is the
  scope that matters for the API path and for CI.
- the working index is what the next commit will create. Staging a fix without
  committing it leaves `HEAD` bad, and scanning only the index would call that
  clean.

Exit codes follow ADR-035: 0 clean, 1 violations found, 2 configuration or
tooling error. That last one covers more than an absent git: a git too old for
`GIT_ATTR_SOURCE`, producer output this parser cannot read, a local
`info/attributes` that outranks the pinned attribute source, a `--fix` target
the process is not standing in, and a renormalize that did not take effect.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

# Bootstrap: CI runs this file by path
# (`uv run --frozen python scripts/validation/check_index_line_endings.py`),
# and a bare-script invocation puts only this file's own directory on
# sys.path, so `scripts.validation` does not resolve without help. Mirrors the
# identical block at `scripts/validation/check_skill_portability.py:50-53`,
# verbatim::
#
#     _PROJECT_ROOT = Path(__file__).resolve().parents[2]
#     _VALIDATION_PACKAGE_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
#     if _VALIDATION_PACKAGE_SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
#         sys.path.insert(0, str(_PROJECT_ROOT))
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_PACKAGE_SENTINEL = _PROJECT_ROOT / "scripts" / "validation" / "models.py"
if _VALIDATION_PACKAGE_SENTINEL.is_file() and str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.validation.index_line_endings_git import (  # noqa: E402
    argv_batches,
    attribute_isolation,
    git_environment,
    has_commits,
    refuse_local_attribute_overrides,
    require_attr_source,
    run_git,
    run_git_paths,
    top_level,
    worktree_edits,
)
from scripts.validation.index_line_endings_record import (  # noqa: E402
    Violation,
    display_path,
    is_spellable,
    parse_violations,
    shell_argument,
)

REMEDIATION = "git add --renormalize <path>, then commit the result"


def _ls_files_eol(repo_root: Path, env: dict[str, str] | None = None) -> str:
    """Return NUL-terminated `git ls-files --eol` output.

    `-z` is required, not cosmetic. Without it git applies `core.quotePath` and
    C-quotes any non-ASCII or control character in a path, so a violation would
    be reported under its display spelling and the remediation would name a file
    that does not exist.
    """
    return run_git_paths(repo_root, ["ls-files", "--eol", "-z"], env=env)


def _empty_file(path: Path) -> Path:
    """Create an empty file and return it, for a config value that must find nothing.

    `core.attributesFile` pointed at a path git can read and that says nothing
    is the only spelling that works everywhere. `/dev/null` is not portable and
    an unset value falls back to the host's own file, which is the thing being
    removed from the answer.
    """
    path.write_text("", encoding="utf-8")
    return path


def _head_env(repo_root: Path, scratch: Path) -> dict[str, str]:
    """Environment pointing git at a scratch index and attributes from HEAD.

    `GIT_INDEX_FILE` isolates the blobs, but git still reads `.gitattributes`
    from the working tree, so an uncommitted attribute edit would judge HEAD's
    blobs by rules HEAD does not carry: adding `-text` locally would hide a
    committed violation, and removing it would invent one. `GIT_ATTR_SOURCE`
    pins the attributes to the same tree as the blobs, so the HEAD scope
    answers one question about one commit. `require_attr_source` is what
    makes that pin something the caller can rely on.

    The base is `git_environment()`, not `os.environ.copy()`. Copying the
    ambient environment would carry an exported `GIT_DIR` into the isolated
    scan, so the two variables set below would isolate the index of a
    repository other than `repo_root`.
    """
    env = git_environment()
    env.update(attribute_isolation(_empty_file(scratch / "attributes")))
    env["GIT_INDEX_FILE"] = str(scratch / "head.index")
    env["GIT_ATTR_SOURCE"] = "HEAD"
    run_git(repo_root, ["read-tree", "HEAD"], env=env)
    return env


def empty_worktree(scratch: Path) -> Path:
    """The directory git is pointed at so it finds no `.gitattributes`.

    A subdirectory rather than `scratch` itself, because `scratch` also holds
    the empty file `core.attributesFile` is redirected to, and a work tree the
    gate put a file in is not the empty one the mechanism describes.
    """
    tree = scratch / "tree"
    tree.mkdir(exist_ok=True)
    return tree


def _index_env(repo_root: Path, scratch: Path) -> dict[str, str]:
    """Environment that makes git read attributes from the index, not the disk.

    The index scope asks what the next commit will store, and a commit stores
    the staged `.gitattributes` along with the staged blobs. Git answers from
    the working tree instead: with `*.md text` staged and an unstaged
    `handoff.md -text` edit on disk, `git ls-files --eol` reports `attr/-text`
    for a staged CRLF blob, so the scope that exists to catch the next commit
    calls it clean and the commit lands the contradiction anyway. The inverse
    spelling of the same edit invents a violation committing would not produce.
    Both measured on git 2.51.0.

    Git falls back to the index when the working tree holds no `.gitattributes`,
    so pointing `GIT_WORK_TREE` at an empty directory is enough to ask the
    question the scope means. Two properties follow, and both matter.

    It writes nothing. `.claude/rules/ci-scripts.md` MUST-7 governs a script
    that resolves a root and then writes to it, and read-only mode runs before
    any worktree-identity check, so the index scope must not write at all.
    Measured: the object count under the git directory is unchanged across
    repeated scans.

    It is also stable, which the obvious alternative is not. `git write-tree`
    names the tree the index would commit and looks like the symmetric partner
    to `_head_env`, but it records a cache-tree in the index as a side effect.
    Measured on git 2.51.0: with the tree written into a scratch object
    directory that is then discarded, the next `write-tree` returns the same id
    out of that cache-tree and writes nothing, `GIT_ATTR_SOURCE` cannot resolve
    it, and git reports `attr/text` with no `eol=lf`. Every blob then looks
    exempt and the scan reports zero violations. A second run answering
    differently from the first, in the safe direction, is the exact silent pass
    this gate exists to prevent.

    `GIT_DIR` is asked for rather than assembled: `repo_root / ".git"` is a
    file, not a directory, in a linked worktree.

    The caller must also run git from `empty_worktree(scratch)`. Measured: with
    `GIT_WORK_TREE` set but the current directory still inside the real
    checkout, git reads that checkout's `.gitattributes` and the isolation does
    nothing.
    """
    env = git_environment()
    env.update(attribute_isolation(_empty_file(scratch / "attributes")))
    env["GIT_DIR"] = run_git(repo_root, ["rev-parse", "--absolute-git-dir"]).stdout.strip()
    env["GIT_WORK_TREE"] = str(empty_worktree(scratch))
    return env


def check_repository(repo_root: Path) -> tuple[list[Violation], int]:
    """Return violations across HEAD and the working index, plus files examined.

    A path bad in both scopes is reported once, under HEAD, because that is the
    scope a push transmits and one remediation fixes both.

    The root is resolved to git's top level here rather than in the callers,
    because every caller needs it and the failure is silent: `git ls-files`
    lists the subtree under its working directory, so a HEAD scan rooted at a
    subdirectory reports that subtree clean and says nothing about the rest.
    The index scope is already immune, since it points `GIT_DIR` at the
    repository and runs git from an empty directory outside it.
    """
    repo_root = top_level(repo_root)
    violations: list[Violation] = []
    examined = 0
    require_attr_source(repo_root)
    refuse_local_attribute_overrides(repo_root)

    if has_commits(repo_root):
        # NamedTemporaryFile would hand git an existing empty file, which
        # read-tree rejects as a malformed index, so reserve a name instead.
        with tempfile.TemporaryDirectory() as scratch:
            env = _head_env(repo_root, Path(scratch))
            violations, examined = parse_violations(
                _ls_files_eol(repo_root, env=env), scope="HEAD"
            )

    seen = {violation.path for violation in violations}
    staged, staged_examined = index_violations(repo_root)
    violations.extend(v for v in staged if v.path not in seen)
    return violations, max(examined, staged_examined)


def index_violations(repo_root: Path) -> tuple[list[Violation], int]:
    """The index scope on its own, judged by the attributes the index stores.

    Separate from `check_repository` because `renormalize` needs this scope
    alone. `check_repository` reports a path bad in both scopes once, under
    HEAD, so its output cannot say whether the index half was fixed.
    """
    # The empty directory is the whole mechanism, and git has to be run from
    # inside it: `GIT_WORK_TREE` alone does not stop git reading a
    # `.gitattributes` it can still see from the current directory.
    with tempfile.TemporaryDirectory() as scratch:
        index_env = _index_env(repo_root, Path(scratch))
        return parse_violations(
            _ls_files_eol(empty_worktree(Path(scratch)), env=index_env), scope="index"
        )


def _report(
    violations: list[Violation], examined: int, remediable: set[str], repo_root: Path
) -> None:
    """Print each violation, and a command only for what `git add` can act on.

    `remediable` is the set of paths the index scope still reports. A path
    outside it is wrong in HEAD only, and `git add --renormalize` cannot touch
    it: the index already holds what the next commit will store, which for a
    path staged for deletion is nothing at all. Advertising the command for
    those paths prints one that fails.
    """
    for violation in violations:
        print(f"  {violation.render()}")
    if violations:
        print(f"index-line-endings: {len(violations)} blob(s) contradict gitattributes")
        # Both lines describe renormalizing, which is a no-op on a path the
        # index no longer holds wrong. `_print_paste_command` tells the
        # operator to commit instead, and two contradictory instructions are
        # worse than the one that applies.
        if remediable:
            print(f"  Fix: {REMEDIATION}")
            print("  Or re-run this check with --fix, which calls git directly.")
        _print_paste_command(violations, remediable, repo_root)
    print(f"index-line-endings: {len(violations)} violation(s) in {examined} tracked files")


def _print_paste_command(
    violations: list[Violation], remediable: set[str], repo_root: Path
) -> None:
    """Print a copy-paste renormalize command that works for every path.

    `shell_argument` picks the spelling per path. A path that survives
    `display_path` unchanged gets `shlex.quote`, which POSIX `sh` understands.
    One that does not, because it carries bytes unsafe to print verbatim (a
    control character, a bidi override, an unpaired surrogate), gets bash and
    zsh's `$'...'` form instead: not because POSIX `sh` cannot express those
    bytes in a plain single-quoted string, but because `shlex.quote` would
    quote the escaped display spelling, and a command built from the display
    spelling would name a file the repository does not hold, which is why an
    earlier revision withheld the command entirely rather than print one that
    could not remediate anything. Do not restore that: `display_path` is for
    reading, `shell_argument` is for running, and the two are different
    renderings of the same path.

    The same test applies to the repository root printed after `-C`: a root
    whose path is unsafe to display verbatim needs the same `$'...'` form,
    independent of whether any target path does. Checking only the targets
    would print a command that silently uses that form for the root while
    telling the operator no path needed it.

    Only the paths in `remediable` get a command. The rest are wrong in HEAD
    alone, where `git add --renormalize` fails with `pathspec ... did not match
    any files` if the index no longer holds them, so they get a line telling
    the operator to commit instead.

    The command names the repository with `-C` and sets `--literal-pathspecs`.
    Without the first it fails from a subdirectory, because these paths are
    relative to the root. Without the second git reads the trailing arguments
    as pathspecs, so a tracked name such as `*.md` globs: measured on git
    2.51.0, `git add --renormalize -- '*.md'` against a repository holding a
    file literally named `*.md` also staged an unrelated `other.md` that had
    an uncommitted edit. `run_git` sets the same variable for the executed
    path.

    The quoting is load-bearing either way. A tracked path may carry shell
    syntax or a leading dash, and an unquoted join would print a command that
    runs attacker-controlled text if a maintainer pasted it (CWE-78). `--`
    stops a leading-dash path from parsing as a git option.

    The note about bash and zsh is printed only when a path needs that form,
    and it names `--fix` as the portable route: `--fix` passes an argument
    list to git and never builds a string, so it needs no shell at all.
    """
    targets = [v for v in violations if v.path in remediable]
    committed_only = [v for v in violations if v.path not in remediable]
    if targets:
        paths = " ".join(shell_argument(v.path) for v in targets)
        # `-C` because these paths are relative to the repository root and the
        # operator may be anywhere; `--literal-pathspecs` because a tracked
        # name such as `*.md` is a path to this gate and a glob to git.
        root_str = str(repo_root)
        root = shell_argument(root_str)
        print(f"  git -C {root} --literal-pathspecs add --renormalize -- {paths}")
        unspellable_targets = [v for v in targets if not is_spellable(v.path)]
        root_needs_escaping = not is_spellable(root_str)
        if unspellable_targets or root_needs_escaping:
            described = []
            if root_needs_escaping:
                described.append("the repository root")
            if unspellable_targets:
                described.append(f"{len(unspellable_targets)} of {len(targets)} path(s)")
            print(
                f"  {' and '.join(described)} carry bytes unsafe to display verbatim, "
                "so the command above renders them with bash and zsh's $'...' form "
                "instead of plain quoting. --fix passes the real bytes as argv and "
                "needs no shell at all."
            )
    if committed_only:
        print(
            f"  {len(committed_only)} path(s) are wrong in HEAD only. The index "
            "already holds what the next commit will store, so commit the staged "
            "result rather than renormalizing again."
        )


def refuses_write_from_outside(repo_root: Path) -> bool:
    """True when the process is not standing inside the tree git will write to.

    ``.claude/rules/ci-scripts.md`` MUST-7: a script that resolves the
    repository root and then writes to it MUST confirm the current directory
    is inside the resolved root before the first write, and the rule names the
    comparison verbatim as ``Path.cwd().resolve().is_relative_to(top_level)``.
    ``--fix`` stages into whatever tree git decides on, so without this a
    mistyped root renormalizes a checkout nobody was looking at and leaves
    staged changes there for someone else to find.

    The comparison is against ``git rev-parse --show-toplevel``, not against
    ``--repo-root``. Those are two different claims and they can disagree: a
    repository-local ``core.worktree`` value redirects git while the typed root
    still looks right. Measured on git 2.51.0, with ``core.worktree`` set to a
    sibling directory, ``git rev-parse --show-toplevel`` run from inside the
    checkout returned the sibling, so a guard comparing the current directory
    to ``--repo-root`` passes while git writes somewhere else entirely. The
    same rule warns about ``GIT_WORK_TREE``; ``git_environment`` already
    strips that one, which is why the probe below is run through it.
    """
    cwd = Path.cwd().resolve()
    top_level = Path(run_git(repo_root, ["rev-parse", "--show-toplevel"]).stdout.strip()).resolve()
    if cwd.is_relative_to(top_level):
        return False
    print(
        f"Refusing to renormalize {top_level} while running from {cwd}. "
        "--fix stages into the tree git resolves, and a tree that is not an "
        "ancestor of the current directory means the two disagree about "
        "which checkout is being changed (.claude/rules/ci-scripts.md MUST-7). "
        f"Requested root: {repo_root}.",
        file=sys.stderr,
    )
    return True


def renormalize(repo_root: Path) -> None:
    """Renormalize the paths the index is still wrong about, then check it worked.

    The targets come from the index scope, not from the reported violations.
    Those include HEAD-only paths, and a path can be bad in HEAD while absent
    from the index because it was staged for deletion or renamed. Measured on
    git 2.51.0: `git add --renormalize -- h.md` on such a path exits 128 with
    `fatal: pathspec 'h.md' did not match any files`, so passing the reported
    set to git makes both advertised remediations fail on a repository whose
    staged removal would have cleared the gate on its own. A HEAD-only path
    needs a commit, not an add, so there is nothing here to hand git.

    Paths reach git as argv entries, so a filename carrying shell syntax is
    inert. `--` stops a leading-dash filename from parsing as an option.

    The working-tree check ahead of the add is not belt and braces either; see
    `worktree_edits` for what `git add --renormalize` would otherwise stage.

    The re-scan is not belt and braces. `git add --renormalize` applies the
    clean filter according to the *working tree's* `.gitattributes`, while the
    index scope judged the blob by the *staged* one, and the two can disagree.
    Measured on git 2.51.0 with `*.md text` staged and an unstaged
    `handoff.md -text` on disk: the gate reports the staged CRLF blob, `git add
    --renormalize` exits 0, and the index blob is still `i/crlf`. Without this
    check the run would print "renormalized 1 path(s); commit the result" over
    a blob it did not change, which is worse than not offering `--fix` at all:
    the operator commits and pushes believing it is fixed.
    """
    staged, _ = index_violations(repo_root)
    paths = sorted({violation.path for violation in staged})
    if not paths:
        return
    edited = worktree_edits(repo_root, paths)
    if edited:
        rendered = ", ".join(display_path(path) for path in sorted(edited))
        raise RuntimeError(
            f"{len(edited)} of {len(paths)} path(s) have uncommitted working-tree "
            f"changes beyond line endings: {rendered}. `git add --renormalize` "
            "stages the working copy, so running it here would stage those "
            "changes too, or fail outright on a file deleted locally. Commit, "
            "stash or revert them and re-run."
        )
    for batch in argv_batches(paths):
        run_git(repo_root, ["add", "--renormalize", "--", *batch])
    remaining, _ = index_violations(repo_root)
    unfixed = sorted(set(paths) & {violation.path for violation in remaining})
    if unfixed:
        rendered = ", ".join(display_path(path) for path in unfixed)
        raise RuntimeError(
            f"git add --renormalize left {len(unfixed)} of {len(paths)} path(s) "
            f"still contradicting their staged attributes: {rendered}. "
            "`git add` applies the clean filter by the working tree's "
            ".gitattributes and this check judges the blob by the staged one, "
            "so an uncommitted attribute edit makes the remediation a no-op. "
            "Stage or revert that edit and re-run."
        )
    print(f"index-line-endings: renormalized {len(paths)} path(s); commit the result")


def validate_index_line_endings(repo_root: Path) -> bool:
    """Blocking pre-PR gate. Returns False when any blob contradicts its attrs.

    """
    try:
        violations, examined = check_repository(repo_root)
        resolved_root = top_level(repo_root)
        staged, _ = index_violations(resolved_root)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[FAIL] index line endings: {exc}", file=sys.stderr)
        return False
    _report(violations, examined, {v.path for v in staged}, resolved_root)
    return not violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to inspect (default: current directory)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Renormalize the violating paths via git argv instead of printing a command",
    )
    args = parser.parse_args(argv)

    requested = Path(args.repo_root).resolve()
    # Separate from validate_index_line_endings so a broken git invocation
    # exits 2 (config error) instead of 1 (violations found). Collapsing the
    # two would report "line endings are wrong" when git never ran.
    try:
        # The write guard runs against the directory the operator named, before
        # anything resolves it. Resolving first would hand the guard the tree a
        # redirecting `core.worktree` chose, which is the disagreement it exists
        # to report rather than to adopt.
        if args.fix and refuses_write_from_outside(requested):
            return 2
        # `git ls-files` lists the subtree under its working directory, so the
        # scan root has to be the whole tree, not whatever directory was typed.
        repo_root = top_level(requested)
        violations, examined = check_repository(repo_root)
        staged, _ = index_violations(repo_root)
        _report(violations, examined, {v.path for v in staged}, repo_root)
        if args.fix:
            renormalize(repo_root)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"[FAIL] index line endings: {exc}", file=sys.stderr)
        return 2

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
