"""Skip error shared by the code-scanning reader modules.

Dependency-free on purpose: the pure scope helpers raise it, and the /review
pre-step imports those helpers without the ``github_core`` library on its path.
"""

from __future__ import annotations

EXIT_EXTERNAL = 3
EXIT_AUTH = 4


class SkipError(Exception):
    """The read cannot complete. ``reason`` is a fixed string, never remote text."""

    def __init__(self, reason: str, exit_code: int = EXIT_EXTERNAL) -> None:
        super().__init__(reason)
        self.reason = reason
        self.exit_code = exit_code
