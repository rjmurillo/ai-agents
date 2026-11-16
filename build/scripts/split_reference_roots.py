"""Host-specific plugin-root paths for split-agent skill references.

Six agents (architect, critic, implementer, orchestrator, qa, security) load
reference files from a skill's ``references/`` folder. The authored templates
write that folder with the shared fallback root, which names both plugin-root
variables and the ``.claude`` checkout default.

A host that rewrites its own bare token in an agent body gets that token
instead. Claude Code rewrites a bare ``${CLAUDE_PLUGIN_ROOT}`` to an absolute
path (ADR-121, evidence row 4). The Copilot CLI render uses
``${COPILOT_PLUGIN_ROOT}``. A copy for any other host keeps the shared form,
because ADR-115 records that a Cursor shell sees no plugin-root variable.

Stdlib only: ``detect_agent_drift.py`` runs as plain ``python3``.
"""

from __future__ import annotations

import re

SPLIT_REFERENCE_SKILLS: tuple[str, ...] = (
    "adr-review",
    "decision-critic",
    "build",
    "autoplan",
    "test",
    "security-scan",
)

SHARED_ROOT = "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}"
CLAUDE_ROOT = "${CLAUDE_PLUGIN_ROOT}"
COPILOT_ROOT = "${COPILOT_PLUGIN_ROOT}"

_HOST_ROOTS = frozenset({CLAUDE_ROOT, COPILOT_ROOT})

_BARE_ROOT_REFERENCE = re.compile(
    r"\$\{(?:CLAUDE_PLUGIN_ROOT|COPILOT_PLUGIN_ROOT)\}"
    r"(/skills/(?:" + "|".join(re.escape(s) for s in SPLIT_REFERENCE_SKILLS) + r")/references/)"
)


def render_host_reference_roots(text: str, host_root: str) -> str:
    """Replace the shared root with ``host_root`` on split-agent reference paths only.

    Other skill paths and other folders under a split skill keep the shared root.
    Raises ``ValueError`` for a root that is not a known host token.
    """
    if host_root not in _HOST_ROOTS:
        raise ValueError(f"unknown host plugin root: {host_root!r}")
    for skill in SPLIT_REFERENCE_SKILLS:
        suffix = f"/skills/{skill}/references/"
        text = text.replace(SHARED_ROOT + suffix, host_root + suffix)
    return text


def restore_shared_reference_roots(text: str) -> str:
    """Return split-agent reference paths that carry a bare host root to the shared root.

    The inverse of :func:`render_host_reference_roots` for either host token. A copy
    of a Claude body for another host uses it, and drift detection uses it to compare
    host renders as one text.
    """
    return _BARE_ROOT_REFERENCE.sub(lambda m: SHARED_ROOT + m.group(1), text)
