"""Parse gist URLs and build safe GitHub API commands."""

from __future__ import annotations

import json
import re
import shlex
from typing import Any
from urllib.parse import SplitResult, parse_qs, unquote, urlsplit, urlunsplit

from url_validation import (
    SAFE_GIST_ID_RE,
    SAFE_GIST_REVISION_RE,
    SAFE_OWNER_REPO_RE,
    is_safe_input,
    is_safe_raw_path,
)

GIST_SUFFIXES = {"revisions"}
GIST_HOSTS = {"gist.github.com", "gist.githubusercontent.com"}


def _parse_url(url: str) -> SplitResult | None:
    if any(ord(character) < 32 or ord(character) == 127 for character in url):
        return None
    try:
        return urlsplit(url)
    except ValueError:
        return None


def _classify_path(
    parsed_url: SplitResult,
    segments: list[str],
) -> tuple[str | None, str, list[str]] | None:
    raw_content_url = parsed_url.netloc == "gist.githubusercontent.com"
    if raw_content_url:
        if len(segments) < 3 or segments[2] != "raw":
            return None
        return segments[0], segments[1], segments[2:]

    ownerless_with_suffix = (
        len(segments) > 1
        and is_safe_input(segments[0], SAFE_GIST_ID_RE)
        and (
            segments[1] in GIST_SUFFIXES
            or is_safe_input(segments[1], SAFE_GIST_REVISION_RE)
        )
    )
    if len(segments) == 1 or ownerless_with_suffix:
        return None, segments[0], segments[1:]
    return segments[0], segments[1], segments[2:]


def _parse_non_raw_selector(selector_segments: list[str]) -> tuple[str | None, bool]:
    if not selector_segments:
        return None, True
    selector = selector_segments[0]
    if selector == "revisions":
        return None, len(selector_segments) == 1
    if is_safe_input(selector, SAFE_GIST_REVISION_RE):
        return selector, len(selector_segments) == 1
    return None, False


def _parse_page_file_selector(
    parsed_url: SplitResult,
    embed_url: bool,
) -> tuple[str | None, str | None, str | None] | None:
    if embed_url:
        query_files = parse_qs(
            parsed_url.query,
            keep_blank_values=True,
        ).get("file", [])
        if len(query_files) > 1 or (query_files and not query_files[0]):
            return None
        if query_files:
            # Reject ambiguous selector: ?file= and #file- both present.
            if parsed_url.fragment.startswith("file-"):
                return None
            return query_files[0], None, None
    if not parsed_url.fragment.startswith("file-"):
        return None, None, None

    requested_file_slug = unquote(parsed_url.fragment.removeprefix("file-"))
    # Reject empty or control-character-containing decoded selectors.
    if not requested_file_slug or any(
        ord(c) < 32 or ord(c) == 127 for c in requested_file_slug
    ):
        return None
    requested_file_base_slug = re.sub(
        r"-L\d+(?:-L\d+)?$",
        "",
        requested_file_slug,
    )
    return None, requested_file_slug, requested_file_base_slug


def _parse_location(
    url: str,
) -> tuple[SplitResult, str | None, str, list[str], bool] | None:
    parsed_url = _parse_url(url)
    if parsed_url is None:
        return None
    if parsed_url.scheme not in {"http", "https"}:
        return None
    if parsed_url.netloc not in GIST_HOSTS:
        return None

    segments = [segment for segment in parsed_url.path.split("/") if segment]
    if not segments:
        return None
    classified = _classify_path(parsed_url, segments)
    if classified is None:
        return None
    owner, gist_id, selector_segments = classified

    embed_url = gist_id.endswith(".js")
    gist_id = gist_id.removesuffix(".js")
    if owner is not None and not is_safe_input(owner, SAFE_OWNER_REPO_RE):
        return None
    if not is_safe_input(gist_id, SAFE_GIST_ID_RE):
        return None
    return parsed_url, owner, gist_id, selector_segments, embed_url


def _parse_content_selector(
    parsed_url: SplitResult,
    selector_segments: list[str],
    embed_url: bool,
) -> tuple[str | None, str | None, str | None, str | None, str | None] | None:
    raw_request = parsed_url.netloc == "gist.githubusercontent.com" or (
        bool(selector_segments) and selector_segments[0] == "raw"
    )
    if raw_request:
        if parsed_url.query or parsed_url.fragment:
            return None
        if not is_safe_raw_path(selector_segments[1:]):
            return None
        raw_url = urlunsplit(
            ("https", parsed_url.netloc, parsed_url.path, "", "")
        )
        return raw_url, None, None, None, None

    revision, valid_selector = _parse_non_raw_selector(selector_segments)
    if not valid_selector:
        return None
    file_selector = _parse_page_file_selector(parsed_url, embed_url)
    if file_selector is None:
        return None
    requested_file, requested_file_slug, requested_file_base_slug = file_selector
    return (
        None,
        revision,
        requested_file,
        requested_file_slug,
        requested_file_base_slug,
    )


def parse_gist_url(url: str) -> dict[str, Any] | None:
    """Parse a gist URL and preserve immutable content selectors."""
    location = _parse_location(url)
    if location is None:
        return None
    parsed_url, owner, gist_id, selector_segments, embed_url = location
    content = _parse_content_selector(parsed_url, selector_segments, embed_url)
    if content is None:
        return None
    (
        raw_url,
        revision,
        requested_file,
        requested_file_slug,
        requested_file_base_slug,
    ) = content

    return {
        "owner": owner,
        "repo": None,
        "url_type": "Gist",
        "resource_id": gist_id,
        "raw_url": raw_url,
        "revision": revision,
        "requested_file": requested_file,
        "requested_file_slug": requested_file_slug,
        "requested_file_base_slug": requested_file_base_slug,
        "ref": None,
        "path": None,
        "fragment_type": None,
        "fragment_id": None,
    }


def _file_slug_query(requested_file_slug: str, requested_file_base_slug: str) -> str:
    slug = json.dumps(requested_file_slug.lower())
    base_slug = json.dumps(requested_file_base_slug.lower())
    selected_slug = base_slug if base_slug != slug else slug
    return (
        'def slug: ascii_downcase | gsub("[^a-z0-9_-]+"; "-") '
        '| sub("^-+"; "") | sub("-+$"; ""); '
        ".files | to_entries | "
        f'map(select((.key | slug) == {selected_slug})) | '
        'if length == 1 then .[0].value else error("ambiguous or missing file selector") end'
    )


def build_gist_command(parsed: dict[str, Any]) -> str:
    """Build a shell-safe gh command for a parsed gist URL."""
    raw_url = parsed.get("raw_url")
    if raw_url:
        return f"gh api {shlex.quote(raw_url)}"

    endpoint = f"gists/{parsed['resource_id']}"
    revision = parsed.get("revision")
    if revision:
        endpoint = f"{endpoint}/{revision}"
    command = f'gh api "{endpoint}"'

    requested_file = parsed.get("requested_file")
    if requested_file:
        jq_query = f".files[{json.dumps(requested_file)}]"
        return f"{command} --jq {shlex.quote(jq_query)}"

    requested_file_slug = parsed.get("requested_file_slug")
    if requested_file_slug:
        jq_query = _file_slug_query(
            requested_file_slug,
            parsed.get("requested_file_base_slug", ""),
        )
        return f"{command} --jq {shlex.quote(jq_query)}"
    return command
