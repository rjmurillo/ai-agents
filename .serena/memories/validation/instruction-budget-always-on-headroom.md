# The Always-On Instruction Budget Has About 400 Bytes of Headroom

Adding a paragraph to an always-on rule under `.claude/rules/` can fail the
push, and the failure arrives after the twenty minute test suite rather than
before it.

## Measure before you write

```bash
uv run --frozen python scripts/validation/instruction_budget.py
```

The script is at `scripts/validation/instruction_budget.py`. Guessing
`check_instruction_budget.py` produces `Errno 2`, which reads like the check
does not exist.

Measured on `origin/main` at `ede9fd1fe`:

| Ext | Files | Bytes | Ceiling | Usage | Status |
|---|---|---|---|---|---|
| `.cs` | 11 | 95599 | 99000 | 96.6% | PASS |
| `.md` | 9 | 82603 | 83000 | 99.5% | PASS |
| `.ps1` | 11 | 95431 | 99000 | 96.4% | PASS |
| `.py` | 11 | 95722 | 99000 | 96.7% | PASS |

`.md` is the binding constraint at 397 bytes of headroom. The other three each
have over 3000.

## Why .md is different

The budget sums the language-universal `.github/instructions/*.instructions.md`
files, the ones whose `applyTo` is `**`. Every language inherits those, so the
`.md` row is the always-on corpus that loads on every turn regardless of what
is being edited. Issue #3419 added the ratchet so that corpus cannot grow
silently.

## What this means in practice

A single added paragraph in a universal rule is enough. One roughly 500 byte
paragraph added to `.claude/rules/code-quality.md` took `.md` from 82603 to
83100, which is 100.1% and a hard FAIL. Note that the rule file itself is not
what is measured; the generated mirror under `.github/instructions/` is. Editing
the canonical rule and regenerating with `build/scripts/generate_rules.py` moves
the number.

So a new always-on rule has to displace an existing one rather than join it.
Decide what it displaces before writing it, not after the push fails.

A rule scoped with a narrower `applyTo` does not count against this budget. If
the guidance only binds when editing a particular tree, scope it and the ceiling
stops being a constraint.

## Cost of finding out the slow way

The pre-push hook runs `python-tests` for about 1189 seconds and reports the
validation group afterward. The budget check itself takes 0.11 seconds. Running
it by hand first turns a twenty minute round trip into an instant answer.
