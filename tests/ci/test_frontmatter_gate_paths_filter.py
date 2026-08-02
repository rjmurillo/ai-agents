"""The frontmatter gate must run whenever the surface it scans changes.

A gate that scans more than its trigger covers is the exact defect this gate
was written to catch. ``check_plugin_frontmatter_self_containment.py`` walks
every Markdown file under all three plugin roots, so the ``dorny/paths-filter``
entry that decides whether the required job runs has to cover all three roots
whole, not a hand-listed subset of their subdirectories.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/validate-generated-agents.yml"
MARKETPLACE_MANIFESTS = (
    REPO_ROOT / ".github/plugin/marketplace.json",
    REPO_ROOT / ".claude-plugin/marketplace.json",
)
PATHS_FILTER_ACTION = "dorny/paths-filter@"


def _paths_filter_steps(steps: list[dict]) -> list[dict]:
    """Select by the action, not by the shape.

    A search for the first step carrying a ``with.filters`` key picks up any
    other step that grows one later, and every assertion downstream then reports
    against a step that was never the subject.
    """
    return [step for step in steps if str(step.get("uses", "")).startswith(PATHS_FILTER_ACTION)]


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
    steps = _paths_filter_steps(document["jobs"]["check-paths"]["steps"])
    assert steps, f"no {PATHS_FILTER_ACTION} step in check-paths"
    return yaml.safe_load(steps[0]["with"]["filters"])["agents"]


def _manifest_sources() -> list[str]:
    sources: list[str] = []
    for manifest in MARKETPLACE_MANIFESTS:
        document = json.loads(manifest.read_text(encoding="utf-8"))
        for plugin in document["plugins"]:
            source = plugin["source"].removeprefix("./").rstrip("/")
            if source not in sources:
                sources.append(source)
    return sources


def test_scanner_roots_match_marketplace_manifest_sources() -> None:
    expected = _manifest_sources()
    assert set(_gate().PLUGIN_ROOTS) == set(expected)


def test_every_manifest_source_is_covered_whole() -> None:
    patterns = set(_filter_patterns())
    missing = [root for root in _manifest_sources() if f"{root}/**" not in patterns]
    assert missing == [], (
        f"The manifests ship {missing} but the paths filter does not cover them whole, "
        "so a PR touching only those files would skip the required check."
    )


def test_the_gate_step_is_present_and_guarded() -> None:
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = document["jobs"]["validate"]["steps"]
    needle = "check_plugin_frontmatter_self_containment"
    matches = [step for step in steps if needle in str(step.get("run", ""))]
    assert len(matches) == 1, "expected exactly one frontmatter gate step"
    assert matches[0].get("if") == "steps.should-run.outputs.skip != 'true'"
    assert str(matches[0].get("run", "")).startswith("uv run python "), (
        "the gate must run through the project environment"
    )


def test_the_filter_result_actually_reaches_the_gate() -> None:
    """Follow the wiring, not the strings on either end of it.

    Covering the roots in the filter and guarding the gate step both pass while
    the link between them is broken: renaming the paths-filter step's ``id``
    leaves ``steps.<old>.outputs.agents`` resolving to empty, which reads as
    "nothing changed" and skips the required job. GitHub does not error on a
    reference to a step that does not exist, so nothing else catches this.
    Each hop below is resolved from the previous one rather than hardcoded, so
    renaming any link breaks the chain here.
    """
    document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    check = document["jobs"]["check-paths"]

    filter_steps = _paths_filter_steps(check["steps"])
    assert len(filter_steps) == 1, f"expected exactly one {PATHS_FILTER_ACTION} step"
    filter_id = filter_steps[0].get("id")
    assert filter_id, "the paths-filter step needs an id or its output is unreadable"

    published = str(check.get("outputs", {}).get("should-run-agents", ""))
    if f"steps.{filter_id}.outputs.agents" not in published:
        # The output may name an intermediate step instead of the filter. That
        # is still a valid chain, so long as the step it names reads the
        # filter's output.
        deciders = [
            step
            for step in check["steps"]
            if f"steps.{filter_id}.outputs.agents" in str(step.get("env", {}))
            and step.get("id")
            and f"steps.{step['id']}.outputs." in published
        ]
        assert deciders, (
            f"check-paths publishes {published!r}, which neither reads "
            f"steps.{filter_id}.outputs.agents nor names a step that does"
        )

    validate = document["jobs"]["validate"]
    needs = validate["needs"]
    assert "check-paths" in ([needs] if isinstance(needs, str) else needs)
    guards = [
        step
        for step in validate["steps"]
        if "needs.check-paths.outputs.should-run-agents" in str(step.get("env", {}))
    ]
    assert guards, "validate never reads the check-paths decision"
    assert guards[0].get("id") == "should-run", (
        "the gate step's `if:` names steps.should-run, so the guard step must be it"
    )
