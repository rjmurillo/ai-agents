#!/usr/bin/env python3
"""Validate PR description matches actual code changes.

BLOCKING validation that prevents PR description vs diff mismatches.
Detects when PR description claims files were changed that are not in the diff,
or when major changes are not mentioned in the description.

Exit codes follow ADR-035:
    0 - Success (validation passed, or warnings only)
    1 - Logic error (CRITICAL issues found, CI mode only)
    2 - Config error (missing dependency, failed to fetch PR data)
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Severity = Literal["CRITICAL", "WARNING"]
_VALID_SEVERITIES: frozenset[str] = frozenset({"CRITICAL", "WARNING"})

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.github_core.api import RepoInfo  # noqa: E402

# File extensions considered significant for mention checking
SIGNIFICANT_EXTENSIONS: frozenset[str] = frozenset(
    {".ps1", ".cs", ".ts", ".js", ".py", ".yml", ".yaml"}
)

# Directories whose files are flagged when changed but not mentioned
SIGNIFICANT_DIRS_PATTERN: re.Pattern[str] = re.compile(r"^(\.github|scripts|src|\.agents)")

# File extension pattern for extracting file references from description
_EXT_GROUP = r"ps1|md|yml|yaml|json|cs|ts|js|py|sh|bash"

# Negative lookahead anchoring the extension to a token boundary. Rejects
# any continuation character that would extend a real filename into a
# longer extension, identifier, or path component (issue #1874). Without
# this, the body group in `FILE_MENTION_PATTERNS` greedy-backtracks across
# longer real tokens and produces a known shorter extension as a false
# positive. The set covers:
#   - alphanumerics: `runs.jsonl` -> `runs.json`, `app.tsx` -> `app.ts`,
#     `module.pyc` -> `module.py`, `script.bashrc` -> `script.bash`
#   - underscore: `foo.json_schema` -> `foo.json`
#   - path separators (`/`, `\`): `path/to/file.py/extra` -> `path/to/file.py`
# A bare period (`.`) is intentionally NOT rejected so sentence-ending
# periods (`Updated foo.json. Some comment.`) still match. But a period
# followed by an alphanumeric or underscore is a further dotted segment (a
# real longer filename), so it IS rejected via the `\.[A-Za-z0-9_]`
# alternative (issue #1881; `_` added per review feedback):
#   - double extension: `runs.json.bak` -> [] (file is `.bak`, not `.json`)
#   - double extension: `module.py.orig` -> [] (file is `.orig`)
#   - underscore segment: `file.py._bak` -> [] (file is `._bak`)
# This preserves the sentence-period carve-out because `.` followed by a
# space or end-of-string does not match `\.[A-Za-z0-9_]`. A genuine longer
# filename whose LAST segment is a recognized extension still matches via
# the greedy body group (`tsconfig.spec.json` -> `tsconfig.spec.json`).
_EXT_BOUNDARY = r"(?![A-Za-z0-9_/\\]|\.[A-Za-z0-9_])"

_LINE_SUFFIX = r"(?::\d+(?::\d+)?)?"

# Default label name that bypasses CRITICAL description-validation failures.
DEFAULT_BYPASS_LABEL = "description-validation-bypass"

# Section names whose file mentions are contextual references, not change
# claims. Matches `## Heading` (h2) at the start of a line, case-insensitive.
# Each entry is a regex fragment for the heading text only.
#
# These are matched EXACTLY (the whole `## ...` line must be the name, modulo
# trailing whitespace). Use this list for ambiguous single words where a
# trailing suffix can carry a real change claim (e.g. `## Notes on the auth
# rewrite` must stay validated). Multi-word template headings that are pure
# references ("Related Issues", "Notes for Reviewers") are listed explicitly so
# the exact-match anchor accepts them.
_CONTEXTUAL_SECTION_NAMES: tuple[str, ...] = (
    r"Test\s*Plan",
    r"Design\s*Decisions?",
    r"Related",
    r"Related[ \t]+Files",
    r"Related[ \t]+Issues",
    r"References?",
    r"See\s*Also",
    r"Notes?",
    r"Notes[ \t]+for[ \t]+Reviewers",
    r"Background",
    r"Inspired\s*By",
    r"Pattern\s*From",
    r"Prior\s*Art",
    # Proof/results headings that name an activity, not a changed file.
    # Listed here (exact match) instead of _REFERENCE_SECTION_PREFIXES so that
    # headings like "## Validation Script" or "## Verification Steps", which
    # describe real validator changes, are NOT stripped. Only bare proof headings
    # and known summary suffixes strip.
    r"Validation",
    r"Validation[ \t]+Summary",
    r"Validation[ \t]+Results",
    r"Validation[ \t]+Report",
    r"Verification",
    r"Verification[ \t]+Results",
    r"Verification[ \t]+Summary",
    r"Verification[ \t]+Report",
)

_CHANGE_CLAIM_SECTION_NAMES: tuple[str, ...] = (
    r"Changes",
    r"Per[- \t]?file[ \t]+changes",
    r"Files[ \t]+Changed",
    r"Changed[ \t]+Files",
    # Natural synonym used in ~10% of merged PR bodies (measured 2026-07-30:
    # 10/100 recent merged PRs used "What changed" vs 20 using "Changes").
    # Without this entry, inline code and markdown links under "## What changed"
    # are silently skipped, giving the gate a false-clean result on bodies it
    # never checked.
    r"What[ \t]+changed",
)

_CHANGE_CLAIM_SCOPED_PATTERN_INDEXES: frozenset[int] = frozenset({0, 3, 4})

# Section-name PREFIXES whose file mentions are proof or scope references, never
# change claims. Matched as a prefix at a word boundary, so ANY suffix is
# absorbed. This kills the exact-name treadmill for Evidence and Out-of-Scope
# headings: agent PR-body templates emit many variants, and enumerating each one
# recurs on the next variant.
#
# Validation and Verification are NOT here (they moved to _CONTEXTUAL_SECTION_NAMES
# as exact-match entries). Those words can prefix real change-claim sections
# (e.g., "## Validation Script", "## Verification Steps"), so a blind prefix
# match would suppress CRITICAL checks for genuine drift.
#
# Evidence never precedes a real change-claim section in this codebase, so the
# prefix absorbs all Evidence variants safely.
#
# Out-of-Scope is unambiguous by definition: it explicitly names files NOT
# changed in this PR.
_REFERENCE_SECTION_PREFIXES: tuple[str, ...] = (
    r"Evidence",
    r"Out[ \t-]*of[ \t-]*Scope",
)

# Patterns to extract file paths from PR description text
# List item pattern accepts both unwrapped paths (`- path/file.ext`) and
# backtick-wrapped paths (`- \`path/file.ext\`: description`). The autonomous
# PR template uses backtick-wrapped paths; using [^\s`]+ stops cleanly at the
# trailing backtick instead of relying on normalize_path to strip it.
#
# Every pattern appends `_EXT_BOUNDARY` after the captured extension so the
# match cannot terminate inside a longer real extension (issue #1874).
FILE_MENTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(rf"`([^`]+\.({_EXT_GROUP})){_EXT_BOUNDARY}{_LINE_SUFFIX}`"),  # inline code
    re.compile(rf"\*\*([^*]+\.({_EXT_GROUP})){_EXT_BOUNDARY}{_LINE_SUFFIX}\*\*"),  # bold
    re.compile(
        rf"^\s*[-*+]\s+`?([^\s`]+\.({_EXT_GROUP})){_EXT_BOUNDARY}`?",
        re.MULTILINE,
    ),  # list items (optionally backtick-wrapped)
    re.compile(rf"\[([^\]]+\.({_EXT_GROUP})){_EXT_BOUNDARY}{_LINE_SUFFIX}\]"),  # markdown links
    re.compile(
        rf"\]\(((?!(?:https?:|ftp:|//|www\.))[^)]+\.({_EXT_GROUP}))"
        rf"{_EXT_BOUNDARY}{_LINE_SUFFIX}\)",
        re.IGNORECASE,
    ),  # markdown link targets [label](path.ext) (issue #2113)
]

# Inline citation-cue pattern for fix #2252.
#
# A backtick file path preceded immediately (within the same line) by one of
# these citation cue words/phrases is a REFERENCE, not a change claim. Examples:
#
#   see `.claude/commands/spec.md`
#   per `.agents/architecture/ADR-035-exit-code-standardization.md`
#   e.g. `.claude/skills/security-scan/scripts/scan_vulnerabilities.py`
#   for example `scripts/validate_session_json.py`
#   as documented in `scripts/ai_review_common/cache_guard.py`
#
# The pattern is matched globally and the matching span is replaced with
# `<CITE>` before FILE_MENTION_PATTERNS runs. This prevents the path from
# being collected as a change claim.
#
# INTENTIONALLY NARROW: the cue must appear on the SAME line as the path
# and be separated only by optional whitespace / parentheses / colons.
# This avoids suppressing list-item change claims that happen to follow
# a citation on an adjacent line.
_INLINE_CITATION_PATTERN = re.compile(
    r"(?i)"
    r"\b(?:see|per|e\.g\.|e\.g|eg\.|for example|as in|for instance"
    r"|as documented in|referenced by|defined in|introduced in"
    r"|reference path|cf\.|compare)"
    r"[: \t(]*"
    r"`[^`]+\.[a-zA-Z][a-zA-Z0-9_]*`",
)

# Summary text patterns that identify a <details> block as bot-generated
# (Renovate, Dependabot). Matched case-insensitively against the inner text
# of the <summary> tag. When a <details> block's summary matches any of these,
# the block is informational (changelog, dependency lookup, branch metadata)
# and stripped before file extraction. Otherwise the block is preserved so
# human-authored file claims (e.g. "<summary>Files changed</summary>")
# survive into validation.
#
# Patterns are anchored to the start of the summary (after optional
# whitespace) so a human summary like
# ``<summary>Files changed for Renovate migration</summary>`` is preserved.
# Without the anchor, mid-string `renovate` or `dependabot` would strip
# legitimate human summaries that happen to mention those words.
_BOT_DETAILS_SUMMARY_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*(?:chore\(deps\)|fix\(deps\)|renovate\b|dependabot\b|bump\s)",
    re.IGNORECASE,
)


@dataclass
class Issue:
    """A validation issue found during PR description checking.

    `severity` MUST be one of `CRITICAL` or `WARNING`. The CRITICAL gate at
    `validate_pr_description` and the audit emitter both branch on the exact
    string; a typo (`"critical"` lowercase) silently slips past the gate.
    """

    severity: Severity
    issue_type: str
    file: str
    message: str

    def __post_init__(self) -> None:
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"Issue.severity must be one of {sorted(_VALID_SEVERITIES)}, got {self.severity!r}"
            )


def get_repo_info() -> RepoInfo:
    """Parse owner/repo from git remote origin URL.

    Returns RepoInfo with owner and repo.
    Raises RuntimeError on failure.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise RuntimeError("Could not determine git remote origin") from exc

    if result.returncode != 0:
        raise RuntimeError("Could not determine git remote origin")

    remote_url = result.stdout.strip()
    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote_url)
    if not match:
        raise RuntimeError(f"Could not parse GitHub owner/repo from remote URL: {remote_url}")

    return RepoInfo(owner=match.group(1), repo=match.group(2))


