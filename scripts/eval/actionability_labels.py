"""Label, split, and prediction-status values for the comment actionability eval.

One home for the strings that the corpus, predict, arms, and score code share, so
a rename cannot leave one module speaking a different vocabulary. Stdlib only and
no imports, so any module can import it without cost.

Label values come from ``evals/comment-actionability/RUBRIC.md``. A null label
means the row is not yet labeled.
"""

from __future__ import annotations

LABEL_ACTIONABLE = "actionable"
LABEL_NOT_ACTIONABLE = "not_actionable"
LABEL_UNSURE = "unsure"
VALID_LABELS = (LABEL_ACTIONABLE, LABEL_NOT_ACTIONABLE, LABEL_UNSURE)
# Truth value per scored label. ``unsure`` has none: the scorer drops those rows.
LABEL_TRUTH = {LABEL_ACTIONABLE: True, LABEL_NOT_ACTIONABLE: False}

SPLIT_DEV = "dev"
SPLIT_HELDOUT = "heldout"
SPLIT_OUTSIDE = "outside"

STATUS_OK = "ok"
STATUS_PARSE_ERROR = "parse_error"
STATUS_CALL_ERROR = "call_error"
# HTTP 401 or 403: the credential is wrong, so predict stops instead of failing every row.
STATUS_AUTH_ERROR = "auth_error"
# A local ValueError while building the message: the row, not the transport, is at fault. It
# never counts toward the consecutive call_error breaker.
STATUS_INPUT_ERROR = "input_error"
STATUSES = (
    STATUS_OK,
    STATUS_PARSE_ERROR,
    STATUS_CALL_ERROR,
    STATUS_AUTH_ERROR,
    STATUS_INPUT_ERROR,
)

# Per-row diff hunk outcome. Null means the row has not been asked yet.
HUNK_FETCHED = "fetched"
HUNK_NO_HUNK = "no_hunk"

# The fields that say which model run a prediction came from. predict refuses to resume a log
# whose ok records differ in any of them, and score refuses a predictions file that mixes them.
PROVENANCE_FIELDS = ("provider", "model", "prompt_sha256")

# Default seed for every seeded step (sample, sheet, score), so one run is reproducible end to end.
DEFAULT_SEED = 20261124
