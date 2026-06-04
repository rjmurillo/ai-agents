#!/usr/bin/env python3
"""Flag contradictions between a PR description, its linked issues, and code.

The "Validate Spec Coverage" CI check reads the PR description, the linked
issue text, and the implementation as a single spec, then fails on
contradiction. PR #1897 round-7 hit that gate: Issue #1894 still claimed
``model_tier: sonnet`` for the implementer while the committed agent
frontmatter shipped ``model: opus`` (user override). Three rounds of
code-only fixes did not move the gate; one PR-description update closed it.
CI surfaced the failure roughly 90 seconds after each push. This check
catches the same contradiction locally in seconds.

The check fetches the current branch's PR body via the gh CLI, extracts the
linked-issue references (``Closes/Fixes/Resolves/Implements #N``), fetches
each linked issue body, then compares two classes of load-bearing claim
against the committed agent frontmatter:

  1. Model tier: a spec text saying ``model: sonnet`` (or ``model_tier:
     sonnet``) contradicts a committed agent file whose frontmatter declares
     ``model: opus``.
  2. Numeric threshold: a spec text saying ``model: 3`` style key-value pair
     contradicts the same committed key with a different value.

The comparison target is the committed frontmatter, parsed from the agent
markdown files changed on the branch. The agent frontmatter ``model:`` field
is documented in ADR-002 (agent model selection); valid tiers are
``opus``, ``sonnet``, and ``haiku``.

Detection is heuristic. This is a shift-left tool, not a substitute for the
CI gate. False positives are tolerable (the author reads the WARN and moves
on); a false negative reintroduces the round-7 loop.

EXIT CODES (ADR-035):
  0 - Success (no contradictions found, OR --advisory downgraded a finding,
      OR no PR / no gh / no linked issues so nothing to compare)
  1 - Logic error: one or more contradictions found (only when NOT --advisory)
  2 - Config error (could not resolve repo owner/name)

Stricter/looser/different than canonical:
  This check does NOT mirror a single canonical regex. The model-tier token
  set ``{opus, sonnet, haiku}`` is taken from the agent frontmatter contract
  documented in ADR-002, not copied from another validator. The numeric
  threshold comparison is novel to this check. The only shared contract is
  the ADR-035 exit-code table (0 ok, 1 logic, 2 config), quoted above
  verbatim from ``.agents/architecture/ADR-035-exit-code-standardization.md``.
  This check is LOOSER than the "Validate Spec Coverage" CI gate: it inspects
  only the model-tier and numeric-threshold axes, where that gate reads the
  whole spec. It is also advisory when invoked from ``pre_pr.py`` (the
  ``--advisory`` flag downgrades exit 1 to 0) so a heuristic false positive
  never blocks the local pre-PR cycle.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.github_core.api import resolve_repo_params  # noqa: E402

# Valid model tiers per ADR-002 (agent model selection). A spec text that
# names one tier while the committed agent frontmatter names another is the
# canonical PR #1897 round-7 contradiction.
MODEL_TIERS: frozenset[str] = frozenset({"opus", "sonnet", "haiku"})

# Issue-linking keywords. GitHub closes an issue on merge for the first three;
# "Implements" and "Spec" are project conventions that still point at a spec
# issue. Case-insensitive, followed by an optional colon and a `#<number>`.
_ISSUE_LINK_RE: re.Pattern[str] = re.compile(
    r"\b(?:closes|fixes|resolves|implements|refs?|spec)\b\s*:?\s*#(\d+)",
    re.IGNORECASE,
)

# Model-tier claim in spec text. Matches `model: sonnet`, `model_tier: opus`,
# `model-tier = haiku`, with optional surrounding backticks or quotes. The
# captured tier is normalized to lowercase by the caller.
_MODEL_CLAIM_RE: re.Pattern[str] = re.compile(
    r"\bmodel(?:[_-]?tier)?\b\s*[:=]\s*[`'\"]?(opus|sonnet|haiku)[`'\"]?",
    re.IGNORECASE,
)

# Numeric `key: N` claim in spec text. The key is a simple identifier; the
# value is an integer. Used to flag a spec threshold that disagrees with the
# committed frontmatter value of the same key.
_NUMERIC_CLAIM_RE: re.Pattern[str] = re.compile(
    r"\b([a-z][a-z0-9_]{2,})\b\s*[:=]\s*(\d+)\b",
    re.IGNORECASE,
)

# Numeric keys worth comparing. A blanket numeric compare would flag prose
# like "version 2" against unrelated frontmatter; restrict to keys that carry
# a threshold meaning in this codebase.
_NUMERIC_KEYS: frozenset[str] = frozenset(
    {"priority", "timeout", "max_retries", "threshold", "version", "complexity"}
)


@dataclass(frozen=True)
class Contradiction:
    """One detected mismatch between a spec claim and committed code.

    `axis` is "model-tier" or "numeric"; `claimed` is the value found in the
    PR or issue text; `committed` is the value found in the agent frontmatter;
    `source` names where the claim came from (e.g. "issue #1894").
    """

    axis: str
    key: str
    claimed: str
    committed: str
    file: str
    source: str


def fetch_current_pr_body(owner: str, repo: str) -> str | None:
    """Return the open PR body for the current branch, or None.

    Returns None (never raises) when gh is absent, no PR exists for the
    current branch, or gh fails. A missing PR is the common pre-PR case and
    must not crash the local cycle.
    """
    try:
        result = subprocess.run(
            [
                "gh", "pr", "view",
                "--json", "body",
                "-q", ".body",
                "--repo", f"{owner}/{repo}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    body = result.stdout.strip()
    return body or None


def fetch_issue_body(issue_number: int, owner: str, repo: str) -> str | None:
    """Return the body of a linked issue, or None on any failure."""
    try:
        result = subprocess.run(
            [
                "gh", "issue", "view", str(issue_number),
                "--json", "body",
                "-q", ".body",
                "--repo", f"{owner}/{repo}",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    body = result.stdout.strip()
    return body or None


def extract_linked_issues(pr_body: str) -> list[int]:
    """Return unique linked issue numbers from a PR body, in first-seen order."""
    seen: set[int] = set()
    ordered: list[int] = []
    for match in _ISSUE_LINK_RE.finditer(pr_body or ""):
        number = int(match.group(1))
        if number not in seen:
            seen.add(number)
            ordered.append(number)
    return ordered


def extract_model_claims(text: str) -> set[str]:
    """Return the set of model tiers (lowercase) claimed in spec text."""
    return {m.group(1).lower() for m in _MODEL_CLAIM_RE.finditer(text or "")}


def extract_numeric_claims(text: str) -> dict[str, set[int]]:
    """Return numeric `key -> {values}` claims for the comparison key set."""
    claims: dict[str, set[int]] = {}
    for match in _NUMERIC_CLAIM_RE.finditer(text or ""):
        key = match.group(1).lower()
        if key not in _NUMERIC_KEYS:
            continue
        claims.setdefault(key, set()).add(int(match.group(2)))
    return claims


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse a flat YAML frontmatter block into a string-keyed dict.

    Minimal parser: only the top-level ``key: value`` pairs in the leading
    ``---`` fenced block. Nested mappings (e.g. ``metadata:``) are skipped.
    Uses the same lightweight approach as
    ``scripts/validation/yaml_utils.py:_parse_yaml_frontmatter`` (top-level
    keys only, no external YAML dependency); this copy stops at the first
    nested block and does not coerce booleans or integers because the
    comparison here is string-based.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[4:end]
    result: dict[str, str] = {}
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # Skip nested entries (indented) and block openers (`key:` with no value).
        if line[0] in (" ", "\t"):
            continue
        colon = line.find(":")
        if colon == -1:
            continue
        key = line[:colon].strip()
        value = line[colon + 1 :].strip()
        if not value:
            continue
        # Strip inline YAML comments (e.g. "model: opus  # override") so the
        # trailing comment is not captured as part of the value, which would
        # cause silent false negatives. Uses the same behavior as
        # scripts/validation/yaml_utils.py:_parse_yaml_frontmatter (only strip
        # when the value does not open with a quote; cut at the first "#").
        if value[0] not in ('"', "'"):
            comment_pos = value.find("#")
            if comment_pos > 0:
                value = value[:comment_pos].strip()
                if not value:
                    continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key] = value
    return result


def find_contradictions(
    spec_text: str,
    source_label: str,
    frontmatter_files: dict[str, str],
) -> list[Contradiction]:
    """Compare spec claims against committed frontmatter; return mismatches.

    Args:
        spec_text: combined PR body + linked issue text (one source).
        source_label: human label for `spec_text` (e.g. "issue #1894").
        frontmatter_files: relpath -> committed file text (agent markdown).
    """
    contradictions: list[Contradiction] = []
    claimed_tiers = extract_model_claims(spec_text)
    claimed_numeric = extract_numeric_claims(spec_text)

    for relpath, file_text in frontmatter_files.items():
        front = parse_frontmatter(file_text)

        committed_model = front.get("model", "").lower()
        if committed_model in MODEL_TIERS and claimed_tiers:
            for tier in sorted(claimed_tiers):
                if tier != committed_model:
                    contradictions.append(
                        Contradiction(
                            axis="model-tier",
                            key="model",
                            claimed=tier,
                            committed=committed_model,
                            file=relpath,
                            source=source_label,
                        )
                    )

        for key, values in claimed_numeric.items():
            committed_raw = front.get(key, "")
            if not committed_raw.isdigit():
                continue
            committed_value = int(committed_raw)
            for claimed_value in sorted(values):
                if claimed_value != committed_value:
                    contradictions.append(
                        Contradiction(
                            axis="numeric",
                            key=key,
                            claimed=str(claimed_value),
                            committed=str(committed_value),
                            file=relpath,
                            source=source_label,
                        )
                    )

    return contradictions


def _changed_agent_files(repo_root: Path, base_ref: str) -> dict[str, str]:
    """Return committed markdown files changed on the branch with frontmatter.

    Reads each path from the HEAD blob (``git show HEAD:<path>``) rather than
    the working tree so the scan matches the committed state the CI gate sees.
    Restricted to files that begin with a ``---`` frontmatter fence.
    """
    diff = subprocess.run(
        [
            "git", "-C", str(repo_root), "diff",
            "--name-only", "--diff-filter=ACMR", f"{base_ref}...HEAD",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if diff.returncode != 0:
        return {}
    files: dict[str, str] = {}
    for relpath in diff.stdout.splitlines():
        if not relpath.endswith(".md"):
            continue
        show = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"HEAD:{relpath}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if show.returncode != 0:
            continue
        if show.stdout.startswith("---"):
            files[relpath] = show.stdout
    return files


def _resolve_base_ref(repo_root: Path) -> str | None:
    """Resolve the branch base ref, trying upstream then origin/main."""
    for ref in ("@{u}", "refs/remotes/origin/HEAD", "origin/main"):
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", ref],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return ref
    return None


def collect_contradictions(
    repo_root: Path, owner: str, repo: str, base_ref: str | None = None
) -> list[Contradiction]:
    """Fetch PR + linked issues, diff agent frontmatter, return contradictions.

    Returns an empty list (not an error) when there is no PR, no gh, no linked
    issues, or no changed agent files. Those are the common pre-PR states and
    mean "nothing to compare", not "contradiction found".

    When ``base_ref`` is provided (e.g. a value resolved by pre_pr.py's
    ``_resolve_branch_base_ref``) it is used as the diff base. Otherwise the
    base ref is resolved locally via ``_resolve_base_ref``.
    """
    pr_body = fetch_current_pr_body(owner, repo)
    if pr_body is None:
        return []

    if base_ref is None:
        base_ref = _resolve_base_ref(repo_root)
    if base_ref is None:
        return []
    frontmatter_files = _changed_agent_files(repo_root, base_ref)
    if not frontmatter_files:
        return []

    contradictions: list[Contradiction] = []
    contradictions.extend(
        find_contradictions(pr_body, "PR description", frontmatter_files)
    )
    for issue_number in extract_linked_issues(pr_body):
        issue_body = fetch_issue_body(issue_number, owner, repo)
        if issue_body is None:
            continue
        contradictions.extend(
            find_contradictions(
                issue_body, f"issue #{issue_number}", frontmatter_files
            )
        )
    return contradictions


def format_report(contradictions: list[Contradiction]) -> str:
    """Render a human-readable report of contradictions."""
    if not contradictions:
        return "[PASS] No spec-vs-code contradictions detected."
    lines = [
        f"[WARN] {len(contradictions)} spec-vs-code contradiction(s) detected:",
    ]
    for c in contradictions:
        lines.append(
            f"  - {c.file}: spec ({c.source}) claims {c.key}={c.claimed!r} "
            f"but committed frontmatter has {c.key}={c.committed!r} "
            f"(axis: {c.axis})"
        )
    lines.append(
        "  Fix: update the PR description and linked issue to match the "
        "committed value, or change the committed value to match the spec."
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with env var defaults."""
    parser = argparse.ArgumentParser(
        description=(
            "Flag contradictions between a PR description, its linked "
            "issues, and committed agent frontmatter."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=str(_PROJECT_ROOT),
        help="Repository root (default: inferred from this script's path)",
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
        "--advisory",
        action="store_true",
        default=os.environ.get("SPEC_CONTRADICTION_ADVISORY", "").lower()
        in ("1", "true"),
        help=(
            "Advisory mode: print findings but always exit 0 "
            "(env: SPEC_CONTRADICTION_ADVISORY). Used by pre_pr.py."
        ),
    )
    parser.add_argument(
        "--base",
        default=None,
        help=(
            "Base ref to diff committed agent frontmatter against "
            "(e.g. origin/main). When omitted, resolved locally from the "
            "branch upstream, origin/HEAD, then origin/main."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an ADR-035 exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    owner: str = args.owner
    repo: str = args.repo

    try:
        info = resolve_repo_params(owner, repo)
    except SystemExit:
        return 2
    owner = info.owner
    repo = info.repo

    contradictions = collect_contradictions(
        repo_root, owner, repo, base_ref=args.base
    )
    print(format_report(contradictions))

    if contradictions and not args.advisory:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