def fetch_pr_data(pr_number: int, owner: str, repo: str) -> dict[str, Any]:
    """Fetch PR data (title, body, files, labels) via REST API calls.

    Uses three separate REST calls instead of a single GraphQL-backed
    ``gh pr view --json`` call, because workflow installation tokens return
    HTTP 401 for GraphQL while accepting the same token for REST.

    Returns a dict with the same shape as before:
        {"title": str, "body": str,
         "files": [{"path": str}, ...],
         "labels": [{"name": str}, ...]}

    Raises RuntimeError on failure.
    """

    def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("gh CLI not found. Install: https://cli.github.com/") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Timed out fetching PR #{pr_number}") from exc

    # 1. Title + body
    result = _run(["gh", "api", f"repos/{owner}/{repo}/pulls/{pr_number}"])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch PR #{pr_number}: {result.stderr}")
    pr_info: dict[str, Any] = json.loads(result.stdout)

    # 2. Changed files (paginated; REST uses "filename", normalize to "path")
    result = _run(["gh", "api", f"repos/{owner}/{repo}/pulls/{pr_number}/files", "--paginate"])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch PR #{pr_number} files: {result.stderr}")
    raw_files: list[dict[str, Any]] = json.loads(result.stdout)
    files = [{"path": f["filename"]} for f in raw_files]

    # 3. Labels (paginated for safety). The pull payload already carries the
    # same labels, so retain it as a fallback when the issues endpoint rejects
    # an otherwise valid workflow token (observed as HTTP 422 on PR #5135).
    result = _run(["gh", "api", f"repos/{owner}/{repo}/issues/{pr_number}/labels", "--paginate"])
    if result.returncode != 0:
        embedded_labels = pr_info.get("labels")
        if not isinstance(embedded_labels, list):
            raise RuntimeError(f"Failed to fetch PR #{pr_number} labels: {result.stderr}")
        labels = [label for label in embedded_labels if isinstance(label, dict)]
        print(
            f"Warning: labels endpoint failed for PR #{pr_number}; "
            "using labels embedded in the pull response.",
            file=sys.stderr,
        )
    else:
        labels = json.loads(result.stdout)

    base_info: dict[str, Any] = pr_info.get("base") or {}
    base_repo: dict[str, Any] = base_info.get("repo") or {}

    return {
        "title": pr_info.get("title") or "",
        "body": pr_info.get("body", "") or "",
        "files": files,
        "labels": [{"name": lbl.get("name") or ""} for lbl in labels],
        "base_ref": base_info.get("ref") or "",
        "default_branch": base_repo.get("default_branch") or "",
    }


