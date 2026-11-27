# The older import validators walk try blocks and skip only function bodies, so a doc saying they skip guarded imports was half wrong

**Atomicity**: 90%
**Category**: Validator docs
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E083. State checked on main at 1be533c496 (2026-11-26).

## Question

Do the older module-level import validators skip imports inside try blocks?

## Conventional answer

`CONTRIBUTING.md:823` and the PR body said the older validators skip imports inside try blocks.

## First-principles position

`_import_time_nodes` visits `try`, `except`, `else` and `finally` blocks. The probe found `yaml` inside a `try` block. It skipped `toml` inside a function. Only the claim about function bodies held.

## Evidence with limits

- Probe on 2026-11-05 against `check_doc_interpreter_portability.py`: input was a try-guarded `import yaml` plus a function-level `import toml`. Result: `['yaml']`.
- Quote: "---PROBE ['yaml']  (input: try: import yaml / except ImportError: yaml=None; def f(): import toml)"
- Limits: One probe on 2026-11-05. `check_plugin_root_interpreter.py` was read, not probed separately. The doc is already corrected.
- State on main at 1be533c496 (2026-11-26): fixed. `CONTRIBUTING.md:915` now says the validator also flags imports inside try blocks, which those validators walk. `check_doc_interpreter_portability.py:289-291` still descends into try bodies and handlers.

## Decision

Before a doc states what a validator skips, run the validator on a two-line fixture. Do not describe AST walk coverage from memory.

## Related

- `.serena/memories/decision-script-mode-import-breakage-needs-execution.md`
