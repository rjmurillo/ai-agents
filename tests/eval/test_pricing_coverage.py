"""Coverage test for the eval pricing table (Issue #2902).

The base evaluator and the model sweep both fail closed on an unpriced model.
That is correct, but it means an unpriced pin fails a *live* sweep at runtime
instead of failing CI. This test asserts every model id the harness can
actually dispatch (the sweep default plus the live pins enumerated in #2840)
has a pricing entry, so a missing rate is caught here, not on spend.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    from _anthropic_api import DEFAULT_MODEL  # noqa: E402
    from _eval_common import (  # noqa: E402
        MODEL_PRICING_RATES_USD_PER_1K_TOKENS,
    )
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))

# Live model pins enumerated in issue #2840 (skills/agents/commands frontmatter).
# The bare `haiku` alias is intentionally excluded: it is not a dispatchable id
# and #2840 tracks removing it. Keep this list in sync with the pins that reach
# the API; a new pin without a rate should trip this test.
LIVE_PINNED_MODEL_IDS = frozenset(
    {
        "claude-sonnet-4-6",
        "claude-opus-4-6",
        "claude-opus-4-8",
        "claude-haiku-4-5",
    }
)


def test_sweep_default_model_is_priced() -> None:
    assert DEFAULT_MODEL in MODEL_PRICING_RATES_USD_PER_1K_TOKENS


def test_all_live_pinned_models_are_priced() -> None:
    unpriced = sorted(
        m for m in LIVE_PINNED_MODEL_IDS if m not in MODEL_PRICING_RATES_USD_PER_1K_TOKENS
    )
    assert not unpriced, (
        "Live pinned model ids missing a pricing entry in "
        "MODEL_PRICING_RATES_USD_PER_1K_TOKENS (scripts/eval/_eval_common.py): "
        f"{unpriced}. A live sweep over these would fail closed at runtime."
    )


def test_pricing_rates_have_positive_input_and_output() -> None:
    for model_id, rates in MODEL_PRICING_RATES_USD_PER_1K_TOKENS.items():
        assert set(rates) == {"input", "output"}, model_id
        assert rates["input"] > 0, model_id
        assert rates["output"] > 0, model_id
        assert rates["output"] >= rates["input"], model_id
