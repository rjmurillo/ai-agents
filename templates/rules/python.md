---
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/requirements*.txt"
description: Python idioms, typing, tooling, and pitfalls. Applies when editing Python or packaging files.
---

# Python Rules

These rules apply when you write or review Python. The dev and install target is
3.14 (`.python-version`, CI, `requires-python = ">=3.14"`). But plugin hooks and
skill scripts run under the host's ambient interpreter, which may be older, so a
blocking gate (`scripts/validation/validate_python_syntax.py`, issue #2655)
requires every tracked file to parse at the hook-portability syntax floor,
currently 3.10. Write to that floor: avoid syntax newer than 3.10, such as PEP
695 generics (`def f[T]()`, 3.12+) and PEP 758 unparenthesized `except A, B:`
(3.14). Defer to `pyproject.toml`, `ruff` config, and `mypy` settings over
personal preference.

## Typing

- Type every public function signature: parameters and return. Internal helpers
  with obvious types may omit annotations, but a boundary without types is a bug.
- Use built-in generics (`list[str]`, `dict[str, int]`, `tuple[int, ...]`) and
  `X | None` instead of `Optional[X]`.
- Prefer precise types: `Sequence`/`Mapping` for read-only parameters,
  `Protocol` for structural interfaces, `Literal` for fixed string sets,
  `TypedDict` for structured dict payloads at a boundary.
- Run `mypy` in CI and treat type errors as failures. A passing
  type checker is part of the contract, not optional.

## Idioms

- Use `@dataclass(frozen=True, slots=True)` for immutable value objects. Reach for
  Pydantic only when you need validation or serialization at a boundary; do not
  pay its cost for internal data.
- Prefer comprehensions and generator expressions over `map`/`filter` with
  lambdas. Use a generator when the result is consumed once and may be large;
  materialize a list only when you need to index or reuse it.
- Manage every resource with a context manager (`with`). Write your own with
  `contextlib.contextmanager` rather than paired `open`/`close` calls.
- Use `pathlib.Path` for filesystem paths, not string concatenation or `os.path`.
- Use structural pattern matching (`match`/`case`) for dispatch over shapes, not
  as a glorified `if` chain over equal values; a dict lookup is clearer there.

## Tooling

- `uv` for environments and dependency resolution; `ruff check` for lint; `mypy`
  for types; `pytest` for tests.
- Tests follow Arrange/Act/Assert, one behavior per test, names that describe the
  behavior (`returns_empty_when_no_rows`). Mock only at I/O and process
  boundaries; never mock the function under test.
- Pin the interpreter and dependencies. Do not rely on the system Python.
- **Never run `ruff format` or cite `ruff format --check` as a gate.**
  No gate runs it; main does not conform. Issue #5304 and
  `tests/validation/test_ruff_format_not_enforced.py` hold the evidence.

## Errors

- Catch the narrowest exception you can act on. Re-raise with bare `raise` to
  preserve the traceback; use `raise NewError(...) from exc` to wrap at a boundary
  without losing the cause.
- Validate untrusted input (request bodies, env vars, file contents) at the
  boundary; trust it after. Do not re-validate the same value at every layer.
- Use exceptions for exceptional cases, not control flow. A function that returns
  a result object or `None` for an expected miss is clearer than one that raises.

## Anti-Patterns to Reject

- **Mutable default arguments** (`def f(x, items=[])`). The default is shared
  across calls and accumulates state. Use `None` and create the list inside.
- **Late-binding closures in a loop** (`[lambda: i for i in range(3)]` all return
  2). Bind per iteration with a default arg (`lambda i=i: i`) or a factory.
- **Bare `except:`** or `except Exception: pass`. It swallows `KeyboardInterrupt`
  and hides real failures. Catch a specific type; if you must log and continue,
  log with context.
- **`assert` for runtime validation.** `assert` is stripped under `python -O`.
  Use it for invariants that should be impossible, raise for invalid input.
- **Module-level side effects** (I/O, network, mutation) at import time. Imports
  must be cheap and pure; put work behind a function or `if __name__ == "__main__"`.
- **`.get(key, default)` on a field that can be explicitly `null`.** When the key
  exists with value `None` (common in JSON and GraphQL payloads), the default is
  bypassed and you get `None`, not the default; a later attribute or index access
  then raises `AttributeError`/`TypeError`. Collapse only explicit `None`:
  `v = data.get(key); v = default if v is None else v`. Avoid
  `data.get(key) or default`, which also overrides valid falsy values such as
  `0`, `False`, and `""`.

## Version Compatibility Reviews

Before reporting a version-sensitive finding in a review, read `project.requires-python`
from `pyproject.toml`. Do not flag syntax or stdlib APIs that are universally available
at the repository's declared floor.

Concrete known-valid patterns at the current floor (`>=3.14`):

- `isinstance(value, A | B)` and `issubclass(cls, A | B)` use PEP 604 union syntax
  and are valid runtime arguments since Python 3.10. Do not flag them.
- `X | None` and `X | Y` type annotations are valid in function signatures since 3.10.
- `match`/`case` structural pattern matching is valid since 3.10.
- PEP 695 generic syntax (`def f[T]()`) is 3.12+; the repo syntax-floor gate
  (`scripts/validation/validate_python_syntax.py`) rejects it.

Invalid-at-any-floor runtime uses still warrant a finding:

- `isinstance(value, list[int])` fails at runtime even in 3.14 because parameterized
  generics are not valid `isinstance` arguments.
- `isinstance(value, int | None)` where `None` is not a class (`type(None)` is
  required: `isinstance(value, int | type(None))`).

Compatibility findings must cite the detected Python floor from `pyproject.toml`,
for example: `requires-python = ">=3.14" detected; PEP 604 isinstance unions are
valid at this floor.`

- Python language reference: <https://docs.python.org/3/reference/>
- Typing: <https://docs.python.org/3/library/typing.html>
- `ruff`: <https://docs.astral.sh/ruff/>
- `uv`: <https://docs.astral.sh/uv/>
- `pytest`: <https://docs.pytest.org/>
