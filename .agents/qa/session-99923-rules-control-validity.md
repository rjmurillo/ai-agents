---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99923-2dd747176-rules-control-validity.json
qaCommit: 9c31b9104498b301df5b7f52aa7457f96953f095
---

# QA Report: testing.md control-validity rule (issue #5187)

- Issue: #5187
- Branch: `claude/issue-5187-control-validity`
- Session log: `.agents/sessions/2026-08-21-session-99923-2dd747176-rules-control-validity.json`
- QA commit: `9c31b9104498b301df5b7f52aa7457f96953f095`

## Verdict

PASS.

## Scope under test

One item added to `.claude/rules/testing.md` (SHOULD 17) and the two
instruction mirrors regenerated from it. No code, no test, no workflow.

## What "tested" means for a rule change

There is no runtime behavior here, so the checkable properties are the ones the
repository already gates. Each was run rather than assumed:

| Property | Command | Result |
|---|---|---|
| Mirrors match the rule, so no tree is stale | `build/scripts/build_all.py --check` | no staleness after commit |
| Always-on instruction budget is untouched | `scripts/validation/instruction_budget.py` | PASS, all four language rows |
| Repository-wide validation | `scripts/validation/pre_pr.py` | all validations passed |
| Session log is well formed and its SHA reachable | `scripts/validate_session_json.py` | PASS |

The budget check is the one that could have failed. The `.py` always-on row had
764 bytes of headroom, so adding this item to an always-on rule such as
`code-quality.md` would have broken every contributor's push. `testing.md` is
path-scoped to test trees, so its bytes never enter that budget. Verified by
reading the generated frontmatter rather than assuming the scope survived
generation: both mirrors carry the test-tree `applyTo`, not `**`.

## What is deliberately not claimed

The rule is guidance for authors. Nothing enforces it, and this report does not
claim otherwise. `.claude/rules/` is the binding surface across Claude, Codex,
and Copilot per `knowledge-persistence.md`, which is why the item lives there
rather than in a Serena memory, but binding means "every harness reads it", not
"a gate rejects a violation".

## Evidence for the rule's own claim

The item asserts a failure mode measured twice in PR #5176, and the rule text
carries both measurements inline: the exact expressions, the tier the case ran,
and what each edit did or failed to do. That is deliberate, so the binding claim
stands on its own and does not depend on a file the reader may not have.

The fuller write-ups live on PR #5176's branch, in its QA companion and its
retrospective. Those are named here as *contents of that PR*, reachable through
it, and not as paths resolvable from this branch, because they are not: if this
PR merges first they do not exist on `main` yet. Copilot flagged the earlier
wording for exactly that reason. `.claude/rules/canonical-source-mirror.md`
covers the general case under "True when you wrote it is not true at merge",
and the remedy it names is the one applied here: keep the load-bearing evidence
on the branch that carries the claim, and reference cross-branch material by PR
rather than by path.
