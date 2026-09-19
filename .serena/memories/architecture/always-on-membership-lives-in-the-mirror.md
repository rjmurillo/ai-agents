# Always-on membership lives in the mirror

This repository usually treats the canonical source as authoritative. Generated
mirrors are not authoritative for content. Always-on membership is the exception.

## Decision

A rule loads on every Copilot turn when its generated `applyTo` resolves to
`**`. Check the generated instruction tree for that question.

The supported source declaration uses `paths:`. The generator transforms that
scope for each consumer. It skips a rule when all of its paths are internal to
the repository and the destination does not retain those paths.

The generated trees currently preserve this membership:

| Tree | Consumer | Always-on membership |
|---|---|---|
| `.github/instructions` | Copilot in this repository | `builder-ethos`, `universal`, `voice` |
| `src/copilot-cli/instructions` | the shipped plugin | `builder-ethos`, `universal`, `voice` |

Do not infer membership from source grep. Parse generated frontmatter with
`yaml.safe_load`. Inline scopes and block-list scopes express the same contract.

## Why this matters

The source and the mirror use different scope keys. `paths:` controls Claude
rules. `applyTo:` controls the generated Copilot mirror. `globs:` remains
literal and does not become `applyTo:`. `alwaysApply:` is removed by the
generator. These forms do not answer the same question.

Issue #4317 fixed the internal-only fallback. PR #4426 made the generator skip
the rule instead of universalizing it in the plugin. Issue #5492 narrowed
`knowledge-persistence` to the trees it governs.

## Where this is enforced

`tests/validation/test_always_on_corpus_claims.py` compares the named membership
with the generated mirror. Update the membership table when scope changes.

## Related

- `.claude/rules/canonical-source-mirror.md`, section "The one place the mirror outranks the source: always-on membership".
- `.claude/skills/context-optimizer/references/model-context-doctrine.md`, which explains the activation policy.
- `.agents/architecture/ADR-088-progressive-disclosure-book-rules.md`, which records the progressive-disclosure decision.
