"""The committed half of a portability baseline, read straight out of git.

Split from `portability_floor` because locating a blob in history and deciding
what a baseline means fail for unrelated reasons. Half the branches here are
git plumbing and half of the other module is JSON, and one function holding
both is the shape that hides a missing case in either half.

Every function keeps one discipline: absence is only ever concluded from a
command that answered. A guard that reads its floor through a subprocess is
disarmed by anything that makes the subprocess fail, so "git errored" and "the
file is new" must never reach the caller as the same value. The dangerous
answer is not an error but a shrug, and several git commands shrug on input
that is not what it looks like.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

TreeEntry = tuple[str, str, str, str]
"""One `ls-tree` record as `(mode, kind, object id, name)`."""

REGULAR_FILE_MODES = ("100644", "100755")
"""The modes a baseline may be committed under.

Git stores a symlink as a blob whose content is the target path, so a symlink
passes a `kind == "blob"` test while the bytes behind it are a pathname rather
than the JSON the checker wrote. Reading the floor from one file and the
replacement from another is the whole failure this module exists to prevent.
"""

GIT_TIMEOUT_SECONDS = 30.0
GIT_TIMEOUT_RETURN_CODE = 124


def git_timeout_problem(
    proc: subprocess.CompletedProcess[bytes] | None, action: str
) -> str | None:
    """Describe a timed-out Git probe without masking other failures."""
    if proc is None or proc.returncode != GIT_TIMEOUT_RETURN_CODE:
        return None
    detail = proc.stderr.decode(errors="replace")
    return f"git timed out while {action} ({detail})"


def run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    """Run one git command with every local override stripped out.

    `--no-replace-objects` is not decoration. A repository can carry
    `refs/replace/<oid>` entries that make git serve a different object than the
    one an id names, and those refs live in `.git`, are not pushed by default,
    and never appear in a diff. The floor is supposed to be the copy an edit
    cannot reach; honouring a replacement ref would let one be forged in place
    and then deleted, leaving no trace of the substitution.
    """
    env = {
        key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")
    }
    try:
        return subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repo_root), *args],
            capture_output=True,
            env=env,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, bytes) else b""
        stderr = exc.stderr if isinstance(exc.stderr, bytes) else b""
        if stderr:
            stderr += b"\n"
        stderr += f"git command timed out after {GIT_TIMEOUT_SECONDS:g}s".encode()
        return subprocess.CompletedProcess(exc.cmd, GIT_TIMEOUT_RETURN_CODE, stdout, stderr)
    except OSError:
        return None


def was_recorded(
    repo_root: Path, path: Path
) -> tuple[bool | None, str | None]:
    """Report whether branch history has the baseline and any timeout detail.

    The two failures of `resolve().relative_to()` are not the same answer and
    must not share a return. `ValueError` means the path resolved fine and sits
    outside this repository, so this repository's history genuinely does not
    record it: that is a real `False`. `OSError` means the filesystem refused to
    resolve the path at all, so nothing was learned. Reporting `False` there
    tells the caller "no debt has ever been recorded" on the strength of a
    question that was never answered, and `read_previous_sections()` reads that
    `False` as permission to proceed.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return None, None
    try:
        rel = resolved.relative_to(repo_root.resolve())
    except OSError:
        return None, None
    except ValueError:
        return False, None

    proc = run_git(repo_root, "log", "-1", "--format=%H", "HEAD", "--", str(rel))
    if problem := git_timeout_problem(proc, "checking commit history for the baseline"):
        return None, problem
    if proc is None:
        return None, None
    if proc.returncode == 0:
        return bool(proc.stdout.strip()), None

    refs = run_git(repo_root, "show-ref", "--head")
    if problem := git_timeout_problem(refs, "checking repository refs"):
        return None, problem
    if refs is None:
        return None, None
    if refs.returncode == 1 and not refs.stdout:
        return False, None
    return None, None


