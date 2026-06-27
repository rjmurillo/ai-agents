---
name: prose-self-check
version: 0.1.0
description: Pre-emit AI-vernacular self-check an agent runs on its OWN prose
  before writing a session-log narrative, ADR context section, retrospective, or
  PR description. Four layers ordered by reader-trust, not ease of detection.
  Use when you say `prose self-check`, `audit my writing for AI tells`, `does
  this read as AI-written`, or before emitting any prose artifact. Do NOT use
  for code style (use style-enforcement) or to rewrite human-authored text.
license: MIT
model: claude-sonnet-4-6
---

# Prose Self-Check

Run this on prose you are about to emit. It catches AI-vernacular tells before
the artifact lands. It audits your OWN output, not human-authored text. It does
not touch code style (that is `style-enforcement`).

The layers are ordered by reader-trust, not by ease of detection. The cheap
keyword signal (Layer 1) and the real reader-cited signal (Layers 2-4) point in
different directions. Weight structural and semantic findings above lexical.

Empirical ranking from a public 89k-post study (John Carter, "I pulled ~90,000
Reddit posts about what makes writing sound like AI (Part 2)," r/ClaudeCode,
2026-06-22): em-dash 7.1% of reader cites, flat rhythm 4.0%, "not X, it's Y"
2.8%. Top keyword matches (`however`, `moreover`, `nuanced`) are ~0% reader-cited.

## Triggers

- `prose self-check`
- `audit my writing for AI tells`
- `does this read as AI-written`
- `check this prose before I send it`

## When To Use

Run before emitting any prose artifact: session-log narrative, ADR context
section, retrospective, PR body, issue body, design doc, agent-authored comment.

Skip for: code (use `style-enforcement`), pure data/config files, human-authored
text you were asked to preserve, and one-line acknowledgements with no prose.

## Process

Run the four layers in order. Do not stop at Layer 1; the weakest signal is
first so you clear it cheaply, then spend attention where readers actually look.

### Layer 1: Lexical (weakest signal)

Tiered banned-list check. The canonical word list is NOT duplicated here. It
lives in one place: the "Banned Vocabulary" section of `.claude/rules/voice.md`.
Read that section now and apply it. Do not maintain a second copy; a forked list
drifts.

Two tiers:

- **High-signal (scrub on sight).** Em-dash (U+2014) and en-dash (U+2013),
  any leftover model-identity phrase ("as an AI language model", "I'm just an
  AI"), and the strongest tells in the voice.md list (for example `delve`,
  `tapestry`, `showcase`). Remove these whenever they appear.
- **Low-signal (do NOT flag on presence alone).** Words that top keyword scans
  but readers rarely cite: `however`, `thus`, `moreover`, `additionally`,
  `nuanced`, `comprehensive`. Flag one of these ONLY when the sentence it sits
  in is also empty or bland (fails Layer 4). A blanket scrub here produces the
  "robot pretending not to be a robot" over-correction and reads worse.

The em-dash/en-dash ban is also a hard repo rule (`.claude/rules/universal.md`
MUST NOT 5). Verify at the byte level, not by eye:

```bash
python3 -c 'import sys; print(open(sys.argv[1],"rb").read().count(chr(0x2014).encode()))' FILE
```

Swap `0x2014` (em-dash) for `0x2013` (en-dash) to count en-dashes. Both counts
must be 0 outside the `tests/hooks/fixtures/` carve-out.

### Layer 2: Structural

Sentence- and paragraph-shape tells. These are the #1 reader-cited sentence-level
signals and survive any keyword pass. Scan for and rewrite:

- **Contrast framing**: `not X, it's Y` / `it's not just X, it's Y` / `X isn't
  about Y, it's about Z`. The single most-cited sentence tell. Rewrite to state
  the claim directly.
