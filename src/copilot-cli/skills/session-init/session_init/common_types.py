"""Shared types for session-init modules.

Defines ApplicationFailedError used by git_helpers and template_helpers
for wrapping unexpected errors with diagnostic context.

Note: Issue #840 - Extracted from duplicate definitions.
"""

from __future__ import annotations


class ApplicationFailedError(Exception):
    """Wraps unexpected errors with diagnostic context."""
