# A mutation that survives may mean an upstream invariant made the branch unreachable

## Symptom

You mutate production code in a way that is obviously wrong, run the full suite,
and every test still passes. The mutation "survives". You already ruled out the
usual causes: the mutation really applied (`cmp -s` against a backup), the
bytecode is fresh (`__pycache__` purged), and pytest exited 0 rather than 4.

## The cause nobody looks for

An invariant **upstream** of the mutated code can make the mutated branch
unreachable through the real type. The test that claims to cover that branch
cannot construct an input that reaches it, so it asserts nothing, and no mutation
of that branch can ever be observed.

## Worked example, 2026-08-02, `scripts/validation/instruction_budget.py`

`_status_of()` returns FAIL when `over_budget`, WARN when `under_reserve`, else
PASS. Mutation M3 swapped the branch order so WARN was checked first. It survived
the entire 86 test suite.

Reason: `ExtensionResult.under_reserve` opens with

```python
if self.reserve_bytes <= 0 or self.over_budget:
    return False
```

so no instance of the real type can ever report both flags true. The precedence
between FAIL and WARN is unobservable through `ExtensionResult`. My
`test_status_of_prefers_fail_over_warn` was constructing a real `ExtensionResult`
and therefore asserting nothing at all about precedence.

## Fix pattern

Test the function against a **duck-typed stub that violates the upstream
invariant**, proving the function prefers the harder verdict on its own rather
than leaning on its caller. Then add a second test asserting the upstream
invariant structurally, so the two facts are covered separately:

1. `_status_of` prefers FAIL over WARN even when handed both flags (stub).
2. `ExtensionResult` never reports both flags (real type).

After the fix, M3 kills exactly `test_status_of_prefers_fail_over_warn`.

## Why this matters beyond one file

Defensive guards are good and should stay. The hazard is that a guard silently
converts a downstream test into a tautology, and nothing in the test output says
so. Coverage reports it as covered. The test name claims it is tested. Only a
mutation harness that prints real per-mutant output finds it.

Corollary worth internalizing: **a surviving mutation is information even when
you cannot immediately explain it.** The instinct to write it off as "the
mutation was not meaningful" is exactly backwards. Chase every survivor to a
named cause.

## Checklist when a mutation survives

1. Did the mutation actually apply? `cmp -s` against a backup.
2. Is the bytecode stale? Purge `__pycache__`; CPython invalidates on
   (mtime in whole seconds, size), so a same-size line swap inside one wall clock
   second grades the mutated bytecode on the restore run.
3. Did pytest exit 4? That is a collection error, not a kill.
4. **Can any input reach the mutated branch through the real type?** Read every
   guard upstream. If a guard makes the branch unreachable, the test is vacuous.
5. Is the assertion trivially true independent of the mutation?

## Why this is a memory and not an always-on rule

It is needed only at the moment a mutation survives, which the admission test
says makes it retrievable rather than always-on. There is also a hard constraint:
the `.md` instruction budget had 998 bytes of headroom against an 83000 byte
ceiling when this was written, and always-on steering text is the scarce resource
being rationed. Conditional knowledge does not earn a permanent slot.
