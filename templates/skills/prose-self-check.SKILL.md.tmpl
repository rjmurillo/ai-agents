---
name: prose-self-check
version: 0.3.0
description: Pre-emit AI-vernacular self-check an agent runs on its OWN prose
  before writing a session-log narrative, ADR context section, retrospective, or
  PR description. Four layers ordered by reader-trust, not ease of detection.
  Use when you say `prose self-check`, `audit my writing for AI tells`, `does
  this read as AI-written`, or before emitting any prose artifact. Do NOT use
  for code style (use style-enforcement) or to rewrite human-authored text.
license: MIT
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

Layers 1 to 3 are pattern matches over text, so scripts run them. Layer 4 is
the one no scanner can do, and it is where your attention belongs.

Start by running both helpers over the artifact:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/prose_lint.py" FILE
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/burstiness.py" FILE
```

`prose_lint.py` covers Layers 1 and 2 and exits 1 on any high-severity
finding. Fix what it reports, re-run until it exits 0, then do Layer 4 by
hand. Do not scan for these tells by eye; you will miss some and spend
attention you need for Layer 4.

### Layer 1: Lexical (weakest signal)

`prose_lint.py` runs this layer. It reports two tiers, and the tiering is the
point:

- **High-signal (`high`, fails the run).** Em-dash (U+2014) and en-dash
  (U+2013), model-identity phrases (`as an AI language model`), and the
  strongest tells in the banned list. Remove every one.
- **Low-signal (`info`, never fails).** Words that top keyword scans but
  readers rarely cite. The script reports them so Layer 4 can adjudicate:
  a flagged word inside a paragraph that makes a real claim stays; one
  inside filler goes with the filler. A blanket scrub here produces the
  "robot pretending not to be a robot" over-correction and reads worse. The
  exact low-signal set is the `LOW_SIGNAL_WORDS` constant in the script.

The canonical word list is NOT duplicated in this skill or in the script. It
lives in one place, the "Banned Vocabulary" section of `.claude/rules/voice.md`,
and `prose_lint.py` parses it from there at runtime. A forked list drifts.

The dash ban is also a hard repo rule (`.claude/rules/universal.md` MUST NOT
5). The script verifies it at the character level, so no eyeballing is needed.

### Layer 2: Structural

Sentence- and paragraph-shape tells. These are the #1 reader-cited
sentence-level signals and survive any keyword pass. `prose_lint.py` detects
the three that have a fixed shape:

- **Contrast framing** (`contrast_framing`): `not X, it's Y` / `it's not just
  X, it's Y` / `X isn't about Y, it's about Z`. The single most-cited sentence
  tell. Rewrite to state the claim directly.
- **Manufactured trailing offers** (`trailing_offer`): a sentence proposing
  new, uninvited scope (`Want me to also`, `I could also`, `Let me know if
  you'd like`). Delete it. (Mirrors the STOP-TOKEN rule in CLAUDE.md.)
- **Signposting / throat-clearing openers** (`signposting`): `Honestly,` /
  `Look,` / `Let's dive in` / `It's worth noting that` / `In today's
  landscape`. Delete the opener; lead with the point.

Two shapes stay yours because judging them needs the meaning, not the string:

- **Rule-of-three padding**: three parallel adjectives or clauses where one
  carries the meaning ("fast, reliable, and scalable"). Cut to the
  load-bearing term. Whether the third term is padding or content is a
  reading, not a match.
- **Inline-header lists**: bullets that each open with a bolded restatement
  ("**Speed**: it is fast.") when the bold adds nothing. Drop the label or
  fold into prose. The same shape is correct when the label is a real index
  into a set, which is why the script does not flag it.

### Layer 3: Distributional (proxy only)

Two reader-cited tells invisible to keyword passes. Use the proxies below; a
classifier (Pangram, GPTZero) is OUT of scope because it cannot run in-agent.

