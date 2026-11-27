# A regex treated brackets as a character class and missed three of four dead checks

**Atomicity**: 90%
**Category**: Guard testing, regex
**Source**: Agent session sweep, sessions dated 2026-07. Sweep ids E098. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a passing guard test plus a claim of mutation kills prove the guard detects the defects it names?

## Conventional answer

A passing guard test and PR-body claims of mutation kills meant the guard detected the defects it named.

## First-principles position

The agent ran the guard's four DEAD_GREP_PATTERNS against the pre-fix template text. Only the `Status: pending` pattern matched. The three patterns with a doubled backslash before the bracket returned no match. The doubled backslash matches a literal backslash. The regex then treats the bracketed text as a character class instead of matching the full status. The guard test still passed.

## Evidence with limits

- The guard shipped in PR 4069 with four patterns. Run on the pre-fix template (2026-07-31), only the `Status: pending` pattern detected dead code.
- The three bracket patterns, such as `grep[^\n]*"Status: \\[ACKNOWLEDGED\\]`, returned "DETECTS DEAD CODE? False".
- The PR body had claimed mutation kills. The guard test passed.
- A later change (PR 4484) replaced the guard with one regex and pinned the old dead line in a test.
- Limits: One guard in one PR, probed on 2026-07-31 against one pre-fix file. The transcript does not show the PR's original mutation harness, so the PR-body kill claim is not independently tested.
- State on main at 1be533c496 (2026-11-26): fixed. Main replaced DEAD_GREP_PATTERNS with DEAD_STATUS_FIELD_RE (commit 03b67dc586). `test_dead_detector_flags_the_pattern_shipped_before_this_fix` asserts all three old alternatives match.

## Decision

Run a new guard's patterns against the known-bad text before trusting a green test. In raw strings, escape a literal bracket once.

## Related

- `.serena/memories/decision-doc-only-repairs-need-an-executable-guard.md`
- `.serena/memories/decision-calibrate-guards-on-the-whole-corpus.md`
- `.serena/memories/mutation-testing-false-green.md`
