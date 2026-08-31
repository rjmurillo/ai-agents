"""Read a captured run inventory, or a recovery manifest, back off disk.

Issue #4835. Split out of ``scripts/bulk_cancel_guard.py`` so that file stays
under the 500-line taste ceiling once the live provenance and auth paths landed.

This is the guard's most dangerous boundary. Every other input arrives from the
GitHub API; this one arrives from a file an operator may have truncated,
hand-edited, or copied out of a terminal mid-incident. A run record that loses
its context arrays reads as "publishes nothing required", and a run that
publishes nothing required needs no recovery event, so it is cancelled
unguarded. Every field is therefore validated, never defaulted and never
coerced.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .recovery_manifest import WorkflowRun

__all__ = [
    "load_runs_file",
    "run_from_manifest_entry",
    "run_from_mapping",
    "string_list",
]


def string_list(value: object, field: str) -> list[str]:
    """Validate a JSON string array, rejecting every other shape.

    Validation, never coercion. Accepting any iterable and stringifying its
    items turns a malformed record into a plausible one: a nested object
    becomes its key names, an integer becomes ``"7"``, and each of those is a
    context string no ruleset requires, so the run reads as publishing nothing
    required and is cancelled unguarded. A `str` is itself iterable and would
    decompose into single characters, which is the same failure spelled
    differently.

    Raises:
        ValueError: when ``value`` is not a list, or any item is not a string.
    """
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a JSON list of strings, got: {value!r}")
    validated: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                f"{field} must hold only strings; got {item!r} in {value!r}"
            )
        validated.append(item)
    return validated


def _json_bool(value: object, field: str, *, default: bool) -> bool:
    """Read a JSON boolean, rejecting anything truthiness would misread.

    ``bool("false")`` is ``True`` and ``bool(0)`` is ``False``, so coercion
    reads a malformed record as the opposite of what it says. For
    ``jobs_verified`` the dangerous direction is the first: the string
    ``"false"`` recorded for an unmaterialized run would replay as trusted and
    clear a run whose published contexts were never read.

    Raises:
        ValueError: when ``value`` is present and is not a JSON boolean.
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be a JSON boolean (true/false), got: {value!r}")


def _optional_str(value: object, field: str) -> str:
    """Read an optional JSON string field, absent meaning the empty string.

    Validated rather than stringified for the same reason as
    :func:`string_list`: ``str()`` of a dict or a number produces a plausible
    path that resolves to nothing, and a workflow path that resolves to nothing
    is indistinguishable from one that was never recorded.

    Raises:
        ValueError: when ``value`` is present and is not a string.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ValueError(f"{field} must be a JSON string, got: {value!r}")


def run_from_mapping(payload: Mapping[str, Any]) -> WorkflowRun:
    """Build a :class:`WorkflowRun` from a JSON object.

    Raises:
        ValueError: when a field is missing or has the wrong type. Failing here
            is deliberate: a run record silently defaulted to an empty context
            tuple would be classified as non-required and cancelled without a
            recovery event, which is the exact failure this guard exists to
            prevent.
    """
    try:
        contexts = string_list(payload["contexts"], "contexts")
        # An absent key keeps the documented default of True. An explicit false
        # is honored so a manifest written for an unmaterialized run replays as
        # unverified instead of silently regaining trust on the round trip.
        # An explicit JSON null is treated as absent (default True), not as a
        # third state, because the field's contract is boolean-or-absent.
        _sentinel = object()
        jv_raw = payload.get("jobs_verified", _sentinel)
        if jv_raw is _sentinel or jv_raw is None:
            jobs_verified = True
        else:
            jobs_verified = _json_bool(jv_raw, "jobs_verified", default=True)
        run_id_raw = payload["run_id"]
        if not isinstance(run_id_raw, int) or isinstance(run_id_raw, bool):
            raise ValueError(
                f"run_id must be a JSON integer, got {type(run_id_raw).__name__}: "
                f"{run_id_raw!r}"
            )
        pr_number_raw = payload["pr_number"]
        if not isinstance(pr_number_raw, int) or isinstance(pr_number_raw, bool):
            raise ValueError(
                f"pr_number must be a JSON integer, got {type(pr_number_raw).__name__}: "
                f"{pr_number_raw!r}"
            )
        return WorkflowRun(
            run_id=run_id_raw,
            workflow_name=str(payload["workflow_name"]),
            pr_number=pr_number_raw,
            branch=str(payload["branch"]),
            event=str(payload["event"]),
            status=str(payload["status"]),
            contexts=tuple(contexts),
            jobs_verified=jobs_verified,
            workflow_path=_optional_str(payload.get("workflow_path"), "workflow_path"),
            head_repo=_optional_str(payload.get("head_repo"), "head_repo") or "",
        )
    except (KeyError, TypeError) as exc:
        raise ValueError(f"malformed workflow run record: {payload!r}") from exc


def run_from_manifest_entry(entry: object) -> WorkflowRun:
    """Rebuild a run record from one recovery-manifest entry.

    A manifest entry is a superset of a run record wearing different key names,
    and it splits one ``contexts`` list into ``required_contexts`` and
    ``other_contexts``. Rejoining them restores the original inventory exactly,
    because ``_classify`` partitions on membership in the required set and
    discards nothing.

    Both arrays are required and both are type-checked. Substituting an empty
    list for a missing or wrongly-typed one, which this did, converts a
    truncated recovery record into a plausible non-required run: the very
    "nothing required here" reading ``load_runs_file`` promises to refuse.

    Raises:
        ValueError: when the entry is not a mapping, a key is missing, or
            either context array is absent or holds a non-string.
    """
    if not isinstance(entry, Mapping):
        raise ValueError(f"malformed recovery manifest entry: {entry!r}")
    for key in ("required_contexts", "other_contexts"):
        if key not in entry:
            raise ValueError(
                f"recovery manifest entry is missing {key!r}, so the contexts "
                f"this run publishes cannot be reconstructed: {entry!r}"
            )
    required = string_list(entry["required_contexts"], "required_contexts")
    other = string_list(entry["other_contexts"], "other_contexts")
    try:
        return run_from_mapping(
            {
                "run_id": entry["run_id"],
                "workflow_name": entry["workflow"],
                "pr_number": entry["pull_request"],
                "branch": entry["branch"],
                "event": entry["event"],
                "status": entry["status"],
                "contexts": [*required, *other],
                "jobs_verified": entry.get("jobs_verified"),
                "workflow_path": entry.get("workflow_path"),
            }
        )
    except KeyError as exc:
        raise ValueError(f"malformed recovery manifest entry: {entry!r}") from exc


def load_runs_file(path: Path) -> list[WorkflowRun]:
    """Read a captured run inventory, or a recovery manifest, from disk.

    Two shapes are accepted, because the manifest this tool writes is the file
    an operator reaches for mid-incident. A recovery manifest is recognized by
    carrying both ``version`` and ``entries``; anything else is read as a run
    inventory, either a bare list or an object with a ``runs`` key.

    Raises:
        ValueError: on unreadable, non-JSON, or structurally wrong input. The
            caller converts this to exit code 2 rather than proceeding with a
            partially-parsed inventory, because a dropped run record reads as
            "nothing required here" and would be cancelled unguarded.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc

    if isinstance(payload, dict) and "entries" in payload and "version" in payload:
        entries = payload["entries"]
        if not isinstance(entries, list):
            raise ValueError(f"{path} manifest entries must be a JSON list")
        return [run_from_manifest_entry(entry) for entry in entries]

    records = payload.get("runs") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"{path} must hold a JSON list of run records")
    return [run_from_mapping(record) for record in records]
