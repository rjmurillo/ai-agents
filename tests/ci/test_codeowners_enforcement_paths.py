"""Every enforcement path must carry a CODEOWNERS entry.

ADR-101 Phase 0 item 3 (issue #5244). ADR-101's invariant is that a gate
protecting artifacts at plane N computes its verdict above N, from evidence
the gated actor cannot forge. The paths pinned here decide whether a change
may merge, so an unowned one is a gate a pull request can edit without any
review above it.

This pins a seed list, not the closure. ADR-101's typed dependency closure
(Phase 1) computes the real edge set and fails closed on an unresolvable
edge. An earlier hand-written revision of this same list omitted
``scripts/workflows/``, which is why the closure exists.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"

# Seed set from issue #5244 item 3. Each entry is the CODEOWNERS pattern, not
# a filesystem path: a leading slash anchors to the repository root and a
# trailing slash marks a directory.
ENFORCEMENT_PATTERNS: frozenset[str] = frozenset(
    {
        "/.github/workflows/",
        "/.github/actions/",
        "/scripts/validation/",
        "/scripts/ci/",
        "/scripts/workflows/",
        "/build/scripts/",
        "/lefthook.yml",
        "/.github/CODEOWNERS",
    }
)


def parse_codeowners(text: str) -> dict[str, list[str]]:
    """Map each CODEOWNERS pattern to its owner list.

    Comments and blank lines are ignored. A line with a pattern but no owner
    is retained with an empty owner list so a caller can reject it; GitHub
    treats such a line as removing ownership rather than granting it.
    """
    owners: dict[str, list[str]] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        owners[fields[0]] = fields[1:]
    return owners


def test_every_enforcement_path_has_an_owner() -> None:
    """Positive: each seed pattern is present with at least one owner."""
    owners = parse_codeowners(CODEOWNERS.read_text(encoding="utf-8"))
    missing = sorted(p for p in ENFORCEMENT_PATTERNS if p not in owners)
    assert not missing, f"enforcement paths absent from CODEOWNERS: {missing}"
    unowned = sorted(p for p in ENFORCEMENT_PATTERNS if not owners.get(p))
    assert not unowned, f"enforcement paths present but unowned: {unowned}"


def test_a_missing_enforcement_path_is_detected() -> None:
    """Negative control: the check fails when a pattern is dropped.

    Without this, the positive test could pass against a parser that returned
    every pattern regardless of file contents.
    """
    text = CODEOWNERS.read_text(encoding="utf-8").replace(
        "/scripts/workflows/", "/scripts/workflows-renamed/"
    )
    owners = parse_codeowners(text)
    assert "/scripts/workflows/" not in owners


def test_a_pattern_with_no_owner_is_reported_unowned() -> None:
    """Negative: an ownerless line grants nothing and must not count."""
    owners = parse_codeowners("/scripts/ci/\n")
    assert owners == {"/scripts/ci/": []}
    assert not owners["/scripts/ci/"]


def test_comments_and_blank_lines_are_ignored() -> None:
    """Edge: comment lines, inline comments, and blanks parse away."""
    owners = parse_codeowners(
        "# a comment\n\n"
        "/scripts/ci/ @rjmurillo  # trailing comment\n"
        "   \n"
    )
    assert owners == {"/scripts/ci/": ["@rjmurillo"]}


def test_scripts_workflows_is_owned() -> None:
    """The entry that an earlier hand-written revision omitted.

    determine_should_run_from_filters.py lives here and decides six of the
    eight contexts pinned in scripts/ci/ruleset_required_contexts.py.
    """
    owners = parse_codeowners(CODEOWNERS.read_text(encoding="utf-8"))
    assert owners.get("/scripts/workflows/")
