"""Corpus hygiene checks for routing scenarios (issue #5425).

Two rules keep the corpus reusable across routing arms:

* model neutrality: no model or harness name in any driver-visible field or
  file (#5425 "Do not put model-specific prompt scaffolding inside the
  scenario");
* no answer-key leak: a known-good line must not already appear in any
  driver-visible text, and the resolved architecture decision must not appear
  in the requirement or `initial/` (#5425 "ensure the expected fix is not
  leaked to the driver as an answer key").

Driver-visible text is the title, requirement, invariants, acceptance
criteria, the architecture driver contract, and every `initial/` file.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from _routing_fixtures import RoutingCorpusError, fixture_files, read_fixture_text

if TYPE_CHECKING:
    from _routing_scenario import Scenario

LEAK_MIN_LINE_CHARS = 30

_MODEL_NAME_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(sol|luna|terra|gpt|claude|opus|sonnet|haiku|codex|copilot|gemini"
    r"|llama|anthropic|openai)(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def driver_visible_text(scenario: Scenario) -> list[tuple[str, str]]:
    """Every (label, text) pair a driver can read."""
    fields: list[tuple[str, str]] = [
        ("title", scenario.title),
        ("requirement", scenario.requirement),
    ]
    fields += [("invariants", item) for item in scenario.invariants]
    fields += [("acceptance_criteria", item) for item in scenario.acceptance_criteria]
    if scenario.architecture is not None:
        fields.append(("architecture.driver_contract", scenario.architecture.driver_contract))
    for logical, path in fixture_files(scenario.fixture_dir("initial")).items():
        fields.append((f"initial/{logical}", read_fixture_text(path)))
    return fields


def check_model_neutral(scenario: Scenario) -> None:
    for label, text in driver_visible_text(scenario):
        match = _MODEL_NAME_PATTERN.search(text)
        if match:
            raise RoutingCorpusError(
                f"{scenario.scenario_id}: {label} names {match.group(0)!r}; "
                "scenarios must stay model-agnostic"
            )


def check_no_answer_leak(scenario: Scenario) -> None:
    """Refuse a known-good line, or the resolved decision, that a driver can already read.

    Lines the same file already holds in `initial/` are unchanged context, not
    part of the answer, so they are skipped.
    """
    initial = fixture_files(scenario.fixture_dir("initial"))
    initial_texts = {logical: read_fixture_text(path) for logical, path in initial.items()}
    source_visible = "\n".join(initial_texts.values()) + "\n" + scenario.requirement
    all_visible = "\n".join(text for _, text in driver_visible_text(scenario))
    for logical, path in fixture_files(scenario.fixture_dir("known_good")).items():
        unchanged = set(initial_texts.get(logical, "").splitlines())
        for line in read_fixture_text(path).splitlines():
            stripped = line.strip()
            if line in unchanged or len(stripped) < LEAK_MIN_LINE_CHARS:
                continue
            if stripped in all_visible:
                raise RoutingCorpusError(
                    f"{scenario.scenario_id}: known_good/{logical} line {stripped!r} "
                    "already appears in driver-visible text (answer-key leak)"
                )
    if scenario.architecture is not None:
        decision = scenario.architecture.resolved_decision.casefold()
        if decision in source_visible.casefold():
            raise RoutingCorpusError(
                f"{scenario.scenario_id}: resolved_decision text appears in driver-visible text"
            )
