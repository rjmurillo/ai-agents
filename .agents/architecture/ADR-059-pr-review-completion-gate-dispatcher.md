# ADR-059: /pr-review Completion Gate Dispatcher and pass_when DSL

## Status

Proposed

## Date

2026-05-08

## Context

PR #1887 introduced a /pr-review completion gate as a narrative checklist:
the agent reviewed the PR, then claimed verdicts like "0 unresolved threads"
inline. The retrospective at
`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` records four
times the gate was satisfied while review threads were unresolved. The
failure mode is named "Reporting-Without-Acting Anti-Pattern" (Layer 6 in
the retrospective): an audit output that asserts state instead of measuring
it produces the same wrong answer on retry.

## Decision

1. Replace the narrative completion gate with a dispatcher.
   `.claude/skills/github/scripts/pr/run_completion_gate.py` reads
   `pr-review-config.yaml`, runs each criterion's command, parses its
   stdout as JSON, evaluates `pass_when`, and prints a per-criterion table.
   Exit 0 if all pass, 1 if any fail, 2 on usage.

2. Define a small `pass_when` DSL: dotted-path resolution, literals
   (integers, `true`, `false`, `null`, double-quoted strings), `==`/`!=`
   comparisons, `AND`/`OR` composition (left-to-right, no parentheses).
   AND/OR evaluate left-to-right with equal precedence; atoms are pure
   lookups with no side effects, so the evaluation order does not affect
   correctness.

3. Provide `pass_when_python` as an escape hatch. Evaluated with `eval`
   against an empty `__builtins__` dict. NOT a sandbox (Python class
   hierarchy remains reachable). Acceptable because the config file is
   repo-controlled and `--config` is locked to the repo root.

4. Fail closed by default. `fail_open` defaults to false.

5. Lock `--config` to the repo root via `validate_safe_path` (CWE-22).

6. Make `fetched_pages_complete` a Published Language across verifiers.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep narrative gate | No new code | Same failure mode | Root cause unaddressed |
| Policy engine (OPA) | Mature | Heavy dependency | Overkill for 3 criteria |
| Python-only (no DSL) | One mechanism | Every criterion is eval | DSL keeps common case safe |
| DSL-only (no eval) | No eval surface | Limits future logic | Escape hatch is rare |

## Consequences

### Positive

- Verdicts are functions of verifier output, not agent narration
- Pagination cliffs surface via `fetched_pages_complete`
- New criteria are config-only changes

### Negative

- DSL is not parens-aware
- `pass_when_python` is an eval surface
- Adding operators requires parser changes
- **PR-branch trust boundary**: when `/pr-review` runs after
  `gh pr checkout`, the config it reads is the PR branch's copy. A
  malicious PR can change `completion_criteria.command` or
  `pass_when_python` and the dispatcher will execute it. This is the
  same trust a reviewer extends by running tests/linters on a PR
  branch, but more direct. Mitigations documented in the dispatcher
  docstring and the `/pr-review` workflow; structural hardening
  (loading config from `main` or refusing to run on divergence) is
  deferred as follow-up. Surfaced by CodeRabbit review on PR #1898.

## References

- `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`
- `.claude/skills/github/scripts/pr/run_completion_gate.py`
- PR #1898
