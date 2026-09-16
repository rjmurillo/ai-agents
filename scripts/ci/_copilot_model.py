"""Copilot CLI model selection for the ai-review driver.

Holds the model this repository sends to Copilot CLI and the check that the
CLI actually served it.

Copilot CLI answers a retired or unknown `--model` id with
`not available; using "<other>" instead` and exits 0, so the run still produces
a verdict but bills at the session default's rate instead of the economical
model the workflow selected. That is a cost defect the caller cannot see in the
exit code, and it is exactly how `copilot-model: claude-sonnet-4.5` kept
running long after Copilot stopped serving that id.

Resolution behavior measured on Copilot CLI 1.0.79 and 1.0.81-0 for the agent
frontmatter resolver; see
`.agents/analysis/2026-08-12-adr-080-copilot-model-resolution.md`. The `--model`
flag namespace was not probed there, so a miss means undetected drift, not
proof the pin resolved.
"""

from __future__ import annotations

import re

# The model every ai-review call uses unless a caller overrides it. GPT-5.6
# Luna is the cheapest model Copilot CLI serves ($0.20 in / $1.20 out per 1M
# tokens under usage-based billing), five times under Claude Haiku 4.5 and
# roughly twelve times under GPT-5.4, which is the priciest model `auto` routes
# to. This action runs on every PR synchronize and on an hourly PR sweep, so
# that ratio is the whole credit bill.
#
# Output-contract risk is bounded by `scripts/ci/parse_ai_review_output.py`:
# output with no `VERDICT:` line parses to UNKNOWN, UNKNOWN is a blocking
# verdict, and the check goes red. A model that cannot hold the contract fails
# loudly rather than passing quietly. What that does not catch is a
# well-formed verdict from a shallow review, which is the accepted trade.
#
# This is the floor, not a duplicate of the action input default: an unset or
# empty COPILOT_MODEL previously sent `--model ""` to the CLI, and a composite
# action input that is passed explicitly-empty overrides its own default.
# `tests/ci/test_ai_review_model_economy.py` fails if the two disagree.
DEFAULT_COPILOT_MODEL = "gpt-5.6-luna"

MODEL_FALLBACK_PATTERN = re.compile(
    r"not available;\s*using\s+[\"']?(?P<substitute>[^\"'\n]+?)[\"']?\s+instead",
    re.IGNORECASE,
)


def report_model_fallback(requested_model: str, *output_streams: str) -> str | None:
    """Warn when Copilot CLI substituted a different model for the one requested.

    Returns the substitute model name when a fallback is detected, else None.
    """
    for stream in output_streams:
        if not stream:
            continue
        match = MODEL_FALLBACK_PATTERN.search(stream)
        if match is None:
            continue
        substitute = match.group("substitute").strip()
        print(
            f"::warning::Copilot CLI did not serve the requested model "
            f"{requested_model!r} and used {substitute!r} instead. The run is "
            f"billed at the substitute's rate. Update COPILOT_MODEL to a model "
            "id Copilot CLI currently serves."
        )
        return substitute
    return None
