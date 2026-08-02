"""Constants shared by the Copilot CLI eval transport."""

from __future__ import annotations

import re

FOOTER_LABEL_RE = re.compile(
    r"^(?:Changes|AI Credits|Tokens|Resume|Total duration|Wall time)( +)",
)
FOOTER_COLUMN: int = 11
FOOTER_VALUE_MAX_WORDS: int = 5
FOOTER_PROSE_ENDINGS: tuple[str, ...] = (".", "!", "?", ":", ",")
SESSION_STATE_ENV: str = "COPILOT_SESSION_STATE_DIR"
UNVERIFIED_MODEL_ENV: str = "EVAL_COPILOT_ALLOW_UNVERIFIED_MODEL"
TRACE_LINE_PREFIXES: tuple[str, ...] = ("\u25cf", "\u2502", "\u251c", "\u2514")
PROVIDER_LABEL: str = "Copilot CLI"
