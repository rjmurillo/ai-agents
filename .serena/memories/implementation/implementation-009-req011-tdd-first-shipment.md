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

1. **Structural verification beats fixture-stubbing for bash hooks**. Phase 5c is bash with subprocess calls; faithful integration tests need to stub `gh` and `python3` on PATH, which is fragile across CI environments. The `test_drift_check.py` pattern (string-presence and `bash -n` syntax) is sufficient for bash hooks that are thin delegates: each AC pins a single token or regex shape in the hook. 11 tests covered all four ACs without subprocess plumbing.
2. **Scoping the grep to a single phase block** with a regex like `# Phase 5c.*?(?=# Phase \d|\Z)` prevents Phase 5b assertions from polluting Phase 5c assertions. Cheaper than parsing.
3. **One commit per TDD phase** keeps the trace reviewable. Reviewer can `git show <red-sha>` and see the failing contract, then `git show <green-sha>` and see only the implementation. Bundling red+green into one commit hides the contract.

## Trap: literal strings in source comments collide with test greps

The Phase 5c block documents its warn-only property with the comment `# Warn-only. Never calls record_fail.` The test `test_phase_5c_warn_only_never_fails` originally asserted `"record_fail" not in block`. The comment's literal text triggered a false positive: the hook documents what it does NOT do, but the test treated the documentation as a call site.

**Fix**: strip comment lines (`line.lstrip().startswith("#")`) before grepping for call sites. The test now asserts the absence of `record_fail` in code lines only.

**Why**: a static-string presence test cannot distinguish a comment from a call. Either (a) write the comment without the literal token (less faithful documentation) or (b) make the test aware of comments (more faithful). (b) is correct.

**Generalization**: any test that uses `not in block` on a hook or shell script must strip comments first if the absent token is documented in a comment.

## How to apply

- When pinning the absence of a function call in a bash/Python file, filter comment lines before assertion.
- When pinning the presence of a call, do not filter; presence is presence either way.
- When the scope is a single section of a larger file, use a regex with a non-greedy match and a lookahead to the next section header.

## References

- PR for REQ-011: opens `feat/issue-1991-req-011-m5-bot-cascade-pre-push` -> `main`
- Tests: `tests/hooks/test_bot_cascade_warning.py`
- Hook: `.githooks/pre-push` Phase 5c block
- Prior structural pattern: `tests/hooks/test_drift_check.py` (Phase 5b)
- Build command: `.claude/commands/build.md` (TDD-first sequence)
