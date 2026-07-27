# Decision: validate trigger phrases against real prompts, not authored ones

## Question

How do we know a skill's trigger phrases are the words a user would actually
type, rather than words we invented while writing the skill?

## Conventional answer

The repo's own `.agents/governance/skill-description-trigger-standard.md` says
to include "trigger keywords (how users will search)" and provides a formula
plus a review checklist. Every one of those checks scores a phrase the author
wrote against a rule the author wrote. Nothing in the pipeline consults a
prompt the author did not write.

## First-principles position

That is a closed loop, and a closed loop cannot measure whether a phrase is
realistic. The wiki concept `Skill Triggering Failure Modes` records the
collapse: a practitioner's skill-activation classifier scored 93 percent
precision and recall on 40 prompts he wrote, then 27 percent precision on 86
prompts mined from his own transcripts. Same classifier, same author. The only
variable was who wrote the prompts.

## Evidence

Built `scripts/eval/eval-trigger-phrase-realism.py`, which mines the local
Claude Code transcript store and matches on word boundaries. Against 203 unique
operator-typed prompts extracted from 480 transcripts:

- documented in a `## Triggers` section: 17 of 422 phrases ever said (4.0%)
- promoted into a description: 8 of 226 phrases ever said (3.5%)

Treat those percentages as a snapshot, not a constant. They move with corpus
scope, time window, and parser version, and a single-project scope moved the
promoted figure between 0 and 12.9 percent. The durable finding is the shape,
the large majority of documented phrases have never been typed, not the digits.

**The first version of this measurement was wrong twice over, and an adversarial
review on a second model caught both.** The corpus counted 640 prompts, but 437
of them (68.3%) were `isSidechain` entries, prompts an agent wrote for a
subagent. They carry the `user` role but nobody typed them, so the eval designed
to detect a closed loop was itself running inside one. Separately the parser read
only Markdown table rows, while the standard permits a trigger "table or list",
so it saw 212 of 422 documented phrases. Both defects are fixed and each now
carries a negative-control test.

The phrases that do occur are conversational and lifecycle-shaped: `complete
session`, `create session log`, `start new session`, `your call`, `handle it`,
`do it`, `security review`, `threat model`. The ones that never occur are
formal technical constructions.

Read this as evidence about provenance, not about the router. This is a
lexical-provenance diagnostic: it never executes the router and reports no
precision, recall, or activation rate. A phrase nobody typed verbatim can still
route correctly under semantic matching, so this does not show the
practitioner's collapse reproduces here. What it establishes is narrower, that
the phrases were authored rather than observed, which is the precondition his
classifier failed under.

## Decision

Added an Independent-Distribution Validation section to
`.agents/governance/skill-description-trigger-standard.md` (Part 4) with the
measured table and two rules: prefer an observed phrase to an invented one, and
never benchmark trigger phrases on prompts you wrote. Added a checklist line.
The eval refuses to fall back to authored prompts and exits 3 instead, because
that substitution would defeat its purpose.

## The measurement lesson that generalises

I got my own measurement wrong twice, and caught both only by disbelieving the
number rather than by any check.

1. A 600-character cap in the first extractor silently dropped roughly 95
   percent of the corpus, yielding 66 turns from 480 transcript files. The tell
   was that 66 from 480 is implausible. Real prompt length is p50 1,820 chars,
   p90 8,175, max 107,478.
2. The first scorer used bare substring matching and reported `analyze` at 60
   occurrences. Every one was inside ordinary prose. This is precisely the
   word-boundary failure the wiki documents: every incorrect hard block in the
   practitioner's hook traced to a pattern matching inside a word. Fixed with
   `(?<!\w)...(?!\w)`.

Both errors produced a number that looked reportable. Neither was caught by a
test, a lint, or a reviewer. The general rule: when a measurement is the whole
point of the work, verify the measurement tooling before you trust its output,
and treat an implausible magnitude as a defect report against your own code.

## Transcript store format (needed to reproduce)

`~/.claude/projects/<slugified-cwd>/*.jsonl`. Real prompts are entries where
`type == "user"` and `message.content` is a string, or a list containing
`{"type": "text"}` parts. Most `user` entries are actually tool results and
must be excluded, as must entries starting with `<`, `[Request interrupted`,
or `Caveat:`, and any containing `<local-command`. A `last-prompt` entry is
only a pointer (`{type, leafUuid, sessionId}`), not the text.

Never commit the extracted corpus. It is raw user input.
