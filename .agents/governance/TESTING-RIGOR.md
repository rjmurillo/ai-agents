# Testing Rigor

**Created**: 2026-04-26
**Source**: PR #1756 review (lessons from rubric fix in #1755)
**Status**: BLOCKING for code changes
**Related**: `.agents/governance/TESTING-ANTI-PATTERNS.md`, `AGENTS.md`

---

## Principle

**Every new function MUST have positive AND negative tests.** Happy path alone is insufficient. Don't ship "the change works" with only success-case tests; bots and reviewers will catch what tests missed (whitespace, type validation, error paths, conditional branches).

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

## Why This Matters

Bots and external reviewers (Copilot, CodeRabbit, Gemini) systematically catch the gaps that happy-path-only tests leave behind. Shipping with success-case tests alone wastes review cycles, exposes real defects to merge, and signals that the contributor has not internalized the failure modes of their own code.

The cost of writing pos+neg+edge tests up front is small. The cost of shipping a defective change, getting a review round, fixing it, re-running CI, and re-requesting review is roughly 10x larger. This rule pays for itself.
