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

Selection: the first release, in the API's newest-first order, that is neither a
draft nor a prerelease and is not the tag being promoted, and that holds a usable
asset of that name (the newest ``created_at`` if it holds several). An asset counts only
when it is ``uploaded``, no larger than ``MAX_MANIFEST_BYTES``, and was uploaded
by ``github-actions[bot]``, the identity the workflow token carries.

The chosen asset is parsed with ``parse_previous_manifest`` from
``scripts/validation/promotion_findings.py``, which requires "an enforced
``promote`` verdict". The parse uses the gate's own strict loader
(``parse_previous_manifest_bytes``). Releases are read newest first and reading
stops at the first page that holds a usable asset. A newest asset that fails to
parse raises: silently falling back to an older one would report fixes against a
stale baseline.

Stricter/looser/different than canonical: the uploader check is added here. Any
workflow in this repository with ``contents: write`` could upload under that
login, so it narrows who can write a baseline to the repository's own Actions
token, not to the one release job. The baseline feeds only the non-blocking
``remediated`` class, so a forged one cannot unblock a promotion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.validation.promotion_fetch import GitHubApiError, GitHubReader
from scripts.validation.promotion_findings import ManifestError, parse_previous_manifest_bytes

MANIFEST_ASSET_NAME = "promotion-manifest.json"
MANIFEST_FILE_NAME = MANIFEST_ASSET_NAME
NO_BASELINE_FILE = "no-baseline.json"
PAGE_SIZE = 100
MAX_PAGES = 20
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
    """Return the manifest asset of the first usable release, or None for a first promotion.

    ``releases`` is in the API's order, newest release first, so the first release
    holding a usable manifest is the most recent promotion. Within that release the
    newest asset wins. An older release that gains a manifest later does not
    displace a newer release's.
    """
    for release in releases:
        if not isinstance(release, dict):
            continue
        if release.get("draft") is not False or release.get("prerelease") is not False:
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or tag == exclude_tag:
            continue
        assets = release.get("assets")
        candidates = (
            [_asset_candidate(item, tag) for item in assets] if isinstance(assets, list) else []
        )
        found = [candidate for candidate in candidates if candidate is not None]
        if found:
            return _newest(found)
    return None


def _newest(found: list[BaselineAsset]) -> BaselineAsset:
    try:
        return max(found, key=lambda item: item.created_at)
    except TypeError as exc:  # naive and aware times cannot be ordered
        raise GitHubApiError("release asset times cannot be compared") from exc


def _find_baseline(reader: GitHubReader, repo: str, exclude_tag: str) -> BaselineAsset | None:
    """Read release pages newest first and stop at the first page holding a usable asset."""
    path = f"repos/{repo}/releases"
    for page in range(1, MAX_PAGES + 1):
        body = reader.get_json(path, {"per_page": str(PAGE_SIZE), "page": str(page)})
        if not isinstance(body, list):
            raise GitHubApiError(f"{path} did not return a list")
        chosen = select_baseline(body, exclude_tag)
        if chosen is not None:
            return chosen
        if len(body) < PAGE_SIZE:
            return None
    limit = MAX_PAGES * PAGE_SIZE
    raise GitHubApiError(f"{path} has more than {limit} releases without a baseline")


def fetch_baseline(
    reader: GitHubReader, *, repo: str, exclude_tag: str, output_dir: Path
) -> BaselineAsset | None:
    """Write the previous promoted manifest, or the no-baseline marker, into ``output_dir``.

    Exactly one of ``promotion-manifest.json`` and ``no-baseline.json`` is written
    on success, so the gate can tell a first promotion from a step that never ran.
    Raises ``GitHubApiError`` when GitHub cannot answer, and ``ManifestError``
    when the chosen asset is not a promoted manifest.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    # A reused directory must not carry an earlier run's answer into this one, even
    # when this run then fails, so the files go before anything can raise.
    for stale in (MANIFEST_FILE_NAME, NO_BASELINE_FILE):
        (output_dir / stale).unlink(missing_ok=True)
    chosen = _find_baseline(reader, repo, exclude_tag)
    if chosen is None:
        (output_dir / NO_BASELINE_FILE).write_text('{"baseline": "none"}\n', encoding="utf-8")
        return None
    body = reader.get_bytes(f"repos/{repo}/releases/assets/{chosen.asset_id}", OCTET_STREAM)
    if len(body) > MAX_MANIFEST_BYTES:
        raise ManifestError(f"the previous manifest is larger than {MAX_MANIFEST_BYTES} bytes")
    parse_previous_manifest_bytes(body)
    (output_dir / MANIFEST_FILE_NAME).write_bytes(body)
    return chosen
