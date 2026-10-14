# Writing Style And Completeness Scores

Migrated from `.claude/rules/voice.md` (epic #5456, M4). Applies to review findings and PR-facing output this skill produces.

## Writing Style

Applies to `AskUserQuestion`, replies to user-facing questions, and findings (review output, analysis reports, retro write-ups, PR descriptions). `AskUserQuestion` format is structure; this section is prose quality.

Rules:

- **Gloss jargon on first use per skill invocation**, even if the user pasted the term. Jargon is a term of art from one subfield, the kind the retired list enumerated: `idempotent`, `N+1`, `backpressure`, `CSRF`, `quorum`, `cache stampede`. Do not gloss ordinary engineering vocabulary, and do not gloss a term the reader's next action does not depend on. One parenthetical, five to twelve words, once per skill run rather than once per response. Skip only when the user-turn override applies. Good: `N+1 (one query per row instead of one query for all rows)`. Bad: a clause-by-clause definition of the access pattern and its performance behavior.
- **Frame questions in outcome terms**: what pain is avoided, what capability unlocks, what user experience changes. Bad: "Do you want to use Redis or Postgres?" Good: "Redis cuts the auth check from 40ms to 2ms but adds a second store to operate. Postgres keeps one store but the auth check stays at 40ms. Which trade do you want?"
- **Short sentences, concrete nouns, active voice.** Subject does verb to object. "The worker drops the message" beats "messages may be dropped under certain conditions."
- **Close decisions with user impact**: what the user sees, waits for, loses, or gains. Every option in a question should end on the consequence to the person who runs the system or uses it.

### User-Turn Override

If the current user message asks for terse output, says "no explanations," "just the answer," "skip the gloss," "I know what X means," or sets caveman mode, skip this section. The override applies to the current turn only and resets on the next user message unless the override is sticky (caveman mode, explicit "stay terse for the rest of this session").

## Completeness Principle: Boil the Lake

AI makes completeness cheap. The marginal cost of covering one more edge case, one more error path, one more test is roughly zero. Use that. Recommend the complete lake. Flag the ocean.

`builder-ethos.md` section 1 is canonical for what lake and ocean mean and where the line falls. Do not restate those definitions here. This section covers only the output consequence: how completeness shows up in what you write.

### Completeness Scores

When recommending options that differ in **coverage** (same kind of thing, more or less of it), include a `Completeness: X/10` score on each option.

- `10`: all edge cases, all error paths, all known callers handled.
- `7`: happy path plus the obvious error cases. Some edges punted with a TODO or an issue.
- `5`: happy path plus one or two failure modes. Several known edges left bare.
- `3`: shortcut. Demo path only. Caller is on their own for everything else.
- `1`: stub. Compiles, returns the right type, does not do the work.

When options differ in **kind** (different approaches, different trade spaces, not comparable on a coverage axis), write:

> `Note: options differ in kind, not coverage. No completeness score.`

Do not fabricate scores. Do not score one option and skip the others. Do not score across incomparable options to manufacture a winner.

Example, coverage-differentiated:

> Option A: add null check at `auth.ts:47`. Completeness: 4/10. Fixes the reported white screen. Leaves three other middlewares with the same bug.
>
> Option B: extract a `requireSession` helper and route all four middlewares through it. Completeness: 9/10. Fixes the reported bug plus the three latent ones. Leaves the websocket path (separate auth flow) for a follow-up.
