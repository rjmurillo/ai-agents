"""Pricing rows must match how each harness spells a model id.

Claude Code accepts only `claude-opus-5-5` and Copilot CLI only
`claude-opus-5.5` (see `scripts/eval/_runtime_output.py`). The price lookup in
`_eval_common.py` is an exact key match, so each dispatched spelling needs its
own row, and two rows for one model must quote one price.
"""

from __future__ import annotations

import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"

_path_added = str(EVAL_DIR) not in sys.path
if _path_added:
    sys.path.insert(0, str(EVAL_DIR))
try:
    from _eval_common import MODEL_PRICING_RATES_USD_PER_1K_TOKENS
    from _runtime_output import harness_model_id
finally:
    if _path_added and str(EVAL_DIR) in sys.path:
        sys.path.remove(str(EVAL_DIR))


def test_opus_5_5_is_priced_in_both_harness_spellings() -> None:
    """Opus 5.5 lists at $4 input and $20 output per million tokens."""
    expected = {"input": 0.004, "output": 0.020}

    assert MODEL_PRICING_RATES_USD_PER_1K_TOKENS["claude-opus-5-5"] == expected
    assert MODEL_PRICING_RATES_USD_PER_1K_TOKENS["claude-opus-5.5"] == expected


def test_gpt6_routing_candidates_are_priced_as_verified() -> None:
    """GPT-6 Astra/Sol/Luna rates match developers.openai.com/api/docs/models."""
    assert MODEL_PRICING_RATES_USD_PER_1K_TOKENS["gpt-6-astra"] == {
        "input": 0.010,
        "output": 0.050,
    }
    assert MODEL_PRICING_RATES_USD_PER_1K_TOKENS["gpt-6-sol"] == {
        "input": 0.002,
        "output": 0.010,
    }
    assert MODEL_PRICING_RATES_USD_PER_1K_TOKENS["gpt-6-luna"] == {
        "input": 0.0001,
        "output": 0.0005,
    }


def test_spellings_of_one_model_share_one_rate() -> None:
    """A dotted and a dashed row for one model must not quote two prices."""
    by_model: dict[str, set[tuple[float, float]]] = {}
    for model_id, rates in MODEL_PRICING_RATES_USD_PER_1K_TOKENS.items():
        canonical = harness_model_id("claude", model_id)
        by_model.setdefault(canonical, set()).add((rates["input"], rates["output"]))

    conflicting = sorted(m for m, rates in by_model.items() if len(rates) > 1)

    assert not conflicting, f"Spellings of one model carry different rates: {conflicting}"
