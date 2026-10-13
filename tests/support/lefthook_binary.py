"""One resolver for the lefthook binary that test modules drive.

lefthook is a pinned dev dependency (``lefthook==`` in pyproject's dev extra),
so the binary that matches the pin sits in the running interpreter's scripts
directory. A bare PATH lookup agrees only while that directory leads PATH,
which ``uv run`` arranges and a directly invoked ``.venv/bin/pytest`` does not.
Measured with a stub ``lefthook`` placed earlier on PATH: ``uv run`` resolved
``.venv/bin/lefthook`` either way, while ``.venv/bin/python`` resolved the stub
under PATH and the pinned 2.1.12 under the scripts directory. Binary identity
is not incidental, because the tests that drive the real binary pin lefthook's
own scheduling, skip, and templating behavior, which moves between releases.

Every test module that needs the binary imports ``resolve_lefthook`` from here
instead of calling ``shutil.which("lefthook")`` (Issue #5568, Refs #5567).
"""

from __future__ import annotations

import shutil
import sysconfig


def resolve_lefthook(scripts: str | None = None) -> str | None:
    """Locate lefthook, preferring the running interpreter's own environment.

    PATH remains the fallback so a host without the dev extra installed keeps
    whatever lefthook it has instead of failing every test that needs one.
    Returns None when neither source has a binary, so callers can fail loudly.
    """
    directory = scripts if scripts is not None else sysconfig.get_path("scripts")
    return shutil.which("lefthook", path=directory) or shutil.which("lefthook")
