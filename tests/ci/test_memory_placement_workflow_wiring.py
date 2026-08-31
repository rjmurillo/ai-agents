"""Path-filter wiring for the memory placement workflow (issue #5391).

The gate reads the diff, so a path filter is the right shape for it
(`.claude/rules/ci-scripts.md`, "Path filters gate the diff, never the tree").
What a diff-shaped filter still has to do is name every file whose change can
alter the verdict. The checker's logic is spread across three modules, so a
filter naming only the entry point would let a PR that changes a threshold or
a signal regex match nothing: `check-paths` would emit
`should-run-placement != 'true'` and `skip-placement` would report a fresh
green tick in the checker's place. That is the failure recorded for the
agent-skill discriminator in
`tests/ci/test_agent_skill_discriminator_workflow_wiring.py`; this file holds
the same line for the placement gate.

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
_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "memory-placement-check.yml"

# Every first-party file the verdict depends on: the CLI, the signals, the
# ratchet, and the committed debt register a run compares against.
_PLACEMENT_SOURCES = (
    "scripts/validation/check_memory_placement.py",
    "scripts/validation/memory_placement_signals.py",
    "scripts/validation/memory_placement_baseline.py",
    "scripts/validation/memory_placement_baseline.json",
)


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _memory_filter_patterns() -> list[str]:
    """The parsed ``memories`` filter patterns from the paths-filter step.

    ``filters:`` is a YAML document nested inside a workflow string scalar, so
    it is parsed twice: once to reach the step, once to read the filter body.
    """
    steps = _workflow()["jobs"]["check-paths"]["steps"]
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
    patterns = filters["memories"]
    assert isinstance(patterns, list) and patterns, (
        "The 'memories' filter parsed to something other than a non-empty "
        f"list: {patterns!r}. Every assertion below would pass vacuously."
    )
    return [str(pattern) for pattern in patterns]


class TestMemoryFilterCoversTheCheckerSources:
    """The filter names every file the placement verdict depends on."""

    def test_the_filter_output_gates_the_run(self) -> None:
        """The parsed filter is what decides whether the checker runs at all."""
        workflow = _workflow()
        outputs = workflow["jobs"]["check-paths"]["outputs"]

        assert "steps.filter.outputs.memories" in outputs["should-run-placement"]
        assert (
            workflow["jobs"]["validate-placement"]["if"]
            == "needs.check-paths.outputs.should-run-placement == 'true'"
        )

    def test_the_memory_corpus_is_a_filter_pattern(self) -> None:
        assert ".serena/memories/**.md" in _memory_filter_patterns()

    def test_every_placement_source_is_a_filter_pattern(self) -> None:
        patterns = _memory_filter_patterns()

        missing = [src for src in _PLACEMENT_SOURCES if src not in patterns]

        assert not missing, (
            f"{len(missing)} of {len(_PLACEMENT_SOURCES)} placement source "
            f"files are not named in the 'memories' path filter: {missing}. "
            "A PR changing only such a file skips the gate and the skip job "
            f"reports success in its place. Filter holds: {patterns}"
        )

    def test_every_named_source_exists_on_disk(self) -> None:
        """A filter entry naming a moved or deleted file gates nothing."""
        for source in _PLACEMENT_SOURCES:
            assert (_REPO_ROOT / source).is_file(), (
                f"The 'memories' path filter names {source}, which does not "
                "exist. A rename that missed the filter fails open."
            )


class TestPlacementStepsUseTheLockedEnvironment:
    """Every checker step runs under uv, and both modes read the baseline."""

    def _run_steps(self) -> list[str]:
        steps = _workflow()["jobs"]["validate-placement"]["steps"]
        return [
            str(step["run"])
            for step in steps
            if isinstance(step, dict)
            and "run" in step
            and "check_memory_placement.py" in str(step["run"])
        ]

    def test_both_modes_are_wired(self) -> None:
        runs = self._run_steps()
        assert len(runs) == 2, (
            "Expected a changed-files step and a full-corpus step invoking "
            f"the checker, found {len(runs)}."
        )
        assert any("--all" in run for run in runs), "No full-corpus invocation."

    def test_no_step_calls_the_checker_with_bare_python(self) -> None:
        """MUST-18: the checker imports markdown-it, so it needs uv.

        `.claude/rules/ci-scripts.md` MUST-18, quoted verbatim: "A step that
        invokes a script with bare ``python3`` may import only the standard
        library."
        """
        for run in self._run_steps():
            assert "uv run --frozen" in run, (
                f"Checker step does not use `uv run --frozen`: {run!r}. A bare "
                "python3 call fails at module load on the markdown-it import."
            )

    def test_every_invocation_reads_the_debt_register(self) -> None:
        """Without --baseline the recorded debt fails PRs that touch it."""
        for run in self._run_steps():
            assert "--baseline" in run, (
                f"Checker step does not pass --baseline: {run!r}."
            )
