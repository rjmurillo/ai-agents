"""Bind the SKILL.md contract for the capability scripts (mine, forms, drift, eval).

Companion to test_skill_md_contract.py, which owns the boundary-script contract.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_skill_md_contract import _skill_dir, _skill_md, locator_calls

BUNDLED_SCRIPTS = (
    "scripts/bootstrap_boundary.py",
    "scripts/bootstrap_mine.py",
    "scripts/bootstrap_forms.py",
    "scripts/bootstrap_drift.py",
    "scripts/bootstrap_eval.py",
)


def test_capability_eval_runs_between_context_optimizer_and_skillopt() -> None:
    text = _skill_md()
    heading = re.search(r"^### Phase 5: .*$", text, re.MULTILINE)
    assert heading is not None
    title = heading.group(0)
    assert title.index("context-optimizer") < title.index("capability eval")
    assert title.index("capability eval") < title.index("skillopt")


@pytest.mark.parametrize(
    "script", ("bootstrap_mine.py", "bootstrap_forms.py", "bootstrap_drift.py", "bootstrap_eval.py")
)
def test_every_bundled_script_is_documented_with_the_portable_root(script: str) -> None:
    assert script in {name for name, _ in locator_calls(_skill_md())}


def test_every_script_on_disk_is_bundled_and_documented() -> None:
    on_disk = {f"scripts/{p.name}" for p in (_skill_dir(".claude") / "scripts").glob("*.py")}
    text = _skill_md()

    helpers = {
        "scripts/adr_commits.py",
        "scripts/adr_docs.py",
        # Listed as a helper until the skill step documents its locator (issue #7499).
        "scripts/bootstrap_adr.py",
        "scripts/adr_scan.py",
        "scripts/adr_locate.py",
        "scripts/adr_log.py",
        "scripts/adr_reason.py",
        "scripts/adr_shape.py",
        "scripts/adr_write.py",
        "scripts/bootstrap_friction.py",
        "scripts/bootstrap_sweep.py",
        "scripts/bootstrap_sweep_import.py",
        # The reply-friction audit is documented in references/reply-friction.md.
        "scripts/replies_audit.py",
        "scripts/replies_corpus.py",
        "scripts/replies_flags.py",
        "scripts/replies_prepare.py",
        "scripts/replies_sample.py",
        "scripts/replies_tally.py",
        "scripts/boundary_grants.py",
        "scripts/bootstrap_review.py",
        "scripts/review_clusters.py",
    }
    assert on_disk == set(BUNDLED_SCRIPTS) | helpers
    assert "`bootstrap_friction.py`" in text
    assert "`bootstrap_sweep.py`" in text
    assert "`review_clusters.py`" in text
    assert "`bootstrap_review.py`" in text
    documented = {name for name, _ in locator_calls(text)}
    for rel in BUNDLED_SCRIPTS:
        assert rel.removeprefix("scripts/") in documented, rel


def test_skill_md_defines_both_tool_forms_and_both_modes() -> None:
    text = _skill_md()

    for term in ("**scaffold**", "**instrument**", "`workflow` (default)", "`knowledge`"):
        assert term in text, term