def tree_entries(
    repo_root: Path, treeish: str, *, may_be_empty: bool = False
) -> tuple[list[TreeEntry] | None, str | None]:
    """List one level of a committed tree.

    `--full-tree` is load-bearing. Without it `ls-tree` applies the current
    directory as a prefix to whatever tree-ish it is handed, not only to `HEAD`.
    That is harmless on the first call and fatal on every later one, because the
    prefix is applied a second time inside a subtree that does not contain it:
    git finds nothing, exits 0, and prints nothing. Empty output is not an
    error, so the walk concluded the baseline was untracked and the floor
    disappeared for any repository whose root was below the git top level.

    `may_be_empty` is false everywhere except the root tree. Git does not store
    an empty subtree, so an empty listing for a tree object is a lookup that
    failed rather than a directory with nothing in it. Only the root tree of an
    empty commit can honestly be empty.

    Names are decoded the way the filesystem decodes them. Decoding with
    `"replace"` turns any byte that is not valid UTF-8 into U+FFFD, while the
    path this is compared against arrives through argv carrying surrogate
    escapes. The two never match, so a committed baseline with such a name read
    as untracked, which is the shrug that erases the floor.
    """
    listing = run_git(repo_root, "ls-tree", "-z", "--full-tree", treeish)
    if problem := git_timeout_problem(listing, "listing the committed baseline directory"):
        return None, problem
    if listing is None or listing.returncode != 0:
        return None, "git could not list the committed baseline directory"

    entries: list[TreeEntry] = []
    for record in listing.stdout.split(b"\0"):
        if not record:
            continue
        meta, _, name = record.partition(b"\t")
        fields = meta.split()
        if len(fields) != 3:
            return None, f"git returned a tree entry this guard cannot read ({record!r})"
        mode, kind, oid = (field.decode("ascii", "replace") for field in fields)
        entries.append((mode, kind, oid, os.fsdecode(name)))

    if not entries and not may_be_empty:
        return None, (
            "git listed a committed directory as empty, which no stored tree "
            "object can be, so the lookup failed rather than finding nothing"
        )
    return entries, None


def _descend(
    entries: list[TreeEntry], component: str
) -> tuple[TreeEntry | None, str | None]:
    """Pick the committed entry a path component names, or say why it cannot.

    Every candidate that matches case-insensitively is collected before
    anything is decided. Deciding on the first one instead refused a path git
    tracks exactly whenever a case twin happened to sort ahead of it, and the
    exact match is the one the caller asked for.
    """
    folded = [entry for entry in entries if entry[3].casefold() == component.casefold()]
    if not folded:
        return None, None
    for entry in folded:
        if entry[3] == component:
            return entry, None

    tracked = ", ".join(sorted(repr(entry[3]) for entry in folded))
    return None, (
        f"git tracks {tracked} where the baseline path says {component!r}; those "
        "differ only by case, so on a case-insensitive filesystem the write "
        "would reach a file this lookup would report as untracked"
    )


def _committed_directory(
    repo_root: Path, parts: tuple[str, ...]
) -> tuple[list[TreeEntry] | None, str | None]:
    """List the committed tree that should hold the baseline.

    Walked one component at a time rather than handed to git as a pathspec. A
    pathspec is matched case-sensitively, so a parent spelled with different
    case listed nothing, and nothing was read as "no committed copy exists" by
    the caller. On a case-insensitive filesystem the write still landed on the
    tracked file, so the guard reported no floor for an artifact it was about
    to overwrite. Walking per component puts both halves of the path under the
    one rule.
    """
    entries, problem = tree_entries(repo_root, "HEAD", may_be_empty=True)
    if problem or entries is None:
        return None, problem

    for component in parts:
        entry, problem = _descend(entries, component)
        if problem:
            return None, problem
        if entry is None:
            return None, None
        _, kind, oid, name = entry
        if kind != "tree":
            return None, (
                f"the committed baseline path runs through {name!r}, which git "
                f"records as a {kind} rather than a directory"
            )
        entries, problem = tree_entries(repo_root, oid)
        if problem or entries is None:
            return None, problem

    return entries, None


