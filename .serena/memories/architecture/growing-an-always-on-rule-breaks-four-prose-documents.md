# Growing an Always-On Rule Invalidates Measured Figures in Four Documents

**Atomicity**: 92%
**Category**: repository quirk, pre-push failure
**Source**: 2026-08-07 fleet session. Adding one section to `.claude/rules/voice.md`
took it from 17,527 to 19,072 bytes and failed the pre-push test run. Branch
`docs/walk-the-gate`, commits `81809daea` and `02cda6d85`.

## The failure

Edit any rule whose generated `applyTo` resolves to `**`, then push. Both of
these files fail, always, never one alone:

- `tests/validation/test_always_on_corpus_claims.py`
- `tests/validation/test_audit_procedure_claims.py`

Measured 2026-08-07 by appending bytes to each of the eight always-on rules in
turn, regenerating, and running both files in one pytest invocation:

| Edit | corpus_claims | audit_claims | total |
|---|---|---|---|
| `builder-ethos.md` +1 | 8 | 2 | 10 |
| `builder-ethos.md` +400 | 9 | 2 | 11 |
| any non-quoted rule +400 | 9 | 2 | 11 |
| `code-quality.md` +400 | 9 | 3 | 12 |
| `voice.md` +1,545 | 10 | 3 | 13 |

So the range is 10 to 13. The two variables are edit size, which decides
whether a rounded multiplier moves, and whether the audit procedure quotes the
rule by name, which `voice.md` and `code-quality.md` are and the other six are
not. The audit file contributes at least 2 either way; it is never the
discriminator.

Do not treat any single count as the signature. The count tracks how many
claims the corpus holds, so it grows whenever someone adds an assertion: the
same 1,545-byte `voice.md` edit failed 11 when first measured and fails 13
today against the same rule and the same byte count. Treat the two file names
as the signature.

The assertions read like this:

```
doctrine states a `.py` edit sees 11 files / 96784 bytes; measured 11 / 98329
audit procedure quotes voice.md at 17527 bytes; the file is 19072
```

Nothing in the failure names the files you have to edit, and there is no
regenerator. The figures are prose, hand-maintained, and a test is the only
thing keeping them honest.

## The four documents

| Document | What it quotes |
|---|---|
| `.claude/skills/context-optimizer/references/model-context-doctrine.md` | source basis, mirror always-on, per-language totals, both 8KB multipliers, the largest rule |
| `.claude/skills/context-optimizer/references/rule-audit-procedure.md` | the size of the largest rule |
| `.claude/rules/canonical-source-mirror.md` | source basis and mirror always-on, as evidence for the source-to-mirror delta |
| `.serena/memories/architecture/always-on-membership-lives-in-the-mirror.md` | the same two totals |

The first two also have generated copies under
`src/copilot-cli/skills/context-optimizer/references/`. Do not hand-edit those.
Run `uv run --frozen python build/scripts/build_all.py` and they follow.

## What moves and what does not

Every total moves by exactly the byte delta of your edit. In the 2026-08-06
case that was 1,545 bytes: source basis 71,168 to 72,713, mirror always-on
71,033 to 72,578, a Python edit 96,784 to 98,329.

The **135-byte gap between the source tree and the mirror tree survives a body
edit but is not a repository constant.** `generate_rules.py` rewrites
frontmatter and leaves the body alone, so the gap is a per-rule sum over the
always-on set, not a fixed number: 19 bytes each for six rules that declare
`priority:`, 17 for `knowledge-persistence`, which declares `priority:` too but
also rewrites `paths:`, and 4 for `code-quality`, which uses `alwaysApply:`
instead. Seven of the eight declare `priority:`; only six of them cost 19.

A ninth always-on rule moves the gap only if its frontmatter carries a key the
generator rewrites. Measured by adding a probe rule and re-reading the gap:
`applyTo: '**'` plus `priority: critical` costs 19, `alwaysApply: true` costs
4, and a bare `applyTo: '**'` with no other key costs 0. So membership can
change, in either direction, without moving the gap at all, and two members can
swap with no net effect. If the gap changes and you did not add, drop, or
reshape a member, you changed frontmatter, and that is a different problem.

Two derived multipliers move independently and are easy to miss because they
are rounded to one decimal. The corpus against the 8KB threshold went 8.7x to
8.9x, and a Python edit went 11.8x to 12.0x. The second one is quoted in prose
as `11.8x` in the same sentence as the first, so a substitution keyed on the
number alone catches one and skips the other.

## Recipe

1. Make the rule edit and regenerate: `uv run --frozen python build/scripts/generate_rules.py`.
2. Run the two test files directly rather than waiting for pre-push. They take
   about one second, against roughly eleven minutes for the suite that contains
   them.
3. Read the assertion messages. Each one states the claimed value and the
   measured value, so the substitution list writes itself.
4. Apply the substitutions to the four documents. The figures carry thousands
   separators in prose (`71,168`) and none in the assertion message (`71168`),
   so key your search on the comma form.
5. Re-run the two files, fix the multipliers the numeric substitution missed,
   then `build_all.py` for the generated copies.

## Why this costs more than it looks

The commit-file-count hook caps a commit at five authored files. Only the
memory under `.serena/memories/` is exempt: the exemption list covers session
episodes, MCP config, agent catalog, and every file under
`.serena/memories/**/*.md`. The generated instruction mirrors and the generated
`src/copilot-cli/skills/` copies are **not** exempt.

Counted with the hook's own tables, a full refresh alongside the rule edit that
triggered it puts ten files against the cap of five: the rule and its two
mirrors, three authored prose documents, and four generated companions. Split
it into three commits or fewer files each. The hook skips merge commits
(`skip: [merge]` in `lefthook.yml`), so a refresh that lands inside a merge
resolution is not blocked.

## Related

- `.serena/memories/decision-a-whole-corpus-gate-cannot-be-path-filtered.md`
  covers why the CI job that runs these tests cannot be path-filtered. Same
  corpus, different failure.
- `.serena/memories/architecture/always-on-membership-lives-in-the-mirror.md`
  is both a consumer of these figures and the answer to which rules count.
