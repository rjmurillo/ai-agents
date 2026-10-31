"""Detect a usage-limit or credit-exhaustion stop in a routing result row (issue #5426).

A live run that keeps starting invocations after the account is out of usage or credits
spends nothing useful and fills the results with identical harness failures. The runner
stops at the first such failure, writes every remaining row as `NOT_RUN` with the reason,
and exits nonzero (PREDICTIONS.md Run design: a row the cap cuts off is `NOT_RUN`).

Texts matched, case-insensitive, against an invocation's failure detail:

* Codex: `Your workspace is out of credits` (reported by the owner on 2026-10-23).
* Claude: a usage-limit refusal such as `You've hit your usage limit`. The committed
  fixture `usage-limit.synthetic.stdout.jsonl` is synthetic, because a real refusal was
  not induced, so this text is a best match and not a capture.

Not matched, so the run continues: a bad model id (404), a timeout, a crash, a billing
guard failure, and any other harness failure.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

LIMIT_PATTERNS = (
    re.compile(r"out of credits", re.IGNORECASE),
    re.compile(r"usage limit", re.IGNORECASE),
    re.compile(r"hit your (?:usage )?limit", re.IGNORECASE),
    re.compile(r"credit balance is too low", re.IGNORECASE),
)
_REASON_LIMIT = 300


def limit_detail(item: Mapping[str, Any]) -> str | None:
    """The first harness failure detail in a result row that names a limit, else `None`."""
    for invocation in item.get("invocations") or []:
        failure = invocation.get("failure") if isinstance(invocation, Mapping) else None
        if not isinstance(failure, Mapping) or failure.get("kind") != "harness":
            continue
        detail = str(failure.get("detail", ""))
        if any(pattern.search(detail) for pattern in LIMIT_PATTERNS):
            return detail[:_REASON_LIMIT]
    return None
