# Skill description routing: shorter descriptions against main

Date: 2026-11-26. Harness: `evals/skill-description-routing/`. Claude Code CLI 2.1.332.

## Question

Do shorter skill descriptions route requests as well as the descriptions on main?
The run scored 103 of them. The change ships 97.

## Verdict

Yes, within the registered margins. All four gates pass on both models.
No changed skill fails the per-skill gate, so the eval reverts no description.
Two descriptions stay at main's text for other reasons. See "Coverage after rebase".

The gates test for harm. A pass means no harm was detected at this sample size.

## Method

Each run starts `claude --print` in a fresh workspace that holds every skill as a stub.
A stub keeps the real frontmatter of one arm and a one-line body. `Skill` is the only tool.

- `before` arm: frontmatter at origin/main 9fc6531958 (2026-11-26).
- `after` arm: frontmatter in the candidate tree.
- Queries: 340 over 121 skills. 98 `verbatim`, 121 `close`, 121 `paraphrase`.
- Models: `claude-sonnet-5-5` and `claude-opus-5-5`. One run per query per arm per model.
- Runs: 1,360 in total. 0 errors. 0 pairs excluded.
- `SLASH_COMMAND_TOOL_CHAR_BUDGET=80000`, so both arms show all 121 descriptions.
- `listed` reads 139 on every row. The workspace holds 121 stubs; the rest are CLI built-ins.

The `verbatim` queries quote the `before` descriptions. A separate agent wrote the other two kinds.
That agent saw only the `before` descriptions.

## Gates

The gates were written in a session note before any routing score was read.
The note was not committed, so this report is the first durable copy.

| Gate | Scope | Passes when |
|---|---|---|
| G1 | Per model | `after` correct rate minus `before` correct rate is -0.03 or better |
| G2 | Per model | `after` wrong rate minus `before` wrong rate is +0.03 or lower |
| G3 | Per model | `before` does not win the discordant pairs at p < 0.05, two-tailed sign test |
| G4 | Per skill | Summed over both models, `after` is correct on at most 1 fewer run than `before` |

One addendum came before the scores, after a probe showed the listing cap.
It moved the deciding run from the default cap to full visibility. See "The listing cap" below.

## Results

### All queries

| Model | n | Before correct | After correct | Delta correct | Delta wrong | Discordant, before wins | Discordant, after wins | Sign p | G1 | G2 | G3 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-sonnet-5-5 | 340 | 0.953 | 0.947 | -0.006 | +0.006 | 4 | 2 | 0.688 | pass | pass | pass |
| claude-opus-5-5 | 340 | 0.962 | 0.962 | 0.000 | 0.000 | 3 | 3 | 1.000 | pass | pass | pass |

### Outcome counts

| Model | Arm | Correct | Wrong | None |
|---|---|---|---|---|
| claude-sonnet-5-5 | before | 324 | 2 | 14 |
| claude-sonnet-5-5 | after | 322 | 4 | 14 |
| claude-opus-5-5 | before | 327 | 2 | 11 |
| claude-opus-5-5 | after | 327 | 2 | 11 |

### By query kind

| Model | Kind | n | Before correct | After correct | Before wins | After wins | Sign p |
|---|---|---|---|---|---|---|---|
| claude-sonnet-5-5 | verbatim | 98 | 0.898 | 0.898 | 0 | 0 | 1.000 |
| claude-sonnet-5-5 | close | 121 | 0.975 | 0.984 | 1 | 2 | 1.000 |
| claude-sonnet-5-5 | paraphrase | 121 | 0.975 | 0.950 | 3 | 0 | 0.250 |
| claude-opus-5-5 | verbatim | 98 | 0.908 | 0.929 | 0 | 2 | 0.500 |
| claude-opus-5-5 | close | 121 | 0.984 | 0.984 | 1 | 1 | 1.000 |
| claude-opus-5-5 | paraphrase | 121 | 0.984 | 0.967 | 2 | 0 | 0.500 |

Paraphrase queries lean toward `before` on both models: 5 losses and 0 wins in 242 pairs.
Pooled over both models that is p=0.063. It is the one pattern worth a second look.
Each kind still passes G1 and G2 alone.

### Other cuts

| Model | Cut | n | Before correct | After correct |
|---|---|---|---|---|
| claude-sonnet-5-5 | Changed skills only | 293 | 0.949 | 0.942 |
| claude-sonnet-5-5 | Unchanged skills only | 47 | 0.979 | 0.979 |
| claude-sonnet-5-5 | Without the 17 name-bearing verbatim queries | 323 | 0.966 | 0.960 |
| claude-opus-5-5 | Changed skills only | 293 | 0.956 | 0.956 |
| claude-opus-5-5 | Unchanged skills only | 47 | 1.000 | 1.000 |
| claude-opus-5-5 | Without the 17 name-bearing verbatim queries | 323 | 0.972 | 0.972 |

No unchanged skill changed outcome between the arms on either model.

### Every discordant pair

