from __future__ import annotations

import subprocess
from typing import Any

from github_core.bot_config import canonicalize_login, is_bot

JsonObject = dict[str, Any]
FOCUSED_JSON_FIELDS = {
    "author_is_bot": ("author",),
    "auto_merge_method": ("autoMergeRequest",),
}


def context_fetch_failure_message(
    result: subprocess.CompletedProcess[str],
    command: str,
) -> str:
    message = (result.stderr or result.stdout).strip()
    if message:
        return message
    return f"{command} exited with return code {result.returncode} and no error output"


def record_context_fetch_failure(
    data: dict[str, object],
    field: str,
    result: subprocess.CompletedProcess[str],
    command: str,
) -> None:
    failures = data.get("context_fetch_failures")
    if not isinstance(failures, list):
        failures = []
        data["context_fetch_failures"] = failures
    failures.append({
        "field": field,
        "message": context_fetch_failure_message(result, command),
    })


def author_is_bot(author: object) -> bool | None:
    """Classify the PR author as a bot, or return None when it cannot be read.

    Canonical rule, `scripts/github_core/bot_config.py:328`, verbatim:
    `def is_bot(login: str, user_type: str | None = None) -> bool:`. `canonicalize_login`
    (line 309) runs first so `app/copilot-swe-agent` and `Copilot`, the spellings this repo's
    own bot PRs arrive under, reach it as `[bot]` logins; GitHub's flag feeds `user_type`.

    Stricter/looser/different than canonical. *Stricter input boundary*: canonical takes
    `login: str` and classifies anything, so `"   "` came back a real `False`; this takes
    `author: object` and refuses a non-dict, an empty or non-`str` login, and any login
    bearing whitespace, reclassifying no known bot (no canonical name has any). *Tri-state
    return*: canonical always returns `bool`; this returns `bool | None`, `None` for every
    input that boundary refuses, so a caller fails closed rather than an unearned `False`.
    """
    if not isinstance(author, dict):
        return None
    login = author.get("login")
    if not isinstance(login, str) or not login or any(c.isspace() for c in login):
        return None
    user_type = "Bot" if author.get("is_bot") is True else None
    return bool(is_bot(canonicalize_login(login), user_type))


def selected_fields(requested: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(requested))


def requested_json_fields(selected: tuple[str, ...], default_fields: str) -> str:
    if not selected:
        return default_fields

    seen: set[str] = set()
    json_fields: list[str] = []
    for field in selected:
        for json_field in FOCUSED_JSON_FIELDS[field]:
            if json_field in seen:
                continue
            seen.add(json_field)
            json_fields.append(json_field)
    return ",".join(json_fields)


def focused_context(pr_data: JsonObject, selected: tuple[str, ...]) -> dict[str, object]:
    data: dict[str, object] = {}
    for field in selected:
        if field == "author_is_bot":
            data[field] = author_is_bot(pr_data.get("author"))
        elif field == "auto_merge_method":
            auto_merge = pr_data.get("autoMergeRequest")
            data[field] = auto_merge.get("mergeMethod") if isinstance(auto_merge, dict) else None
    return data
