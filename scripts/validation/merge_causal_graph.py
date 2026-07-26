"""Git merge driver for the generated causal graph.

Every merge of the default branch into a feature branch conflicts on
``.agents/memory/causality/causal-graph.json``. The file is generated state
committed as one blob, and the pre-commit generator rewrites it on essentially
every commit, so both sides of any merge have touched it. Git cannot reconcile
two rewrites of one JSON document, so it hands the developer a conflict in a
file no human authored (issue #3345).

The documented workaround made it worse. ``git checkout origin/main -- <graph>``
takes one side wholesale and discards every node the branch contributed, and
rerunning the generator does not restore them: the generator is incremental and
only processes episodes staged in the current commit, of which a merge has none.
Measured on main at the time of writing, 41 of 242 episodes on disk had no node
in the committed graph, and the most recent absences were episodes that had
arrived through exactly this path.

This driver resolves the conflict by content instead. Nodes, edges, and patterns
are append-mostly and carry stable identities, so the merge of two graphs is the
union of their records. Counters reconcile three-way against the ancestor
(``base + (ours - base) + (theirs - base)``) rather than summing, which would
double-count everything the two sides already shared.

Failure is loud. If any input will not parse, the driver exits nonzero and git
leaves the conflict markers in place for a human. Silently taking a side is the
behavior that caused the drift this driver exists to stop.

Registered by the pre-commit hook through
``scripts/maintenance/install_merge_drivers.py``, so a clone self-heals on its
first commit rather than depending on a setup step someone can skip. A
``.gitattributes`` entry without the matching ``git config`` is a silent no-op,
which is why registration is automatic.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, TextIO, TypeAlias

# A value as it comes out of json.load. Naming it beats `Any`: these helpers
# genuinely accept whatever the generated graph holds, and the alias says so
# without disabling the ban on untyped signatures.
JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]

# Which record collections we merge, and the field that identifies a record
# within each. Node ids are content hashes, patterns are keyed by name because
# committed patterns may omit ids, and an edge is identified by the pair it
# connects (matching the generator's deduplication in update_causal_graph.py).
# Ordered nodes, patterns, edges to match the schema
# order the generator writes (see .agents/memory/causality/causal-graph.json),
# so a merge that changes no content does not also reorder the top-level JSON
# and produce a noisy diff.
_COLLECTIONS: dict[str, tuple[str, ...]] = {
    "nodes": ("id",),
    "patterns": ("name",),
    "edges": ("source", "target"),
}

# Field-merge policy. Anything not named here falls through to _prefer_diverged.
_COUNTERS = frozenset({"evidence_count", "occurrences", "frequency"})
_SET_VALUED = frozenset({"episodes"})
_EARLIEST = frozenset({"created"})
_LATEST = frozenset({"last_used", "updated"})
# Metadata the generator is known to drop on a fresh write (issue #3351).
# _prefer_diverged would read that omission as a deletion and propagate the
# loss into the merge even when the other side still has the value.
_PREFER_PRESENT = frozenset({"version"})


class GraphMergeError(Exception):
    """An input could not be read or was not a causal graph."""


def _discard(temporary: str) -> OSError | None:
    """Remove the sibling temporary, returning any failure instead of raising.

    The caller is already unwinding a more interesting error. Raising from
    cleanup would replace it.
    """
    try:
        Path(temporary).unlink(missing_ok=True)
    except OSError as cleanup:
        return cleanup
    return None


def _release(handle: TextIO | None, temporary: str) -> str | None:
    """Close the temporary and remove it, describing every failure.

    Closing comes first because Windows refuses to unlink an open file: a
    temporary that was still open when the write unwound would survive the
    cleanup that exists to remove it. On POSIX the unlink succeeds either way
    and the damage is a leaked descriptor instead, which is quieter and just as
    real inside a long-lived `git merge`.
    """
    failures: list[str] = []
    if handle is not None:
        try:
            handle.close()
        except OSError as close_error:
            failures.append(f"failed to close temporary file {temporary}: {close_error}")
    cleanup = _discard(temporary)
    if cleanup is not None:
        failures.append(f"failed to remove temporary file {temporary}: {cleanup}")
    return "; ".join(failures) or None


def _close_descriptor(fd: int) -> str | None:
    """Close a descriptor left by fdopen, ignoring only already-closed."""
    try:
        os.close(fd)
    except OSError as close_error:
        if close_error.errno != errno.EBADF:
            return f"failed to close temporary file descriptor {fd}: {close_error}"
    return None


def _surface_cleanup(primary: BaseException, *details: str | None) -> None:
    """Preserve an OSError cause, or report cleanup beside an interrupt."""
    detail = "; ".join(item for item in details if item is not None)
    if not detail:
        return
    if isinstance(primary, OSError):
        raise OSError(primary.errno, f"{primary.strerror or primary}; {detail}") from primary
    print(f"ERROR: causal graph merge driver cleanup: {detail}", file=sys.stderr)


def _atomic_write_text(path: Path, text: str) -> None:
    """Replace ``path`` only after its full content reaches a sibling file."""
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        handle = os.fdopen(fd, "w", encoding="utf-8")
    except BaseException as primary:
        # Whether the descriptor is still ours depends on how far io.open got.
        # Measured on CPython: an invalid mode raises before it wraps the
        # descriptor and leaves it open, an unknown encoding raises after and
        # closes it on the way out. An interrupt can land on either side. So
        # this close is required in the first case and answers EBADF in the
        # second. Only EBADF is harmless; every other close failure is reported
        # beside the error that explains why fdopen failed.
        close_detail = _close_descriptor(fd)
        # No handle to close: fdopen did not return one, and the descriptor is
        # already settled above. _release still owns the message, so a failure
        # to remove the temporary reads the same here as on the write path.
        detail = _release(None, temporary)
        _surface_cleanup(primary, close_detail, detail)
        raise

    open_handle: TextIO | None = handle
    try:
        handle.write(text)
        handle.flush()
        # Flush the payload before replace. This does not make the directory
        # entry crash-durable; it prevents replacing the destination with a
        # temporary whose content is still only buffered in this process.
        os.fsync(handle.fileno())
        handle.close()
        open_handle = None
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    except BaseException as primary:
        # BaseException rather than OSError: a merge driver runs inside an
        # interactive `git merge`, so the realistic failure is Ctrl-C, and
        # KeyboardInterrupt would otherwise leave the temporary beside the
        # graph it failed to replace.
        detail = _release(open_handle, temporary)
        _surface_cleanup(primary, detail)
        raise


def _load(path: Path, label: str, *, may_be_empty: bool = False) -> dict[str, Any]:
    """Read one side of the merge.

    An empty ancestor is normal: git passes an empty file for an add/add
    conflict, where the two sides have no common history for this path. An empty
    ours or theirs is not. Reading it as an empty graph would let a truncated
    file merge cleanly and delete everything the other side has, which is the
    silent data loss this driver exists to prevent.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GraphMergeError(f"cannot read {label} ({path}): {exc}") from exc

    if not text.strip():
        if may_be_empty:
            return {}
        raise GraphMergeError(f"{label} ({path}) is empty, expected a graph")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GraphMergeError(f"{label} ({path}) is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise GraphMergeError(f"{label} ({path}) is {type(data).__name__}, expected an object")
    return data


def _records(graph: dict[str, Any], collection: str) -> list[dict[str, Any]]:
    """Return the records in one collection, ignoring anything malformed.

    A non-list collection or a non-object record is dropped rather than raised
    on: the graph is generated, and one bad record should not block a merge that
    can still carry every good one.
    """
    value = graph.get(collection)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _key(record: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, ...]:
    """Identify a record for matching across the three sides.

    A record missing any identity field has no usable identity, and keying it on
    the absent ones collapses every such record onto the same key, keeping
    exactly one. Measured on the committed graph: 6 of 10 patterns carry no
    ``id``, so union merging dropped 5 of them. Partial identities collapse the
    same way and were the second half of the bug: three malformed edges carrying
    only ``source`` all key to ``("a", "")``, so two are dropped.

    Requiring every field, rather than any, is what makes the fallback fire in
    both cases. Those records fall back to their content, which matches an
    untouched record across sides and, at worst, carries an edited one through
    twice. A duplicate is recoverable; a dropped record is not.
    """
    if all(field in record for field in fields):
        return tuple(str(record[field]) for field in fields)
    return ("", json.dumps(record, sort_keys=True, default=str))


def _index(
    records: list[dict[str, Any]], fields: tuple[str, ...]
) -> dict[tuple[str, ...], dict[str, Any]]:
    return {_key(record, fields): record for record in records}


def _survives(
    key: tuple[str, ...],
    base_index: dict[tuple[str, ...], dict[str, Any]],
    ours_index: dict[tuple[str, ...], dict[str, Any]],
    theirs_index: dict[tuple[str, ...], dict[str, Any]],
) -> bool:
    """Decide whether a record one side dropped was deleted or never held.

    A union keeps everything either side ever had, so a deliberate removal comes
    back the moment a branch that predates it merges. Every branch open across a
    purge then pays the same manual strip (issue #3375).

    Tombstones are the usual answer to that, and they are not needed here. Git
    hands a merge driver the common ancestor, and presence in it is the whole
    discriminator: a record in the ancestor that one side no longer carries was
    removed by that side. A record absent from the ancestor was added by
    whichever side has it. Nothing has to be written into the artifact.

    Delete beats modify. In this file a removal is always deliberate, a purge of
    something that should not be committed, while a modification is usually the
    generator bumping a counter. Keeping the record to preserve a counter would
    undo the purge, which is the bug. Measured over the file's whole history:
    of 85 commits that touched it, 3 removed rows, and all three were
    deliberate (663bbac48 the #3358 purge, c2264799b the PowerShell to Python
    migration, bdacb6b19 a session protocol change). The generator itself only
    ever adds.
    """
    if key not in base_index:
        return True
    return key in ours_index and key in theirs_index


def _merge_counter(base: JsonValue, ours: JsonValue, theirs: JsonValue) -> JsonValue:
    """Apply both sides' deltas to the ancestor.

    Summing ours and theirs would count everything they inherited twice. Three
    way keeps a counter that neither side touched unchanged.
    """
    ours_count = ours if isinstance(ours, (int, float)) else None
    theirs_count = theirs if isinstance(theirs, (int, float)) else None
    if ours_count is None or theirs_count is None:
        # Only one side holds a number, so there are no two deltas to reconcile.
        # Keep whichever side has one: dropping it because the other side is
        # malformed would lose the count the good side actually recorded.
        if ours_count is not None:
            return ours_count
        if theirs_count is not None:
            return theirs_count
        return ours if ours is not None else theirs
    # When there is no ancestor value, both branches independently added this
    # record. Take the maximum rather than summing deltas, which would
    # double-count when both sides added the same content with the same count.
    if not isinstance(base, (int, float)):
        return max(ours_count, theirs_count)
    # Three-way merge: apply both sides' deltas to the ancestor.
    merged = base + (ours_count - base) + (theirs_count - base)
    return max(merged, 0)


def _merge_set(ours: JsonValue, theirs: JsonValue) -> JsonValue:
    """Union two list-valued fields.

    Sorted on a canonical rendering so the result does not depend on which side
    git called ours, and deduplicated so a record merged twice does not grow its
    episode list.
    """
    if not isinstance(ours, list) or not isinstance(theirs, list):
        return ours if isinstance(ours, list) else theirs
    seen: dict[str, Any] = {}
    for item in ours + theirs:
        seen.setdefault(json.dumps(item, sort_keys=True), item)
    return [seen[rendering] for rendering in sorted(seen)]


def _extreme(base: JsonValue, ours: JsonValue, theirs: JsonValue, *, latest: bool) -> JsonValue:
    """Pick the earliest or latest of three comparable values, tolerating None."""
    candidates = [value for value in (base, ours, theirs) if isinstance(value, str) and value]
    if not candidates:
        return ours if ours is not None else theirs
    return max(candidates) if latest else min(candidates)


def _prefer_diverged(base: JsonValue, ours: JsonValue, theirs: JsonValue) -> JsonValue:
    """Take whichever side moved away from the ancestor.

    When both moved, take ours. A merge driver is called with a defined ours and
    theirs, so this is deterministic for the caller even though it is not
    symmetric, and it matches what `git merge -X ours` would do for the field.
    """
    if ours == theirs:
        return ours
    if ours == base:
        return theirs
    return ours


def _ordered_keys(ours: dict[str, Any], theirs: dict[str, Any]) -> list[str]:
    """Ours first, then anything only theirs has, so diffs stay readable."""
    return list(ours) + [field for field in theirs if field not in ours]


def _fields_to_merge(
    base: dict[str, Any],
    ours: dict[str, Any],
    theirs: dict[str, Any],
    exclude: frozenset[str] = frozenset(),
) -> list[str]:
    """Fields to merge: everything either side carries, plus recoverable ones.

    A key neither side carries is normally an agreed deletion, and iterating
    only what the sides carry is what keeps it deleted. _PREFER_PRESENT names
    the exception. Those fields go missing because the generator drops them on
    a fresh write, so once both sides have regenerated, neither carries the
    field and the ancestor holds the only surviving copy.

    Records and the top-level document share this for the same reason they
    share _merge_fields. Extending only the top-level key list is how version
    and updated became one-off special cases the first time.
    """
    keys = [field for field in _ordered_keys(ours, theirs) if field not in exclude]
    recoverable = [
        field
        for field in base
        if field in _PREFER_PRESENT and field not in keys and field not in exclude
    ]
    return recoverable + keys


def _merge_fields(
    base: dict[str, Any],
    ours: dict[str, Any],
    theirs: dict[str, Any],
    keys: list[str],
) -> dict[str, Any]:
    """Apply the field-merge policy table to one level of the document.

    Records and the top-level document merge their fields the same way, so this
    is shared rather than restated. Restating it is how the top level came to
    handle version and updated as one-off special cases.
    """
    merged: dict[str, Any] = {}
    for field in keys:
        base_value, ours_value, theirs_value = base.get(field), ours.get(field), theirs.get(field)
        if field in _COUNTERS:
            merged[field] = _merge_counter(base_value, ours_value, theirs_value)
        elif field in _SET_VALUED:
            merged[field] = _merge_set(ours_value, theirs_value)
        elif field in _EARLIEST:
            merged[field] = _extreme(base_value, ours_value, theirs_value, latest=False)
        elif field in _LATEST:
            merged[field] = _extreme(base_value, ours_value, theirs_value, latest=True)
        elif field in _PREFER_PRESENT:
            # Falling back to the ancestor matters. These fields go missing
            # because the generator drops them on a fresh write, not because
            # anyone deleted them. Without the base fallback, two sides that
            # both regenerated would agree on the omission and merge_graphs
            # would strip the field, turning a generator defect into a
            # permanent loss the next merge cannot recover.
            merged[field] = next(
                (value for value in (ours_value, theirs_value, base_value) if value is not None),
                None,
            )
        else:
            merged[field] = _prefer_diverged(base_value, ours_value, theirs_value)
    return merged


def _merge_record(
    base: dict[str, Any] | None,
    ours: dict[str, Any] | None,
    theirs: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge one record present on at least one side."""
    if ours is None:
        return dict(theirs or {})
    if theirs is None:
        return dict(ours)

    ancestor = base or {}
    return _merge_fields(ancestor, ours, theirs, _fields_to_merge(ancestor, ours, theirs))


def _merge_collection(
    base: dict[str, Any],
    ours: dict[str, Any],
    theirs: dict[str, Any],
    collection: str,
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    """Union one collection, preserving ours-first order so diffs stay readable."""
    base_index = _index(_records(base, collection), fields)
    ours_index = _index(_records(ours, collection), fields)
    theirs_index = _index(_records(theirs, collection), fields)

    ordered = list(ours_index) + [key for key in theirs_index if key not in ours_index]
    return [
        _merge_record(base_index.get(key), ours_index.get(key), theirs_index.get(key))
        for key in ordered
        if _survives(key, base_index, ours_index, theirs_index)
    ]


def merge_graphs(
    base: dict[str, Any], ours: dict[str, Any], theirs: dict[str, Any]
) -> dict[str, Any]:
    """Merge two causal graphs against their common ancestor."""
    # Every top-level key either side carries, including ones the schema grows
    # later. Collections have their own union rule and are merged below.
    scalars = _fields_to_merge(base, ours, theirs, exclude=frozenset(_COLLECTIONS))
    merged = _merge_fields(base, ours, theirs, scalars)

    for collection, fields in _COLLECTIONS.items():
        merged[collection] = _merge_collection(base, ours, theirs, collection, fields)

    return {field: value for field, value in merged.items() if value is not None}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base", type=Path, help="common ancestor (git %%O)")
    parser.add_argument("ours", type=Path, help="our version, also the output path (git %%A)")
    parser.add_argument("theirs", type=Path, help="their version (git %%B)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Return 0 on success, 1 for invalid input, or 3 for a write failure."""
    args = parse_args(argv)
    try:
        merged = merge_graphs(
            _load(args.base, "ancestor", may_be_empty=True),
            _load(args.ours, "ours"),
            _load(args.theirs, "theirs"),
        )
        _atomic_write_text(args.ours, json.dumps(merged, indent=2) + "\n")
    except GraphMergeError as exc:
        print(f"ERROR: causal graph merge driver: {exc}", file=sys.stderr)
        print("Leaving the conflict in place; resolve it by hand.", file=sys.stderr)
        return 1
    except OSError as exc:
        print(
            f"ERROR: causal graph merge driver could not write {args.ours}: {exc}",
            file=sys.stderr,
        )
        # ADR-035: filesystem failure is external (3), not a logic error (1).
        # Git reads any nonzero the same way, as "leave the conflict in place",
        # so this only distinguishes the two when a human runs the driver by
        # hand to resolve a conflict, which is exactly when it is worth knowing
        # whether the input was malformed or the disk refused the write.
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
