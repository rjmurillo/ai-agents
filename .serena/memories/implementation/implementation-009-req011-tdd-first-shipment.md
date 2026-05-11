---
name: implementation-009-req011-tdd-first-shipment
description: TDD-first shipment of REQ-011 Phase 5c bot-cascade warning; structural verification pattern; comment-vs-call distinction
type: implementation
confidence: HIGH
tier: 2
related:
  - REQ-011
  - DESIGN-011
  - TASK-011
  - implementation-008-spec-schema-validation
  - retrospective/2026-05-10-pr-1989-recursive-failure
created: 2026-05-10
---

# REQ-011 TDD-First Shipment: Lessons

REQ-011 (M5 bot-cascade pre-push warning) shipped as the first end-to-end demonstration of the TDD-first sequence codified in `.claude/commands/build.md`. Sequence on the branch: docs(spec) -> test(hooks) RED -> feat(hooks) GREEN. Each step landed as a separate commit, traceable from the PR.

## What worked

1. **Structural verification beats fixture-stubbing for bash hooks**. Phase 5c is bash with subprocess calls; faithful integration tests need to stub `gh` and `python3` on PATH, which is fragile across CI environments. The `test_drift_check.py` pattern (string-presence and `bash -n` syntax) is sufficient for bash hooks that are thin delegates: each AC pins a single token or regex shape in the hook. The suite scopes every assertion to the Phase 5c block via a regex with a lookahead to the next phase header so Phase 5b assertions cannot pollute Phase 5c assertions, and adds one test that asserts each of `record_skip`/`record_warn`/`record_pass` has at least one call site (REQ-011-05). The suite covers all four ACs without subprocess plumbing; exact test count moves as the contract evolves.
2. **Scoping the grep to a single phase block** with a regex like `# Phase 5c.*?(?=# Phase \d|\Z)` prevents Phase 5b assertions from polluting Phase 5c assertions. Cheaper than parsing.
3. **One commit per TDD phase** keeps the trace reviewable. Reviewer can `git show <red-sha>` and see the failing contract, then `git show <green-sha>` and see only the implementation. Bundling red+green into one commit hides the contract.

## Trap: literal strings in source comments collide with test greps

The Phase 5c block documents its warn-only property with the comment `# Warn-only. Never calls record_fail.` The test `test_phase_5c_warn_only_never_fails` originally asserted `"record_fail" not in block`. The comment's literal text triggered a false positive: the hook documents what it does NOT do, but the test treated the documentation as a call site.

**Fix**: strip comment lines (`line.lstrip().startswith("#")`) before grepping for call sites. The test now asserts the absence of `record_fail` in code lines only.

**Why**: a static-string presence test cannot distinguish a comment from a call. Either (a) write the comment without the literal token (less faithful documentation) or (b) make the test aware of comments (more faithful). (b) is correct.

**Generalization**: any test that uses `not in block` on a hook or shell script must strip comments first if the absent token is documented in a comment.

## Trap: backticks inside `bash -c "..."` embedded Python

The hook passes inline Python via `"${PYTHON_CMD[@]}" -c "..."` using a double-quoted bash string. Inside a double-quoted bash string, backticks are command substitution. A backtick in a Python comment (`# pass an \`isinstance(x, int)\` check`) made bash try to execute `isinstance(x, int)` at runtime: `syntax error near unexpected token \`x,'`.

`bash -n` does NOT catch this: static syntax checking does not expand command substitutions. Only running the hook surfaces it, which is exactly what the TASK-011-04 self-apply gate did.

**Rule**: any Python (or other) code embedded in a `bash -c "..."` double-quoted string MUST NOT contain backticks, `$(...)`, or unescaped `$`. Prefer single-quoted heredocs (`<<'PY'`) for embedded code where possible; when the call site forces double quotes, scrub the embedded code of shell metacharacters and say so in a comment.

## Structural-test lenience: match call sites, not text

Structural tests that grep the whole block for a string (`/reviews`, `Bot`, `|| true`) can pass vacuously because the same string appears in comments. Three failure shapes seen on PR #2011:

- `assert "/reviews" in block` passed because the Phase 5c header comment mentions `/reviews`.
- `assert "Bot" in block` passed because the phase title is "Bot-cascade".
- `assert "|| true" not in line for review-lines` was bypassed because a multiline `gh api` continuation put `gh api` and `reviews` on different lines, so the filtered line list was empty.

**Rule**: when pinning a *behavior* (a command invocation, a jq filter, an absent anti-pattern), strip comment lines first (`line.lstrip().startswith("#")`) and assert against the literal expression on a code line. Share a `_code_lines()` helper. When pinning *presence* of documentation text, the whole-block grep is fine.

## How to apply

- When pinning the absence of a function call in a bash/Python file, filter comment lines before assertion.
- When pinning the presence of a behavior (call, filter, flag), match the literal expression on a non-comment line, not a bare substring anywhere.
- When pinning the presence of documentation text, do not filter.
- When the scope is a single section of a larger file, use a regex with a non-greedy match and a lookahead to the next section header.
- Never put backticks or `$(...)` in code embedded inside a `bash -c "..."` double-quoted string. `bash -n` will not catch the bug; only a runtime invocation (or the self-apply gate) will.

## References

- PR for REQ-011: opens `feat/issue-1991-req-011-m5-bot-cascade-pre-push` -> `main`
- Tests: `tests/hooks/test_bot_cascade_warning.py`
- Hook: `.githooks/pre-push` Phase 5c block
- Prior structural pattern: `tests/hooks/test_drift_check.py` (Phase 5b)
- Build command: `.claude/commands/build.md` (TDD-first sequence)
