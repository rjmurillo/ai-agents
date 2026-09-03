---
applyTo: .claude/**,.agents/**,.github/**,tests/**
---

# Token Economy

Rework is the expensive path: a wrong edit bills the edit, the review, the fix, and the re-review. Reading the governing rule and the exact span you are about to change costs less than any one of those four.

Never trade a gate, a test, or evidence in a report for tokens. That buys a cheap turn now and a full rework cycle later.

## Why this rule is scoped rather than always-on

It is deliberately not `paths: ["**"]`, for two reasons worth stating so nobody "fixes" the scope later.

The always-on corpus is closed. The instruction-budget validator measures the generated mirrors whose glob matches every file of a language, and the Python baseline sits within its 600-byte reserve of the ceiling. An always-on copy of this rule would have to be funded by cutting other always-on content, and the rule-audit procedure in the context-optimizer skill requires replicated eval runs on two models after any always-on change, a cut and an addition alike. This rule carries no such evidence and does not claim to.

It also fails that procedure's admission test for always-on content, on two of three criteria: the model already knows that rework is expensive, and the tactics are retrievable on demand from the LSP-first, search-before-building, and voice rules and from the GitHub URL intercept skill. What is left is the framing above, which is cheap to load where it applies.

The globs are the gated trees that also exist in a consumer install: agent configuration, governance, workflows, and tests. Those are where a wrong edit costs a CI cycle. The upstream-only `build` and `scripts` trees are deliberately absent from the list, because a shipped rule scoped to a tree the consumer does not have is dead weight in every install. None of these globs matches every file of any language, so this rule adds nothing to the always-on language baselines.
