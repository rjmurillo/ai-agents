"""Path-filter wiring for the agent-skill discriminator workflow (issue #4087).

The gate reads the diff, so a path filter is the right shape for it
(`.claude/rules/ci-scripts.md`, "Path filters gate the diff, never the tree").
What a diff-shaped filter still has to do is name every file whose change can
alter the verdict. `check_agent_skill_discriminator.py` moved half its logic
into `agent_skill_discriminator_baseline.py` and the filter kept naming only
the first, so a PR touching only the helper matched nothing, `check-paths`
emitted `should-run-discriminator != 'true'`, and `skip-discriminator`
reported a fresh green tick in the checker's place. Nothing was inherited from
an earlier run; the tick asserted only that the diff looked uninteresting.

Asserted against the parsed object graph, never a substring of the YAML text,
per `.claude/rules/testing.md` MUST-9: a text match passes when the pattern
survives in a comment or a neighbouring job after the filter entry itself has
been deleted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = (
    _REPO_ROOT / ".github" / "workflows" / "agent-skill-discriminator-check.yml"
)

# Every first-party module the checker's own logic lives in. A change to any
# one of them can move an agent's score, so a diff touching only that file
# must still run the gate.
_DISCRIMINATOR_SOURCES = (
    "scripts/validation/check_agent_skill_discriminator.py",
    "scripts/validation/agent_skill_discriminator_baseline.py",
    "scripts/validation/portability_*.py",
)


def _agent_filter_patterns() -> list[str]:
    """The parsed ``agents`` filter patterns from the paths-filter step.

    ``filters:`` is a YAML document nested inside a workflow string scalar, so
    it is parsed twice: once to reach the step, once to read the filter body.
    Both reads go through ``yaml.safe_load``; neither inspects raw text.
    """
    workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["check-paths"]["steps"]
    filter_steps = [
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("dorny/paths-filter@")
    ]
    assert len(filter_steps) == 1, (
        f"Expected exactly one dorny/paths-filter step in check-paths, found "
        f"{len(filter_steps)} across {len(steps)} steps."
    )
    filters: dict[str, Any] = yaml.safe_load(filter_steps[0]["with"]["filters"])
    patterns = filters["agents"]
    assert isinstance(patterns, list) and patterns, (
        "The 'agents' filter parsed to something other than a non-empty list: "
        f"{patterns!r}. Every assertion below would pass vacuously."
    )
    return [str(pattern) for pattern in patterns]


class TestAgentFilterCoversTheCheckerSources:
    """The filter names every module the discriminator's verdict depends on."""

    def test_the_filter_output_gates_the_run(self) -> None:
        """The parsed filter is what decides whether the checker runs at all.

        Without this, a filter that covers every source proves nothing: the
        job could ignore ``steps.filter.outputs.agents`` entirely.
        """
        workflow = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
        outputs = workflow["jobs"]["check-paths"]["outputs"]

        assert "steps.filter.outputs.agents" in outputs["should-run-discriminator"]
        assert (
            workflow["jobs"]["validate-discriminator"]["if"]
            == "needs.check-paths.outputs.should-run-discriminator == 'true'"
        )

    def test_every_discriminator_source_is_a_filter_pattern(self) -> None:
        patterns = _agent_filter_patterns()

        missing = [src for src in _DISCRIMINATOR_SOURCES if src not in patterns]

        assert not missing, (
            f"{len(missing)} of {len(_DISCRIMINATOR_SOURCES)} discriminator "
            f"source files are not named in the 'agents' path filter: "
            f"{missing}. A PR changing only such a file skips the gate and "
            f"the skip job reports success in its place. Filter holds: "
            f"{patterns}"
        )

    def test_every_named_source_pattern_exists_on_disk(self) -> None:
        """A filter entry naming a moved or deleted file gates nothing.

        The pattern list is the only place these paths are written down, so a
        rename that misses it fails open rather than loudly.
        """
        for source in _DISCRIMINATOR_SOURCES:
            if "*" in source:
                matches = list(_REPO_ROOT.glob(source))
                assert matches, (
                    f"{source} is named in _DISCRIMINATOR_SOURCES but matches "
                    "no files. Either the modules moved and the filter is now "
                    "stale, or this glob is wrong."
                )
            else:
                assert (_REPO_ROOT / source).is_file(), (
                    f"{source} is named in _DISCRIMINATOR_SOURCES but is not a "
                    "file. Either the module moved and the filter is now stale, "
                    "or this list is."
                )

    def test_the_agent_definition_roots_are_still_covered(self) -> None:
        """Control: the pre-existing agent-corpus patterns are untouched.

        Without it, deleting every agent pattern and leaving the two script
        entries would satisfy the test above.
        """
        patterns = _agent_filter_patterns()

        assert ".claude/agents/**.md" in patterns
        assert "templates/agents/**.shared.md" in patterns
