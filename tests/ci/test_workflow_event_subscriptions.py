"""Tests for workflow event subscription parsing (issue #4835).

The load-bearing case is the one the 2026-08-09 incident hit: a workflow with an
explicit ``pull_request.types`` list that omits ``reopened``. Reopening the PR
produces no run for it, so a close/reopen recovery plan silently leaves that
workflow's required contexts missing.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from scripts.github_core.workflow_event_subscriptions import (
    DEFAULT_PULL_REQUEST_TYPES,
    RECOVERY_EVENTS,
    load_workflow_subscriptions,
    parse_workflow_subscriptions,
    subscribes_to,
)

_WORKFLOWS_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def parse_yaml(source: str, name: str = "wf.yml"):
    """Parse a workflow snippet the same way yaml.safe_load does in production."""
    return parse_workflow_subscriptions(
        yaml.safe_load(textwrap.dedent(source)), fallback_name=name
    )


class TestTriggerShapes:
    def test_bare_on_key_is_read_despite_yaml_boolean_coercion(self):
        # `on:` is a YAML 1.1 boolean, so safe_load produces the key True.
        document = yaml.safe_load("on:\n  pull_request:\n    types: [opened]\n")

        assert True in document, "precondition: safe_load coerced the on key"

        subscriptions = parse_workflow_subscriptions(document)

        assert subscriptions.pull_request_types == frozenset({"opened"})

    def test_string_literal_on_key_is_also_read(self):
        subscriptions = parse_workflow_subscriptions(
            {"on": {"pull_request": {"types": ["reopened"]}}}
        )

        assert subscriptions.pull_request_types == frozenset({"reopened"})

    def test_pull_request_without_types_uses_the_documented_default(self):
        subscriptions = parse_yaml("on:\n  pull_request:\n")

        assert subscriptions.pull_request_types == DEFAULT_PULL_REQUEST_TYPES

    def test_list_form_on_block_uses_the_documented_default(self):
        subscriptions = parse_yaml("on: [push, pull_request]\n")

        assert subscriptions.pull_request_types == DEFAULT_PULL_REQUEST_TYPES

    def test_scalar_form_on_block_is_understood(self):
        subscriptions = parse_yaml("on: pull_request\n")

        assert subscriptions.pull_request_types == DEFAULT_PULL_REQUEST_TYPES

    def test_pull_request_target_types_union_into_the_same_set(self):
        subscriptions = parse_yaml(
            """
            on:
              pull_request:
                types: [opened]
              pull_request_target:
                types: [reopened]
            """
        )

        assert subscriptions.pull_request_types == frozenset({"opened", "reopened"})

    def test_workflow_dispatch_is_recorded(self):
        subscriptions = parse_yaml("on:\n  workflow_dispatch:\n")

        assert subscriptions.has_workflow_dispatch is True

    def test_workflow_with_no_triggers_subscribes_to_nothing(self):
        subscriptions = parse_yaml("name: Orphan\njobs: {}\n")

        assert subscriptions.pull_request_types == frozenset()
        assert subscriptions.has_workflow_dispatch is False

    def test_unusable_types_value_yields_no_subscription_not_the_default(self):
        # Failing closed matters: defaulting here would assert `reopened`
        # coverage the workflow never declared.
        subscriptions = parse_workflow_subscriptions(
            {"on": {"pull_request": {"types": 7}}}
        )

        assert subscriptions.pull_request_types == frozenset()

    def test_an_on_block_that_is_neither_string_list_nor_mapping_yields_nothing(self):
        subscriptions = parse_workflow_subscriptions({"on": 5})

        assert subscriptions.pull_request_types == frozenset()
        assert subscriptions.has_workflow_dispatch is False

    def test_single_string_types_value_is_treated_as_one_type(self):
        subscriptions = parse_yaml("on:\n  pull_request:\n    types: synchronize\n")

        assert subscriptions.pull_request_types == frozenset({"synchronize"})


class TestNaming:
    def test_declared_name_wins(self):
        subscriptions = parse_yaml("name: Validate PR\non:\n  pull_request:\n")

        assert subscriptions.name == "Validate PR"

    def test_missing_name_falls_back_to_the_filename(self):
        subscriptions = parse_yaml("on:\n  pull_request:\n", name="pr-validation.yml")

        assert subscriptions.name == "pr-validation.yml"

    def test_empty_name_falls_back_to_the_filename(self):
        subscriptions = parse_workflow_subscriptions(
            {"name": "", "on": {"pull_request": None}}, fallback_name="fallback.yml"
        )

        assert subscriptions.name == "fallback.yml"


class TestSubscribesTo:
    def test_reopened_omission_blocks_a_close_reopen_recovery(self):
        subscriptions = parse_yaml(
            "on:\n  pull_request:\n    types: [opened, synchronize]\n"
        )

        assert subscribes_to(subscriptions, "synchronize") is True
        assert subscribes_to(subscriptions, "reopened") is False

    def test_rerun_needs_no_trigger_subscription(self):
        subscriptions = parse_yaml("on:\n  schedule:\n    - cron: '0 0 * * *'\n")

        assert subscribes_to(subscriptions, "rerun") is True

    def test_workflow_dispatch_requires_the_declared_trigger(self):
        without = parse_yaml("on:\n  pull_request:\n")
        with_dispatch = parse_yaml("on:\n  pull_request:\n  workflow_dispatch:\n")

        assert subscribes_to(without, "workflow_dispatch") is False
        assert subscribes_to(with_dispatch, "workflow_dispatch") is True

    def test_unknown_event_name_is_false(self):
        subscriptions = parse_yaml("on:\n  pull_request:\n")

        assert subscribes_to(subscriptions, "labeled") is False

    @pytest.mark.parametrize("event", sorted(RECOVERY_EVENTS))
    def test_every_recovery_event_is_answerable(self, event: str):
        subscriptions = parse_yaml("on:\n  pull_request:\n  workflow_dispatch:\n")

        assert subscribes_to(subscriptions, event) is True


class TestLoadWorkflowSubscriptions:
    def test_registers_both_filename_and_declared_name(self, tmp_path: Path):
        (tmp_path / "validate.yml").write_text(
            "name: Validate PR\non:\n  pull_request:\n", encoding="utf-8"
        )

        loaded = load_workflow_subscriptions(tmp_path)

        assert loaded["validate.yml"].name == "Validate PR"
        assert loaded["Validate PR"].pull_request_types == DEFAULT_PULL_REQUEST_TYPES

    def test_missing_directory_yields_an_empty_map(self, tmp_path: Path):
        assert load_workflow_subscriptions(tmp_path / "absent") == {}

    def test_malformed_workflow_is_skipped_without_hiding_its_siblings(
        self, tmp_path: Path
    ):
        (tmp_path / "broken.yml").write_text("name: [unclosed\n", encoding="utf-8")
        (tmp_path / "good.yml").write_text(
            "name: Good\non:\n  pull_request:\n", encoding="utf-8"
        )

        loaded = load_workflow_subscriptions(tmp_path)

        assert "broken.yml" not in loaded
        assert loaded["Good"].pull_request_types == DEFAULT_PULL_REQUEST_TYPES

    def test_non_yaml_files_are_ignored(self, tmp_path: Path):
        (tmp_path / "README.md").write_text("not a workflow\n", encoding="utf-8")

        assert load_workflow_subscriptions(tmp_path) == {}

    def test_scalar_document_is_skipped(self, tmp_path: Path):
        (tmp_path / "scalar.yml").write_text("just a string\n", encoding="utf-8")

        assert load_workflow_subscriptions(tmp_path) == {}

    def test_parses_this_repository_s_real_workflow_corpus(self):
        # A synthesized fixture proves the parser's branches; only the real
        # corpus proves it reads the files the guard will actually be pointed
        # at. `.github/workflows/pr-validation.yml` line 1 declares
        # `name: PR Validation` and line 12 declares
        # `types: [opened, edited, synchronize, reopened]`.
        loaded = load_workflow_subscriptions(_WORKFLOWS_DIR)

        assert len(loaded) > 10, "the workflow corpus should not be empty"
        pr_validation = loaded["PR Validation"]
        assert "reopened" in pr_validation.pull_request_types
        assert "synchronize" in pr_validation.pull_request_types

    def test_first_file_wins_when_two_workflows_share_a_name(self, tmp_path: Path):
        (tmp_path / "a.yml").write_text(
            "name: Dup\non:\n  pull_request:\n    types: [synchronize]\n",
            encoding="utf-8",
        )
        (tmp_path / "b.yml").write_text(
            "name: Dup\non:\n  pull_request:\n    types: [reopened]\n", encoding="utf-8"
        )

        loaded = load_workflow_subscriptions(tmp_path)

        assert loaded["Dup"].pull_request_types == frozenset({"synchronize"})
        assert loaded["b.yml"].pull_request_types == frozenset({"reopened"})
