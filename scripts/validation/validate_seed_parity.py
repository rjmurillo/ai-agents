#!/usr/bin/env python3
"""Forensic tool: was a canonical review-axis hand-paraphrased or verbatim-seeded?

This is a FORENSIC TOOL, not a regression gate. Do NOT add it to CI.

Background. REQ-008-01 mandated that each canonical
``.claude/skills/review-axes/references/{role}.md`` was seeded verbatim from the matching
``.github/prompts/pr-quality-gate-{role}.md`` at the seeding commit on
the main branch. The seed transform adds YAML frontmatter, balances any
unclosed code fence, and appends an ``## Output Schema`` section. The
underlying body must round-trip: SHA-256 of the canonical body (minus
those additions) must equal SHA-256 of the CI prompt body on main.

What this script does. Compares those two SHA-256 values per role and
reports parity. Useful when a maintainer is investigating whether a
specific canonical file was hand-paraphrased after the seed event
(rather than copy-pasted character-for-character).

When this script will FAIL by design. Once a maintainer intentionally
edits the canonical body (and the canonical IS the system of record),
the script will report a mismatch. That is expected. PR #1965 already
amended canonical files for vendored-install survival, UNKNOWN
handling, and severity-token alignment, so on the post-merge tree the
script will not pass. Treat a non-zero exit as evidence of intentional
divergence, not a regression. PR #1965 critic Finding 6 + copilot 6l8V.

Usage::

    python3 scripts/validation/validate_seed_parity.py        # all 6 roles
    python3 scripts/validation/validate_seed_parity.py analyst architect

Exit codes (per ADR-035):
    0  Canonical body and CI prompt body match (verbatim seed intact).
    1  Mismatch (canonical was edited after seed, or never seeded
       verbatim). NOT a regression on a post-#1934 tree.
    2  Configuration error (missing canonical, missing CI prompt source
       on main, or git unavailable). Always a real problem.

Refs #1934 (REQ-008-01) PR #1965.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CANONICAL_DIR = REPO_ROOT / ".claude" / "skills" / "review-axes" / "references"
CI_PROMPTS_DIR = REPO_ROOT / ".github" / "prompts"

ALL_ROLES: tuple[str, ...] = (
    "analyst",
    "architect",
    "qa",
    "security",
    "devops",
    "roadmap",
)


class ParityError(Exception):
    """Domain error for seed parity validation."""


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end_idx = text.find("\n---\n", 4)
    if end_idx == -1:
        return "", text
    return text[4:end_idx], text[end_idx + 5 :]


def _strip_appended_output_schema(body: str) -> str:
    """Remove the trailing ``## Output Schema`` section added by the seed.

    The seed appended a ``## Output Schema`` section containing the canonical
    field list and the verdict-line regex contract. Strip it for parity
    comparison; the CI source did not have this section.
    """
    marker = "\n## Output Schema\n"
    idx = body.rfind(marker)
    if idx == -1:
        return body
    return body[:idx]


def _strip_balanced_fence(body: str, ci_body: str) -> str:
    """Drop the trailing ```` ``` ```` line if it was added to balance fences.

    The seed appended a closing ```` ``` ```` when the CI source had an odd
    number of fence markers (an intentionally unclosed ```` ```json ````
    template at the end of several CI prompts). Strip it only when the CI
    source had an odd fence count.
    """
    ci_fence_count = sum(1 for line in ci_body.splitlines() if line.startswith("```"))
    if ci_fence_count % 2 == 0:
        return body
    # Remove a trailing closing fence if present.
    return re.sub(r"\n```\n*$", "\n", body)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_for_compare(text: str) -> str:
    """Normalize whitespace so insignificant differences do not break parity.

    - strip trailing whitespace from every line
    - strip leading and trailing blank lines (frontmatter strip leaves a
      blank where the closing ``---`` was)
    - enforce a single trailing newline
    """
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n"


def _ci_source_from_main(role: str) -> str | None:
    """Read the CI prompt as it existed on the main branch (pre-PR seed).

    The current PR's generator overwrites .github/prompts/pr-quality-gate-{role}.md
    with regenerated content. To verify SEED parity (canonical body matches
    what was on main before this PR), we compare against git's historical
    copy, not the current working-tree copy.
    """
    import subprocess

    rel = f".github/prompts/pr-quality-gate-{role}.md"
    try:
        result = subprocess.run(
            ["git", "show", f"main:{rel}"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def check_role(role: str) -> tuple[bool, str]:
    """Return (parity_ok, message) for one role."""
    canonical = CANONICAL_DIR / f"{role}.md"

    if not canonical.is_file():
        raise ParityError(f"canonical missing: {canonical}")

    # The seed parity check is meaningful ONLY against the pre-PR CI prompt
    # content from the main branch. Falling back to the working-tree copy
    # silently produces false `status=ok` when canonical was regenerated
    # from the same source, which defeats the purpose of seed parity.
    # PR #1965 coderabbit H_6: fail closed when base-branch CI source is
    # unavailable.
    ci_text_from_main = _ci_source_from_main(role)
    if ci_text_from_main is None:
        raise ParityError(
            f"CI source on main missing or unreadable for role={role}; "
            "seed parity is a one-shot verification against the original "
            "CI prompts, NOT the regenerated working-tree copy"
        )
    ci_text = ci_text_from_main
    source_label = "main"

    canonical_text = canonical.read_text(encoding="utf-8")

    # Drop CI header that the generator prepends (in case ci_text is from
    # working tree post-regen).
    ci_body_after_strip = re.sub(r"\A(?:<!--[^\n]*-->\n){1,5}\n?", "", ci_text)

    _, canonical_body = _split_frontmatter(canonical_text)
    canonical_body = _strip_appended_output_schema(canonical_body)
    canonical_body = _strip_balanced_fence(canonical_body, ci_body_after_strip)

    canonical_hash = _hash(_normalize_for_compare(canonical_body))
    ci_hash = _hash(_normalize_for_compare(ci_body_after_strip))

    if canonical_hash == ci_hash:
        return (
            True,
            f"role={role} status=ok source={source_label} "
            f"hash={canonical_hash[:16]}",
        )
    return (
        False,
        f"role={role} status=mismatch source={source_label} "
        f"canonical_hash={canonical_hash[:16]} ci_hash={ci_hash[:16]}",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify canonical review-axes were seeded faithfully from CI prompts. "
            "REQ-008-01 (issue #1934). ADR-035 exit codes."
        )
    )
    parser.add_argument(
        "roles",
        nargs="*",
        choices=list(ALL_ROLES) + [],
        help="roles to check (default: all 6 canonical roles)",
    )
    args = parser.parse_args(argv)

    roles = args.roles or list(ALL_ROLES)

    mismatches = 0
    for role in roles:
        try:
            ok, message = check_role(role)
        except ParityError as exc:
            print(f"role={role} status=config_error error={exc}")
            return 2
        print(message)
        if not ok:
            mismatches += 1

    if mismatches > 0:
        print(f"role=ALL status=mismatch count={mismatches}")
        return 1
    print(f"role=ALL status=ok count={len(roles)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
