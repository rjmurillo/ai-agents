"""Cost governance for the ai-review action's Copilot model selection.

ADR-080's `check_model_pins.py` scans unit frontmatter only (`_UNIT_GLOBS`), so
the `copilot-model` input on `.github/actions/ai-review` and its workflow
overrides are ungoverned. That gap already shipped a defect: the artifact
insight scanner pinned `claude-sonnet-4.5` after Copilot CLI stopped serving
it, and Copilot answers an unserved id by falling back to the session default,
so the pin quietly bought a pricier model than the one it named.

This action runs on every PR `synchronize` (ai-spec-validation, two calls per
run) and on an hourly PR sweep (pr-maintenance, up to two calls per PR), so the
per-token rate of the selected model is the dominant credit cost.

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

# The agents and prompts this action drives are Anthropic-authored and the
# pipeline parses a free-form `VERDICT:` line, so a cross-family swap needs its
# own output-contract evidence before it is allowed here.
ANTHROPIC_MODELS = {name for name in SERVED_MODEL_RATES if name.startswith("claude-")}


def _action_default() -> str:
    action = yaml.safe_load(_ACTION.read_text(encoding="utf-8"))
    return action["inputs"]["copilot-model"]["default"]


def _workflow_overrides() -> dict[Path, str]:
    overrides: dict[Path, str] = {}
    for path in sorted(_WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("copilot-model:"):
                overrides[path] = stripped.split(":", 1)[1].strip().strip("\"'")
    return overrides


def test_action_default_is_a_model_copilot_cli_serves():
    default = _action_default()
    assert default in SERVED_MODEL_RATES, (
        f"ai-review defaults to {default!r}, which Copilot CLI does not serve. "
        "Copilot falls back to the session default instead of erroring, so the "
        "runs silently bill at a rate nobody chose."
    )


def test_action_default_is_the_cheapest_anthropic_model():
    default = _action_default()
    cheapest = min(ANTHROPIC_MODELS, key=lambda name: SERVED_MODEL_RATES[name])
    assert default == cheapest, (
        f"ai-review defaults to {default!r} at {SERVED_MODEL_RATES[default]} USD/1M "
        f"(in, out); {cheapest} costs {SERVED_MODEL_RATES[cheapest]}. This action "
        "runs per PR push and hourly, so a pricier default multiplies across "
        "every run. Raise it only with measured evidence that the cheap tier "
        "fails the task."
    )


def test_action_default_beats_auto_worst_case():
    """`auto` discounts 10 percent but may route to a model several times pricier."""
    default_in, default_out = SERVED_MODEL_RATES[_action_default()]
    # GitHub documents auto routing across mixed tiers; GPT-5.4 is the priciest
    # model named in its CLI routing pool.
    auto_worst_in, auto_worst_out = SERVED_MODEL_RATES["gpt-5.4"]
    assert default_in <= auto_worst_in * 0.9
    assert default_out <= auto_worst_out * 0.9


@pytest.mark.parametrize("retired", ["claude-sonnet-4.5", "claude-sonnet-4.6", "claude-opus-4.5"])
def test_retired_ids_are_not_treated_as_served(retired):
    assert retired not in SERVED_MODEL_RATES


def test_no_workflow_overrides_with_an_unserved_or_pricier_model():
    default_rate = SERVED_MODEL_RATES[_action_default()]
    for path, model in _workflow_overrides().items():
        rel = path.relative_to(_REPO_ROOT)
        assert model in SERVED_MODEL_RATES, (
            f"{rel} pins copilot-model: {model!r}, which Copilot CLI does not "
            "serve. It will fall back to the session default and bill at that rate."
        )
        assert SERVED_MODEL_RATES[model] >= default_rate, (
            f"{rel} pins copilot-model: {model!r}, cheaper than the action "
            "default. Move the cheaper model to the action default instead of "
            "overriding one caller."
        )


def test_action_default_matches_the_driver_floor():
    """Two places name the model; they must name the same one.

    `scripts/ci/invoke_copilot_cli.py` is what actually drives the CLI, so its
    floor is what runs when COPILOT_MODEL arrives unset or empty. The action
    input default is what runs otherwise. A divergence means the composite
    action and a direct script invocation buy different models.
    """
    assert _action_default() == DEFAULT_COPILOT_MODEL
