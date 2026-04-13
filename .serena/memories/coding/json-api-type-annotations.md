# JSON API Response Type Annotations

## Rule
Use `dict[str, Any]` (from `typing.Any`) for GraphQL and REST API JSON responses. Never use `dict[str, object]`.

## Why
`dict[str, object]` causes mypy errors on `.get()` chains because `object` has no `.get()` method. JSON responses have nested dicts that require chained access.

## Evidence
PR #1593: First mypy fix attempt used `dict[str, object]`, which caused `"object" has no attribute "get"` error on line 146. Required a second fix iteration to `dict[str, Any]`.