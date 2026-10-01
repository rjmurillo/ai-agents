#!/usr/bin/env python3
"""Find and download the previous promoted manifest from a GitHub Release.

ADR-113 Resolved Question 3 (decision D21), issue #5636. Quoted from
``.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md``:

    "A GitHub Release holds it as a release asset. The release step runs in a
    narrowly scoped job with `contents: write`. [...] It runs only after a
    promoted publish, so a failed run never becomes the baseline."

and decision 9: "The baseline for `remediated` is the previous promoted manifest,
kept as a release asset. It affects only this non-blocking class. The first
promotion has no baseline, so it reports no `remediated` findings."

The asset name is ``promotion-manifest.json``, the file the ``release-manifest``
job in ``.github/workflows/promotion-gate.yml`` uploads with
``gh release upload "$RELEASE_TAG" "$RUNNER_TEMP/manifest/promotion-manifest.json"``.

Selection: among releases that are not drafts and not the tag being promoted,
take the asset of that name with the newest ``created_at``. An asset counts only
when it is ``uploaded``, no larger than ``MAX_MANIFEST_BYTES``, and was uploaded
by ``github-actions[bot]``, the identity the workflow token carries.

The chosen asset is parsed with ``parse_previous_manifest`` from
``scripts/validation/promotion_findings.py``, which requires "an enforced
``promote`` verdict". A newest asset that fails to parse raises: silently falling
back to an older one would report fixes against a stale baseline.

Stricter/looser/different than canonical: the uploader check is added here. Any
workflow in this repository with ``contents: write`` could upload under that
login, so it narrows who can write a baseline to the repository's own Actions
token, not to the one release job. The baseline feeds only the non-blocking
``remediated`` class, so a forged one cannot unblock a promotion.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.validation.promotion_fetch import GitHubApiError, GitHubReader, paginate
from scripts.validation.promotion_findings import ManifestError, parse_previous_manifest

MANIFEST_ASSET_NAME = "promotion-manifest.json"
MANIFEST_FILE_NAME = MANIFEST_ASSET_NAME
UPLOADER_LOGIN = "github-actions[bot]"
MAX_MANIFEST_BYTES = 1_048_576
OCTET_STREAM = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class BaselineAsset:
    """The release asset chosen as the previous promoted manifest."""

    tag: str
    asset_id: int
    created_at: datetime


def _int_id(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _asset_candidate(asset: object, tag: str) -> BaselineAsset | None:
    """Return the asset as a candidate, or None when it cannot be the baseline."""
    if not isinstance(asset, dict) or asset.get("name") != MANIFEST_ASSET_NAME:
        return None
    uploader = asset.get("uploader")
    login = uploader.get("login") if isinstance(uploader, dict) else None
    size, identifier = _int_id(asset.get("size")), _int_id(asset.get("id"))
    created = _instant(asset.get("created_at"))
    ok = (
        asset.get("state") == "uploaded"
        and login == UPLOADER_LOGIN
        and size is not None
        and 0 < size <= MAX_MANIFEST_BYTES
        and identifier is not None
        and created is not None
    )
    return BaselineAsset(tag, identifier, created) if ok and identifier and created else None


def select_baseline(releases: list[Any], exclude_tag: str) -> BaselineAsset | None:
    """Return the newest usable manifest asset across releases, or None for a first promotion."""
    found: list[BaselineAsset] = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") is not False:
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or tag == exclude_tag:
            continue
        assets = release.get("assets")
        for asset in assets if isinstance(assets, list) else []:
            candidate = _asset_candidate(asset, tag)
            if candidate is not None:
                found.append(candidate)
    if not found:
        return None
    try:
        return max(found, key=lambda item: item.created_at)
    except TypeError as exc:  # naive and aware times cannot be ordered
        raise GitHubApiError("release asset times cannot be compared") from exc


def fetch_baseline(
    reader: GitHubReader, *, repo: str, exclude_tag: str, output_dir: Path
) -> BaselineAsset | None:
    """Write the previous promoted manifest into ``output_dir`` and return its asset.

    Returns None, writing nothing, when no release holds a usable manifest.
    Raises ``GitHubApiError`` when GitHub cannot answer, and ``ManifestError``
    when the chosen asset is not a promoted manifest.
    """
    releases = paginate(reader, f"repos/{repo}/releases", None, {})
    chosen = select_baseline(releases, exclude_tag)
    if chosen is None:
        return None
    body = reader.get_bytes(f"repos/{repo}/releases/assets/{chosen.asset_id}", OCTET_STREAM)
    if len(body) > MAX_MANIFEST_BYTES:
        raise ManifestError("the previous manifest is larger than the size cap")
    try:
        document: Mapping[str, Any] = json.loads(body.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise ManifestError(f"the previous manifest is not valid JSON: {exc}") from exc
    parse_previous_manifest(document)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / MANIFEST_FILE_NAME).write_bytes(body)
    return chosen