def tracked_blob(repo_root: Path, rel: Path) -> tuple[str | None, str | None]:
    """Return the HEAD blob id for `rel`, or a reason the floor cannot be read.

    `(None, None)` means HEAD provably tracks nothing at that path, which is
    what a genuinely new baseline looks like. Every other failure returns a
    reason, because treating "git errored" the same as "the file is new" hands
    an attacker a lever: break the lookup and the ratchet has no floor left.
    """
    parts = rel.parts
    if not parts:
        return None, "the baseline path names no file"

    entries, problem = _committed_directory(repo_root, parts[:-1])
    if problem or entries is None:
        return None, problem

    entry, problem = _descend(entries, parts[-1])
    if problem or entry is None:
        return None, problem

    mode, kind, oid, name = entry
    if kind != "blob":
        return None, f"the committed baseline is not a regular file ({name!r} is a {kind})"
    if mode not in REGULAR_FILE_MODES:
        return None, (
            f"git records {name!r} under mode {mode} rather than a regular file; "
            "a symlink is stored as the text of its target, so the floor would "
            "be parsed from a different file than the checker reads"
        )
    return oid, None


def _no_commits_or_refuse(repo_root: Path) -> tuple[str | None, str | None]:
    """Decide whether an unresolvable HEAD means no commits or a broken pointer.

    A repository that has never been committed to and one whose HEAD names a
    branch somebody deleted answer `rev-parse --verify --quiet HEAD` the same
    way: non-zero, empty. Reading that single answer as "nothing is committed"
    is what let an edit to one file inside `.git` erase the floor, because the
    worktree copy then became the only surviving witness to the old debt.

    Refs are only the reachable half of the answer. Deleting every ref leaves
    the commits sitting in the object database, where a pseudoref such as
    `ORIG_HEAD` still names them, so no refs is not yet proof that nothing was
    committed. The object database is the question with an answer, and it is
    only asked in the state no healthy repository reaches.
    """
    refs = run_git(repo_root, "for-each-ref", "--format=%(objectname)", "--count=1")
    if problem := git_timeout_problem(refs, "listing repository refs"):
        return None, problem
    if refs is None or refs.returncode != 0:
        return None, "git could not list the repository's refs to confirm it has no commits"
    if refs.stdout.strip():
        return None, (
            "HEAD does not resolve but the repository has refs, so it holds "
            "commits whose baseline should floor this write; refusing rather "
            "than trusting the working tree copy alone"
        )

    objects = run_git(repo_root, "cat-file", "--batch-check=%(objecttype)", "--batch-all-objects")
    if problem := git_timeout_problem(objects, "enumerating the object database"):
        return None, problem
    if objects is None or objects.returncode != 0:
        return None, (
            "git could not enumerate the object database to confirm the "
            "repository holds no commits"
        )
    if b"commit" in objects.stdout.split():
        return None, (
            "HEAD does not resolve and no ref survives it, but the object "
            "database still holds commits, so this is a repository whose refs "
            "were removed rather than one that was never committed to"
        )
    return None, None


def committed_blob(repo_root: Path, path: Path) -> tuple[str | None, str | None]:
    """Name the object id HEAD records for this baseline, or say why it cannot.

    Returns `(None, None)` only when the repository answered and the answer was
    that no committed copy exists.

    The path is made relative to the git top level rather than to `repo_root`.
    Those differ whenever a checker is pointed at a subdirectory, and `ls-tree`
    is walked with `--full-tree`, so a `repo_root`-relative path would name a
    file at the wrong depth.
    """
    toplevel = run_git(repo_root, "rev-parse", "--show-toplevel")
    if problem := git_timeout_problem(toplevel, "locating the repository root"):
        return None, problem
    if toplevel is None or toplevel.returncode != 0:
        return None, (
            "the baseline is not inside a readable git repository, so the "
            "committed copy that floors this ratchet cannot be consulted"
        )

    try:
        top = Path(os.fsdecode(toplevel.stdout.strip())).resolve()
        rel = path.resolve().relative_to(top)
    except ValueError:
        # Outside the work tree, so git tracks no copy and there is no floor.
        # No checker CLI can reach this: all three reject an out-of-root
        # `--baseline` before calling in. It stays for direct library callers,
        # and it is honest for them, because git really does track nothing here.
        return None, None
    except OSError as exc:
        return None, f"the baseline path could not be resolved ({exc.strerror})"

    head = run_git(repo_root, "rev-parse", "--verify", "--quiet", "HEAD")
    if head is None:
        return None, "git could not be run to read the committed baseline"
    if problem := git_timeout_problem(head, "reading the committed baseline"):
        return None, problem
    if head.returncode != 0:
        if head.stdout.strip():
            return None, "git could not identify HEAD"
        return _no_commits_or_refuse(repo_root)

    return tracked_blob(repo_root, rel)