| Model | Query | Before | After |
|---|---|---|---|
| claude-sonnet-5-5 | `merge-resolver:paraphrase` | correct | wrong, picked `git-advanced-workflows` |
| claude-sonnet-5-5 | `review:paraphrase` | correct | wrong, picked the built-in `code-review` |
| claude-sonnet-5-5 | `reflect:paraphrase` | correct | none |
| claude-sonnet-5-5 | `panning-for-gold:close` | correct | none |
| claude-sonnet-5-5 | `ai-agents-failure-archaeology:close` | none | correct |
| claude-sonnet-5-5 | `validate-pr-description:close` | none | correct |
| claude-opus-5-5 | `autoplan:paraphrase` | correct | wrong, picked `build` |
| claude-opus-5-5 | `spec-generator:paraphrase` | correct | none |
| claude-opus-5-5 | `memory:close` | correct | none |
| claude-opus-5-5 | `ai-agents-failure-archaeology:close` | none | correct |
| claude-opus-5-5 | `github:verbatim` | wrong, picked `push-pr` | correct |
| claude-opus-5-5 | `prompt-engineer:verbatim` | none | correct |

### Per-skill gate, G4

| Net correct runs, after minus before, both models | Skills |
|---|---|
| +2 | 1 (`ai-agents-failure-archaeology`) |
| +1 | 3 (`github`, `prompt-engineer`, `validate-pr-description`) |
| 0 | 110 |
| -1 | 7 (`autoplan`, `memory`, `merge-resolver`, `panning-for-gold`, `reflect`, `review`, `spec-generator`) |
| -2 or worse | 0 |

No skill reaches the -2 line. No skill lost on both models.
Every changed skill has at least one scored query.

## Coverage after rebase

The run used a candidate with 103 changed descriptions.
Main changed the `skill-doctor` description during the run, in #7738.
The registered rule says such a skill is unproven, so `skill-doctor` keeps main's text.

`ship` also keeps main's text. Its scored description passed every gate.
The `skillforge` commit hook rejects any commit that touches the `ship` skill file.
The skill gained scripts in #7737 and has no `## Scripts` section.
That defect is on main and outside this change, so the `ship` file stays untouched.

Four more skills keep main's text to preserve contracts checked outside this eval.
`context-optimizer` and `skillforge` retain trigger ownership and redirect wording.
`memory-documentary` retains its source availability wording.
`pr-review` still routes through SkillForge for `which skill handles pull requests?`.

The change ships 97 descriptions. Each matches the text the eval scored.

## The listing cap

Claude Code caps the skill listing. Past the cap it drops descriptions and keeps names.
The cap comes from `skillListingBudgetFraction`, which defaults to 0.01 of the context window.
`SLASH_COMMAND_TOOL_CHAR_BUDGET` overrides it. `skillListingMaxDescChars` defaults to 1,536 per entry.

| Listing | Arm | Descriptions shown | First-turn prompt tokens |
|---|---|---|---|
| Default cap | before | 48 of 121 | 13,853 |
| Default cap | after | 71 of 121 | 14,101 |
| Budget 80,000 | before | 121 of 121 | 24,025 |
| Budget 80,000 | after | 121 of 121 | 19,331 |

Each row is one probe request on `claude-sonnet-5-5`, read from the gateway log.

Two things follow.

1. Under the default cap this change saves about no tokens. The listing fills to the cap either way.
   What changes is coverage: 23 more skills show a description.
2. With the cap lifted, the change saves 4,694 first-turn tokens in this workspace, about 20%.

A capped run cannot decide the question. The arms show different sets of descriptions.
A skill shown in neither arm would pass without its text being read.
So the deciding run lifted the cap, and both arms showed everything.

## Size

| Tree | Before, chars | After, chars |
|---|---|---|
| `.claude/skills`, 121 skills on 2026-11-27 | 51,188 | 37,100 |
| `src/copilot-cli/skills`, 103 skills on 2026-11-27 | not recorded | 31,362 |

`skill_description_budget.py` measured the base and final catalogs on 2026-11-27.
The ratchet drops to 37,200 and 31,400 chars.

## Deviations from the registered plan

- The default-cap Sonnet run was meant as a confirmatory run. It stopped at 202 of 680 rows.
  It was not resumed and its rows were not read. More runs spend the quota this change protects.
  So the net routing effect under the default cap is not measured here.
- The registered text asked for a Sonnet rerun only if G4 reverted a skill. G4 reverted none.
  Six candidate descriptions do not ship. Those skills keep main's text.
  The eval did not run the final mix as one catalog.

## Limits

- One run per query per arm per model. Twelve discordant pairs cannot separate signal from run noise.
- The power is low. The sign test would need a lopsided split to reject.
- Stub bodies remove the skill text. This measures routing, never what a skill does once loaded.
- The queries come from the `before` descriptions. They can miss requests no description names.
- The workspace holds only this repo's 121 skills. Plugin skills in a real session add competitors.
- The gates were registered in an uncommitted note. Nothing in the tree dates them.
- Codex, Copilot CLI, Cursor, Hermes and Muse were not run. They receive the same descriptions.

## Reproduce

```bash
uv run python evals/skill-description-routing/extract_arms.py <candidate-worktree> <out-dir> <before-ref>
uv run python evals/skill-description-routing/route_cli.py \
    --arms <out-dir>/arms.json --queries evals/skill-description-routing/queries.json \
    --out <out-dir>/sonnet.jsonl --models claude-sonnet-5-5 --workers 2 --char-budget 80000
python3 evals/skill-description-routing/score.py <out-dir> <out-dir>/sonnet.jsonl <out-dir>/opus.jsonl
```

The scored rows are in `evals/skill-description-routing/results/`.
