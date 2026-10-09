"""Cost governance for the Copilot driver floor and the Claude-only ai-review action.

REQ-047 (issue #6069) moved every ai-review caller to Claude, so the action no
longer exposes a Copilot surface. ``scripts/ci/_copilot_model.py`` stays because
``invoke_claude_review.py`` and ``scripts/eval`` import it. This module keeps two
guards:

- the action and the workflows carry no Copilot model input, so a Copilot token
  cannot creep back into the review path;
- the Copilot driver floor stays the cheapest served model, because the eval
  harness still runs that driver.

ADR-080's `check_model_pins.py` scans unit frontmatter only (`_UNIT_GLOBS`).
A stale Copilot pin once bought a pricier model silently: Copilot answers an
unserved id by falling back to the session default.

Rates are GitHub's published usage-based per-1M-token prices
(https://docs.github.com/en/copilot/reference/copilot-billing/models-and-pricing).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.ci._copilot_model import DEFAULT_COPILOT_MODEL

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACTION = _REPO_ROOT / ".github" / "actions" / "ai-review" / "action.yml"
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"

# Models Copilot CLI serves, with (input, output) USD per 1M tokens.
# "auto" carries no fixed rate: it routes freely and only discounts the chosen
# model by 10 percent, so its worst case is the priciest model in its pool.
SERVED_MODEL_RATES: dict[str, tuple[float, float]] = {
    "claude-haiku-4.5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-4.8": (5.00, 25.00),
    "claude-opus-5": (5.00, 25.00),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.6-sol": (4.00, 20.00),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.7-flash": (0.75, 3.75),
    "mai-code-1.1-flash": (0.20, 1.20),
    "kimi-k3": (3.00, 15.00),
}

# Ids Copilot CLI no longer serves. An unserved id is not an error: Copilot
# falls back to the session default and exits 0, so a stale pin quietly buys a
# pricier model. Kept as an explicit list so a regression names the id.
RETIRED_MODEL_IDS = ("claude-sonnet-4.5", "claude-sonnet-4.6", "claude-opus-4.5", "gpt-5.1")


def _action_inputs() -> dict:
    action = yaml.safe_load(_ACTION.read_text(encoding="utf-8"))
    return action["inputs"]


def _driver_default() -> str:
    return DEFAULT_COPILOT_MODEL


def _workflow_overrides() -> dict[Path, str]:
    overrides: dict[Path, str] = {}
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("copilot-model:"):
                overrides[path] = stripped.split(":", 1)[1].strip().strip("\"'")
    return overrides


@pytest.mark.parametrize(
    "removed_input",
    ["copilot-token", "copilot-model", "provider", "enable-diagnostics"],
)
def test_action_has_no_copilot_input(removed_input):
    assert removed_input not in _action_inputs()


def test_action_has_no_copilot_step_or_secret():
    text = _ACTION.read_text(encoding="utf-8")
    for needle in ("COPILOT_GITHUB_TOKEN", "install_copilot_cli", "invoke_copilot_cli"):
        assert needle not in text


def test_no_workflow_passes_a_copilot_model_to_the_action():
    assert _workflow_overrides() == {}


def test_driver_default_is_a_model_copilot_cli_serves():
    default = _driver_default()
    assert default in SERVED_MODEL_RATES, (
        f"The Copilot driver floor is {default!r}, which Copilot CLI does not serve. "
        "Copilot falls back to the session default instead of erroring, so the "
        "runs silently bill at a rate nobody chose."
    )


def test_driver_default_is_the_cheapest_model_copilot_serves():
    """Cheapest overall, not cheapest within one vendor."""
    default = _driver_default()
    cheapest_rate = min(SERVED_MODEL_RATES.values())
    assert SERVED_MODEL_RATES[default] == cheapest_rate, (
        f"The Copilot driver floor is {default!r} at {SERVED_MODEL_RATES[default]} "
        f"USD/1M (in, out); the cheapest served model costs {cheapest_rate}."
    )


def test_driver_default_beats_auto_worst_case():
    """`auto` discounts 10 percent but may route to a model several times pricier."""
    default_in, default_out = SERVED_MODEL_RATES[_driver_default()]
    auto_worst_in, auto_worst_out = SERVED_MODEL_RATES["gpt-5.4"]
    assert default_in <= auto_worst_in * 0.9
    assert default_out <= auto_worst_out * 0.9


@pytest.mark.parametrize("retired", RETIRED_MODEL_IDS)
def test_retired_ids_are_not_treated_as_served(retired):
    assert retired not in SERVED_MODEL_RATES
