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

Built `scripts/eval/eval-trigger-phrase-realism.py`, which reads two local
prompt stores and matches on word boundaries.

**The bare percentage is not the result. The ratio against a negative control
is.** A low operator score on its own is ambiguous, because a broken matcher
produces one too. So the eval scores the identical phrase set against the
machine-authored half of the same transcripts: sidechain, meta, and
agent-authored turns. Agents read the skill documentation, so if the phrases
are matchable at all they will appear there. They do:

| Corpus | Prompts | Documented phrases matched |
| --- | --- | --- |
| Operator-typed | 286 | 3 of 428 (0.7%) |
| Machine-authored control | 612 | 28 of 428 (6.5%) |

Same phrases, same matcher, one variable: who wrote the text. Twenty-seven
documented phrases appear **only** in machine-authored text, among them
`complete session`, `finalize session`, `initialize session`, `fill the retro`,
`review this ADR`, `handle it`, and `prose self-check`. Those are verbatim
documented triggers, written into subagent prompts by agents that had read the
docs. The phrases circulate inside the loop that defined them.

Three phrases survive in operator text: `chaos engineering` (19x),
`create a PR`, `retro fill`.

Cite the ratio, not the percentage. Both halves move together when the corpus
changes, so the ratio is the statistic that survives.

Read this as evidence about provenance, not about the router. This is a
lexical-provenance diagnostic: it never executes the router and reports no
precision, recall, or activation rate. A phrase nobody typed verbatim can still
route correctly under semantic matching, so this does not show the
practitioner's collapse reproduces here. What it establishes is narrower, that
the phrases are unobserved in this corpus, which is the precondition his
classifier failed under.

## Decision

Added an Independent-Distribution Validation section to
`.agents/governance/skill-description-trigger-standard.md` (Part 4) with the
measured table and two rules: prefer an observed phrase to an invented one, and
never benchmark trigger phrases on prompts you wrote. Added a checklist line.
The eval refuses to fall back to authored prompts and exits 3 instead, because
that substitution would defeat its purpose.

## The measurement lesson that generalises

This eval reported three different wrong numbers before it reported a right
one. Every failure was a corpus defect the code could not see, and every one
was caught by disbelieving a number rather than by a test, a lint, or a gate.

1. A 600-character cap in the first extractor silently dropped roughly 95
   percent of the corpus, yielding 66 turns from 480 transcript files. The tell
   was that 66 from 480 is implausible. Real prompt length is p50 1,820 chars,
   p90 8,175, max 107,478.
2. The first scorer used bare substring matching and reported `analyze` at 60
   occurrences. Every one was inside ordinary prose. This is precisely the
   word-boundary failure the wiki documents: every incorrect hard block in the
   practitioner's hook traced to a pattern matching inside a word. Fixed with
   `(?<!\w)...(?!\w)`.

3. The corpus was 95 percent synthetic and nobody noticed for two rounds.
   The transcript format carries a ground-truth `promptSource` field the eval
   never read. Of the entries it accepted, 213 were `isMeta`, 95 were
   `promptSource='system'`, and only 26 were `promptSource='typed'`. After
   excluding meta and sidechain, 154 of 163 unique texts began with `<`, and
   the 9 remaining prose entries were mostly compaction boilerplate. The real
   Claude operator corpus was about 26 prompts, not 203.

Both errors produced a number that looked reportable. The general rule: when a
measurement is the whole point of the work, verify the measurement tooling
before you trust its output, and treat an implausible magnitude as a defect
report against your own code.

**And verify the reviewer's premise too.** The review that caught defect 3 also
proposed the fix: accept only entries with explicit `promptSource='typed'`.
That fix is wrong. The field is present on only 120 of 3,331 non-meta user
entries, and the labelled and unlabelled sets span identical dates
(2026-06-23 to 2026-07-26). It is sparsity, not a schema boundary, so absence
is not evidence and an acceptance rule keyed on it over-filters to nothing.
The correct design is rejection-based: reject known non-human flags and
sources, keep the unlabelled majority. Complying with a correct diagnosis does
not oblige you to accept its proposed remedy.

## Where the operator corpus actually lives

The Claude transcript store is not it. After provenance filtering it yields
about 26 usable operator prompts, below any threshold that supports a
percentage.

`~/.copilot/session-store.db` is the real corpus. SQLite; `turns.user_message`
is the human turn **by construction**, so provenance there is structural rather
than inferred from heuristics. Join `turns` to `sessions` on `sessions.id` and
filter `sessions.repository`. Totals at time of writing: 3,461 turns across
1,711 sessions over three months; scoped to this repo and excluding
`<`-prefixed synthetic turns, 439 unique operator prompts, 17x the usable
Claude corpus.

Open it read-only, `sqlite3.connect(f"file:{path}?mode=ro", uri=True)`, so a
measurement can never mutate a live store. The per-session `session.db` files
under `~/.copilot/session-state/<uuid>/` are a different thing and have no
`turns` table.

## Minimum corpus, with a derivation

A phrase used in 1 percent of prompts appears at least once in 200 prompts with
probability `1 - 0.99**200`, about 0.87. Below that a zero reading and a small
non-zero reading are indistinguishable. `MINIMUM_CORPUS = 200` and the CLI
exits 3 rather than publish an uninterpretable percentage. The old Claude-only
corpus of 26 fails this guard; the dual-source corpus of 286 clears it.

## Transcript store format (needed to reproduce)

`~/.claude/projects/<slugified-cwd>/*.jsonl`. Real prompts are entries where
`type == "user"` and `message.content` is a string, or a list containing
`{"type": "text"}` parts. Most `user` entries are actually tool results and
must be excluded, as must entries starting with `<`, `[Request interrupted`,
or `Caveat:`, and any containing `<local-command`. A `last-prompt` entry is
only a pointer (`{type, leafUuid, sessionId}`), not the text.

Never commit the extracted corpus. It is raw user input.
