"""Read-only PR evidence snapshot.

The parser is tolerant: a missing or wrongly typed field becomes ``None`` and
the engine holds on it. A snapshot is data. Nothing here fetches from GitHub.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")

FILE_STATUSES = frozenset({"added", "modified", "removed", "renamed", "copied", "changed"})
REVIEW_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED", "PENDING"})
MERGEABLE_STATES = frozenset({"MERGEABLE", "CONFLICTING", "UNKNOWN"})


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _table(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(section: dict[str, Any]) -> list[dict[str, Any]] | None:
    items = section.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        return None
    return items


@dataclass(frozen=True)
class ChangedFile:
    path: str | None
    previous_path: str | None
    status: str | None
    additions: int | None
    deletions: int | None
    binary: bool | None
    patch_present: bool | None
    touches_code_fence: bool | None


@dataclass(frozen=True)
class Review:
    reviewer_id: int | None
    state: str | None
    commit_id: str | None


@dataclass(frozen=True)
class Label:
    name: str | None


@dataclass(frozen=True)
class RequiredCheck:
    context: str | None
    app_id: int | None


@dataclass(frozen=True)
class CheckResult:
    context: str | None
    app_id: int | None
    conclusion: str | None
    head_sha: str | None


@dataclass(frozen=True)
class Section(Generic[T]):
    """A list of evidence plus the collector's completeness claim."""

    complete: bool
    items: tuple[T, ...]


@dataclass(frozen=True)
class Snapshot:
    repository_id: int | None
    default_branch: str | None
    default_branch_sha: str | None
    number: int | None
    state: str | None
    draft: bool | None
    head_sha: str | None
    head_repository_id: int | None
    base_ref: str | None
    base_sha: str | None
    merge_base_sha: str | None
    mergeable: str | None
    author_id: int | None
    files: Section[ChangedFile]
    labels: Section[Label]
    reviews: Section[Review]
    unresolved_threads: int | None
    threads_complete: bool
    required_checks: Section[RequiredCheck]
    check_results: Section[CheckResult]
    repo_stop: bool | None


def _section(raw: object, build: Callable[[dict[str, Any]], T]) -> Section[T]:
    table = _table(raw)
    items = _items(table)
    if items is None:
        return Section(False, ())
    return Section(table.get("complete") is True, tuple(build(item) for item in items))


def parse_snapshot(raw: object) -> Snapshot:
    """Build a ``Snapshot`` from decoded JSON. Never raises on bad fields."""
    root = _table(raw)
    repo = _table(root.get("repository"))
    pr = _table(root.get("pull_request"))
    author = _table(pr.get("author"))
    threads = _table(root.get("review_threads"))
    checks = _table(root.get("checks"))
    stops = _table(root.get("stops"))
    return Snapshot(
        repository_id=_int(repo.get("id")),
        default_branch=_str(repo.get("default_branch")),
        default_branch_sha=_str(repo.get("default_branch_sha")),
        number=_int(pr.get("number")),
        state=_str(pr.get("state")),
        draft=_bool(pr.get("draft")),
        head_sha=_str(pr.get("head_sha")),
        head_repository_id=_int(pr.get("head_repository_id")),
        base_ref=_str(pr.get("base_ref")),
        base_sha=_str(pr.get("base_sha")),
        merge_base_sha=_str(pr.get("merge_base_sha")),
        mergeable=_str(pr.get("mergeable")),
        author_id=_int(author.get("id")),
        files=_section(
            root.get("files"),
            lambda f: ChangedFile(
                path=_str(f.get("path")),
                previous_path=_str(f.get("previous_path")),
                status=_str(f.get("status")),
                additions=_int(f.get("additions")),
                deletions=_int(f.get("deletions")),
                binary=_bool(f.get("binary")),
                patch_present=_bool(f.get("patch_present")),
                touches_code_fence=_bool(f.get("touches_code_fence")),
            ),
        ),
        labels=_section(root.get("labels"), lambda item: Label(_str(item.get("name")))),
        reviews=_section(
            root.get("reviews"),
            lambda r: Review(
                _int(r.get("reviewer_id")), _str(r.get("state")), _str(r.get("commit_id"))
            ),
        ),
        unresolved_threads=_int(threads.get("unresolved")),
        threads_complete=threads.get("complete") is True,
        required_checks=_section(
            checks.get("required"),
            lambda c: RequiredCheck(_str(c.get("context")), _int(c.get("app_id"))),
        ),
        check_results=_section(
            checks.get("results"),
            lambda c: CheckResult(
                _str(c.get("context")),
                _int(c.get("app_id")),
                _str(c.get("conclusion")),
                _str(c.get("head_sha")),
            ),
        ),
        repo_stop=_bool(stops.get("repository")),
    )
