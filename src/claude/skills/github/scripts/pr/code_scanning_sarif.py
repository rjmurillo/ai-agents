"""Pure helpers that reduce code-scanning data to rule id, path, and line.

Used by ``get_pr_code_scanning_alerts.py``. Nothing here touches the network or
the filesystem, so every function is testable with plain dicts.

The reduction is a security boundary. A result reaches a reviewing model as
untrusted data (ADR-041 amendment 2026-11-09, rule "Untrusted data"; the rules
file is ``.project-toolkit/analysis/adr-041-review-caller-rules.md``). So this
module passes on three things only: a rule id that matches ``RULE_ID_PATTERN``,
a repository-relative path, and a line number. It never returns a message, a
rule name, or any other free text from the results.

Stricter/looser/different than canonical
========================================
``RULE_ID_PATTERN`` copies the amendment's pattern text
``^[A-Za-z0-9/_.-]{1,100}$``. It is applied with ``fullmatch``, which is
stricter than ``re.match`` on that text: ``$`` also matches before a trailing
newline, so ``match`` would accept ``"rule\\n"``. ``fullmatch`` rejects it.

Standard library only: this module ships in the plugin tree.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

#: The amendment's rule-id pattern, verbatim. Apply it with ``fullmatch``.
RULE_ID_PATTERN = re.compile(r"^[A-Za-z0-9/_.-]{1,100}$")

#: SARIF property GitHub adds to each result in the ``application/sarif+json``
#: media type of ``GET /repos/{owner}/{repo}/code-scanning/analyses/{id}``.
ALERT_NUMBER_PROPERTY = "github/alertNumber"

_MAX_PATH_LENGTH = 1024
_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")

#: One reduced location: repository-relative path and 1-based start line (0 when
#: the location carries no start line).
Location = tuple[str, int]


def is_valid_rule_id(value: object) -> bool:
    """Return True when ``value`` is a string that passes ``RULE_ID_PATTERN``."""
    return isinstance(value, str) and RULE_ID_PATTERN.fullmatch(value) is not None


def normalize_repo_path(raw: object) -> str | None:
    """Return a clean repository-relative POSIX path, or None when unusable.

    Rejects what could point outside the repository or smuggle a different
    meaning to a reader: absolute paths, drive letters, URI schemes, backslashes,
    control characters, and ``..`` segments. A leading ``./`` and doubled slashes
    are folded. None means "cannot be matched to the diff", never "empty path".
    """
    if not isinstance(raw, str) or not raw or len(raw) > _MAX_PATH_LENGTH:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return None
    if "\\" in raw or "://" in raw or raw.startswith("/") or _WINDOWS_DRIVE.match(raw):
        return None
    segments = [segment for segment in raw.split("/") if segment not in ("", ".")]
    if not segments or ".." in segments:
        return None
    return "/".join(segments)


def _location_from_physical(physical: object) -> Location | None:
    """Reduce one SARIF ``physicalLocation`` to ``(path, line)``."""
    if not isinstance(physical, Mapping):
        return None
    artifact = physical.get("artifactLocation")
    uri = artifact.get("uri") if isinstance(artifact, Mapping) else None
    path = normalize_repo_path(uri)
    if path is None:
        return None
    region = physical.get("region")
    line = region.get("startLine") if isinstance(region, Mapping) else None
    return path, line if isinstance(line, int) and not isinstance(line, bool) and line > 0 else 0


def _physical_of(location: object) -> object:
    return location.get("physicalLocation") if isinstance(location, Mapping) else None


def _flow_locations(code_flows: object) -> Iterator[object]:
    """Yield every location wrapper in every thread flow of every code flow."""
    for flow in code_flows if isinstance(code_flows, list) else []:
        thread_flows = flow.get("threadFlows") if isinstance(flow, Mapping) else None
        for thread_flow in thread_flows if isinstance(thread_flows, list) else []:
            steps = thread_flow.get("locations") if isinstance(thread_flow, Mapping) else None
            for step in steps if isinstance(steps, list) else []:
                yield step.get("location") if isinstance(step, Mapping) else None


def sarif_result_locations(result: Mapping[str, Any]) -> list[Location]:
    """Return every usable location of a SARIF result, primary first.

    Order: ``locations`` (primary), ``relatedLocations``, then the steps of each
    ``codeFlows[].threadFlows[].locations[].location``. This is the amendment's
    "any location" scope: primary location, related locations, or code-flow steps.
    A location whose path cannot be normalized is skipped.
    """
    wrappers: list[object] = []
    for key in ("locations", "relatedLocations"):
        value = result.get(key)
        wrappers.extend(value if isinstance(value, list) else [])
    wrappers.extend(_flow_locations(result.get("codeFlows")))
    reduced = (_location_from_physical(_physical_of(wrapper)) for wrapper in wrappers)
    return [location for location in reduced if location is not None]


def sarif_results_by_alert_number(sarif: object) -> dict[int, Mapping[str, Any]]:
    """Index a SARIF document's results by ``github/alertNumber``.

    Raises:
        ValueError: when the document is not a SARIF object with a ``runs`` list.
            A result without a usable alert number is not indexed.
    """
    runs = sarif.get("runs") if isinstance(sarif, Mapping) else None
    if not isinstance(runs, list):
        raise ValueError("SARIF document has no runs list")
    indexed: dict[int, Mapping[str, Any]] = {}
    for run in runs:
        results = run.get("results") if isinstance(run, Mapping) else None
        for result in results if isinstance(results, list) else []:
            number = _alert_number(result)
            if number is not None:
                indexed[number] = result
    return indexed


def _alert_number(result: object) -> int | None:
    properties = result.get("properties") if isinstance(result, Mapping) else None
    number = properties.get(ALERT_NUMBER_PROPERTY) if isinstance(properties, Mapping) else None
    return number if isinstance(number, int) and not isinstance(number, bool) else None


def normalize_changed_files(raw_paths: Iterable[str]) -> frozenset[str]:
    """Normalize the caller's diff file list; unusable entries are ignored.

    An entry that cannot be normalized cannot equal any alert path, so ignoring
    it never attaches a result that is outside the diff.
    """
    paths = (normalize_repo_path(raw) for raw in raw_paths)
    return frozenset(path for path in paths if path is not None)


def first_location_in_diff(
    locations: Iterable[Location], changed_files: frozenset[str]
) -> Location | None:
    """Return the first location whose path the diff touches, else None."""
    return next((loc for loc in locations if loc[0] in changed_files), None)
