#!/usr/bin/env python3
"""Cluster repeated human review interventions on agent pull requests.

A repeated human correction is evidence that no artifact carries the lesson.
This module counts repeats from explicit signals only. It never compares
free text, so every count is reproducible from the inputs.

Cluster definition (fixed before the first run; do not tune after seeing results)
----------------------------------------------------------------------------------
Intervention
    The first comment of a review thread, written by a human, on a pull
    request opened by an agent. The caller filters to that population and
    passes one record per thread. A later reply in a thread is not a new
    intervention.

Signals (all explicit)
    rule         A rule citation in the comment body: ``ADR-NNN``, or a
                 path of the form ``rules/<name>.md``.
    area         The directory of the commented file, cut to the first
                 ``AREA_DEPTH`` path segments. A thread with no path has no
                 area signal.
    disposition  The ``disposition`` value of a suppressed-finding entry.
                 The disposition file records no pull request and no date.
                 It cannot join the window or the distinct-PR count, so
                 this signal counts distinct entries over the whole file.

Cluster
    One ``(signal, key)`` pair seen on at least ``THRESHOLD`` distinct pull
    requests (for ``disposition``: ``THRESHOLD`` distinct entries). Two
    interventions on one pull request count once. Only interventions created
    in the trailing ``WINDOW_DAYS`` days count. ``THRESHOLD`` is 3.

What the output proves
    A cluster proves the same explicit marker recurred on three or more
    pull requests. It does not prove the corrections were about the same
    defect. A reader judges that from the evidence list. An ``area`` cluster
    in a busy directory can be volume, not a recurring lesson.

The output always carries an ``examined`` block, so a result of zero clusters
reads as zero clusters in N interventions, not as "nothing was looked at".

Functions raise ``ValueError`` on malformed input rather than skipping it.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

Payload = dict[str, Any]

THRESHOLD = 3
WINDOW_DAYS = 90
AREA_DEPTH = 4
ROOT_AREA = "(repo root)"

SIGNAL_RULE = "rule"
SIGNAL_AREA = "area"
SIGNAL_DISPOSITION = "disposition"

_ADR_RE = re.compile(r"\bADR[- ]?(\d{2,4})\b", re.IGNORECASE)
_RULE_PATH_RE = re.compile(r"\brules/([a-z0-9][a-z0-9-]*)\.md\b")


def rules_cited(body: str) -> list[str]:
    """Return the sorted distinct rule keys cited in ``body``.

    Keys are ``ADR-NNN`` (zero padded to three digits) and ``rules/<name>``.
    """
    keys = {f"ADR-{int(n):03d}" for n in _ADR_RE.findall(body)}
    keys.update(f"rules/{name}" for name in _RULE_PATH_RE.findall(body))
    return sorted(keys)


def file_area(path: str | None) -> str | None:
    """Return the area of ``path``, or None when the thread has no path."""
    if not path:
        return None
    parts = [p for p in path.replace("\\", "/").split("/") if p and p != "."]
    directory = parts[:-1]
    if not directory:
        return ROOT_AREA
    return "/".join(directory[:AREA_DEPTH])


def parse_timestamp(value: object) -> datetime:
    """Parse an ISO 8601 timestamp, treating a naive value as UTC."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"timestamp must be a non-empty string, got {value!r}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"unparseable timestamp {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _intervention_fields(item: object, index: int) -> tuple[int, str, datetime, str, str | None]:
    where = f"intervention {index}"
    if not isinstance(item, Mapping):
        raise ValueError(f"{where} is not an object")
    pr = item.get("pr")
    if not isinstance(pr, int) or isinstance(pr, bool) or pr < 0:
        raise ValueError(f"{where} needs an integer `pr`")
    thread = item.get("thread_id")
    if not isinstance(thread, str) or not thread:
        raise ValueError(f"{where} needs a string `thread_id`")
    body = item.get("body")
    if not isinstance(body, str):
        raise ValueError(f"{where} needs a string `body`")
    path = item.get("path")
    if path is not None and not isinstance(path, str):
        raise ValueError(f"{where} has a non-string `path`")
    created = parse_timestamp(item.get("created_at"))
    return pr, thread, created, body, path


def _disposition_categories(dispositions: Mapping[str, Any] | None) -> dict[str, list[str]]:
    """Group disposition entry keys by their ``disposition`` value."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for key, entry in (dispositions or {}).items():
        if not isinstance(entry, Mapping):
            raise ValueError(f"disposition {key!r} is not an object")
        category = entry.get("disposition")
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"disposition {key!r} needs a non-empty `disposition`")
        grouped[category.strip()].append(str(key))
    return grouped


def cluster_interventions(
    interventions: Iterable[Mapping[str, Any]],
    dispositions: Mapping[str, Any] | None = None,
    *,
    now: datetime,
    window_days: int = WINDOW_DAYS,
    threshold: int = THRESHOLD,
) -> Payload:
    """Cluster interventions and dispositions by explicit signal.

    Args:
        interventions: One record per human-opened review thread on an agent
            pull request: ``pr``, ``thread_id``, ``created_at``, ``body``,
            ``path`` (or None).
        dispositions: The suppressed-finding disposition registry, or None.
        now: The reference time. The window is ``[now - window_days, now]``
            at the lower edge only; later timestamps count.
        window_days: Window length in days.
        threshold: Minimum distinct pull requests (or entries) per cluster.

    Returns:
        ``{"window_days", "threshold", "examined", "clusters", "cluster_count"}``.
        ``clusters`` holds ``signal``, ``key``, ``unit``, ``count`` and
        ``evidence`` per cluster, ordered by descending count then key.
    """
    if threshold < 1 or window_days < 1:
        raise ValueError("threshold and window_days must be at least 1")
    cutoff = now - timedelta(days=window_days)

    total = 0
    in_window = 0
    seen_threads: set[tuple[int, str]] = set()
    by_key: dict[tuple[str, str], dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))

    for index, item in enumerate(interventions):
        total += 1
        pr, thread, created, body, path = _intervention_fields(item, index)
        if (pr, thread) in seen_threads:
            raise ValueError(f"duplicate thread {thread!r} on pull request {pr}")
        seen_threads.add((pr, thread))
        if created < cutoff:
            continue
        in_window += 1
        for rule in rules_cited(body):
            by_key[(SIGNAL_RULE, rule)][pr].add(thread)
        area = file_area(path)
        if area is not None:
            by_key[(SIGNAL_AREA, area)][pr].add(thread)

    clusters: list[Payload] = []
    for (signal, key), prs in by_key.items():
        if len(prs) >= threshold:
            clusters.append(
                {
                    "signal": signal,
                    "key": key,
                    "unit": "pull_request",
                    "count": len(prs),
                    "evidence": [
                        {"pr": pr, "threads": sorted(threads)}
                        for pr, threads in sorted(prs.items())
                    ],
                }
            )

    grouped = _disposition_categories(dispositions)
    for category, keys in grouped.items():
        if len(keys) >= threshold:
            clusters.append(
                {
                    "signal": SIGNAL_DISPOSITION,
                    "key": category,
                    "unit": "disposition_entry",
                    "count": len(keys),
                    "evidence": [{"entry": k} for k in sorted(keys)],
                }
            )

    clusters.sort(key=lambda c: (-c["count"], c["signal"], c["key"]))
    return {
        "window_days": window_days,
        "threshold": threshold,
        "examined": {
            "interventions": total,
            "interventions_in_window": in_window,
            "dispositions": sum(len(v) for v in grouped.values()),
        },
        "clusters": clusters,
        "cluster_count": len(clusters),
    }