- **Burstiness proxy (flat rhythm, #2 reader cite)**: AI prose clusters near a
  uniform sentence length. Human prose varies. Compute the spread of sentence
  lengths in the artifact; if they are all within a narrow band, break some up
  and run others together. Use the helper:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/burstiness.py" FILE
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

This is where low-signal Layer 1 words get adjudicated: a `comprehensive`
inside a paragraph that survives the emptiness gate stays; one inside filler
goes with the filler. The tiers are intersected with the voice rule, so a
low-signal word the rule does not ban (`however`, `thus` today) stays dormant
and never reaches you.

## Output

After running all four layers, the artifact should:

- Exit 0 from `prose_lint.py`, which means zero dashes, no high-signal
  lexical tells, no contrast framing, no manufactured trailing offer, and no
  signposting opener.
- Have every `info` finding adjudicated by Layer 4 rather than scrubbed.
- Vary sentence length (no flat-rhythm warning, or a deliberate reason to keep it).
- Have every paragraph make a nameable, disagreeable claim.

Report what you changed, layer by layer, so the next reader can audit the pass.

## Anti-Patterns

- Scanning for these tells by eye. `prose_lint.py` does Layers 1 and 2
  exactly; hand-scanning is slower, misses matches, and spends the attention
  Layer 4 needs.
- Stopping when `prose_lint.py` exits 0. It clears Layers 1 and 2 only. A
  clean exit says nothing about whether the prose says anything.
- Reflexively scrubbing every `info` finding. Over-correction reads as AI
  overcompensating. Cut a low-signal word only when Layer 4 also fails.
- Copying the banned-word list into this skill or into the script. The list
  lives in `.claude/rules/voice.md`; the script parses it from there.
- Running this on human-authored text. This is self-check on agent output only.
- Treating the burstiness warning as a hard gate. It is a proxy and a prompt.

## Scripts

### prose_lint.py

Layers 1 and 2. Reports dashes, banned vocabulary (parsed from the voice
rule), contrast framing, trailing offers, signposting openers, and
model-identity phrases. Fenced code blocks and inline code spans are skipped.

Usage:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/prose_lint.py" FILE [FILE ...]
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/prose_lint.py" - < draft.md
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/prose_lint.py" FILE --json
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/prose_lint.py" FILE --rules PATH
```

Each finding prints as `FILE:LINE:COLUMN: SEVERITY: KIND: MATCH (note)`.
`-` reads stdin, which is how you check a draft that is not a file yet.

Every run ends with what it examined, not only what it found: `0 findings in
N prose line(s) of M in K file(s)`. A fence that never closes hides the rest
of the document from the scanner, so it is reported as its own high-severity
`unterminated_fence` finding rather than letting a barely-read file exit 0.

Layer 2 matches across the whole document, so a tell that straddles a hard
wrap is still caught. A blank line ends the match: the shapes are sentences,
not paragraphs.

The voice rule is discovered in this order: `--rules`, then
`$CLAUDE_PLUGIN_ROOT/rules/voice.md`, then
`$COPILOT_PLUGIN_ROOT/instructions/voice.instructions.md`, then
`.claude/rules/voice.md` or `.github/instructions/voice.instructions.md`
under the current directory, then `rules/voice.md` or
`instructions/voice.instructions.md` under the plugin install root (the
directory holding `.claude-plugin/plugin.json`). When no copy is reachable the script warns on stderr and runs the dash
and structural checks only, so a vendored install degrades instead of failing.

Exit codes (ADR-035):

- `0` no high-severity findings (`info` findings may still be present)
- `1` at least one high-severity finding
- `2` configuration error (a named file or the rules file cannot be read)

### burstiness.py

Layer 3 helper. Computes sentence-length variance (burstiness) and a
concreteness count (numbers, file paths, multi-word capitalized entities) for a
prose artifact. It is a proxy, not a gate.

Usage:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/burstiness.py" FILE
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/burstiness.py" FILE --json
```

It prints sentence count, word count, mean and standard deviation of sentence
length, coefficient of variation, concreteness count, and a flat-rhythm warning
when variance is low and there are at least four sentences.

Exit codes (ADR-035):

- `0` analyzed successfully (with or without a flat-rhythm warning)
- `2` configuration or input error (missing file, unreadable path)

## Verification

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/prose_lint.py" FILE
echo "exit=$?"   # 0 = Layers 1-2 clean, 1 = findings, 2 = bad input
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/prose-self-check/scripts/burstiness.py" FILE
echo "exit=$?"   # 0 = analyzed, 2 = bad input
```

- [ ] `prose_lint.py` exits 0 (Layers 1 and 2 clean).
- [ ] Every `info` finding was adjudicated by Layer 4, not scrubbed on sight.
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
