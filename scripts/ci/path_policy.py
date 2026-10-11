"""The repository's pytest path policy, read by CI.

`path_policy.yml` next to this module is the list. `.github/workflows/pytest.yml`
hands that same file to `dorny/paths-filter` to decide whether the pytest matrix
runs at all, and the CI wiring tests read it through `load_patterns` so they
describe the same list the gate evaluates.
"""

from __future__ import annotations

from pathlib import Path

import yaml

POLICY_FILE = Path(__file__).with_name("path_policy.yml")

# The filter name `pytest.yml` reads from this document. `dorny/paths-filter`
# publishes one output per top-level key, and `determine_should_run_from_filters
# .py` is wired to this one.
FILTER_NAME = "python"


def load_patterns(policy_file: Path | None = None) -> tuple[str, ...]:
    """The policy's globs, in declaration order.

    Raises:
        ValueError: the document has no `python` key, or its value is not a
            list of globs. Failing here is the safe direction: a caller that
            silently received an empty tuple would treat every path as
            irrelevant, which is the verdict that runs the fewest tests.
    """
    path = policy_file if policy_file is not None else POLICY_FILE
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or FILTER_NAME not in document:
        raise ValueError(f"{path} declares no {FILTER_NAME!r} filter")
    entries = document[FILTER_NAME]
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{path} declares an empty {FILTER_NAME!r} filter")
    return tuple(str(entry) for entry in entries)
