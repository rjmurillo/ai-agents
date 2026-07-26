# Requirement(non_string) raises TypeError, not InvalidRequirement

## Question

Is `except InvalidRequirement: continue` enough to protect a dependency-parsing
loop from a malformed `pyproject.toml`?

## Conventional answer

Yes. `packaging.requirements.InvalidRequirement` is the documented error for a
requirement string the parser cannot understand, so wrapping the call in that
handler is the idiomatic guard. `scripts/validation/check_ci_dependency_pins.py`
was written this way.

## First-principles position

No. `InvalidRequirement` covers a *string* that does not parse. It does not
cover a value that is not a string at all. `Requirement(1)` raises `TypeError`
from inside the tokenizer, which the handler does not catch, so a non-string
item in a dependency list escapes and takes the whole validator down.

TOML permits this shape: `dependencies = [1, 2]` is valid TOML and invalid
metadata. Anything reading a config file written by a human has to type-guard
before it parses, not after.

## Evidence

Measured directly:

```
>>> from packaging.requirements import Requirement
>>> Requirement(1)
TypeError: expected string or bytes-like object, got 'int'
```

Restoring the pre-fix body of `declared_constraints` turned 6 of 8 new
parametrized malformed-table cases red, including the case where a malformed
section blanked a healthy one.

Two cases survived the pre-fix body, and the reason is worth knowing:
`list("oops")` yields single characters, each of which parses as a valid
requirement with no specifiers, so a string where a list belongs degrades
silently rather than crashing.

## Decision

`check_ci_dependency_pins.py` now has `_requirement_strings(value)` and
`_requirement_groups(table)` immediately above `declared_constraints`. Both
filter by `isinstance(..., str)` and `isinstance(..., list)` before any parse.
All three tables (`[project].dependencies`,
`[project.optional-dependencies]`, `[dependency-groups]`) route through them,
which deleted the asymmetric inline guard that previously protected only the
third one.

Refs #3377, PR #3396.
