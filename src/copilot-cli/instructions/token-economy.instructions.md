---
applyTo: .github/**,tests/**
---

# Token Economy

Rework is the expensive path: a wrong edit bills the edit, the review, the fix, and the re-review. Reading the governing rule and the exact span you are about to change costs less than any one of those four.

Never trade a gate, a test, or evidence in a report for tokens. That buys a cheap turn now and a full rework cycle later.

## Why this rule is scoped rather than always-on

It is deliberately not `paths: ["**"]`, for two reasons worth stating so nobody "fixes" the scope later.

This rule stays scoped because its guidance applies during repository changes.
Use progressive disclosure for guidance that does not apply to every file.

It also fails the [admission test in model-context-doctrine.md](https://github.com/rjmurillo/ai-agents/blob/main/.claude/skills/context-optimizer/references/model-context-doctrine.md#the-admission-test) for always-on content. The [rule-audit-procedure.md](https://github.com/rjmurillo/ai-agents/blob/main/.claude/skills/context-optimizer/references/rule-audit-procedure.md) defines the review discipline. The model
already knows that rework is expensive, and the tactics are retrievable on
demand from the LSP-first and voice rules, the programming-advisor,
memory-search, memory-gate, and GitHub URL intercept skills. What remains is
the framing above, which loads where it applies.

The globs are the gated trees that also exist in a consumer install: agent configuration, governance, workflows, and tests. Those are where a wrong edit costs a CI cycle. The upstream-only `build` and `scripts` trees are deliberately absent from the list, because a shipped rule scoped to a tree the consumer does not have is dead weight in every install. None of these globs matches every file of any language, so this rule adds nothing to the always-on language baselines.
