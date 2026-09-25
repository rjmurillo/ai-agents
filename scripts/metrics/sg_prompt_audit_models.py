"""JSON-serializable dataclasses for the security-guidance prompt audit (issue #5856).

Every record here is content-free by construction: fields hold hashes, byte
counts, timestamps, paths, and counters, never the diff or prompt text they
describe. `scripts/metrics/sg_prompt_audit_parse.py` builds ``SessionRecord``
instances from child-review transcripts; `scripts/metrics/sg_prompt_audit.py`
groups them into an ``AuditReport``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Locator:
    """Where a session's first user entry lives on disk."""

    project: str
    file: str
    line: int


@dataclass(frozen=True, slots=True)
class Block:
    """One ``=== DIFF: <path> ===`` section's content, hashed and sized only."""

    path: str
    sha256: str
    bytes: int


@dataclass(frozen=True, slots=True)
class CapCounts:
    """Occurrences of the three security-guidance truncation markers."""

    per_file_truncated: int
    total_truncated: int
    omitted: int


@dataclass(frozen=True, slots=True)
class UsageTotals:
    """The four token-usage fields security-guidance's transcripts report."""

    input_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """One child-review transcript file, reduced to content-free evidence."""

    locator: Locator
    kind: str
    cwd: str
    started_at: str
    ended_at: str
    latency_s: float
    prompt_bytes: int
    prompt_sha256: str
    diff_bytes: int
    diff_sha256: str
    blocks: tuple[Block, ...]
    path_order_sha256: str
    cap: CapCounts
    checkout_note: bool
    assistant_turns: int
    usage: UsageTotals
    first_turn_usage: UsageTotals | None
    succeeded: bool
    failure: str | None


@dataclass(frozen=True, slots=True)
class Window:
    """The ``--since``/``--until`` bounds a report was filtered to, if any."""

    since: str | None
    until: str | None


@dataclass(frozen=True, slots=True)
class RepeatedDiffGroup:
    """Sessions sharing one ``diff_sha256``: the exact-duplicate-diff case."""

    diff_sha256: str
    count: int
    bytes: int
    redundant_bytes: int
    kinds: list[str]
    locators: list[Locator]
    distinct_cwds: int
    time_span_seconds: float


@dataclass(frozen=True, slots=True)
class RepeatedBlockGroup:
    """A single-file diff block reused verbatim across two or more sessions."""

    block_sha256: str
    path: str
    bytes: int
    sessions: int
    distinct_projects: int
    redundant_bytes: int


@dataclass(frozen=True, slots=True)
class FailureEntry:
    """A session that never produced a ``StructuredOutput`` review result."""

    locator: Locator
    reason: str


@dataclass(frozen=True, slots=True)
class Iter2CacheEntry:
    """First-turn cache read vs. cache creation tokens for one iter2 session."""

    locator: Locator
    cache_read_input_tokens: int
    cache_creation_input_tokens: int


@dataclass(frozen=True, slots=True)
class AuditReport:
    """The top-level JSON object ``sg_prompt_audit`` prints or writes."""

    projects_dir: str
    window: Window
    sessions_examined: int
    skipped_lines: int
    counts_by_kind: dict[str, int]
    total_prompt_bytes: int
    estimated_tokens: int
    token_estimate_method: str
    repeated_diffs: list[RepeatedDiffGroup]
    repeated_blocks: list[RepeatedBlockGroup]
    grand_redundant_bytes_diffs: int
    grand_redundant_tokens_diffs: int
    grand_redundant_bytes_blocks: int
    grand_redundant_tokens_blocks: int
    iter2_cache: list[Iter2CacheEntry]
    failures: list[FailureEntry]
