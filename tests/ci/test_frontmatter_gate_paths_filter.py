"""The frontmatter gate must run whenever the surface it scans changes.

A gate that scans more than its trigger covers is the exact defect this gate
was written to catch. ``check_plugin_frontmatter_self_containment.py`` walks
every Markdown file under all three plugin roots, so the ``dorny/paths-filter``
entry that decides whether the required job runs has to cover all three roots
whole, not a hand-listed subset of their subdirectories.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/validate-generated-agents.yml"


def _gate():
    path = REPO_ROOT / "scripts/validation/check_plugin_frontmatter_self_containment.py"
    spec = importlib.util.spec_from_file_location("frontmatter_gate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["frontmatter_gate"] = module
    spec.loader.exec_module(module)
    return module


def _filter_patterns() -> list[str]:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in document["jobs"]["check-paths"]["steps"]:
        filters = step.get("with", {}).get("filters")
        if filters:
            return yaml.safe_load(filters)["agents"]
    raise AssertionError("no paths-filter step in check-paths")


def test_every_scanned_root_is_covered_whole() -> None:
    patterns = set(_filter_patterns())
    missing = [root for root in _gate().PLUGIN_ROOTS if f"{root}/**" not in patterns]
    assert missing == [], (
        f"The gate scans {missing} but the paths filter does not cover them whole, "
        "so a PR touching only those files would skip the required check."
    )


def test_the_gate_step_is_present_and_guarded() -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["validate"]["steps"]
    needle = "check_plugin_frontmatter_self_containment"
    matches = [step for step in steps if needle in str(step.get("run", ""))]
    assert len(matches) == 1, "expected exactly one frontmatter gate step"
    assert matches[0].get("if") == "steps.should-run.outputs.skip != 'true'"
