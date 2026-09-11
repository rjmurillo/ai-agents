"""Pins which skills are template-owned (ADR-108 section 1) on the real tree.

``skill_templates.owned_targets`` is the allowlist
:func:`build_all.assert_no_claude_writes` accepts for writes under
``.claude/``. Its membership is read from ``templates/skills/*.SKILL.md.tmpl``
at run time, per ADR-108 section 1: "A skill joins the class by the presence
of ``templates/skills/<name>.SKILL.md.tmpl`` ... Membership is read from the
directory at run time; no list of names is kept anywhere else." That is a
deliberate design choice (no second list to drift against the directory), but
it also means nothing else in the repository asserts how big that allowlist
is allowed to be on any given commit. Without this test, a template dropped
into ``templates/skills/`` by mistake, or a batch of templates landing ahead
of the review that is supposed to gate them, would silently widen the set of
paths this repository's generators may write under ``.claude/``, and no
existing gate would say so.

``PILOT`` is that assertion. A1 (this change) ships the compile module with
zero templates on disk, so ``PILOT`` is the empty set here. Widening it is an
owner decision, recorded by editing this constant in the same commit that adds
the templates it names: TASK-025's dependency on TASK-024 landing before this
gate, and TASK-026 (the pilot templates themselves) is where ``PILOT`` next
changes, to the eight names DESIGN-020 lists under "Pilot content". A PR that
adds a ``.tmpl`` file without updating this constant fails
``test_discover_matches_the_declared_pilot_set`` below, which is the point:
the failure names the mismatch instead of letting the allowlist grow quietly.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import skill_templates  # noqa: E402

# Empty in A1 (this change): no templates exist under templates/skills/ yet.
# TASK-026 sets this to the eight pilot names DESIGN-020 "Pilot content"
# lists (sync, test, spec, ship, research, plan, checkpoint, build) in the
# same commit that adds their .tmpl files.
PILOT: frozenset[str] = frozenset()


def test_discover_matches_the_declared_pilot_set() -> None:
    """The real tree's template-owned skills are exactly ``PILOT``.

    This is the control on ADR-108's ``.claude/`` write allowlist: it fails
    the moment ``templates/skills/`` gains or loses a template without a
    matching edit to ``PILOT`` in this file, in either direction.
    """
    assert set(skill_templates.discover(REPO_ROOT)) == PILOT


def test_discover_reports_an_extra_template_the_pilot_set_does_not_name(
    tmp_path: Path,
) -> None:
    """Negative control: proves the assertion above is not vacuous.

    Copies the real ``templates/skills/`` tree (if any) into ``tmp_path``,
    adds one more ``.tmpl`` file, and asserts ``discover()`` reports it. If
    this failed to detect the addition, the positive test above would pass
    for the wrong reason: an empty ``PILOT`` matching an empty ``discover()``
    result regardless of whether ``discover()`` actually inspects the
    directory.
    """
    real_templates_dir = REPO_ROOT / "templates" / "skills"
    fixture_templates_dir = tmp_path / "templates" / "skills"
    if real_templates_dir.is_dir():
        shutil.copytree(real_templates_dir, fixture_templates_dir)
    else:
        fixture_templates_dir.mkdir(parents=True)

    before = set(skill_templates.discover(tmp_path))
    assert before == PILOT

    # discover() (PR review of ADR-108) now also requires a valid, slug-
    # shaped name AND an existing .claude/skills/<name>/ directory, so the
    # added candidate needs both to prove discover() picked up a genuinely
    # new, VALID entry rather than being excluded by the newer checks.
    (fixture_templates_dir / "unplanned-extra.SKILL.md.tmpl").write_text(
        "# unplanned\nno partials\n", encoding="utf-8"
    )
    (tmp_path / ".claude" / "skills" / "unplanned-extra").mkdir(parents=True)

    after = set(skill_templates.discover(tmp_path))

    assert after == before | {"unplanned-extra"}
