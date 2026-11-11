#!/usr/bin/env python3
"""Review-friction signals for bootstrap_mine.py: repeated failures and missed items.

Both signals come from optional fields of the `--prs-json` host export. They
use explicit evidence only: a rule citation, a file path, a disposition
category, or a fix-to-introducer link a person wrote. They never compare free
text, so a result is reproducible from the export.

Repeated failures
    Human review threads grouped by `review_clusters`: the same rule cited, the
    same file area, or the same disposition category, on at least
    `review_clusters.THRESHOLD` distinct pull requests inside the trailing
    `review_clusters.WINDOW_DAYS` days. The export defines the population: it
    lists the pull requests, and each thread says whether a human opened it.

Missed items
    Fix pull requests that name the change that introduced the defect, counted
    per file area of the introducing change. A link is `introduced_by` on the
    export item, or a phrase in the description or a commit message of the form
    `introduced by #N`, `caused by #N`, `broken by #N`, `regressed in #N`, or
    `regression of #N`. An introducer that is not in the export, or has no
    `files`, is counted as unresolved and gives no area.

What the output proves
    A cluster proves the same marker recurred on three or more pull requests.
    A missed item proves a person linked a fix to an earlier change. Neither
    proves the corrections shared a cause, that review should have caught the
    defect, or that the introducing change caused it. Read the evidence before
    a skill repeats a case.

Stdlib only, so the script runs from any plugin root. It does not read the
repository or the network.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

import review_clusters

Payload = dict[str, Any]

_INTRODUCER_RE = re.compile(
    r"\b(?:introduced|caused|broken|regressed)\s+(?:by|in)\s+(?:PR\s*)?#(\d+)"
    r"|\bregression\s+(?:of|from|in)\s+(?:PR\s*)?#(\d+)",
    re.IGNORECASE,
)


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _strings(value: object, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{where} must be a list of strings")
    return list(value)


def _thread_row(item_no: int, number: int, raw: object, index: int) -> Payload:
    where = f"item {item_no} review_threads[{index}]"
    if not isinstance(raw, Mapping):
        raise ValueError(f"{where} is not an object")
    thread_id = raw.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        raise ValueError(f"{where} needs a string `thread_id`")
    if not isinstance(raw.get("human"), bool):
        raise ValueError(f"{where} needs a boolean `human`")
    body = raw.get("body")
    if body is None:
        body = ""
    if not isinstance(body, str):
        raise ValueError(f"{where} has a non-string `body`")
    path = raw.get("path")
    if path is not None and not isinstance(path, str):
        raise ValueError(f"{where} has a non-string `path`")
    return {
        "pr": number,
        "thread_id": thread_id,
        "created_at": raw.get("created_at"),
        "body": body,
        "path": path,
        "human": raw["human"],
    }


def _links(item: Mapping[str, Any], item_no: int, number: int) -> set[int]:
    found: set[int] = set()
    declared = item.get("introduced_by", [])
    if not isinstance(declared, list) or not all(_count(v) for v in declared):
        raise ValueError(f"item {item_no} introduced_by must be a list of pull request numbers")
    found.update(declared)
    description = item.get("body")
    if description is not None and not isinstance(description, str):
        raise ValueError(f"item {item_no} has a non-string `body`")
    texts = [description or ""]
    texts.extend(_strings(item.get("commit_messages", []), f"item {item_no} commit_messages"))
    for text in texts:
        for match in _INTRODUCER_RE.finditer(text):
            found.add(int(match.group(1) or match.group(2)))
    found.discard(number)
    return found


def _areas(files: Sequence[str]) -> list[str]:
    seen = {review_clusters.file_area(f) for f in files}
    return sorted(a for a in seen if a is not None)


def mine_review_signals(
    items: Sequence[Mapping[str, Any]],
    *,
    as_of: datetime | None = None,
    dispositions: Mapping[str, Any] | None = None,
) -> tuple[Payload, Payload]:
    """Return ``(review_failures, missed_items)`` for the export items.

    Raises ValueError when an optional review field is malformed, so a bad
    export fails loud and is never read as "no signal".
    """
    now = as_of or datetime.now(timezone.utc)
    interventions: list[Payload] = []
    files_by_pr: dict[int, list[str]] = {}
    links_by_pr: dict[int, set[int]] = {}
    prs_with_threads = threads_total = human_threads = 0
    for item_no, item in enumerate(items):
        number = item.get("number")
        if not _count(number):
            raise ValueError(f"item {item_no} needs an integer `number`")
        threads = item.get("review_threads")
        if threads is not None:
            if not isinstance(threads, list):
                raise ValueError(f"item {item_no} review_threads must be a list")
            prs_with_threads += 1
            for index, raw in enumerate(threads):
                row = _thread_row(item_no, number, raw, index)
                threads_total += 1
                if row.pop("human"):
                    human_threads += 1
                    interventions.append(row)
        files = item.get("files")
        if files is not None:
            files_by_pr[number] = _strings(files, f"item {item_no} files")
        links = _links(item, item_no, number)
        if links:
            links_by_pr[number] = links

    clustered = review_clusters.cluster_interventions(interventions, dispositions, now=now)
    clustered["examined"].update(
        {
            "prs": len(items),
            "prs_with_threads": prs_with_threads,
            "threads": threads_total,
            "human_threads": human_threads,
        }
    )
    clustered["as_of"] = now.isoformat()
    clustered["thread_data_provided"] = prs_with_threads > 0
    return clustered, _missed_items(len(items), files_by_pr, links_by_pr)


def _missed_items(
    pr_count: int, files_by_pr: Mapping[int, list[str]], links_by_pr: Mapping[int, set[int]]
) -> Payload:
    by_area: dict[str, dict[str, set[int]]] = defaultdict(
        lambda: {"fix": set(), "introducer": set()}
    )
    resolved = unresolved = 0
    for fix_pr, introducers in sorted(links_by_pr.items()):
        for introducer in sorted(introducers):
            areas = _areas(files_by_pr.get(introducer, []))
            if not areas:
                unresolved += 1
                continue
            resolved += 1
            for area in areas:
                by_area[area]["fix"].add(fix_pr)
                by_area[area]["introducer"].add(introducer)
    rows = [
        {
            "area": area,
            "count": len(sets["fix"]),
            "fix_prs": sorted(sets["fix"]),
            "introducer_prs": sorted(sets["introducer"]),
        }
        for area, sets in by_area.items()
    ]
    rows.sort(key=lambda r: (-r["count"], r["area"]))
    return {
        "areas": rows,
        "area_count": len(rows),
        "examined": {
            "prs": pr_count,
            "prs_with_files": len(files_by_pr),
            "fix_links": resolved + unresolved,
            "fix_links_resolved": resolved,
            "fix_links_unresolved": unresolved,
        },
    }
