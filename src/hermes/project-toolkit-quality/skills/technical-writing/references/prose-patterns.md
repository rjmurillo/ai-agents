# Prose Patterns

Be direct, use simple words, and keep sentences to three or four clauses unless
a longer sentence has a clear reason.

AI-drafted text falls into patterns readers recognize. One instance may be fine.
Several together make a page read as machine-written and cost the reader time.
Check a draft for these before you finish and rewrite each hit.

## Sentence structure

- Split a sentence with more than four clauses.
- Do not frame with "It's not X, it's Y", "The question isn't X. It's Y", or
  "Not X. Not Y. Just Z." Say what the thing is.
- Do not answer your own question: "The result? Faster startup." Write "Startup is faster."
- Do not use fragments for emphasis, such as "Local. Fast. Free." Write complete sentences.
- List three items only when there are three things.
- Cut trailing "-ing" clauses that add significance without information, such as
  "..., highlighting its flexibility".
- Finish the sentence instead of hanging a short phrase off a final comma.
- Use "from X to Y" only when X and Y are ends of a real range.
- Write "is" where "serves as", "stands as", or "represents" adds nothing.
- Replace "The first... The second... The third..." prose with a list or the site's steps component.

## Negative contrast

Read the page for phrases that explain a fact by contrasting it with something
it is not. Check forms the linter can miss, such as a trailing `, not ...`.
Ask what the reader needs to know or do. If direct wording keeps every fact,
quote the exact replacement in the audit.

- "This preview creates a draft, not a published report." When publication
  limits matter, write "The preview creates draft reports. Publish them separately."
- Keep "Do not delete the original file until the checksum matches."
  The warning states a prerequisite and does not tell readers to delete the file.

## Openings and endings

- Do not count before a list ("Four reasons to..."). State the list.
- Lead with the point, then the evidence.
- Do not narrate the writing or your reasoning, such as "It's worth being precise about...".
- Do not defend uncontroversial points or answer objections nobody raised.
- Cut filler transitions: "It's worth noting", "Importantly", "Interestingly",
  "Notably", "Here's the thing", "Here's the catch".

## Word choice and tone

- Cut marketing words: seamless, unlock, elevate, supercharge, game-changing,
  cutting-edge, unprecedented. Describe what the feature does.
- Do not inflate stakes, such as "... changes how you build software forever".
- Cut empty intensifiers: quietly, deeply, remarkably, arguably, truly.
- Cut stock AI vocabulary: delve, harness, utilize, leverage as a verb (write
  "use"), streamline, certainly, tapestry, landscape, paradigm, synergy,
  load-bearing, and "gated" meaning restricted. Use "ecosystem" and "framework"
  only in their literal technical sense.
- Do not coin labels such as "the configuration trap" and then use them as if
  they were established terms.
- Do not repeat a distinctive phrase from earlier in the page as a callback.
- Skip analogies ("Think of it as...", "Imagine a world where...") unless the
  analogy is clearer than the direct explanation.
- Cut quotable one-liners that carry no information.
- Do not claim something is well known: "famously", "notoriously", "a classic", "as you know".
- Do not cite unnamed sources ("experts recommend", "many teams find"). Link a
  specific source or drop the claim.
- Do not list historical companies or technology shifts to build authority.
- Avoid performative candor such as "And yes, ..." or "To be honest, ...".
- Say where something is defined, stored, or configured, not "where it actually lives".

## Formatting

- Do not use em dashes or parentheses for asides or dramatic pauses. Use commas,
  a colon, or two sentences. A site convention that uses an em dash as a fixed
  separator (a code-block title, for example) is not an aside.
- Do not start every bullet with a bold phrase. Keep bold lead-ins for
  glossary-style definition lists.
- Do not use Unicode arrows or curly quotes in prose. Write "then" or "to", or
  use numbered steps. Arrows are fine inside code and diagrams.

## Automated first pass

The `prose-self-check` skill ships `prose_lint.py`, which flags several of these
patterns. Run it on the draft, then read the page yourself: a scanner catches
words, not a buried point or a missing step. When that skill is not installed,
record the lint as `UNAVAILABLE` and do the manual read.
