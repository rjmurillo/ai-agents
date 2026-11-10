"""Offline friction imports for bootstrap_mine; see references/discovery.md.

Stricter than canonical:
skill-doctor/scripts/collect_sessions.py:main also exports all/multi-project
inventories. Only an explicitly asserted single-project inventory seeds this
repo, to avoid attributing unrelated sessions to it.
No journal paths, source URLs, or embedded instructions are opened or executed.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import parse_qsl, unquote, urlsplit

Payload = dict[str, Any]
MAX_INPUT_BYTES = 5 * 1024 * 1024
PAGINATION_QUERY_KEYS = frozenset({"page", "per_page", "$top", "$skip"})
HOSTED_SIGNALS = {
    "github_pull_request": ("changes_requested", "state"),
    "github_issue": ("reopened", "event"),
    "azure_devops_pull_request": ("active_review_threads", "status"),
    "azure_devops_work_item": ("completed_to_active", "from_state"),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _object(value: Any) -> Payload:
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def _list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("expected a JSON list")
    return value


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected nonempty text")
    return value


def _count(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("expected a nonnegative integer count")
    return value


def _unique_keys(pairs: list[tuple[str, Any]]) -> Payload:
    result: Payload = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-JSON constant: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    _require(math.isfinite(number), "nonfinite JSON number")
    return number


def _read(path: str) -> tuple[Payload, Payload]:
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        _require(len(raw) <= MAX_INPUT_BYTES, "input exceeds 5 MiB")
        data = _object(
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_keys,
                parse_constant=_reject_constant,
                parse_float=_finite_float,
            )
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"cannot import {path}: {exc}") from exc
    return data, {"input": path, "sha256": hashlib.sha256(raw).hexdigest()}


def _local_scope(value: Any, root: Path) -> None:
    path = Path(_text(value))
    _require(path.is_absolute() and path.resolve() == root, "repo scope must match --repo")


def _inventory_path(value: Any) -> PurePosixPath | PureWindowsPath:
    text = _text(value)
    _require(not any(ord(char) < 32 for char in text), "path contains control characters")
    windows = PureWindowsPath(text)
    path: PurePosixPath | PureWindowsPath
    if windows.is_absolute():
        path = windows
    else:
        _require(not windows.drive and "\\" not in text, "malformed or relative Windows path")
        path = PurePosixPath(text)
    _require(path.is_absolute() and ".." not in path.parts, "requires absolute path without '..'")
    return path


def _session_scope(meta: Payload, declared: PurePosixPath | PureWindowsPath) -> None:
    """Check lexical containment without opening recorded directories.

    PureWindowsPath compares case-insensitively; PurePosixPath preserves case.
    This does not resolve historical symlinks or prove the inventory truthful.
    """
    values = [meta.get("cwd")]
    if "cwd_history" in meta:
        history = _list(meta["cwd_history"])
        _require(bool(history), "cwd_history must not be empty")
        values.extend(history)
    for value in values:
        path = _inventory_path(value)
        _require(
            type(path) is type(declared) and path.is_relative_to(declared),
            "session cwd must be same-flavor and within declared repo",
        )


def _url(value: Any, *, page: bool = False) -> str:
    """Accept a credential-free HTTPS URL; only page URLs may carry pagination keys.

    Seeds retain these URLs as provenance, so a signed or tokenized query would
    leak into the miner's output. Page URLs keep plain page counters only.
    """
    text = _text(value)
    parsed = urlsplit(text)
    _require(
        parsed.scheme == "https" and bool(parsed.hostname) and _safe_url_text(text),
        "source URL must be credential-free HTTPS without a fragment",
    )
    keys = {key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    allowed = PAGINATION_QUERY_KEYS if page else frozenset()
    _require(
        keys <= allowed and (bool(keys) or not parsed.query),
        "source URL query may hold only page counters on page URLs",
    )
    return text


def _safe_url_text(text: str) -> bool:
    parsed = urlsplit(text)
    path = unquote(parsed.path)
    return (
        parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and not any(char.isspace() or ord(char) < 32 for char in text)
        and "\\" not in unquote(text)
        and not any(part in (".", "..") for part in path.split("/"))
        and path.count("/") == parsed.path.count("/")
    )


def _scoped_url(value: Any, scope: str, *, page: bool = False) -> str:
    text = _url(value, page=page)
    target, base = urlsplit(text), urlsplit(scope)
    _require(
        target.netloc == base.netloc
        and (target.path == base.path or target.path.startswith(base.path.rstrip("/") + "/")),
        "source URL is outside asserted scope",
    )
    return text


def _seed(identity: list[str], signal: str, count: int, source: Payload) -> Payload:
    return {
        "kind": identity[0],
        "identity": identity,
        "signal": signal,
        "count": count,
        "disposition": "candidate_unverified",
        "sources": [source],
    }


def _merge(rows: list[Payload]) -> list[Payload]:
    merged: dict[tuple[str, ...], Payload] = {}
    for row in rows:
        key = (*row["identity"], row["signal"])
        previous = merged.get(key)
        if previous is None:
            merged[key] = row
            continue
        _require(previous["count"] == row["count"], "conflicting duplicate seed counts")
        _require(
            previous.get("observations") == row.get("observations"),
            "conflicting duplicate observation sets",
        )
        for source in row["sources"]:
            if source not in previous["sources"]:
                previous["sources"].append(source)
    return sorted(merged.values(), key=lambda row: (-row["count"], row["identity"], row["signal"]))


def _session_rows(data: Payload, provenance: Payload) -> list[Payload]:
    rows: list[Payload] = []
    seen: dict[tuple[str, str], Payload] = {}
    declared = _inventory_path(data.get("repo"))
    for index, value in enumerate(_list(data.get("sessions"))):
        session = _object(value)
        meta, stats = _object(session.get("meta")), _object(session.get("stats"))
        _session_scope(meta, declared)
        identity = [_text(session.get("harness")), _text(meta.get("id"))]
        _require(_count(stats.get("assistant_turns")) >= 1, "session is not scoreable")
        _require(_count(stats.get("tool_calls")) >= 1, "session is not scoreable")
        signals = {
            name: _count(stats.get(name)) for name in ("repeated_tool_calls", "error_outputs")
        }
        key = (identity[0], identity[1])
        _require(key not in seen or seen[key] == signals, "conflicting duplicate session")
        seen[key] = signals
        source = {
            **provenance,
            "locator": f"/sessions/{index}",
            "session": {name: session.get(name) for name in ("file", "modified_at", "meta")},
            "stats": stats,
        }
        rows.extend(
            _seed(["skill_doctor_session", *identity], signal, count, source)
            for signal, count in signals.items()
        )
    return rows


def _collection_metadata(data: Payload) -> Payload:
    if "collection_status" not in data and "collection_issues" not in data:
        return {}
    status = _text(data.get("collection_status"))
    issues = _object(data.get("collection_issues"))
    counts = [_count(value) for value in issues.values()]
    expected = "partial" if any(counts) else "complete"
    _require(status == expected, "inconsistent collection status")
    return {"collection_status": status, "collection_issues": issues}


def _sessions(path: str, root: Path) -> tuple[list[Payload], Payload, int]:
    data, provenance = _read(path)
    _require(data.get("conversation_scope") == "projects", "requires projects conversation_scope")
    repos = _list(data.get("repos"))
    _require(len(repos) == 1, "requires exactly one repo")
    _local_scope(repos[0], root)
    _local_scope(data.get("repo"), root)
    _text(data.get("generated_at"))
    _count(data.get("window_days"))
    _object(data.get("sources"))
    stats = _object(data.get("stats"))
    sessions = _list(data.get("sessions"))
    _require(_count(stats.get("sessions_considered")) == len(sessions), "session count mismatch")
    _count(stats.get("sessions_sampled"))
    _count(stats.get("sessions_in_scope"))
    metadata = {
        key: data[key]
        for key in (
            "generated_at",
            "conversation_scope",
            "repo",
            "repos",
            "window_days",
            "sources",
            "stats",
        )
    }
    metadata.update(_collection_metadata(data))
    return _session_rows(data, provenance), {**provenance, "metadata": metadata}, len(sessions)


def _native_id(value: Any) -> str:
    text = _text(value)
    _require(
        text.isascii() and text.isdecimal() and int(text) > 0, "requires positive native ID text"
    )
    _require(str(int(text)) == text, "native ID must not have leading zeros")
    return text


def _observation(record: Any, item: Payload) -> tuple[Payload, int]:
    record = _object(record)
    identity = _text(record.get("id"))
    kind = item["kind"]
    field = HOSTED_SIGNALS[kind][1]
    value = _text(record.get(field))
    normalized = {"id": identity, field: value}
    if kind == "azure_devops_work_item":
        target = _text(record.get("to_state"))
        categories = _state_categories(item["collection"])
        _require(value in categories and target in categories, "unmapped work-item state")
        normalized["to_state"] = target
        return normalized, int(categories[value] == "completed" and categories[target] == "active")
    expected = {
        "github_pull_request": "CHANGES_REQUESTED",
        "github_issue": "reopened",
        "azure_devops_pull_request": "active",
    }
    return normalized, int(value == expected[kind])


def _state_categories(collection: Payload) -> Payload:
    categories = _object(collection.get("state_categories"))
    _require(bool(categories), "requires explicit state_categories")
    _require(
        all(v in ("completed", "active", "other") for v in categories.values()),
        "unsupported state category",
    )
    return categories


def _successful(value: Payload) -> None:
    _require("error" not in value and "errors" not in value, "export contains a source error")
    if "complete" in value:
        _require(value["complete"] is True, "export explicitly declares incomplete data")
    if "status_code" in value:
        status = value["status_code"]
        _require(type(status) is int and 200 <= status < 300, "export has unsuccessful response")


def _page_records(page: Payload, item: Payload, seen: Payload) -> tuple[list[Payload], int]:
    records = []
    count = 0
    for value in _list(page.get("records")):
        record, signal = _observation(value, item)
        previous = seen.get(record["id"])
        _require(previous is None or previous == record, "conflicting duplicate observation")
        count += signal if previous is None else 0
        seen[record["id"]] = record
        records.append(record)
    return records, count


def _collection(item: Payload) -> tuple[Payload, int, int]:
    collection = _object(item.get("collection"))
    _successful(collection)
    url = _scoped_url(collection.get("url"), item["scope"])
    pages = _list(collection.get("pages"))
    _require(bool(pages), "requires a pagination chain, including an empty terminal page")
    expected: str | None = url
    requests: set[str] = set()
    seen: Payload = {}
    normalized = []
    count = 0
    for page in pages:
        page = _object(page)
        _successful(page)
        request = _scoped_url(page.get("request"), item["scope"], page=True)
        _require(request == expected and request not in requests, "broken or cyclic page chain")
        requests.add(request)
        _require("next" in page, "page needs explicit next, null at termination")
        expected = page["next"]
        if expected is not None:
            expected = _scoped_url(expected, item["scope"], page=True)
        records, signals = _page_records(page, item, seen)
        count += signals
        normalized_page = {"request": request, "next": expected, "records": records}
        if "status_code" in page:
            normalized_page["status_code"] = page["status_code"]
        normalized.append(normalized_page)
    _require(expected is None, "partial pagination chain")
    result: Payload = {"url": url, "pages": normalized}
    if item["kind"] == "azure_devops_work_item":
        result["state_categories"] = _state_categories(collection)
    return result, count, len(seen)


def _hosted_item(item: Any, context: Payload) -> tuple[Payload, int]:
    item = _object(item)
    _successful(item)
    kind = _text(item.get("kind"))
    _require(kind in HOSTED_SIGNALS, "unsupported hosted kind")
    _require(item.get("scope") == context["scope"], "item scope mismatch")
    identity = [kind, context["scope"], _native_id(item.get("id"))]
    source = {
        **context["provenance"],
        "locator": context["locator"],
        "url": _scoped_url(item.get("url"), context["scope"]),
    }
    collection, count, records = _collection(item)
    source["collection"] = collection
    row = _seed(identity, HOSTED_SIGNALS[kind][0], count, source)
    observations = {
        record["id"]: record for page in collection["pages"] for record in page["records"]
    }
    row["observations"] = {
        "records": sorted(observations.values(), key=lambda record: record["id"]),
        "url": source["url"],
        "collection_url": collection["url"],
        "state_categories": collection.get("state_categories"),
    }
    return row, records


def _hosted(path: str, root: Path) -> tuple[list[Payload], Payload, int]:
    data, provenance = _read(path)
    _successful(data)
    _require(
        type(data.get("schema_version")) is int and data["schema_version"] == 1,
        "unsupported hosted schema_version",
    )
    _local_scope(data.get("repo"), root)
    scope = _url(data.get("scope"))
    _require(not urlsplit(scope).query and not scope.endswith("/"), "scope must be a base URL")
    _require(
        len(urlsplit(scope).path.strip("/").split("/")) >= 2, "requires repository/project scope"
    )
    items = _list(data.get("items"))
    rows = []
    records = 0
    for index, item in enumerate(items):
        row, examined = _hosted_item(
            item,
            {
                "scope": scope,
                "provenance": provenance,
                "locator": f"/items/{index}",
            },
        )
        rows.append(row)
        records += examined
    return (
        rows,
        {
            **provenance,
            "metadata": {
                "schema_version": 1,
                "repo": data["repo"],
                "scope": scope,
            },
        },
        records,
    )


def import_seeds(root: Path, sessions: str | None, hosted: list[str]) -> Payload:
    """Validate all supplied evidence before returning additive candidate fields.

    Zero rows participate in conflict detection but never become candidates.
    No top-N truncation applies: evidence sources must not disappear at a cutoff.
    """
    rows: list[Payload] = []
    inputs: list[Payload] = []
    counters = {"seed_sessions": 0, "seed_hosted_items": 0, "seed_records": 0}
    if sessions is not None:
        found, source, examined = _sessions(sessions, root)
        rows.extend(found)
        inputs.append(source)
        counters["seed_sessions"] = examined
    for path in hosted:
        found, source, examined = _hosted(path, root)
        rows.extend(found)
        inputs.append(source)
        counters["seed_hosted_items"] += len(found)
        counters["seed_records"] += examined
    candidates = [row for row in _merge(rows) if row["count"] > 0]
    counters["seed_candidates"] = len(candidates)
    return {"candidate_seeds": candidates, "seed_inputs": inputs, "examined": counters}
