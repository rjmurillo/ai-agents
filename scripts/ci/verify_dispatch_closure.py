#!/usr/bin/env python3
"""Verify the completion gate's dispatch closure from outside the tree it checks.

ADR-101, Application B, second residual: "The dispatcher itself is in the tree it
checks. ... lifting the same verification into a base-ref job at P1 removes the
self-assertion. The verification logic is already written and does not need
reinventing."

`run_completion_gate.py` byte-compares each verifier its config names, and their
import closure, against a trusted ref. It runs inside the pull request's checkout,
so a pull request that rewrites the dispatcher itself, or its config, executes
attacker code while printing a trusted verdict. Nothing the script asserts about
itself closes that. This module runs the same verification from the base ref:

  * the resolver code is loaded from THIS tree, the base checkout the workflow
    ran from, never from the head;
  * the head is a separate work tree read as data (`ast` and `git cat-file`),
    never imported and never executed. `--head-sha` writes it from the object
    store with `checkout-index`, so no workflow checkout of pull request code is
    needed;
  * the roots are the base ref's own config, the dispatcher script, and every
    file the base config's commands name, expanded through the head's static
    import closure and its resolvable dynamic loads;
  * every file in that closure is compared byte for byte with the base ref, and a
    dynamic load the resolver cannot resolve is reported, as the gate reports it.

It reuses the gate's own functions (`_collect_command_paths`,
`_expand_import_closure`, `_unresolvable_dynamic_sites`) instead of restating
them, so a fix to the gate reaches this check.

What this changes and what it does not. A change to the dispatcher, its config or
a named verifier is now reported by a job whose definition the pull request cannot
edit. It is reported, not blocked: the job's context is not a required check, and
pinning it needs the publisher App ADR-101 requirement 2 describes. A legitimate
change to a verifier reports here too, exactly as it halts the local gate until a
human approves it.

Every comparison is against the base ref tip, never the merge base: a head
behind the base runs the old copy of a file the base moved. With `--head-sha`, a
finding where the head equals the merge base is labelled STALE, which still
fails and tells the author to merge the base ref (issue #6472).

EXIT CODES (ADR-035):
  0 - the head's dispatch closure is byte-identical to the base ref
  1 - files differ, are removed, new or stale, a symlink was added, or a dynamic
      load cannot be resolved
  2 - configuration: a tree, the base config or the dispatcher cannot be read
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

import yaml

EXIT_OK = 0
EXIT_DIFFERS = 1
EXIT_CONFIG = 2

_MAX_LINK_HOPS = 8
_SYMLINK_MODE = "120000"

# ADR-119: .claude/skills/<name> links into src/claude/skills, and git cannot
# read a blob through a link, so the closure names the plugin-tree paths.
GATE = "src/claude/skills/github/scripts/pr/run_completion_gate.py"
CONFIG = "src/claude/skills/pr-review/pr-review-config.yaml"
CHANGED = "changed"
ADDED = "added"
STALE = "stale"
STALE_REMEDY = (
    "dispatch-closure: STALE files match the merge base but not the base ref: "
    "merge the base ref into the branch and push"
)
_PR_NUMBER = 1  # command templates substitute {pr}; the value does not change which files are named


class DispatchClosureError(Exception):
    """A tree, the config or the dispatcher could not be read."""


@dataclass
class Report:
    """What the head's dispatch closure looks like against the base ref."""

    examined: int = 0
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    symlinks: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        found = (self.changed, self.removed, self.added, self.symlinks, self.unresolved)
        return not any(found) and not self.stale

    def to_json(self) -> dict[str, Any]:
        return {
            "examined": self.examined,
            "changed": sorted(self.changed),
            "removed": sorted(self.removed),
            "symlinks": sorted(self.symlinks),
            "added": sorted(self.added),
            "unresolved": sorted(self.unresolved),
            "stale": sorted(self.stale),
        }


