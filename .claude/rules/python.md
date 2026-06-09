---
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/requirements*.txt"
description: Python idioms, typing, tooling, and pitfalls. Applies when editing Python or packaging files.
---

# Python Rules

These rules apply when you write or review Python. Repo tooling runs on 3.14 and
CI targets it, but package metadata declares `requires-python = ">=3.10"`, so use
only syntax the interpreter target for the code you touch supports (for example,
PEP 695 generics need 3.12+). Defer to `pyproject.toml`, `ruff` config, and `mypy`
settings over personal preference.

## Typing

- Type every public function signature: parameters and return. Internal helpers
  with obvious types may omit annotations, but a boundary without types is a bug.
- Use built-in generics (`list[str]`, `dict[str, int]`, `tuple[int, ...]`) and
  `X | None` instead of `Optional[X]`. Use PEP 695 syntax (`def f[T](x: T) -> T`)
  on 3.12+.
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

- `uv` for environments and dependency resolution; `ruff` for lint and format
  (it replaces black, isort, flake8); `mypy` for types; `pytest` for tests.
- Tests follow Arrange/Act/Assert, one behavior per test, names that describe the
  behavior (`returns_empty_when_no_rows`). Mock only at I/O and process
  boundaries; never mock the function under test.
- Pin the interpreter and dependencies. Do not rely on the system Python.

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

## References

- Python language reference: <https://docs.python.org/3/reference/>
- Typing: <https://docs.python.org/3/library/typing.html>
- `ruff`: <https://docs.astral.sh/ruff/>
- `uv`: <https://docs.astral.sh/uv/>
- `pytest`: <https://docs.pytest.org/>