def normalize_path(path: str) -> str:
    """Normalize a file path for comparison.

    Strips whitespace, markdown bold markers, and normalizes slashes.
    """
    path = path.strip()
    # Strip markdown formatting that may be captured by list item pattern
    path = path.strip("*")
    path = path.strip("`")
    path = path.replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    return path


def _strip_bot_details_blocks(text: str) -> str:
    """Strip <details> blocks whose <summary> matches known bot patterns.

    Preserves <details> blocks that look human-authored so any change claims
    inside them (e.g. ``<details><summary>Files changed</summary>...``)
    survive into file extraction. A block with no <summary> is also
    preserved, since absent a bot marker we cannot assume the contents are
    informational.
    """

    def _replace(match: re.Match[str]) -> str:
        block = match.group(0)
        summary_match = re.search(
            r"<summary\b[^>]*>(.*?)</summary\s*>",
            block,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if summary_match and _BOT_DETAILS_SUMMARY_PATTERN.search(summary_match.group(1)):
            return ""
        return block

    return re.sub(
        r"<details\b[^>]*>.*?</details\s*>",
        _replace,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _strip_informational_sections(description: str) -> str:
    """Remove bot-generated informational sections before file extraction.

    Strips bot-marked <details> blocks (Renovate, Dependabot) and "Detected
    Package Files" sections that list files for informational purposes rather
    than claiming those files were changed. Human-authored <details> blocks
    are preserved so file claims inside them are still validated.

    Also masks fenced code blocks before any heading-based stripping so a
    sample heading inside a fenced ```markdown block does not cause the
    contextual-section regex to over-strip across the real document
    structure.
    """
    # Mask fenced code blocks so headings or filenames inside samples do not
    # interact with the contextual-section regex below. Without this, an
    # AI-generated description containing `## Design Decisions` inside a
    # markdown sample would over-strip across real document structure and
    # either expose phantom file claims from inside the fence or silently
    # consume real change claims that follow it.
    #
    # Three fence styles are masked:
    #   1. Triple backticks (```...```)            - GitHub-flavored Markdown
    #   2. Triple tildes   (~~~...~~~)             - CommonMark alternative
    #   3. HTML <pre>...</pre>                     - PR templates copy raw HTML
    #
    # NOTE: 4-space-indented code blocks are NOT masked. They are
    # indistinguishable from indented list items via regex alone. Authors
    # should prefer fenced blocks in PR descriptions.
    # Triple-backtick: keep unanchored, GFM permits inline ```code``` spans
    # and we want those treated as code regardless of position.
    text = re.sub(r"```.*?```", "<CODE_BLOCK>", description, flags=re.DOTALL)
    # Tilde fence: anchor to start of line (CommonMark requires fences in
    # column 0..3). Without the anchor, prose like `~~~strikethrough~~~`
    # masks any `## Test Plan` heading appearing between two `~~~` tokens.
    text = re.sub(
        r"^[ ]{0,3}~~~.*?^[ ]{0,3}~~~",
        "<CODE_BLOCK>",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    text = re.sub(
        r"<pre\b[^>]*>.*?</pre>",
        "<CODE_BLOCK>",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Strip bot-marked <details>...</details> blocks (Renovate, Dependabot,
    # etc.). Human-authored blocks are preserved so file claims inside them
    # (e.g. ``<summary>Files changed</summary>``) survive into validation.
    text = _strip_bot_details_blocks(text)
    # Strip "Detected Package Files" section up to the next heading or <hr>
    text = re.sub(
        r"###\s*Detected Package Files.*?(?=^###|\n---|\Z)",
        "",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    # Strip GitHub admonition blockquote blocks (> [!WARNING], > [!NOTE], etc.)
    # These contain informational file references, not change claims.
    text = re.sub(
        r"^>\s*\[!(WARNING|NOTE|CAUTION|IMPORTANT|TIP)\].*?(?=\n(?!>)|\Z)",
        "",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    # Strip contextual h2 sections (Test Plan, Design Decisions, Related,
    # References, See Also, Notes, Background, Inspired By, Pattern From,
    # Prior Art). Files mentioned in these sections are references or
    # validation targets, not claims that those files were modified by the PR.
    #
    # The heading name must occupy the entire `## ...` line (modulo trailing
    # whitespace). Without the `\s*$` anchor, `## Notes on the rollout` would
    # also match and silently drop a section that contains real change claims.
    # We accept the tradeoff that `## Notes:` (trailing punctuation) no longer
    # strips: those rare cases can use a contextual-prefix word like
    # `## Notes` (no suffix) or apply the bypass label.
    #
    # The terminating lookahead `(?=^#{1,2}(?!#)|\Z)` matches the next H1
    # or H2 heading (exactly `#` or `##`, not `###` or deeper). Two failure
    # modes this guards against:
    #
    # 1. Without the `(?!#)` negative lookahead, an H3 sub-heading inside a
    #    contextual section (e.g., `### Trade-offs` under `## Design
    #    Decisions`) terminates the strip early and exposes its contents as
    #    phantom change claims.
    # 2. Without H1 (`#{1,2}`) in the heading-class, an H1 that follows a
    #    contextual section is treated as still inside the section and
    #    silently dropped. Per CommonMark, an H2 section ends at the next
    #    heading of equal-or-higher level, so H1 must terminate H2.
    contextual_pattern = (
        r"^##\s+(?:" + "|".join(_CONTEXTUAL_SECTION_NAMES) + r")\s*$.*?(?=^#{1,2}(?!#)|\Z)"
    )
    text = re.sub(
        contextual_pattern,
        "",
        text,
        flags=re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    # Strip proof/scope reference sections by heading PREFIX (any suffix). Unlike
    # the exact-match block above, this absorbs trailing words so heading
    # variants ("Evidence For", "Validation Summary", "Verification Results",
    # "Out of Scope notes") all strip without enumerating each one. The `\b`
    # after the prefix prevents matching a longer word that merely starts with
    # the prefix (e.g. "Validations" or "Evidenced"); the rest of the heading
    # line is then consumed by `[^\n]*$`. Same terminating lookahead as above:
    # the section ends at the next H1 or H2 (not H3+).
    reference_prefix_pattern = (
        r"^##\s+(?:" + "|".join(_REFERENCE_SECTION_PREFIXES) + r")\b[^\n]*$.*?(?=^#{1,2}(?!#)|\Z)"
    )
    text = re.sub(
        reference_prefix_pattern,
        "",
        text,
        flags=re.DOTALL | re.MULTILINE | re.IGNORECASE,
    )
    # Strip inline citation cues so a backtick-wrapped path used as a
    # reference example (e.g. "see `scripts/foo.py`", "per `ADR-035.md`")
    # is not collected as a change claim. The citation pattern is narrow:
    # the cue keyword must appear on the same line as the path (see
    # _INLINE_CITATION_PATTERN for the full list of recognized cues).
    text = _INLINE_CITATION_PATTERN.sub("<CITE>", text)
    return text


def _change_claim_regions(cleaned: str) -> list[tuple[int, int]]:
    """Return spans for H2 sections that carry explicit change claims."""
    change_claim_pattern = (
        r"^##\s+(?:" + "|".join(_CHANGE_CLAIM_SECTION_NAMES) + r")\s*$.*?(?=^#{1,2}(?!#)|\Z)"
    )
    return [
        (match.start(), match.end())
        for match in re.finditer(
            change_claim_pattern,
            cleaned,
            flags=re.DOTALL | re.MULTILINE | re.IGNORECASE,
        )
    ]


def _is_in_change_claim_region(position: int, regions: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in regions)


def extract_mentioned_files(description: str) -> list[str]:
    """Extract unique file paths mentioned in PR description text.

    Strips informational sections (References, Notes, Evidence, etc.) before
    extraction so that file paths used as citations do not trigger a CRITICAL
    "mentioned but not in diff" issue. Use ``extract_all_mentioned_files`` to
    get a broader set that includes those stripped sections (for WARNING
    suppression only, issue #3712).
    """
    if not description:
        return []

    cleaned = _strip_informational_sections(description)
    change_claim_regions = _change_claim_regions(cleaned)

    mentioned: list[str] = []
    for pattern_index, pattern in enumerate(FILE_MENTION_PATTERNS):
        for match in pattern.finditer(cleaned):
            scoped_pattern = pattern_index in _CHANGE_CLAIM_SCOPED_PATTERN_INDEXES
            outside_claim_region = not _is_in_change_claim_region(
                match.start(), change_claim_regions
            )
            if scoped_pattern and outside_claim_region:
                continue
            raw = match.group(1)
            # Skip command-like strings (file paths never contain spaces)
            if " " in raw.strip():
                continue
            mentioned.append(normalize_path(raw))

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for path in mentioned:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def extract_all_mentioned_files(description: str) -> frozenset[str]:
    """Extract all file paths from description, including informational sections.

    Unlike ``extract_mentioned_files``, this function extracts paths from the
    full description after stripping only admonition blocks and citation cues.
    Contextual and reference sections (References, Notes, Evidence, etc.) are
    NOT stripped, so paths cited there are included.

    This broader set is used exclusively for WARNING suppression (check 2 in
    ``validate_pr_description``): a file mentioned anywhere in the description,
    even in an informational section, should not trigger "significant file not
    mentioned" (issue #3712). For the CRITICAL check (file mentioned but not in
    diff), use ``extract_mentioned_files`` which enforces the stricter parse.
    """
    if not description:
        return frozenset()

    # Strip only admonition blocks and citation cues; keep all sections.
    text = re.sub(
        r"^>\s*\[!(WARNING|NOTE|CAUTION|IMPORTANT|TIP)\].*?(?=\n(?!>)|\Z)",
        "",
        description,
        flags=re.DOTALL | re.MULTILINE,
    )
    text = _INLINE_CITATION_PATTERN.sub("<CITE>", text)

    paths: set[str] = set()
    for pattern in FILE_MENTION_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1)
            if " " in raw.strip():
                continue
            paths.add(normalize_path(raw))
    return frozenset(paths)


def file_matches(actual: str, mentioned: str) -> bool:
    """Check if an actual diff path matches a mentioned path.

    Supports exact match, suffix match (e.g. "file.ps1" matches
    "path/to/file.ps1"), and glob patterns (e.g. "src/*.py" matches
    "src/main.py").
    """
    if actual == mentioned:
        return True
    if actual.endswith(f"/{mentioned}"):
        return True
    if "*" in mentioned or "?" in mentioned:
        return fnmatch.fnmatch(actual, mentioned)
    return False


# Em/en-dash detection regex for PR title and body validation. The regex is
# the same shape used by the pre-commit hook section, the commit-msg hook,
# and `pre_pr.py:_DASH_RE`; this is the PR-description analogue.
#
# Uses Unicode escape sequences so this source file does not contain U+2014
# or U+2013 itself (per `.claude/rules/universal.md` MUST NOT entry 5,
# Issue #1923). REQ-006 acceptance criteria cover the four enforcement
# placements: AC1/AC2 (pre-commit hook for staged files), AC3 (commit-msg
# hook for commit messages), AC7 (pre_pr.py for branch-wide files), and the
# universal.md prohibition itself (AC8). PR descriptions live in GitHub and
# are not covered by any AC explicitly; this guard closes that gap and is
# tracked under the broader Issue #1923 umbrella, not a specific AC.
_DASH_RE: re.Pattern[str] = re.compile("[\u2013\u2014]")

# ---------------------------------------------------------------------------
# Closing-link validation (Issue #3827)
# ---------------------------------------------------------------------------

# Matches closing keywords that GitHub auto-closes issues on merge.
# "Refs" is intentionally excluded: it mentions but does not close.
_AUTO_CLOSE_KW: re.Pattern[str] = re.compile(
    r"\b(?:close[sd]?|fix(?:es|ed)?|resolve[sd]?)\s+(?P<repo>[\w.-]+/[\w.-]+)?#(?P<number>\d+)",
    re.IGNORECASE,
)

# GFM inline code span: one or more backticks as the opening fence, closed by
# the same-length backtick run. Does not cross newlines. Handles single (`),
# double (``), triple (```) etc. The previous pattern only matched single
# backticks, missing ``...`` spans entirely (issue #3827).
# CommonMark allows a line ending inside a code span; only a blank line ends
# it. Restricting the body to [^\n] left a span written across two lines
# unstripped, so a closing link inside an example was read as a real one and
# the gate passed on a pull request that closes nothing. Refs #3827.
# A run of three or more backticks at the start of a line opens a fenced block,
# which _FENCED_CODE_BLOCK owns. Letting the multiline alternative claim those
# too would relabel a fence as an inline span and change the reported reason.
# So newlines are allowed only for runs of one or two backticks, which is where
# the real gap was; longer runs stay single line and fences handle the rest.
_INLINE_CODE_SPAN: re.Pattern[str] = re.compile(
    r"(?<!`)(`{1,2})(?!`)(?:[^\n]|\n(?!\s*\n))+?(?<!`)\1(?!`)"
    r"|"
    r"(?<!`)(`{3,})(?!`)[^\n]+?(?<!`)\2(?!`)"
)

# Fenced code block: backtick or tilde fence with optional language tag.
# CommonMark 0.31.2 section 4.5: an unclosed fence still opens a code block
# that runs to the end of the containing block, not to nothing. The first
# alternative takes a real closing fence when one exists; the second consumes
# to EOF when none does, so a body ending mid-fence is still recognized as a
# fenced span instead of matching neither pattern (Copilot review on PR
# #5371, which found this exact gap in the port at
# .claude/skills/github/scripts/issue/check_existing_pr_for_issue.py).
#
# `[ ]{0,3}` on both the opening and closing fence lines tolerates the
# indentation CommonMark 0.31.2 section 4.5 allows (up to three spaces); a
# fourth space starts an indented code block instead, a different construct
# this module does not classify. `[ \t]*$` on the closer requires the line to
# hold nothing but the fence run and optional trailing whitespace, so a line
# like a fence marker followed by other text cannot end the block early:
# `^\1` alone matched any line merely starting with the same run, closing the
# block one line too soon and letting a real claim past it that GitHub still
# renders as code (Copilot review on PR #5371, round 2).
_FENCED_CODE_BLOCK: re.Pattern[str] = re.compile(
    r"^[ ]{0,3}(`{3,}|~{3,})[^\n]*\n(?:.*?^[ ]{0,3}\1[ \t]*$|.*)",
    re.DOTALL | re.MULTILINE,
)


def _span_ranges(body: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    """Return (start, end) pairs for all non-overlapping matches of pattern."""
    return [(m.start(), m.end()) for m in pattern.finditer(body)]


def _in_any_range(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in ranges)


def validate_closing_links(
    body: str,
    base_ref: str = "",
    default_branch: str = "main",
    *,
    base_branch: str | None = None,
) -> list[Issue]:
    """Detect closing keywords that GitHub will silently ignore.

    Two failure modes (Issue #3827):

    1. The keyword is inside an inline code span or fenced code block.
       GitHub does not parse closing keywords inside backtick markup, so
       ``Fixes #N`` written as :literal:`Fixes #N` never creates a link
       and the issue stays open after merge.  This produces a CRITICAL.

    2. The keyword is valid syntax but the PR targets a non-default branch
       (stacked PRs). GitHub only auto-closes issues for merges into the
       default branch.  This produces a WARNING so the author knows to
       close the issue manually once the stack lands.

    ``Refs`` is excluded because it is intentionally advisory and does not
    trigger auto-close regardless of location.
    """
    if base_branch is not None:
        base_ref = base_branch

    issues: list[Issue] = []
    fenced_ranges = _span_ranges(body, _FENCED_CODE_BLOCK)
    code_span_ranges = _span_ranges(body, _INLINE_CODE_SPAN)
    non_default_base = bool(base_ref and default_branch and base_ref != default_branch)

    has_closing_keyword = False
    for m in _AUTO_CLOSE_KW.finditer(body):
        pos = m.start()
        full_kw = m.group(0)
        issue_num = m.group("number")
        has_closing_keyword = True
        # Echo back the owner/repo qualifier the author actually wrote.
        # Dropping it renames the issue: "Fixes other-org/other-repo#5" would
        # be reported, and remediated, as this repository's own #5, which is a
        # different issue. Backticks suppress the closing link whatever repo
        # the reference names, so the finding itself stands either way.
        issue_ref = f"{m.group('repo') or ''}#{issue_num}"

        if _in_any_range(pos, code_span_ranges):
            issues.append(
                Issue(
                    severity="CRITICAL",
                    issue_type="Closing keyword in inline code span",
                    file="<pr-body>",
                    message=(
                        f"Closing keyword '{full_kw}' is inside an inline code span. "
                        f"GitHub will not close issue {issue_ref} on merge. "
                        "Remove the surrounding backticks and place the keyword "
                        f"on its own line: Fixes {issue_ref}"
                    ),
                )
            )
        elif _in_any_range(pos, fenced_ranges):
            issues.append(
                Issue(
                    severity="CRITICAL",
                    issue_type="Closing keyword in fenced code block",
                    file="<pr-body>",
                    message=(
                        f"Closing keyword '{full_kw}' is inside a fenced code block. "
                        f"GitHub will not close issue {issue_ref} on merge. "
                        "Add a plain closing line outside any code block: "
                        f"Fixes {issue_ref}"
                    ),
                )
            )
    if non_default_base and has_closing_keyword:
        issues.append(
            Issue(
                severity="WARNING",
                issue_type="Closing keyword on non-default base branch",
                file="<pr-body>",
                message=(
                    f"This PR targets '{base_ref}', not the default branch "
                    f"'{default_branch}'. GitHub only auto-closes issues when "
                    "a PR merges into the default branch. "
                    "Close the linked issues by hand once this stack lands."
                ),
            )
        )

    return issues


def validate_no_dashes(title: str, body: str) -> list[Issue]:
    """Reject U+2014 (em-dash) or U+2013 (en-dash) in PR title or description.

    Closes the gap that the Lefthook jobs declared in ``lefthook.yml``
    do not cover: PR descriptions live in GitHub, never reach `git
    commit`, and were the source of bot reviewer threads on PR #1930
    despite the hook implementation. See `.claude/rules/universal.md`
    MUST NOT entry 5 (Refs Issue #1923).
    """
    issues: list[Issue] = []
    if _DASH_RE.search(title):
        issues.append(
            Issue(
                severity="CRITICAL",
                issue_type="Em/en-dash in PR title",
                file="<pr-title>",
                message=(
                    "PR title contains U+2014 (em-dash) or U+2013 (en-dash). "
                    "Replace with comma, period, hyphen, or restructure. "
                    "Rule: .claude/rules/universal.md MUST NOT entry 5."
                ),
            )
        )
    if _DASH_RE.search(body):
        # Find offending lines for actionable output
        offending = []
        for lineno, line in enumerate(body.splitlines(), start=1):
            if _DASH_RE.search(line):
                offending.append(f"line {lineno}")
        offending_str = ", ".join(offending[:5])
        if len(offending) > 5:
            offending_str += f", ... (+{len(offending) - 5} more)"
        issues.append(
            Issue(
                severity="CRITICAL",
                issue_type="Em/en-dash in PR description",
                file="<pr-body>",
                message=(
                    f"PR description contains U+2014 or U+2013 ({offending_str}). "
                    "Replace with comma, period, hyphen, or restructure. "
                    "Rule: .claude/rules/universal.md MUST NOT entry 5."
                ),
            )
        )
    return issues


def validate_pr_description(
    pr_files: list[str],
    mentioned_files: list[str],
    *,
    all_mentioned_files: frozenset[str] | None = None,
) -> list[Issue]:
    """Compare mentioned files against actual PR files. Return list of issues.

    ``mentioned_files`` is the strict set from ``extract_mentioned_files``.
    ``all_mentioned_files`` is the broader set from ``extract_all_mentioned_files``,
    used only for WARNING suppression so that informational-section file
    references silence "significant file not mentioned" (issue #3712).
    """
    issues: list[Issue] = []
    warning_mentioned = all_mentioned_files if all_mentioned_files is not None else frozenset()

    # Check 1: Files mentioned but not in diff (CRITICAL)
    for mentioned in mentioned_files:
        found = any(file_matches(actual, mentioned) for actual in pr_files)
        if not found:
            issues.append(
                Issue(
                    severity="CRITICAL",
                    issue_type="File mentioned but not in diff",
                    file=mentioned,
                    message=(
                        "Description claims this file was changed, "
                        "but it's not in the PR diff. "
                        "Inline-backtick file paths outside `## Changes` / "
                        "`## Per-file changes` / `## Files Changed` / "
                        "`## Changed Files` are informational. Move the path "
                        "under one of those headings, use a bullet (`- path.ext`) "
                        "or bold (`**path.ext**`), or wrap it in a code fence. "
                        # CONTRIBUTING.md:909, section "Bypassing Description
                        # Validation", reads verbatim: "1. A human maintainer
                        # MUST add the `description-validation-bypass` label
                        # (case-insensitive match)". Naming it as the reader's
                        # own next step tells an agent to grant itself a
                        # permission it does not hold (issue #4782).
                        #
                        # Stricter/looser/different than canonical:
                        # CONTRIBUTING.md:909 states only who MAY add the
                        # label. This message additionally states who may NOT
                        # (the reader), because the load-bearing half for an
                        # autonomous reader is the prohibition, not the
                        # permission alone.
                        f"For unrecoverable cases the '{DEFAULT_BYPASS_LABEL}' "
                        "label clears this CRITICAL, but CONTRIBUTING.md "
                        '("Bypassing Description Validation") requires a human '
                        "maintainer to add it: ask a maintainer to decide, and "
                        "do not apply it yourself."
                    ),
                )
            )

    # Check 2: Major files changed but not mentioned (WARNING)
    # Suppress when the file appears anywhere in the description, including
    # informational/reference sections (issue #3712).
    for changed in pr_files:
        ext = os.path.splitext(changed)[1]
        if ext not in SIGNIFICANT_EXTENSIONS:
            continue
        if not SIGNIFICANT_DIRS_PATTERN.match(changed):
            continue

        in_strict = any(file_matches(changed, mentioned) for mentioned in mentioned_files)
        in_broad = any(file_matches(changed, mentioned) for mentioned in warning_mentioned)
        if not in_strict and not in_broad:
            issues.append(
                Issue(
                    severity="WARNING",
                    issue_type="Significant file not mentioned",
                    file=changed,
                    message="This file was changed but not mentioned in the description",
                )
            )

    return issues


def print_results(issues: list[Issue], ci: bool) -> int:
    """Print validation results and return exit code."""
    if not issues:
        print("\nPR description matches diff (no mismatches found)")
        return 0

    critical_count = sum(1 for i in issues if i.severity == "CRITICAL")
    warning_count = sum(1 for i in issues if i.severity == "WARNING")

    print(f"\nFound {len(issues)} issue(s):")
    print(f"  CRITICAL: {critical_count}")
    print(f"  WARNING: {warning_count}")
    print()

    for issue in issues:
        print(f"[{issue.severity}] {issue.issue_type}")
        print(f"  File: {issue.file}")
        print(f"  {issue.message}")
        print()

    if critical_count > 0:
        print("CRITICAL issues found. Update PR description to match actual changes.")
        if ci:
            return 1
    elif warning_count > 0:  # pragma: no branch
        print("Warnings found. Consider mentioning significant files in PR description.")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description="Validate PR description matches actual code changes.",
    )
    parser.add_argument(
        "--pr-number",
        type=int,
        required="PR_NUMBER" not in os.environ,
        default=int(os.environ.get("PR_NUMBER", "0")) or None,
        help="PR number to validate (env: PR_NUMBER)",
    )
    parser.add_argument(
        "--owner",
        default=os.environ.get("REPO_OWNER", ""),
        help="Repository owner (env: REPO_OWNER, or inferred from git remote)",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("REPO_NAME", ""),
        help="Repository name (env: REPO_NAME, or inferred from git remote)",
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        default=os.environ.get("CI", "").lower() in ("true", "1"),
        help="CI mode: exit non-zero on CRITICAL failures (env: CI)",
    )
    parser.add_argument(
        "--bypass-label",
        default=os.environ.get("DESCRIPTION_VALIDATION_BYPASS_LABEL", DEFAULT_BYPASS_LABEL),
        help=(
            "PR label that suppresses CRITICAL failures in CI mode "
            f"(env: DESCRIPTION_VALIDATION_BYPASS_LABEL, "
            f"default: {DEFAULT_BYPASS_LABEL})"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    owner: str = args.owner
    repo: str = args.repo

    # Resolve owner/repo from git remote if not provided
    if not owner or not repo:
        try:
            repo_info = get_repo_info()
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        if not owner:
            owner = repo_info.owner
        if not repo:
            repo = repo_info.repo

    # Fetch PR data
    print(f"Fetching PR #{args.pr_number} data...")
    try:
        pr_data = fetch_pr_data(args.pr_number, owner, repo)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    # Extract file lists
    pr_files: list[str] = [f["path"] for f in pr_data.get("files", [])]
    description: str = pr_data.get("body", "") or ""

    print(f"PR has {len(pr_files)} changed files")

    mentioned_files = extract_mentioned_files(description)
    all_mentioned = extract_all_mentioned_files(description)
    print(f"Description mentions {len(mentioned_files)} files")

    # Validate: file mentions vs diff
    issues = validate_pr_description(pr_files, mentioned_files, all_mentioned_files=all_mentioned)

    # Validate: no em/en-dashes in PR title or body (Issue #1923, REQ-006).
    # The Lefthook jobs declared in lefthook.yml cover staged files and commit
    # messages but cannot scan PR descriptions, which live
    # in GitHub and never reach `git commit`. This check closes that gap.
    title: str = pr_data.get("title", "") or ""
    issues.extend(validate_no_dashes(title, description))

    # Validate: closing keywords are not buried in code spans or fenced blocks,
    # and the PR targets the default branch (issue #3827).
    base_branch: str = pr_data.get("base_ref", "") or ""
    default_branch: str = pr_data.get("default_branch", "main") or "main"
    issues.extend(validate_closing_links(description, base_branch, default_branch))

    # Honor the bypass label only when CI mode would otherwise fail. The label
    # is the documented escape hatch for false-positive contextual references
    # that the section allowlist does not cover. The issues are still printed
    # for visibility, but the script exits 0 so the workflow's overall_status
    # propagates as PASS.
    #
    # Label name comparison is case-insensitive. GitHub renders labels case-
    # insensitively in the UI but returns canonical case via the API; a
    # maintainer creating `Description-Validation-Bypass` (Title Case) would
    # otherwise silently miss the bypass against the lowercase default.
    pr_labels: list[str] = [
        label.get("name", "") for label in (pr_data.get("labels") or []) if isinstance(label, dict)
    ]
    bypass_label_lower = args.bypass_label.lower()
    pr_labels_lower = {label.lower() for label in pr_labels}

    # Em/en-dash violations are NEVER bypassable. The
    # `description-validation-bypass` label is the documented escape hatch for
    # file-mention false positives only. Dash violations are bot-revealed
    # style issues that the entire purpose of Issue #1923 is to mechanically
    # prevent; allowing the bypass label to suppress them silently would
    # defeat the rule. Dash criticals always block, before the bypass check.
    dash_issue_types = {"Em/en-dash in PR title", "Em/en-dash in PR description"}
    has_dash_critical = any(
        i.severity == "CRITICAL" and i.issue_type in dash_issue_types for i in issues
    )
    if args.ci and has_dash_critical:
        return print_results(issues, ci=args.ci)

    # File-mention CRITICALs may be bypassed via the bypass label.
    has_non_dash_critical = any(
        i.severity == "CRITICAL" and i.issue_type not in dash_issue_types for i in issues
    )
    if args.ci and has_non_dash_critical and bypass_label_lower in pr_labels_lower:
        print_results(issues, ci=False)
        print(f"\nCRITICAL issues bypassed by '{args.bypass_label}' label. Exiting 0.")
        # Emit a structured marker so audit tooling (Audit-Hook-Bypass
        # workflow, weekly review) can detect bypass usage without parsing
        # stdout. Writes to GITHUB_STEP_SUMMARY when the env var is set
        # (CI context); silently skipped locally.
        _emit_bypass_audit(args.pr_number, args.bypass_label, issues)
        return 0

    return print_results(issues, ci=args.ci)


# ASCII control characters (NUL through US, plus DEL) and `=` are unsafe for
# GITHUB_OUTPUT keys=value lines. Replacing all of them defends against any
# line-delimited or heredoc-style injection vector regardless of which
# GitHub Actions runner version processes the file.
_OUTPUT_UNSAFE_CHARS: re.Pattern[str] = re.compile(r"[\x00-\x1f\x7f=]")


def _safe_label_for_output(label: str) -> str:
    """Return a label safe to embed in GITHUB_OUTPUT key=value lines.

    GitHub Actions parses `GITHUB_OUTPUT` as `name=value` pairs. A value
    containing `\\n` injects a new key (CWE-117 log injection / CVE-2023-32700
    class). Replace every ASCII control character and `=` with `_` so no
    delimiter, heredoc, or escape sequence survives.
    """
    return _OUTPUT_UNSAFE_CHARS.sub("_", label)


def _safe_label_for_markdown(label: str) -> str:
    """Return a label safe to embed in markdown inline code spans.

    A label containing a backtick closes the inline `code` span and breaks
    the audit marker block, defeating downstream `<!-- ... -->` parsers.
    Replace backticks with `'` (visually similar, no markdown semantics).
    """
    return label.replace("`", "'")


def _warn_if_mutated(name: str, original: str, sanitized: str) -> None:
    """Emit a stderr warning when a sanitizer changed its input.

    Without this, a label or file path containing dangerous characters is
    silently rewritten in the audit record. Auditors grepping for the
    original value would not find it. The warning is one-shot per call
    site and never blocks execution.
    """
    if original != sanitized:
        print(
            f"[pr-description] WARNING: {name} sanitized "
            f"(unsafe characters replaced); wrote {sanitized!r} "
            f"instead of original {original!r}",
            file=sys.stderr,
        )


def _write_step_summary(summary_path: str, pr_number: int, label: str, issues: list[Issue]) -> None:
    """Append the human-readable bypass record to `GITHUB_STEP_SUMMARY`.

    OSError is logged to stderr (not silently swallowed): a disk-full or
    permission failure here means the audit trail is lost, which the audit
    machinery exists to prevent. The bypass return path is unaffected.
    """
    safe_label = _safe_label_for_markdown(label)
    _warn_if_mutated("bypass_label (markdown)", label, safe_label)
    critical_files = [i.file for i in issues if i.severity == "CRITICAL"]
    safe_files = [(f, _safe_label_for_markdown(f)) for f in critical_files]
    for original, sanitized in safe_files:
        _warn_if_mutated("file path (markdown)", original, sanitized)
    record = (
        "\n### PR Description Validation Bypass\n\n"
        f"PR #{pr_number} bypassed CRITICAL description-validation "
        f"failures via `{safe_label}` label.\n\n"
        f"Suppressed CRITICAL files ({len(critical_files)}): "
        f"{', '.join(f'`{s}`' for _, s in safe_files) or '(none)'}\n\n"
        "<!-- DESCRIPTION-VALIDATION-BYPASS -->\n"
    )
    try:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(record)
    except OSError as exc:
        print(
            f"[pr-description] WARNING: failed to write bypass audit "
            f"to GITHUB_STEP_SUMMARY ({summary_path}): {exc}",
            file=sys.stderr,
        )


def _write_step_output(output_path: str, label: str, critical_count: int) -> None:
    """Append the workflow signal triple to `GITHUB_OUTPUT`.

    Label is sanitized via `_safe_label_for_output` before write to prevent
    newline injection from synthesizing arbitrary output keys. OSError is
    logged to stderr instead of swallowed: the workflow report relies on
    `bypass_used=true` to render BYPASSED instead of PASS; a silent failure
    here turns the audit machinery into a no-op.
    """
    safe_label = _safe_label_for_output(label)
    _warn_if_mutated("bypass_label (GITHUB_OUTPUT)", label, safe_label)
    try:
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write(
                f"bypass_used=true\nbypass_label={safe_label}\nbypass_count={critical_count}\n"
            )
    except OSError as exc:
        print(
            f"[pr-description] WARNING: failed to write bypass audit "
            f"to GITHUB_OUTPUT ({output_path}): {exc}",
            file=sys.stderr,
        )


def _emit_bypass_audit(pr_number: int, label: str, issues: list[Issue]) -> None:
    """Emit structured bypass signals.

    Distinguishes a bypassed PASS from a clean PASS so the workflow PR
    comment and audit tooling can detect override usage. No-ops when the
    respective env vars are unset (local runs).
    """
    critical_files = [i.file for i in issues if i.severity == "CRITICAL"]
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        _write_step_summary(summary_path, pr_number, label, issues)
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        _write_step_output(output_path, label, len(critical_files))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
