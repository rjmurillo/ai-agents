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

class TestSharedWorkflowNames:
    """A ``name:`` two files declare resolves to what both files subscribe to.

    A run record names its workflow, not its file. Resolving such a name to one
    arbitrary file is the fail-open path issue #4835 exists to close: the guard
    would clear a run for cancellation on a subscription its real workflow never
    declared, leaving a required context with no way back.
    """

    def write_pair(self, directory: Path, first_types: str, second_types: str) -> None:
        """Write two workflow files that declare the same name."""
        (directory / "a.yml").write_text(
            f"name: Dup\non:\n  pull_request:\n    types: {first_types}\n",
            encoding="utf-8",
        )
        (directory / "b.yml").write_text(
            f"name: Dup\non:\n  pull_request:\n    types: {second_types}\n",
            encoding="utf-8",
        )

    def test_an_event_only_one_sharer_declares_does_not_verify(self, tmp_path: Path):
        # The incident scenario: reopening the PR regenerates a.yml and not
        # b.yml, so the name "Dup" must not answer yes for `reopened`.
        self.write_pair(tmp_path, "[opened, reopened]", "[opened, synchronize]")

        loaded = load_workflow_subscriptions(tmp_path)

        assert loaded["Dup"].pull_request_types == frozenset({"opened"})
        assert subscribes_to(loaded["Dup"], "reopened") is False

    def test_an_event_every_sharer_declares_still_verifies(self, tmp_path: Path):
        # The control for the case above. Without it, a fix that dropped the
        # ambiguous name outright would pass the negative test too.
        self.write_pair(tmp_path, "[opened, reopened]", "[reopened, synchronize]")

        loaded = load_workflow_subscriptions(tmp_path)

        assert subscribes_to(loaded["Dup"], "reopened") is True

    def test_each_sharer_still_resolves_by_its_own_filename(self, tmp_path: Path):
        self.write_pair(tmp_path, "[synchronize]", "[reopened]")

        loaded = load_workflow_subscriptions(tmp_path)

        assert loaded["a.yml"].pull_request_types == frozenset({"synchronize"})
        assert loaded["b.yml"].pull_request_types == frozenset({"reopened"})

    def test_workflow_dispatch_needs_every_sharer_to_declare_it(self, tmp_path: Path):
        (tmp_path / "a.yml").write_text(
            "name: Dup\non:\n  pull_request:\n  workflow_dispatch:\n", encoding="utf-8"
        )
        (tmp_path / "b.yml").write_text(
            "name: Dup\non:\n  pull_request:\n", encoding="utf-8"
        )

        loaded = load_workflow_subscriptions(tmp_path)

        assert subscribes_to(loaded["Dup"], "workflow_dispatch") is False
        assert subscribes_to(loaded["a.yml"], "workflow_dispatch") is True

    def test_three_sharers_narrow_to_what_all_three_declare(self, tmp_path: Path):
        for filename, types in (
            ("a.yml", "[opened, reopened, synchronize]"),
            ("b.yml", "[opened, reopened]"),
            ("c.yml", "[opened, synchronize]"),
        ):
            (tmp_path / filename).write_text(
                f"name: Dup\non:\n  pull_request:\n    types: {types}\n",
                encoding="utf-8",
            )

        loaded = load_workflow_subscriptions(tmp_path)

        assert loaded["Dup"].pull_request_types == frozenset({"opened"})

    def test_a_filename_key_always_describes_that_one_file(self, tmp_path: Path):
        # `impostor.yml` declares the name "target.yml", which is also a real
        # file. A filename is unambiguous by construction, so that key keeps
        # describing the file it names rather than the set that answers to it.
        (tmp_path / "impostor.yml").write_text(
            "name: target.yml\non:\n  pull_request:\n    types: [opened]\n",
            encoding="utf-8",
        )
        (tmp_path / "target.yml").write_text(
            "on:\n  pull_request:\n    types: [reopened]\n", encoding="utf-8"
        )

        loaded = load_workflow_subscriptions(tmp_path)

        assert loaded["target.yml"].pull_request_types == frozenset({"reopened"})
