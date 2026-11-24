#!/usr/bin/env python3
"""Citing-file exemptions for the citation-freshness gate.

Extracted from ``check_citation_freshness.py`` at the file-size ceiling.
Historical trees, generated skill mirrors, fixture trees, and recorded
eval runs synthesize citations or copy them from a policed source.
"""

from __future__ import annotations

import re

from stale_script_refs import HISTORICAL_ROOTS

# Directory fragments whose files synthesize citations on purpose.
_FIXTURE_FRAGMENTS = ("/fixtures/",)

# Recorded eval runs (evals/<name>/runs/**/*.jsonl). Raw model replies quote
# the invented paths of the prompts under test, and a run record is a
# point-in-time capture, like a session log. Authored files there stay policed.
_EVAL_RUN_RECORD = re.compile(
    r"^evals/[^/]+/runs/.+\.jsonl$"
    # durable-outcome-live run reports hold the same raw replies (issue #5768).
    r"|^evals/durable-outcome-live/.+/report[^/]*\.json$"
    r"|^evals/docs-review-catch-rate/[^/]+/results/.+\.json$"
    # sol-loop run logs record each finding's file:line at the reviewed head.
    # The skill commits them with the branch, and JSON cannot carry an ignore
    # marker, so a later fix that moves the cited code would block the branch.
    r"|^\.project-toolkit/metrics/sol-loop/[^/]+\.json$"
)

# Historical trees this gate exempts beyond stale_script_refs's tuple:
# episode records are point-in-time captures, exactly like sessions and
# retrospectives, and that tuple is another gate's contract to widen.
_EXTRA_HISTORICAL_ROOTS = (
    ".project-toolkit/memory/",
    ".project-toolkit/planning/",
    ".project-toolkit/pr-comments/",
    ".project-toolkit/qa/",
    ".project-toolkit/retrospective/",
)

# Generated skill mirrors (build/scripts/generate_skills.py,
# build/scripts/skill_support_mirror.py): .claude/skills/ is the canonical,
# hand-maintained source, copied byte for byte into src/claude/skills/ and
# src/copilot-cli/skills/. A citation's staleness is a property of the prose,
# not of which tree happens to carry a copy of it; policing the same broken
# citation again at each mirror path would flag it once per generated copy
# instead of once at the source that should actually be fixed, and would
# retroactively flag EVERY pre-existing citation drift in a skill the first
# time the build populates a new mirror tree for it (ADR-109 B3's
# support-file follow-up populated src/claude/skills/ for 84 skills in one
# PR). Exempted by prefix, not content match: this gate checks prose
# accuracy, not byte identity, so there is nothing content comparison would
# add here that the source's own (still-enforced) citations do not already
# cover.
#
# src/hermes/ (ADR-115 Decision 6) joins the list: each pack copies skills/<name>/
# and the rendered lib/ from those same sources, so the same reasoning holds.
_GENERATED_SKILL_MIRROR_ROOTS = (
    "src/claude/skills/",
    "src/copilot-cli/skills/",
    "src/hermes/",
    "src/codex/skills/",
    "src/muse/skills/",
    # Lib packages render from scripts/ with an import rewrite (lib_mirror.py).
    "src/codex/lib/",
    "src/muse/lib/",
    "src/cursor/skills/",
    # ADR-115: the Cursor tree also renders rules (.mdc) and lib/ from canonical
    # sources, so a citation there is policed once at the source.
    "src/cursor/rules/",
    "src/cursor/lib/",
)


def _is_exempt_citing_file(path: str) -> bool:
    """Return whether a citing file is out of this gate's scope."""
    if path.startswith(HISTORICAL_ROOTS) or path.startswith(_EXTRA_HISTORICAL_ROOTS):
        return True
    if path.startswith(_GENERATED_SKILL_MIRROR_ROOTS) or _EVAL_RUN_RECORD.match(path):
        return True
    # The leading slash makes the fragment match a top-level fixtures/
    # directory too, not only nested ones (diff paths are repo-relative).
    return any(fragment in f"/{path}" for fragment in _FIXTURE_FRAGMENTS)
