"""Pre-commit check: a count word in a JSON or YAML string beside a sibling array.

`nl_cardinality.structured_count_claims` owns the detection. This module only
reads staged blobs, dispatches by extension, and reports. A staged file is read
from the index, not the working tree, so a partial stage is judged as committed.

Exit codes: 0 no contradicted count, 1 a count contradicts its sibling array,
2 an unsafe path.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from scripts.validation.nl_cardinality import structured_count_claims

_KIND_BY_SUFFIX = {".json": "json", ".yaml": "yaml", ".yml": "yaml"}


def check_staged_structured_cardinality(
    paths: Sequence[str],
    repo_root: Path,
    *,
    read_blob: Callable[[Path, str], bytes | None],
    safe_path: Callable[[str], str | None],
) -> int:
    """Return 1 when a staged JSON or YAML file holds a contradicted count."""
    violations: list[str] = []
    examined = 0
    for raw_path in paths:
        path = safe_path(raw_path)
        if path is None:
            print(f"ERROR: unsafe staged path: {raw_path}", file=sys.stderr)
            return 2
        kind = _KIND_BY_SUFFIX.get(Path(path).suffix.lower())
        content = read_blob(repo_root, path) if kind else None
        if kind is None or content is None:
            continue
        examined += 1
        for claim in structured_count_claims(content.decode("utf-8", errors="replace"), kind):
            violations.append(
                f"  {path}:{claim.line}: {claim.path} says {claim.stated}, "
                f"but sibling `{claim.array_key}` has {claim.actual}"
            )
    if not violations:
        print(f"staged-cardinality: 0 contradicted counts in {examined} JSON/YAML files")
        return 0
    print(
        "ERROR: a count in a staged string restates the length of a sibling array "
        "and the two disagree. Fix the number or drop it:",
        file=sys.stderr,
    )
    for line in violations:
        print(line, file=sys.stderr)
    return 1