def _load_gate(tool_root: Path) -> ModuleType:
    path = tool_root / GATE
    spec = importlib.util.spec_from_file_location("verify_dispatch_closure_gate", path)
    if spec is None or spec.loader is None or not path.is_file():
        raise DispatchClosureError(f"dispatcher not found at {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise DispatchClosureError(f"dispatcher at {path} does not load: {exc}") from exc
    return module


def _base_config(tool_root: Path) -> dict[str, Any]:
    path = tool_root / CONFIG
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        raise DispatchClosureError(f"base config {path} cannot be read: {exc}") from exc
    if not isinstance(loaded, dict):
        raise DispatchClosureError(f"base config {path} is not a mapping")
    return loaded


def _criteria(gate: ModuleType, config: dict[str, Any]) -> list[Any]:
    completion = config.get("completion_criteria")
    listed = completion if isinstance(completion, list) else []
    return [*listed, *gate._scripts_map_criteria(config)]


def _base_blob(tool_root: Path, base_ref: str, path: str) -> bytes | None:
    """The bytes of ``path`` at ``base_ref`` in the base checkout, or None if absent."""
    resolved = _resolve_in_ref(tool_root, base_ref, path)
    if resolved is None:
        return None
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{base_ref}:{resolved}"],
        cwd=tool_root,
        capture_output=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


def _named_files(gate: ModuleType, config: dict[str, Any], tree: Path) -> list[str]:
    """Files the config's commands name, classified from inside ``tree``.

    Relative argv tokens resolve against the working directory, exactly as they do
    when the gate dispatches them, so classification has to run from inside the
    tree it reads. From another directory every verifier would classify as outside
    the tree and drop out.
    """
    try:
        with contextlib.chdir(tree):
            named, _, escaping = gate._collect_command_paths(
                _criteria(gate, config), _PR_NUMBER, tree
            )
    except gate.ConfigError as exc:
        raise DispatchClosureError(f"base config commands cannot be classified: {exc}") from exc
    return [*named, *escaping]


def _blob_id(tool_root: Path, ref: str, path: str) -> str | None:
    """The object id of ``path`` at ``ref`` in the base checkout, or None if absent.

    A symlinked directory on the path is followed inside the ref (ADR-119); a
    symlink at the leaf keeps its own blob id so link retargets stay visible.
    """
    resolved = _resolve_in_ref(tool_root, ref, path)
    if resolved is None:
        return None
    result = subprocess.run(
        ["git", *_INERT_GIT, "rev-parse", "--verify", "--quiet", f"{ref}:{resolved}"],
        cwd=tool_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _ref_entry(tool_root: Path, ref: str, path: str) -> tuple[str, str] | None:
    """The (mode, object id) of the entry at ``path`` in ``ref``, or None if absent."""
    listing = subprocess.run(
        ["git", *_INERT_GIT, "ls-tree", "-z", ref, "--", path],
        cwd=tool_root,
        capture_output=True,
        check=False,
    )
    if listing.returncode != 0:
        return None
    text = listing.stdout.decode("utf-8", errors="replace").split("\0", 1)[0]
    meta, _, name = text.partition("\t")
    fields = meta.split()
    if len(fields) != 3 or name != path:
        return None
    return fields[0], fields[2]


def _link_target(link_path: str, text: str) -> str | None:
    """Resolve a tracked link's text against its directory; None if it escapes the repo.

    Same contract as ``_link_target`` in scripts/validation/effective_context_sources.py,
    kept local so the trusted verifier imports nothing from the work tree under test.
    A test pins the two together.
    """
    if text.startswith("/"):
        return None
    parts = list(PurePosixPath(link_path).parent.parts)
    for part in PurePosixPath(text).parts:
        if part == "..":
            if not parts:
                return None
            parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def _read_link(tool_root: Path, sha: str) -> str:
    blob = subprocess.run(
        ["git", "cat-file", "blob", sha], cwd=tool_root, capture_output=True, check=False
    )
    return blob.stdout.decode("utf-8", errors="replace")


def _resolve_in_ref(tool_root: Path, ref: str, path: str) -> str | None:
    """``path`` with every symlinked directory replaced by its target, read inside ``ref``.

    Git object paths do not traverse a symlink, so `.claude/skills/<name>/x` is
    absent from a ref where `.claude/skills/<name>` is a link (ADR-119). Walk one
    component at a time; at mode 120000 read the blob as the target and resolve it
    against the link's parent. A target that is absolute or leaves the repo, a
    missing entry, or more than ``_MAX_LINK_HOPS`` links returns None (fail closed).
    The final component is never followed, so a leaf link keeps its own identity.
    """
    pending = list(PurePosixPath(path).parts)
    resolved: list[str] = []
    hops = 0
    while pending:
        candidate = "/".join([*resolved, pending.pop(0)])
        entry = _ref_entry(tool_root, ref, candidate)
        if entry is None:
            return None
        mode, sha = entry
        if mode != _SYMLINK_MODE or not pending:
            resolved = candidate.split("/")
            continue
        hops += 1
        target = _link_target(candidate, _read_link(tool_root, sha))
        if hops > _MAX_LINK_HOPS or not target:
            return None
        resolved = []
        pending = [*PurePosixPath(target).parts, *pending]
    return "/".join(resolved)


def _in_ref(tool_root: Path, ref: str, path: str) -> bool:
    """True when ``path`` exists at ``ref`` in the base checkout."""
    return _blob_id(tool_root, ref, path) is not None


def _same_symlinks(tool_root: Path, ref: str | None, head_sha: str | None) -> set[str]:
    """Symlinks of ``ref`` that the head carries with the same target.

    A symlink the head retargets is the pull request's own change, so a path match
    alone is not enough: the blob id, which holds the target, has to match too.
    """
    if ref is None or head_sha is None:
        return set()
    return {
        path
        for path in _base_symlinks(tool_root, ref)
        if _blob_id(tool_root, head_sha, path) == _blob_id(tool_root, ref, path)
    }


def _symlinks_in_tree(root: Path) -> set[str]:
    found: set[str] = set()
    for directory, names, files in os.walk(root, followlinks=False):
        for name in [*names, *files]:
            full = Path(directory) / name
            if full.is_symlink():
                found.add(full.relative_to(root).as_posix())
    return found


def _base_symlinks(tool_root: Path, base_ref: str) -> set[str]:
    listing = subprocess.run(
        ["git", *_INERT_GIT, "ls-tree", "-r", "-z", base_ref],
        cwd=tool_root,
        capture_output=True,
        check=False,
    )
    entries = listing.stdout.decode("utf-8", errors="replace").split("\0")
    return {e.split("\t", 1)[1] for e in entries if e.startswith("120000 ") and "\t" in e}


def _merge_base(tool_root: Path, base_ref: str, head_sha: str | None) -> str | None:
    """The commit where the head branched from the base ref, or None when unknown.

    None covers a head given as a work tree (no commit to compare), a shallow
    history that does not reach the fork point, and an unrelated history. The
    merge base only picks the STALE label; it never clears a finding.
    """
    if head_sha is None:
        return None
    result = subprocess.run(
        ["git", *_INERT_GIT, "merge-base", base_ref, head_sha],
        cwd=tool_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def _classify(
    tool_root: Path,
    base_ref: str,
    head_root: Path,
    head_sha: str | None,
    path: str,
    fork: str | None = None,
) -> str | None:
    """How the head's ``path`` compares with the base ref tip, or None when equal.

    With a head SHA the comparison is by blob id, so a `.gitattributes` in the
    head that selects a built-in conversion cannot make the bytes written to the
    scratch tree equal the base's while the committed blob differs.

    Only equality with the base ref tip clears a file. A head blob that differs
    from the tip but equals the merge-base blob is STALE: the base moved or
    deleted the file after the branch point, and the head still runs the old copy.
    """
    base_id = _blob_id(tool_root, base_ref, path)
    if head_sha is None:
        if base_id is None:
            return ADDED
        same = _base_blob(tool_root, base_ref, path) == (head_root / path).read_bytes()
        return None if same else CHANGED
    head_id = _blob_id(tool_root, head_sha, path)
    if head_id is not None and head_id == base_id:
        return None
    if fork is not None and head_id is not None and head_id == _blob_id(tool_root, fork, path):
        return STALE
    return ADDED if base_id is None else CHANGED


def _missing_roots(
    tool_root: Path, head_root: Path, base_ref: str, roots: list[str], fork: str | None
) -> tuple[list[str], list[str]]:
    """Roots the base tip has and the head lacks; stale when the merge base lacks them too."""
    missing = [
        path
        for path in roots
        if not (head_root / path).is_file() and _in_ref(tool_root, base_ref, path)
    ]
    stale = [path for path in missing if fork is not None and not _in_ref(tool_root, fork, path)]
    return [path for path in missing if path not in stale], stale


def _new_symlinks(
    tool_root: Path, head_root: Path, base_ref: str, head_sha: str | None, fork: str | None
) -> tuple[list[str], list[str]]:
    """Head symlinks the base tip lacks (by target with a head SHA), split into added and stale."""
    if head_sha is None:
        known = _base_symlinks(tool_root, base_ref)
    else:
        known = _same_symlinks(tool_root, base_ref, head_sha)
    found = _symlinks_in_tree(head_root) - known
    stale = found & _same_symlinks(tool_root, fork, head_sha)
    return sorted(found - stale), sorted(stale)


def verify(tool_root: Path, head_root: Path, base_ref: str, head_sha: str | None = None) -> Report:
    """Compare the head's dispatch closure with ``base_ref`` without running head code.

    The roots are the files the BASE config names, in the base tree, plus the
    dispatcher and the config. A root the head deletes is reported as removed: a
    pull request that deletes the gate must not read as a clean closure. A symlink
    the head adds anywhere is reported: the local gate fails closed on any
    symlink, and a symlink with the target's bytes compares equal to the target.
    """
    gate = _load_gate(tool_root)
    config = _base_config(tool_root)
    base_named = _named_files(gate, config, tool_root)
    roots = list(dict.fromkeys([GATE, CONFIG, *base_named, *_named_files(gate, config, head_root)]))
    closure = gate._expand_import_closure(
        [path for path in roots if (head_root / path).is_file()], head_root
    )
    fork = _merge_base(tool_root, base_ref, head_sha)
    report = Report(examined=len(closure))
    removed, stale_roots = _missing_roots(tool_root, head_root, base_ref, roots, fork)
    report.removed.extend(removed)
    report.stale.extend(stale_roots)
    buckets = {CHANGED: report.changed, ADDED: report.added, STALE: report.stale}
    for path in closure:
        kind = _classify(tool_root, base_ref, head_root, head_sha, path, fork)
        if kind is not None:
            buckets[kind].append(path)
    symlinks, stale_links = _new_symlinks(tool_root, head_root, base_ref, head_sha, fork)
    report.symlinks.extend(symlinks)
    report.stale.extend(stale_links)
    report.unresolved.extend(gate._unresolvable_dynamic_sites(closure, head_root))
    return report


# Git configuration that makes reading untrusted objects inert. No hook can run
# and no filesystem monitor is started. A `.gitattributes` in the head tree cannot
# name a filter driver, because a driver is defined in configuration and none is
# configured. It can still select the built-in conversions (`text`, `eol`,
# `ident`), which change the bytes written to the scratch tree, so a head SHA is
# compared by blob id and never by those written bytes.
_INERT_GIT = ("-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false")
# A system or global gitconfig can register a filter driver (git-lfs) that
# `checkout-index` would run on head blobs when the head's .gitattributes names it.
_NO_SYSTEM_CONFIG = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
_HEAD_MARKER = "refs/pull/{number}/head"


def _git(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *_INERT_GIT, *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env={**(os.environ if env is None else env), **_NO_SYSTEM_CONFIG},
    )
    if result.returncode != 0:
        raise DispatchClosureError(f"git {args[0]} failed: {result.stderr.strip()[:300]}")
    return result.stdout.strip()


def materialize_head(
    tool_root: Path, pull_number: int, head_sha: str, dest: Path, remote: str = "origin"
) -> None:
    """Write the pull request head's tracked files into ``dest`` without a checkout.

    The head SHA comes from the event payload. It is fetched through the pull
    request ref and the fetched commit must be that SHA: if the branch moved
    between the event and this run the check aborts rather than verify a revision
    nobody named. Files are written from the object store with `checkout-index`,
    which honours no `export-ignore` (unlike `git archive`, where the head's own
    `.gitattributes` could omit a module from the closure) and runs no hook or
    filter. No `.git` directory lands in ``dest``.
    """
    if _rev(head_sha) is None:
        raise DispatchClosureError(f"head SHA {head_sha!r} is not a full commit id")
    _git(
        tool_root,
        "fetch",
        "--no-tags",
        "--no-recurse-submodules",
        remote,
        _HEAD_MARKER.format(number=pull_number),
    )
    fetched = _git(tool_root, "rev-parse", "FETCH_HEAD")
    if fetched != head_sha:
        raise DispatchClosureError(
            f"pull request head moved: event named {head_sha}, the ref is now {fetched}"
        )
    dest.mkdir(parents=True, exist_ok=True)
    index = dest.parent / f"{dest.name}.index"
    env = {**os.environ, "GIT_INDEX_FILE": str(index)}
    _git(tool_root, "read-tree", head_sha, env=env)
    _git(tool_root, "checkout-index", "--all", "--force", f"--prefix={dest}/", env=env)
    index.unlink(missing_ok=True)


def _rev(value: str) -> str | None:
    return value if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument(
        "--tool-root", type=Path, default=Path.cwd(), help="Base checkout (default: cwd)."
    )
    parser.add_argument("--head-root", type=Path, help="Pull request head work tree.")
    parser.add_argument(
        "--head-sha", help="Head commit to fetch and read as data; needs --pull-number."
    )
    parser.add_argument("--pull-number", type=int, help="Pull request number for --head-sha.")
    parser.add_argument(
        "--remote", default="origin", help="Remote to fetch the head from (default: origin)."
    )
    parser.add_argument(
        "--base-ref", default="HEAD", help="Ref in the base checkout to compare against."
    )
    parser.add_argument(
        "--advisory", action="store_true", help="Report, but exit 0 unless a config error."
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    return parser


def _plain(line: str) -> str:
    """ASCII with every control character escaped.

    A head file name reaches this output through a literal dynamic load. A line
    feed followed by `::error::` or `::stop-commands::` would start a workflow
    command at the beginning of a log line, so a name is never printed raw.
    """
    ascii_line = line.encode("ascii", "backslashreplace").decode("ascii")
    return re.sub(r"[\x00-\x1f\x7f]", lambda m: f"\\x{ord(m.group()):02x}", ascii_line)


def _print(report: Report, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.to_json(), indent=2))
        return
    print(
        f"dispatch-closure: {report.examined} files examined; {len(report.changed)} differ, "
        f"{len(report.removed)} removed, {len(report.added)} not in the base ref, "
        f"{len(report.symlinks)} new symlinks, {len(report.unresolved)} unresolved loads, "
        f"{len(report.stale)} stale"
    )
    for label, items in (
        ("DIFFERS", report.changed),
        ("REMOVED", report.removed),
        ("SYMLINK", report.symlinks),
        ("NEW", report.added),
        ("UNRESOLVED", report.unresolved),
        ("STALE", report.stale),
    ):
        for item in sorted(items):
            print(_plain(f"dispatch-closure: {label} {item}"))
    if report.stale:
        print(STALE_REMEDY)


def _head_root(args: argparse.Namespace, scratch: Path) -> Path:
    if args.head_root is not None:
        if args.head_sha is not None:
            raise DispatchClosureError("give --head-root or --head-sha, not both")
        return Path(args.head_root).resolve()
    if args.head_sha is None or args.pull_number is None:
        raise DispatchClosureError("give --head-root, or --head-sha with --pull-number")
    head = scratch / "head"
    materialize_head(
        Path(args.tool_root).resolve(), args.pull_number, args.head_sha, head, args.remote
    )
    return head


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with tempfile.TemporaryDirectory(prefix="dispatch-closure-") as scratch:
            head_root = _head_root(args, Path(scratch))
            report = verify(args.tool_root.resolve(), head_root, args.base_ref, args.head_sha)
    except (DispatchClosureError, OSError) as exc:
        print(_plain(f"ERROR: {exc}"), file=sys.stderr)
        return EXIT_CONFIG
    _print(report, args.json)
    return EXIT_OK if report.clean or args.advisory else EXIT_DIFFERS


if __name__ == "__main__":
    sys.exit(main())
