"""Job identities and trigger path filters in a workflow file (issue #4835).

Split out of ``tests/ci/test_workflow_event_subscriptions.py`` when that file
crossed the 500-line taste ceiling. Trigger shapes, naming, and shared-name
narrowing stay there; this module covers the two fields the planner reads to
decide what a queued run publishes and whether a named event brings it back.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS
from scripts.github_core.workflow_event_subscriptions import (
    declared_required_contexts,
    load_workflow_subscriptions,
    parse_workflow_subscriptions,
)

_WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def parse_yaml(source: str, name: str = "wf.yml"):
    """Parse a workflow snippet the same way yaml.safe_load does in production."""
    return parse_workflow_subscriptions(
        yaml.safe_load(textwrap.dedent(source)), fallback_name=name
    )


class TestJobIdentities:
    """Job declarations are the only static source of a run's check contexts."""

    def test_a_named_job_contributes_its_name(self):
        subscriptions = parse_yaml(
            """
            on:
              pull_request:
            jobs:
              tests:
                name: Run Python Tests
            """
        )

        assert subscriptions.job_names == frozenset({"Run Python Tests"})
        assert subscriptions.job_name_prefixes == frozenset()

    def test_an_unnamed_job_contributes_its_job_id(self):
        subscriptions = parse_yaml("on:\n  pull_request:\njobs:\n  validate:\n    runs-on: x\n")

        assert subscriptions.job_names == frozenset({"validate"})

    def test_a_matrix_job_contributes_only_its_literal_prefix(self):
        subscriptions = parse_yaml(
            """
            on:
              pull_request:
            jobs:
              analyze:
                name: Analyze (${{ matrix.language }})
            """
        )

        assert subscriptions.job_names == frozenset()
        assert subscriptions.job_name_prefixes == frozenset({"Analyze ("})

    def test_a_fully_templated_name_fails_closed_with_an_empty_prefix(self):
        # Nothing about the expanded name is knowable, so it must match every
        # required context rather than silently claiming to publish none.
        subscriptions = parse_yaml(
            """
            on:
              pull_request:
            jobs:
              dynamic:
                name: ${{ matrix.label }}
            """
        )

        assert subscriptions.job_name_prefixes == frozenset({""})
        assert declared_required_contexts(subscriptions, REQUIRED_CONTEXTS) == (
            REQUIRED_CONTEXTS
        )

    def test_a_workflow_with_no_jobs_block_declares_nothing(self):
        subscriptions = parse_yaml("on:\n  pull_request:\n")

        assert subscriptions.job_names == frozenset()
        assert declared_required_contexts(subscriptions, REQUIRED_CONTEXTS) == frozenset()

    def test_declared_required_contexts_ignores_jobs_nothing_requires(self):
        subscriptions = parse_yaml(
            """
            on:
              pull_request:
            jobs:
              lint:
                name: Lint
              tests:
                name: Run Python Tests
            """
        )

        assert declared_required_contexts(subscriptions, REQUIRED_CONTEXTS) == frozenset(
            {"Run Python Tests"}
        )

    def test_a_prefix_match_expands_to_every_required_context_it_covers(self):
        subscriptions = parse_yaml(
            """
            on:
              pull_request:
            jobs:
              analyze:
                name: Analyze (${{ matrix.language }})
            """
        )

        assert declared_required_contexts(subscriptions, REQUIRED_CONTEXTS) == frozenset(
            {"Analyze (actions)", "Analyze (python)"}
        )

    def test_a_literal_name_never_prefix_matches_a_longer_context(self):
        subscriptions = parse_yaml(
            "on:\n  pull_request:\njobs:\n  validate:\n    name: Validate PR\n"
        )

        assert declared_required_contexts(subscriptions, REQUIRED_CONTEXTS) == frozenset(
            {"Validate PR"}
        )

    def test_a_non_mapping_jobs_block_is_tolerated(self):
        subscriptions = parse_yaml("on:\n  pull_request:\njobs: broken\n")

        assert subscriptions.job_names == frozenset()


class TestPathFilters:
    """A path-filtered trigger fires only for changes touching those paths."""

    @pytest.mark.parametrize("key", ["paths", "paths-ignore"])
    def test_either_path_key_marks_the_workflow_as_filtered(self, key: str):
        subscriptions = parse_workflow_subscriptions(
            {"on": {"pull_request": {"types": ["reopened"], key: ["docs/**"]}}}
        )

        assert subscriptions.has_path_filters is True

    def test_a_path_filter_on_pull_request_target_also_counts(self):
        subscriptions = parse_workflow_subscriptions(
            {"on": {"pull_request_target": {"paths": ["src/**"]}}}
        )

        assert subscriptions.has_path_filters is True

    def test_an_unfiltered_pull_request_trigger_is_not_marked(self):
        subscriptions = parse_yaml("on:\n  pull_request:\n    types: [reopened]\n")

        assert subscriptions.has_path_filters is False

    def test_a_branch_filter_alone_is_not_a_path_filter(self):
        # `branches:` narrows the base ref, which does not move on close/reopen,
        # so it cannot suppress a run that already exists for this PR.
        subscriptions = parse_workflow_subscriptions(
            {"on": {"pull_request": {"branches": ["main"]}}}
        )

        assert subscriptions.has_path_filters is False

    def test_a_workflow_with_no_pull_request_trigger_is_not_marked(self):
        subscriptions = parse_yaml("on:\n  workflow_dispatch:\n")

        assert subscriptions.has_path_filters is False


class TestRealCorpus:
    """The synthesized cases above prove the parser's branches. Only the real
    corpus proves it reads the files the guard will be pointed at.
    """

    def test_the_real_corpus_resolves_every_required_context_to_a_workflow(self):
        """Each pinned required context must be claimed by some workflow file.

        A context no workflow declares is a context the guard can never score
        from the definition side, which is the fail-open path the jobs API left
        open for queued runs. This also pins the matrix prefix match: nothing
        declares ``Analyze (actions)`` literally, only
        ``Analyze (${{ matrix.language }})`` in ``codeql-analysis.yml``.
        """
        loaded = load_workflow_subscriptions(_WORKFLOWS_DIR)

        claimed: set[str] = set()
        for subscriptions in loaded.values():
            claimed |= declared_required_contexts(subscriptions, REQUIRED_CONTEXTS)

        assert claimed == set(REQUIRED_CONTEXTS)
        assert declared_required_contexts(
            loaded["CodeQL Analysis"], REQUIRED_CONTEXTS
        ) == frozenset({"Analyze (actions)", "Analyze (python)"})

    def test_the_real_corpus_marks_its_path_filtered_workflows(self):
        """The five files carrying ``paths`` on a pull_request-family trigger."""
        loaded = load_workflow_subscriptions(_WORKFLOWS_DIR)

        filtered = {
            filename
            for filename, subscriptions in loaded.items()
            if filename.endswith((".yml", ".yaml")) and subscriptions.has_path_filters
        }

        assert filtered == {
            "investigation-claim-backstop.yml",
            "software-engineering-library-activation.yml",
            "synthesis-panel-gate.yml",
            "test-codeql-integration.yml",
            "vendor-provenance.yml",
        }
