# The Retrieval Instruction Beats The Docs File Map

**Atomicity**: 90%
**Category**: context engineering, first-principles contradiction
**Source**: 2026-11-25 docs-index probe session on branch `t3/3e40eb6c`.
Repo at `ffc759356b` (2026-11-25). Model `claude-sonnet-5-5` through the local
hub, tools Read, Glob, Grep. The probe and scorer were written by the same agent.

## The rule

On this fixture, the line that tells the model to retrieve did the work. The
map alone scored 22/30; the instruction alone scored 30/30, the same as map
plus instruction. Skip the map for this fixture. This is not a general cost or
accuracy claim: one model, one synthetic fixture.

## Question

Does a compressed docs file map in AGENTS.md (the Vercel pattern) make an
agent answer from the project's docs instead of from pretraining?

## Conventional answer

The Vercel AGENTS.md study reports 100% pass for a passive compressed docs
index, versus 79% for skills with instructions and 53% baseline. Our own memory
`memory/passive-context-vs-skills-vercel-research.md` records that result and
lists the compressed format as an opportunity. Most skills and guides say to
add a file map.

## First-principles position

Accuracy tracks one thing: whether the model looks anything up at all. The map
helps only as a hint that docs exist. One plain instruction to prefer retrieval
gives that hint more strongly, so it wins alone.

## Evidence

Probe 1 used fictional docs with no pretraining conflict. All three arms
(none, pointer, index) scored 30/30. Grep found every answer on the first call.
The index added about 600 input tokens per turn.

Probe 2 used fictional `requests` 3 docs that contradict the real API. The
prompts never mention docs. The workspace pins `requests==3.0.0`.

| Arm | CLAUDE.md content | Correct | Looked up | Mean input tokens |
|---|---|---|---|---|
| none | no file | 0/30 | 0/30 | 7,931 |
| pointer | "requests docs live in ./docs." | 11/30 | 12/30 | 12,184 |
| map | index header plus dir:{files} lines | 22/30 | 22/30 | 15,433 |
| instr | pointer plus the IMPORTANT retrieval line | 30/30 | 30/30 | 18,668 |
| index | full Vercel block (map plus IMPORTANT) | 30/30 | 30/30 | 18,023 |

The token gap comes mostly from tool round trips, not from the block.

Limits: one model, one synthetic fixture, 6 questions repeated 5 times, so not
30 independent trials. The block came from an inline function, not the
shelved `index_docs_tree.py` generator.

## Decision

The docs-index generator for `context-optimizer` was not shipped. Ship
guidance should lead with the retrieval instruction. This probe does not show
the map hurts: both instruction arms hit the 30/30 ceiling, and the full index
used fewer mean input tokens (18,023) than the instruction arm (18,668). It
shows only that the map added no accuracy here. Harder questions may separate
the two arms.

## Why this was nearly lost

The finding sat only in gitignored scratch. The task ended at a "do not ship"
verdict, so nothing required saving it. `builder-ethos.md` now makes a eureka a
required deliverable.
