"""Where pytest puts its temporary directories, and how to recognize one.

Split out of ``slow_test_report`` so that module stays inside the 500 line
taste ceiling, and because "is this path a scratch directory" is a different
question from "what did this test cost". The reporting module is the only
caller today.

`tempfile.gettempdir()` is not the whole answer in this repository.
`.github/workflows/pytest.yml` sets ``PYTEST_NON_TMP_ROOT`` to a path under the
runner work directory rather than under /tmp, so a check against the system
temp dir alone misses every tmp_path on CI. That is not hypothetical: it passed
on every developer machine, where the two agree, and failed on every CI
partition.
"""

from __future__ import annotations

import functools
import os
import tempfile

# Read on demand rather than at import so a runner, or a test, that sets one of
# these after this module loads still gets the right answer.
TEMP_ROOT_ENV_VARS = ("PYTEST_NON_TMP_ROOT", "PYTEST_DEBUG_TEMPROOT", "TMPDIR")


@functools.cache
def temp_roots() -> tuple[str, ...]:
    """Every prefix a pytest ``tmp_path`` can legitimately sit under.

    Cached because the caller runs this on a hot path. A test that moves the
    root calls ``temp_roots.cache_clear()``.
    """
    candidates = [tempfile.gettempdir()]
    for name in TEMP_ROOT_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            candidates.append(value)
    resolved = {os.path.realpath(candidate) for candidate in candidates if candidate}
    # Longest first so a nested root is credited before its parent.
    return tuple(sorted(resolved, key=len, reverse=True))


def is_temp_path(label: str) -> bool:
    """True when *label* sits under any known pytest temp root."""
    resolved = os.path.realpath(label)
    return any(resolved.startswith(root) for root in temp_roots())
