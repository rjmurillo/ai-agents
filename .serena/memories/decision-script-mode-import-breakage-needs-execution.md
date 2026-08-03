# Decision: detect script-mode import breakage by executing, not by scanning

## Question

How do you detect that a `scripts/validation/*.py` entry point will crash when CI
runs it as `python3 scripts/validation/<name>.py`, given that the same file runs
fine on every developer machine and in every pre-push hook?

## Conventional answer

Issue #4210 proposes a static scan: "fails when a module with an
`if __name__ == '__main__'` block imports `scripts.*` at module level without
`sys.path` containing the repo root." The same issue explains why local runs miss
the defect: "`uv` puts the project root on `sys.path` through
`.venv/lib/python3.14/site-packages/__editable__.ai_agents-0.1.0.pth`."

Both statements look right. Both are wrong in a way that makes the obvious
detector report a broken file as clean.

## First-principles position

**The static scan misses the transitive case.** The entry point that turned
`Validate Vendor Portability` red on 2026-08-03 contains zero module-level
`scripts.*` imports. Measured on all three broken files:

```
check_vendor_portability: module-level 'scripts.*' imports = 0
check_rule_activation_coverage: module-level 'scripts.*' imports = 0
check_skill_contract_tests: module-level 'scripts.*' imports = 0
```

Each imports `portability_baseline` as a flat sibling, and `portability_baseline`
performs `from scripts.validation.portability_floor import ...`. The absolute
import is one edge away from the file being scanned. A scan of module-level
imports passes all three. Following the edge means resolving the flat import,
which means executing it.

**The editable install is a meta-path finder, not a path entry.** This is the
part that makes a hand-rolled local reproduction vacuous. The `.pth` file does
not append the repo root to `sys.path`; it runs
`import __editable___ai_agents_0_1_0_finder; __editable___ai_agents_0_1_0_finder.install()`,
which registers an `_EditableFinder` on `sys.meta_path`. Measured:

```
$ uv run --frozen python -c "<strip repo root from sys.path>; import scripts"
    STILL IMPORTABLE -> .../wt-vendport/scripts/__init__.py
```

I hit this directly. My first harness removed the repo root from `sys.path`, ran
against a file with the defect deliberately restored, and reported
`scanned=88 broken=0`. It could not fail. Adding the finder removal changed the
same run to `broken=3`, correctly naming the mutated file.

## Evidence

- Failing job: `Validate Vendor Portability`, run 30832620808, main at
  `11b1b88b8`. `ModuleNotFoundError: No module named 'scripts'` raised from
  `portability_baseline.py:32`, reached from `check_vendor_portability.py:78`.
- Local reproduction with the system interpreter matched CI exactly, RC=1.
- Mutation test: restoring the old one-line bootstrap made the harness report
  `check_vendor_portability.py` broken; the fix cleared it. The harness fails when
  the defect is present and passes when it is not.
- The workflow prints "One of four ratchets failed" and points at four baseline
  files. No ratchet ran. The checker crashed during import. A reader who trusts
  that message updates a baseline that was never consulted.
- `check_model_pins.py` already carried the correct bootstrap, added for issue
  #3073. Its three siblings never received it.

## Decision

`tests/validation/test_validation_entry_point_imports.py` executes every
`scripts/validation/*.py` entry point in a subprocess that reproduces CI's import
environment: repo root removed from `sys.path`, editable finders removed from
`sys.meta_path`, script directory inserted, `runpy.run_path(..., run_name="__not_main__")`
so module-level imports run without the CLI. 64 entry points, about 5 seconds.

Two negative controls ship with it, because a detector that cannot fail has not
been run: a fixture reproducing the flat-sibling defect must fail, and the same
fixture with the bootstrap must pass.

`check_doc_interpreter_portability.py` and `pre_pr.py` remain recorded in
`KNOWN_UNPORTABLE`. Both are latent, invoked only through `uv run`, and the first
sits exactly at the 500-line ceiling so the bootstrap cannot be added without a
split. A third test asserts each recorded file still fails, so the record cannot
outlive its cause and silently exempt a file someone already fixed.

## Transferable rule

When a test must prove a script works without the project installed, removing the
repo root from `sys.path` is not enough. Remove editable finders from
`sys.meta_path` too, then mutate the file under test and confirm the harness goes
red before trusting a green run.

Refs #4210, #3073, #3657, #3711.
