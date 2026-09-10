"""The repository's one test-impact path policy, read by CI and by the hook.

`path_policy.yml` next to this module is the list. `.github/workflows/pytest.yml`
hands that same file to `dorny/paths-filter` to decide whether the pytest matrix
runs at all; this module reads it to classify a changed path for
`select_tests.py`. Issue #5318: before that file existed the local side kept its
own near-copy in `runtime_read_patterns.txt`, and the two drifted every time one
was widened by hand.

Three classes, and the boundary between the first two is what the import graph
can trace:

``SOURCE``
    A Python module. `import_graph.py` maps it to the tests that import it, so a
    change here can be narrowed.
``TEST_INPUT``
    Named by the policy but not traceable by imports: a rule file, a skill
    manifest, a lockfile, an episode JSON. Some test opens it, and no import
    edge records which one.
``UNRELATED``
    Named by nothing in the policy. CI skips the whole pytest matrix for it.

A path that is both, a `.py` file inside a tree the policy names, classifies as
``SOURCE``. That is the pre-existing behavior and it is deliberately kept:
`scripts/memory_enhancement/**` and `.claude/hooks/**` are Python trees the
policy names for their non-Python members, and classifying every `.py` under
them as ``TEST_INPUT`` would force the full suite on ordinary Python edits. The
ceiling is that a `.py` file some test reads as *text* is selected by import
edges that do not describe that read. Issue #5377 owns tightening it.

`UNRELATED` is reported but not yet acted on: `select_tests.py` still sends
every non-Python change to the full suite. Issue #5377 is what turns an
`UNRELATED` push into no pytest process at all.
"""

from __future__ import annotations

import fnmatch
from enum import Enum
from pathlib import Path

import yaml

POLICY_FILE = Path(__file__).with_name("path_policy.yml")

# The filter name `pytest.yml` reads from this document. `dorny/paths-filter`
# publishes one output per top-level key, and `determine_should_run_from_filters
# .py` is wired to this one.
FILTER_NAME = "python"


class Impact(Enum):
    """How a changed path can affect the pytest outcome."""

    SOURCE = "source"
    TEST_INPUT = "test-input"
    UNRELATED = "unrelated"


def load_patterns(policy_file: Path | None = None) -> tuple[str, ...]:
    """The policy's globs, in declaration order.

    Raises:
        ValueError: the document has no `python` key, or its value is not a
            list of globs. Failing here is the safe direction: a caller that
            silently received an empty tuple would classify every path as
            ``UNRELATED``, which is the verdict that runs the fewest tests.
    """
    path = policy_file if policy_file is not None else POLICY_FILE
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or FILTER_NAME not in document:
        raise ValueError(f"{path} declares no {FILTER_NAME!r} filter")
    entries = document[FILTER_NAME]
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path} declares an empty {FILTER_NAME!r} filter")
    return tuple(str(entry) for entry in entries)


def matches(rel: str, pattern: str) -> bool:
    """True when the policy glob ``pattern`` covers repo-relative path ``rel``.

    An approximation of the picomatch semantics `dorny/paths-filter` applies,
    biased to over-match. Two differences from a bare `fnmatch` are load
    bearing:

    - `fnmatch`'s ``*`` crosses ``/``, so collapsing ``**`` to ``*`` widens a
      pattern rather than narrowing it.
    - picomatch's leading ``**/`` matches zero directories, so ``**/*.py``
      covers a root-level ``conftest.py``. `fnmatch` alone would not, and the
      resulting ``UNRELATED`` verdict on a root Python file is the one
      direction that runs too little.
    """
    if rel == pattern:
        return True
    candidates = [pattern]
    if pattern.startswith("**/"):
        candidates.append(pattern[3:])
    return any(fnmatch.fnmatch(rel, candidate.replace("**", "*")) for candidate in candidates)


def matched_pattern(rel: str, patterns: tuple[str, ...]) -> str | None:
    """The first policy glob covering ``rel``, or None when none does."""
    for pattern in patterns:
        if matches(rel, pattern):
            return pattern
    return None


def is_source(rel: str) -> bool:
    """True when the import graph can trace ``rel``.

    `import_graph.py` maps Python modules. `.pyi` stubs are not imported at
    runtime and carry no edges, so they are not source here even though the
    policy names them.
    """
    return rel.endswith(".py")


def classify(rel: str, patterns: tuple[str, ...] | None = None) -> tuple[Impact, str | None]:
    """Classify ``rel`` and return the policy glob that decided it.

    The glob is None for ``UNRELATED``, where nothing matched.
    """
    resolved = patterns if patterns is not None else load_patterns()
    pattern = matched_pattern(rel, resolved)
    if pattern is None:
        return Impact.UNRELATED, None
    if is_source(rel):
        return Impact.SOURCE, pattern
    return Impact.TEST_INPUT, pattern
