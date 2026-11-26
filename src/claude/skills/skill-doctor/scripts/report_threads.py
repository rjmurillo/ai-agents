"""Render the top-level versus subagent sampling table. python3, stdlib only."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

THREAD_LABELS = (("top_level", "Top-level"), ("subagent", "Subagent"))


def thread_table_html(esc: Callable[[Any], str], pct: Callable[[Any], str], per_thread: Any) -> str:
    """Top-level versus subagent counts and grades. Empty when the report has no split."""
    if not per_thread:
        return ""
    rows = "".join(
        f"<tr><td>{esc(label)}</td><td>{esc(c.get('scoreable', 0))}</td>"
        f"<td>{esc(c.get('sampled', 0))}</td>"
        f"<td>{pct(c['overall']) if c.get('overall') is not None else '-'}</td></tr>"
        for key, label in THREAD_LABELS
        if isinstance(c := per_thread.get(key), dict)
    )
    if not rows:
        return ""
    return (
        '<p class="muted">Subagent sessions are child work launched by a parent session. '
        "Their grades are reported apart from top-level sessions, and the harness rows "
        "above pool both.</p>"
        '<div class="table-scroll" role="region" aria-label="Sampling by session type" '
        'tabindex="0"><table><caption>Sampling by session type</caption>'
        '<thead><tr><th scope="col">Session type</th><th scope="col">Scoreable</th>'
        '<th scope="col">Sampled</th><th scope="col">Overall</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )
