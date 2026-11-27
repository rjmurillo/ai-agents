# Skill description routing eval

This eval asks one question. Does a shorter skill `description:` still route a request to the same skill?

It compares two catalogs on the same queries, through the real Claude Code CLI.

1. **before**: the frontmatter of every skill at the base commit.
2. **after**: the frontmatter of every skill in the candidate tree.

## Method

Each run starts `claude --print` in a fresh workspace. The workspace holds every skill as a stub.
A stub keeps the real frontmatter of one arm and a one-line body. `Skill` is the only tool.
The arms differ only in frontmatter, so a routing change comes from the description.

The record keeps the first skill the model invoked. Each run gets one outcome:

| Outcome | Meaning |
|---|---|
| `correct` | The first `Skill` call names the target skill |
| `wrong` | The first `Skill` call names another skill |
| `none` | The model made no `Skill` call |

## Queries

`queries.json` holds 340 queries over 121 skills. Each query names its target skill and a kind.

| Kind | Count | Source |
|---|---|---|
| `verbatim` | 98 | The first trigger phrase quoted in the `before` description, extracted by script |
| `close` | 121 | Written by a separate agent that saw only `before` descriptions |
| `paraphrase` | 121 | Written by the same agent as a reworded request |

The query author never saw the candidate text. That keeps the queries from favoring the `after` arm.
The `verbatim` kind favors the `before` arm by design, since it quotes that arm.

## Files

| File | Role |
|---|---|
| `extract_arms.py` | Reads both trees and writes `arms.json`, `changed.json` and `before-descriptions.json` |
| `route_cli.py` | Runs every query in every arm and appends one row per run to a JSONL file |
| `score.py` | Scores one or more result files against gates G1 to G4 |
| `queries.json` | The 340 queries |
| `changed.json` | The skills whose description differs from the base and ships in the change |
| `results/` | One JSONL file per model for the deciding run |

`arms.json` is not committed. `extract_arms.py` rebuilds it from the two trees.

## Run it

Run from a checkout that holds `scripts/eval`. Keep to two workers on a shared subscription.

```bash
uv run python evals/skill-description-routing/extract_arms.py <candidate-worktree> <out-dir> <before-ref>
cp evals/skill-description-routing/queries.json <out-dir>/
uv run python evals/skill-description-routing/route_cli.py \
    --arms <out-dir>/arms.json --queries <out-dir>/queries.json \
    --out <out-dir>/results-sonnet.jsonl --models claude-sonnet-5-5 --workers 2 --char-budget 80000
uv run python evals/skill-description-routing/route_cli.py \
    --arms <out-dir>/arms.json --queries <out-dir>/queries.json \
    --out <out-dir>/results-opus.jsonl --models claude-opus-5-5 --workers 2 --char-budget 80000
python3 evals/skill-description-routing/score.py <out-dir> <out-dir>/results-sonnet.jsonl <out-dir>/results-opus.jsonl
```

`score.py` reads `queries.json` and `changed.json` from `<out-dir>`. The extractor writes only `changed.json`, so copy the queries in.
Run the models one at a time. Two runs at once double the worker count.

A run resumes. A row already in the output file is skipped unless it errored.

## The listing cap

Claude Code caps the skill listing it sends to the model. Past the cap it drops descriptions and keeps names.
`--char-budget` sets `SLASH_COMMAND_TOOL_CHAR_BUDGET` for the run.
A value of 80000 shows all 121 descriptions in both arms.

Without it, the arms show different numbers of descriptions. A score then mixes three groups of skills.
Some show in both arms, some only in `after`, and some in neither.
A skill shown in neither arm passes without its description being read, so a capped run proves nothing about that skill.

Every row records `listed`, the number of catalog entries the CLI reported. It must be constant across a run.

## Gates

The gates were written down before any routing score was read. They sat in a session note, not in a commit.
The report under `evals/reports/` states them again with the results.

| Gate | Scope | Passes when |
|---|---|---|
| G1 | Per model | `after` correct rate minus `before` correct rate is -0.03 or better |
| G2 | Per model | `after` wrong rate minus `before` wrong rate is +0.03 or lower |
| G3 | Per model | `before` does not win the discordant pairs at p < 0.05, two-tailed sign test |
| G4 | Per skill | Summed over both models, `after` is correct on at most 1 fewer run than `before` |

`score.py` decides G1 and G2 on outcome counts, so a change that lands exactly on the margin passes.

These gates are this eval's own standard. They are not the ADR-057 acceptance gate.
That gate allows no score drop and counts only scenarios that pass every base run.
This eval ran each query once per arm, so it cannot show a stable baseline.

A skill that fails G4 keeps its base description. If G4 reverts any skill, the final catalog reruns on one model.
That rerun must pass G1 and G2.

An errored run reruns once. A pair that still has an error is dropped and counted in the report.
A skill with no scored query does not ship a changed description.

## Limits

- One run per query per arm per model. A single run cannot separate a real change from run noise.
- The stub body removes the skill text, so this measures routing only, never skill behavior.
- The gates test for harm. A pass means no harm was detected at this sample size.
- Queries were written from the `before` descriptions, so they may miss requests those descriptions never named.
