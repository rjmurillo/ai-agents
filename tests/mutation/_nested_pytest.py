"""Private temp root for the nested pytest a mutation test launches.

Issue #7288. A mutation test grades a mutant by running a second pytest in a
subprocess. Under xdist every worker does this at once. The outer run is given
``--basetemp``, so its own workers never share a temp root. The nested run is
not: with no ``--basetemp`` it falls back to ``$TMPDIR/pytest-of-<user>``, one
directory that every nested run on the machine shares.

Pytest keeps a ``pytest-current`` symlink in that directory. At session end
``cleanup_dead_symlinks`` (``_pytest/pathlib.py``) checks ``is_symlink()`` and
then calls ``unlink()`` with nothing in between. A second nested run that
replaces or removes the link in that window turns the ``unlink`` into
``FileNotFoundError: .../pytest-current`` and the nested run exits 1, which the
mutation test reads as a failed suite.

``--basetemp`` makes pytest skip the numbered-directory path entirely
(``_pytest/tmpdir.py`` ``getbasetemp``), so no ``pytest-current`` is created,
cleaned, or shared. Each call gets its own directory.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def private_basetemp() -> Iterator[str]:
    """Yield a ``--basetemp=<path>`` argument for one nested pytest run.

    The directory is created under the system temp dir, never under the
    mutation worktree (a git checkout) and never under the shared
    ``pytest-of-<user>`` root. It is removed when the block exits.
    """
    with tempfile.TemporaryDirectory(prefix="nested-pytest-") as root:
        yield f"--basetemp={Path(root) / 'base'}"