- **Manufactured trailing offers**: a closing sentence that proposes new,
  uninvited scope ("Want me to also...", "I could also...", "Let me know if
  you'd like..."). Delete it. (Mirrors the STOP-TOKEN rule in CLAUDE.md.)
- **Rule-of-three padding**: three parallel adjectives or clauses where one
  carries the meaning ("fast, reliable, and scalable"). Cut to the load-bearing
  term.
- **Signposting / throat-clearing openers**: `Honestly,` / `Look,` / `Let's
  dive in` / `It's worth noting that` / `In today's landscape`. Delete the
  opener; lead with the point.
- **Inline-header lists**: bullets that each start with a bolded restatement of
  the bullet ("**Speed**: it is fast.") when the bold adds nothing. Drop the
  bold label or fold into prose.

### Layer 3: Distributional (proxy only)

Two reader-cited tells invisible to keyword passes. Use the proxies below; a
classifier (Pangram, GPTZero) is OUT of scope because it cannot run in-agent.

- **Burstiness proxy (flat rhythm, #2 reader cite)**: AI prose clusters near a
  uniform sentence length. Human prose varies. Compute the spread of sentence
  lengths in the artifact; if they are all within a narrow band, break some up
  and run others together. Use the helper:

```bash
python3 .claude/skills/prose-self-check/scripts/burstiness.py FILE
```

  It prints sentence count, mean length, standard deviation, and a flat-rhythm
  warning when variance is low. The warning is a prompt to vary rhythm, not a
  hard gate.

- **Concreteness proxy**: count named entities, numbers, and file paths. Prose
  with near-zero of these is usually saying nothing (feeds Layer 4). The same
  helper reports a concreteness count.

### Layer 4: Semantic (emptiness gate)

The top-5 tell no scanner sees: fluent text that says nothing. For each
paragraph, name the one disagreeable claim it makes, the thing a reasonable
reader could push back on. If you cannot name it, the paragraph is filler.
Either give it a real claim with evidence or cut it.

This is where low-signal Layer 1 words get adjudicated: a `however` inside a
paragraph that survives the emptiness gate stays; a `however` inside filler goes
with the filler.

## Output

After running all four layers, the artifact should:

- Carry zero em-dashes and en-dashes (byte-verified).
- Carry no high-signal lexical tells.
- Contain no `not X, it's Y` contrast framing and no manufactured trailing offer.
- Vary sentence length (no flat-rhythm warning, or a deliberate reason to keep it).
- Have every paragraph make a nameable, disagreeable claim.

Report what you changed, layer by layer, so the next reader can audit the pass.

## Anti-Patterns

- Stopping at Layer 1 because the keywords are clean. The reader signal is in
  Layers 2-4.
- Reflexively scrubbing every `however` and `moreover`. Over-correction reads as
  AI overcompensating. Flag low-signal words only when Layer 4 also fails.
- Copying the banned-word list into this skill. The list lives in
  `.claude/rules/voice.md`; read it there.
- Running this on human-authored text. This is self-check on agent output only.
- Treating the burstiness warning as a hard gate. It is a proxy and a prompt.

## Scripts

### scripts/burstiness.py

Layer 3 helper. Computes sentence-length variance (burstiness) and a
concreteness count (numbers, file paths, multi-word capitalized entities) for a
prose artifact. It is a proxy, not a gate.

Usage:

```bash
python3 .claude/skills/prose-self-check/scripts/burstiness.py FILE
python3 .claude/skills/prose-self-check/scripts/burstiness.py FILE --json
```

It prints sentence count, word count, mean and standard deviation of sentence
length, coefficient of variation, concreteness count, and a flat-rhythm warning
when variance is low and there are at least four sentences.

Exit codes (ADR-035):

- `0` analyzed successfully (with or without a flat-rhythm warning)
- `2` configuration or input error (missing file, unreadable path)

## Verification

```bash
python3 .claude/skills/prose-self-check/scripts/burstiness.py FILE
echo "exit=$?"   # 0 = analyzed, 2 = bad input
```

- [ ] Exit 0 means the script analyzed the artifact; exit 2 is a bad-input error.
- [ ] Em-dash and en-dash byte counts are both 0 (Layer 1).
- [ ] No `not X, it's Y` contrast framing and no manufactured trailing offer (Layer 2).
- [ ] No flat-rhythm warning, or a deliberate reason to keep the rhythm (Layer 3).
- [ ] Every paragraph makes a nameable, disagreeable claim (Layer 4).

The gate is your own four-layer pass, not the script. The script supports
Layer 3; Layers 1, 2, and 4 are judgment applied against `voice.md` and the
patterns above.

## Evidence

- John Carter, "I pulled ~90,000 Reddit posts about what makes writing sound
  like AI (Part 2)," r/ClaudeCode, 2026-06-22 (`unslop-ai-text` scanner +
  600-post hand-audit). Establishes the cited-vs-keyword divergence.
- Wikipedia: Signs of AI Writing (WikiProject AI Cleanup), 29-pattern catalog.
- Kobak et al. 2025 (arXiv 2406.07016), excess-vocabulary; "delves" +6,697%.
- Juzek & Ward, COLING 2025, traces lexical overrepresentation to RLHF.

## Related Skills

| Skill | Relationship |
|-------|--------------|
| [style-enforcement](../style-enforcement/SKILL.md) | Code style; this skill is prose only |
| [prompt-engineer](../prompt-engineer/SKILL.md) | Authors prompts; does not audit emitted prose |
| [doc-accuracy](../doc-accuracy/SKILL.md) | Doc factual accuracy; orthogonal to vernacular |

## References

- Banned vocabulary source of truth: `.claude/rules/voice.md` ("Banned
  Vocabulary" section).
- Em-dash/en-dash MUST NOT: `.claude/rules/universal.md`.
- Skill standards: `.claude/skills/CLAUDE.md`.
