# Testing Rigor

**Created**: 2026-04-26
**Source**: PR #1756 review (lessons from rubric fix in #1755)
**Status**: BLOCKING for code changes
**Related**: `.agents/governance/TESTING-ANTI-PATTERNS.md`, `AGENTS.md`

---

## Principle

**Every new function MUST have positive AND negative tests.** Happy path alone is insufficient. Don't ship "the change works" with only success-case tests; bots and reviewers will catch what tests missed (whitespace, type validation, error paths, conditional branches).

**Mirror obligation**: a contract change MUST grep for tests asserting the old contract and flip them in the same diff. Tests must mirror the changed obligation, not only the new happy path.

Coverage measurement makes the gap visible: in PR #1756, the original 20 unit tests gave 24% block coverage. After negative + edge + branch tests, coverage rose to 100%, and the additional tests caught real defects (whitespace handling on verdict matching, conditional OTHER-hint emission, scenario type validation) that the bots had flagged.

---

## Test Cases (per function)

|Cases: pos (valid input → expected output) + neg (invalid → idiomatic error) + edge (whitespace, empty, null/None, type-mismatch)
|Error paths: every `raise`/`throw`/error-return branch exercised
|Conditional output: every if/else branch in user-facing strings exercised
|External I/O: mock subprocess, API calls, file reads (no live deps in unit tests)
|CLI: test argv-failure exits, exit codes, stdout vs --output

---

## Pattern Checklist

Apply per function:

- [ ] pos test for happy path
- [ ] neg test asserts the language's idiomatic error on bad input
- [ ] edge tests: whitespace, empty, null/None, wrong type
- [ ] every error-emitting branch exercised
- [ ] every conditional branch exercised
- [ ] external dependencies mocked

---

## Verify Before Commit

Run the stack's coverage tool, gated to the project target. Use the right one for the file you changed:

- **Python**: `python3 -m coverage run --source=<dir> -m pytest && python3 -m coverage report -m --include='<file>' --fail-under=<target>`
- **PowerShell**: `Invoke-Pester -CodeCoverage <files> -CodeCoverageOutputFile cov.xml` then assert `(Import-Clixml cov.xml).CoveragePercent -ge <target>`
- **Node/TS**: `c8 --100 npm test` or `jest --coverage --coverageThreshold`
- **Go**: `go test -cover -coverprofile=cov.out ./... && go tool cover -func=cov.out`
- **C#/.NET**: `dotnet test --collect:"XPlat Code Coverage"` with `coverlet.runsettings` thresholds

100% block coverage on changed files. Exclude only language-equivalent unreachable defensive branches (Python `# pragma: no cover`, Go `default:` panic guards, etc.) with written justification.

Coverage targets per `AGENTS.md > ## Standards`: 100% security-critical, 80% business logic, 60% docs/glue.

---

## Contract Changes: Flip the Stale Tests

When a change alters an observable contract (a return value, an exception type, a public signature, an error message, a side effect, output ordering, or an external call), the tests that assert the OLD contract become wrong. They are now part of the change. Find them and flip them in the same diff:

1. Grep the suite for the old behavior: the old value, exception type, message string, public method name, output literal, side-effect assertion, or fixture field.
2. Update each stale assertion to the new contract, and say in the commit body why the assertion changed.
3. A green suite that still asserts the old contract is a false pass. It proves the change did not land, not that it is correct.

Never delete a failing test to make the suite green. A test failing on the old contract is information; flip it, do not remove it.

Skip this step for pure internal refactors where no caller-visible behavior changes. If the grep returns nothing, name the search terms in the commit body so reviewers can check the old-contract search.

Security-sensitive contract flips (authentication, authorization, cryptography, error disclosure, or secret handling) require security review before merge.

**Why:** Issue #2791 records this as the testing-rigor child of epic #2789. The failure shape is a false green suite: the implementation changes a contract while tests still encode the old one. ADR-077 records the trade-offs, prior art, and 90-day review checkpoint.

---

## Why This Matters

Bots and external reviewers (Copilot, CodeRabbit, Gemini) systematically catch the gaps that happy-path-only tests leave behind. Shipping with success-case tests alone wastes review cycles, exposes real defects to merge, and signals that the contributor has not internalized the failure modes of their own code.

The cost of writing pos+neg+edge tests up front is small. The cost of shipping a defective change, getting a review round, fixing it, re-running CI, and re-requesting review is roughly 10x larger. This rule pays for itself.

---

## Mutation Harness Safety: Bytecode Cache Invalidation

**Source**: Issue #3896. Observed in mutation testing of
`scripts/ci/parse_memory_validation_results.py`.

### The hazard

CPython validates `.pyc` caches against two fields: `st_mtime` (truncated to
whole seconds) and `st_size`. A same-length source mutation leaves `st_size`
unchanged. If the write lands in the same wall-clock second the cache was
created, `st_mtime` also matches and the interpreter reuses the stale cache.
The suite then runs the ORIGINAL bytecode, not the mutant, and the harness
reports a false verdict.

### The fix (mandatory for every mutation harness)

Before each subprocess invocation that runs under a mutated source file:

1. Purge the `__pycache__` directory:
   ```python
   import shutil, pathlib
   pycache = pathlib.Path(source_file).parent / "__pycache__"
   if pycache.exists():
       shutil.rmtree(pycache)
   ```

2. Set `PYTHONDONTWRITEBYTECODE=1` in the child environment to prevent the
   mutant's bytecode from contaminating the NEXT run's cache:
   ```python
   env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
   subprocess.run([sys.executable, "-m", "pytest", ...], env=env)
   ```

### Why the flag alone is insufficient

`PYTHONDONTWRITEBYTECODE=1` prevents writing new `.pyc` files but does NOT
prevent reading existing ones. If a `.pyc` with matching (mtime, size) headers
is already on disk, the interpreter uses it even with the flag set. The purge
is the load-bearing step; the flag prevents cross-mutant contamination.

### Verification

`tests/test_stale_bytecode_harness.py` contains four tests that reproduce the
defect (`test_before__stale_cache_hides_mutation`), document the insufficient
flag-only approach, and prove both fixes work independently and in combination.

---

## External Tool Fake Fidelity

**Source**: Issue #3885. Two instances of wrong exit-code contracts in git fakes:
`_fake_scan` in `tests/ci/test_taste_count_ratchet.py` and `_confirm_ignored`
tests in `tests/build_scripts/test_build_all.py`.

### The hazard

A monkeypatched fake that models an external binary's exit codes or output
shape is a claim about that binary's behavior. If the claim is wrong, every
test built on the fake passes while asserting a contract the binary does not
have. The production code then inherits the false contract. A wrong fake makes
tests MORE confident, not less.

### The rule

For any fake that encodes an external binary's exit codes, stdout shape, or
error semantics, add at least one test that runs the REAL binary and exercises
the discriminating rows the fake models.

- The real-binary test does not need 100% coverage of the fake. It needs to
  cover the exit codes and output shapes that the fake encodes.
- Write the fake FROM a measurement of the real binary, not from prose or
  documentation alone.
- When a binary is unavailable in CI (e.g., a proprietary tool), document the
  version and environment the fake was measured against in a comment.

### Pattern (from PR #3824)

`tests/ci/test_count_ratchet_against_real_git.py` is the exemplar. It runs
real `git` to exercise the exact bootstrap-detection paths that
`_fake_scan` in `test_taste_count_ratchet.py` models. A failing real-git test
catches a wrong fake at merge time rather than in production.
