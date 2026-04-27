# Code Comment Standards

Comments record the things the code itself cannot say. Names, types, and structure carry the rest. This guide gives the patterns for docstrings, function headers, why-not-what comments, complex-logic annotations, TODOs, and deprecation notices.

## Principles

- A reader who reads the function name and signature should already know most of what it does.
- Comments explain **why**, not **what**. Restating the code is noise.
- A wrong comment is worse than no comment. Update or delete on every change.
- Reference issues or ADRs when the rationale lives elsewhere.

## Function or Method Docstrings

Every public function or method gets a docstring with: purpose, parameters, return value, and raised errors.

### Language-agnostic shape

```text
[One-line summary in the imperative: "Compute the foo." Not "This function computes the foo."]

[Optional paragraph: any non-obvious behavior, side effects, or constraints.]

Parameters:
  [name] ([type]): [meaning, range, default if any]

Returns:
  [type]: [meaning of the value]

Raises:
  [ErrorType]: [condition that produces the error]
```

### Python

```python
def charge_account(account_id: str, amount_cents: int) -> Receipt:
    """Charge the account and return a receipt.

    Idempotent on (account_id, request_id). Safe to retry.

    Parameters:
        account_id: Stable account identifier; must already exist.
        amount_cents: Positive amount in the smallest currency unit.

    Returns:
        A Receipt with the new balance and a transaction id.

    Raises:
        AccountNotFoundError: account_id is not registered.
        InsufficientFundsError: amount_cents exceeds available balance.
    """
```

### JavaScript or TypeScript

```typescript
/**
 * Charge the account and return a receipt.
 *
 * Idempotent on (accountId, requestId). Safe to retry.
 *
 * @param accountId Stable account identifier; must already exist.
 * @param amountCents Positive amount in the smallest currency unit.
 * @returns A Receipt with the new balance and a transaction id.
 * @throws AccountNotFoundError when accountId is not registered.
 * @throws InsufficientFundsError when amountCents exceeds available balance.
 */
function chargeAccount(accountId: string, amountCents: number): Receipt {
  // ...
}
```

## Why-Not-What Comments

Comments inside a function explain motivation, not mechanics.

### Bad (restates the code)

```python
# Increment the counter
counter += 1
```

### Good (explains why)

```python
# The vendor API returns 200 even on validation failure; check the
# `error` field before treating the response as success.
if "error" in response_body:
    raise VendorValidationError(response_body["error"])
```

## Complex-Logic Annotations

When an algorithm is non-obvious, annotate the invariant it preserves or the source of the technique.

### Bad

```python
# Magic happens here
def reconcile(local, remote):
    ...
```

### Good

```python
# Last-writer-wins per field, with a tiebreaker on the (timestamp, replica_id)
# pair. See ADR-019 for the conflict resolution policy.
def reconcile(local: State, remote: State) -> State:
    ...
```

## TODO Format

Track open items with an issue, an owner, or both. A bare `# TODO` rots fast.

### Bad

```python
# TODO: fix this
```

### Good

```python
# TODO(#1234): replace with the new validator once the schema lands.
```

## Deprecation Notice

Mark deprecated symbols so callers see the replacement before they read the body.

### Python

```python
import warnings

def legacy_charge(account_id, amount_cents):
    """Deprecated: use charge_account; will be removed in v3.0 (#1450)."""
    warnings.warn(
        "legacy_charge is deprecated; use charge_account",
        DeprecationWarning,
        stacklevel=2,
    )
    return charge_account(account_id, amount_cents)
```

### TypeScript

```typescript
/**
 * @deprecated Use chargeAccount; will be removed in v3.0 (#1450).
 */
export function legacyCharge(accountId: string, amountCents: number): Receipt {
  return chargeAccount(accountId, amountCents);
}
```

## Anti-Patterns

| Avoid | Why |
|-------|-----|
| `# Get the user` | Restates the code; no information. |
| Author names or dates in comments | Git already records this; the comment goes stale. |
| `// HACK:` with no explanation | Tells the reader something is wrong but not how to fix it. |
| Long block comments at the top of a function | Often a sign the function is doing too much. Split it. |
| Comments that contradict the code | Worse than missing comments; readers stop trusting both. |
