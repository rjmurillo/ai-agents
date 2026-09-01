"""Parsing and lookup helpers shared by the reviewer-findings contract suite.

Split out of ``test_reviewer_findings_routes.py`` to keep that file under the
repository's 500-line file-size ceiling
(``scripts/validation/check_taste_lints.py``, enforced by the
``taste-count-ratchet`` pre-push gate). Not itself a test file: pytest only
collects ``test_*.py``/``*_test.py``, so this module is never discovered as a
test module and needs no ``test_`` prefix.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_NAME = "reviewer-findings"
ROUTER_SKILL = "pr-comment-responder"

# tests/skills/reviewer-findings/_helpers.py -> skills/ -> tests/ -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]

# Roots that ship reviewer-findings and pr-comment-responder to consumers.
# Single source of truth for both the plugin_root fixture (conftest.py) and
# the converse-guard test that checks every on-disk root shipping this skill
# is represented here (Cursor Bugbot on PR #5178: a third mirror could land
# and stay untested while this map silently stayed at two entries).
PLUGIN_ROOTS: dict[str, Path] = {
    "claude": REPO_ROOT / ".claude",
    "copilot-cli": REPO_ROOT / "src" / "copilot-cli",
}

# Claude roots invoke a skill as Skill(skill="name"). The Copilot body
# translation rewrites that same call to skill: "name". Both forms appear
# inline inside backticks, so neither is anchored to the line start.
ROUTE_PATTERNS = (
    re.compile(r'Skill\(skill="([a-z0-9][a-z0-9-]*)"\)'),
    re.compile(r'skill:\s*"([a-z0-9][a-z0-9-]*)"'),
)


def _skills_dir(plugin_root: Path) -> Path:
    return plugin_root / "skills"


def _read(plugin_root: Path, skill: str) -> str:
    path = _skills_dir(plugin_root) / skill / "SKILL.md"
    if not path.is_file():
        pytest.fail(f"{skill}/SKILL.md is missing from plugin root {plugin_root}")
    return path.read_text(encoding="utf-8")


def _read_reference(plugin_root: Path, skill: str, filename: str) -> str:
    path = _skills_dir(plugin_root) / skill / "references" / filename
    if not path.is_file():
        pytest.fail(f"{skill}/references/{filename} is missing from plugin root {plugin_root}")
    return path.read_text(encoding="utf-8")


def _routed_skills(text: str) -> set[str]:
    """Return every skill name invoked as a route in ``text``."""
    found: set[str] = set()
    for pattern in ROUTE_PATTERNS:
        found.update(pattern.findall(text))
    return found


# The router's phases are ordered work. Verification has to happen while the
# finding is being triaged, not after the fix is written, or the skill's whole
# premise ("verify before you fix") is lost while the route still exists.
PHASE_HEADING_RE = re.compile(r"^### Phase (-?\d+)(?![.\d])[^\n]*$", re.MULTILINE)
FENCE_RE = re.compile(
    r"^(?P<fence>```+|~~~+)[^\n]*\n.*?^(?P=fence)[^\n]*$\n?",
    re.MULTILINE | re.DOTALL,
)
TRIAGE_PHASE = "2"
VERIFY_PHASE = "3"


def _blank_fences(text: str) -> str:
    """Blank fenced blocks, preserving offsets so heading positions stay comparable."""
    return FENCE_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _phase_headings(text: str) -> list[tuple[str, int, int]]:
    """Return ``(number, heading_start, body_start)`` for each real phase heading."""
    scannable = _blank_fences(text)
    return [(m.group(1), m.start(), m.end()) for m in PHASE_HEADING_RE.finditer(scannable)]


def _phase_heading_start(text: str, phase: str) -> int:
    """Return the offset where ``### Phase N`` begins, failing loudly when absent."""
    for number, start, _ in _phase_headings(text):
        if number == phase:
            return start
    pytest.fail(f"no '### Phase {phase}' heading found outside fenced blocks")


def _phase_section(text: str, phase: str) -> str:
    """Return the body of one ``### Phase N`` section, excluding later phases."""
    starts = _phase_headings(text)
    for index, (number, _, body_start) in enumerate(starts):
        if number != phase:
            continue
        body_end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        return text[body_start:body_end]
    pytest.fail(f"no '### Phase {phase}' heading found; phases present: "
                f"{[n for n, _, _ in starts] or 'none'}")


# workflow.md uses "## Phase N" (h2), one level shallower than the SKILL.md
# "### Phase N" (h3) the helpers above target, so it needs its own heading regex.
WORKFLOW_PHASE_HEADING_RE = re.compile(r"^## Phase (-?\d+)(?![.\d])[^\n]*$", re.MULTILINE)


def _workflow_phase_section(text: str, phase: str) -> str:
    """Return the body of one workflow.md ``## Phase N`` section."""
    scannable = _blank_fences(text)
    starts = [
        (m.group(1), m.start(), m.end())
        for m in WORKFLOW_PHASE_HEADING_RE.finditer(scannable)
    ]
    for index, (number, _, body_start) in enumerate(starts):
        if number != phase:
            continue
        body_end = starts[index + 1][1] if index + 1 < len(starts) else len(text)
        return text[body_start:body_end]
    pytest.fail(f"no '## Phase {phase}' heading found in workflow.md; phases present: "
                f"{[n for n, _, _ in starts] or 'none'}")


# Premise verification: a finding can be internally consistent with a pre-fix
# tree (grok-4.5 on PR #4485, see dispatched-model-reviewer-reliability.md).
# These helpers back the tests guarding that reviewer-findings names the
# concrete git commands that expose that shape, and that pr-comment-responder
# gates Action: Implement on running them before a code change, per #5069.

DISPOSITION_TOKENS = ("True", "False", "Unverifiable", "Confirmed", "Declined", "Unreproduced")


def _missing_disposition_tokens(text: str) -> list[str]:
    """Return which disposition-mapping tokens are absent from ``text``.

    Shared by the positive smoke test and its negative control so a weakened
    or deleted mapping check fails both the same way (Copilot review on PR
    #5178: a negative control that reimplements its own substring check
    instead of calling the real one cannot detect the real one breaking).
    """
    return [token for token in DISPOSITION_TOKENS if token not in text]


def _row_disposition(text: str, premise: str) -> str | None:
    """Return the Disposition cell for ``premise``'s own table row, or ``None``.

    Shared by the row-pairing positive test and its negative control, for the
    same reason as ``_missing_disposition_tokens`` above.
    """
    row = re.search(rf"^\|\s*{premise}\s*\|.*\|\s*([^|]*)\|\s*$", text, re.MULTILINE)
    return row.group(1) if row else None


HEADING_RE = re.compile(r"^### .+$", re.MULTILINE)


def _bounded_section(text: str, heading: str) -> str | None:
    """Return the body after ``heading``, stopping at the next ``### `` heading.

    Returns ``None`` when ``heading`` is absent. Bounding at the next heading
    (rather than running to end-of-file) keeps a later template's fields from
    masking a regression in this one (Copilot review on PR #5178, line 307).
    """
    start = text.find(heading)
    if start == -1:
        return None
    body_start = start + len(heading)
    next_heading = HEADING_RE.search(text, body_start)
    body_end = next_heading.start() if next_heading else len(text)
    return text[body_start:body_end]
