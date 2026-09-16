#!/usr/bin/env python3
r"""YAML frontmatter parsing for validation scripts.

Extracted from ``scripts/validation/pre_pr.py`` (issue #2223) so the pre-PR
runner stays smaller and the frontmatter parser has a single home that other
validators can reuse. That reuse is the reason this module now delegates rather
than parses: issue #5275 found this helper's boundary arithmetic copied into
three other files, each drifting slightly, so the same document could pass one
gate and crash another.

The fence contract lives in ``scripts/validation/frontmatter_contract.py``,
which delegates to ``python-frontmatter``. This module keeps its own name and
signature so its four call sites need no change, and adds nothing of its own
beyond flattening the contract's status back to the ``dict | None`` those
callers expect.

Stricter/looser/different than canonical
----------------------------------------

Stricter than this helper was before issue #5275 on exactly one shape. It used
``text.find("\n---", 3)``, a substring search, so any line merely starting with
three dashes closed the block, ``--- trailing text`` included. The contract
requires the fence to be dashes and whitespace only, so such a block is now
unterminated and this returns ``None``.

Looser on nothing: ``find("\n---", 3)`` already accepted a padded fence, a tab,
and four or more dashes, which is why the divergence in #5275 ran the other way
(the index generator rejected what this accepted).

Duplicate keys are deliberately still tolerated here, last-one-wins, matching
``yaml.safe_load``. The contract can reject them and the ADR gates ask it to,
but this helper's other callers were not written against that rule and issue
#5275's third acceptance criterion holds their behaviour fixed until each is
reviewed on its own.

Measured before the change: across 4,074 markdown files under ``.agents``,
``.claude``, ``src``, ``templates``, ``docs``, ``.github``, ``scripts``,
``build`` and ``tests``, the old and new implementations return identical
results on every file. The tightening is real but unreached by the corpus.
"""

from __future__ import annotations

from typing import Any

from scripts.validation.frontmatter_contract import FrontmatterStatus, parse_frontmatter


def _parse_yaml_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter from markdown text.

    Returns the parsed mapping, or None when the block is absent, unterminated,
    empty, malformed, or not a mapping. Collapsing those five into one None is
    what this signature has always done; callers needing them apart should call
    :func:`scripts.validation.frontmatter_contract.parse_frontmatter` directly,
    as ``check_adr_lifecycle.py`` does to tell an author which defect they have.

    Only VALID returns a mapping. EMPTY is deliberately excluded even though the
    contract counts it as parsed: ``yaml.safe_load("")`` returns None, which the
    old ``isinstance(result, dict)`` test rejected, so an empty block has always
    been None here. Returning the contract's ``{}`` instead would flip
    ``check_adr_lifecycle``'s reason for such a record from "frontmatter block
    is empty" to a missing-field complaint, which is a different message for the
    same defect.
    """
    result = parse_frontmatter(text, allow_duplicate_keys=True)
    if result.status is not FrontmatterStatus.VALID:
        return None
    return result.metadata
