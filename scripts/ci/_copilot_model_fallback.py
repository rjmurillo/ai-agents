"""Detect when Copilot CLI serves a different model than the one requested.

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
