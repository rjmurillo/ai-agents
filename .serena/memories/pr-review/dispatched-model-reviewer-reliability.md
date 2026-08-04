# Dispatched Model Reviewer Reliability

`pr-006-reviewer-signal-quality.md` rates the bots that comment on a PR:
cursor, Copilot, coderabbitai, gemini-code-assist. This memory covers the
other population, the models you dispatch yourself through the task tool to
review work before it ships. Their failure modes are different and the bot
signal rates do not transfer.

## Verify every number a dispatched reviewer gives you

Treat a reviewer's factual claims as unverified until you run the command
yourself. Fabrication here is not rare and it does not look like fabrication.

Measured on the guards in PR #4485. `grok-4.5` filed four High findings and two
Mediums. Every one of the six rests on a premise that `git log -S` refutes, and
three of them prescribe a fix the file under review had already applied.

* It reported `model-context-doctrine.md:179` shipping a `.py` effective size
  of 96,848 and prescribed 96,785. `git log -S "96,848"` on that path returns
  nothing on any branch, so the figure it reported has never been in the file.
  The document carried 96,785 from `81b877fd8`, the merge of #4485, until
  `f326f3399` changed it to 94,869, which is the value there now. Run the
  search rather than trusting this sentence: an earlier draft of it claimed
  the file had held 96,785 since `f326f3399`, which inverts what that commit
  did, and a dispatched reviewer caught it. A memory about fabricated premises
  shipped one for a day.
* It reported the same 96,848 in the commit message. That message reads
  `.py effective: 94,088 bytes -> 96,785 bytes`.
* It called the byte and multiplier claims "unguarded theater," and it flagged
  the header as stale at 2026-07-29. `git log -S` puts both the five
  figure-guard tests and the 2026-08-03 header in `81b877fd8`, the merge of
  #4485 itself.
* It said the internal-only fallback path should be scoped to the plugin tree
  because `.github/instructions` sits in `keepInternalGlobsFor`. The doc it was
  reviewing already said exactly that, citing
  `templates/platforms/copilot-cli.yaml:39-40`. The enumeration it was
  correcting has never existed in that file.

## The dangerous shape: a reviewer that reviews the motivation, not the result

Those six are not random noise. They are internally consistent with a
*pre-fix* version of the tree. The reviewer appears to have reconstructed the
problem the commit was solving and reported that, which is why every
prescription matches what the commit already did.

Findings of this shape are maximally plausible, because they are true
statements about the world one commit ago. They also defeat the obvious check.
Verifying the **recommendation** ("is 96,785 the right number? yes") confirms
the finding. Only verifying the **premise** ("does the file actually say
96,848?") exposes it.

So check what the reviewer claims the current state is, not just what it
proposes to change that state to. `git log -S "<the quoted value>" -- <path>`
settles it in one command. Accepting one of these costs a no-op edit that feels
like progress; accepting the "unguarded theater" one costs deleting figure
claims that five passing tests already pin.

Corollary for dispatch: hand the reviewer the post-change artifact and say so
explicitly. A prompt that leads with the problem being solved invites the
reviewer to answer about the problem.

This cuts both ways. In the same review round `gemini-3.1-pro-preview` filed
two findings on the same branch and both were real: a self-shape assertion that
could never fail, and an import convention deviation. Verify does not mean
distrust. It means the verdict comes from the command, not the reviewer.

Second round, 2026-08-03, red-main branch: `gemini-3.1-pro-preview` produced
one correct High (a comment claiming every uv consumer in `validate-pr` was
behind the bot-skip guard; seven are not) and one overstated Medium (claimed
policy was permanently lost when the substance had been compressed into
`builder-ethos.md`). Precision one in two, and the correct one drove a real
fix. Worth the dispatch.

Third round, 2026-08-03, two documentation branches, same model. Seven findings
across both, three of which held. The three that held were each worth the
round: a documentation branch citing a test name and a symbol that existed on
no branch but the one it was split from, and a factual error in this very
memory. The four that failed all failed the same way, on a local convention the
reviewer could not see.

## A reviewer that cannot see a convention will misread data against the one it assumes

This is a distinct failure from fabrication and the countermeasure is
different. Fabrication invents a premise. This reads a real premise correctly
and interprets it against the wrong rule, so the quoted evidence is genuine and
the conclusion is still wrong. Quoting requirements do not catch it.

Measured. A reviewer flagged `memory-index.md` for "wildly incorrect byte
counts," quoting a real line that reads `(1579)` beside a file of 6,644 bytes,
and it pasted true `wc -c` output. The number is a token count, not a byte
count. Every entry in that index ratios between 3.8 and 5.1 bytes per unit, and
6644/1579 is 4.21. The finding was High severity, the evidence was real, and
the conclusion was backwards. In the same round another finding declared a rule
file an always-on context cost when its frontmatter scopes it to `tests/**`,
and a third reported `TESTING-RIGOR.md` missing after running `ls` from a
directory that was not the worktree.

The tell is that all three are claims about how this repository works rather
than about the change under review. So treat any finding of that kind as
unverified until you check the convention itself, and prefer to state the
convention in the dispatch prompt when you already know the reviewer will need
it. Acting on the byte-count finding would have replaced correct token counts
with byte counts across the index.

## Recall is worth more than precision, but only if you pay for verification

A reviewer whose findings are mostly false is still worth running when the true
ones were invisible to the author. `gemini-3.1-pro-preview` at one real finding
in two clears that bar. `grok-4.5` at zero in six on this branch did not, and
the six cost more than they returned, because a fabricated premise is
indistinguishable from a real one until you run the command.

Do not stop dispatching a model because it has fabricated before. Change what
you do with its output: verify the premise of every finding before its
recommendation, discard the ones that do not reproduce, and do not argue with
the model about it. Budget the verification time at dispatch, not after. If you
cannot afford to check every finding, dispatch fewer reviewers rather than
skimming more of them.

## Model selection for the `code-review` agent type

The durable part of this section is the shape, not the roster. Dispatched
reviewers fail in two independent ways, liveness and precision, and a model can
be good at one and bad at the other. So pick on both axes, and treat a hang as
a permanent cost rather than a retryable one. That much outlives any model
name.

The roster below is perishable. It is one session's observation in this
repository, current as of 2026-08-03, on the `code-review` agent type only.
Re-measure before relying on it; if these version strings no longer resolve,
the roster is expired and only the paragraph above still applies.

* `gpt-5.6-terra` hangs on `code-review` here. Multiple dispatches ran past
  four and six hours with zero turns completed and never returned. Do not
  assign it to `code-review` on this repository. It occupies an agent slot for
  the rest of the session and produces nothing.
* `gpt-5.5` behaved the same way on the same agent type: one dispatch reached
  8,286 seconds with 17 tool calls and zero completed turns.
* `gemini-3.1-pro-preview` usually returns and its findings are usually real,
  but it also hangs sometimes. One dispatch sat at zero turns past 3,300
  seconds while a sibling dispatch of the same model on the same branch
  returned a full report in 784 seconds.
* `grok-4.5` returns reliably. Precision is the problem, not liveness.

There is no tool to kill a background agent once it hangs. The slot is gone
until the session ends. That makes model choice at dispatch time the only
control you have, so spend the thought there.

## Practical shape

Dispatch two families rather than one, on the theory that they fail
differently, and give each one a numbered list of named attack surfaces rather
than "review this." A surface list produces findings tied to a location. An
open-ended request produces a summary. When both families return, verify every
factual claim from both before acting on any of them.

That advice has a cost, and the #4485 round is what exposed it. A numbered
surface list asks for a verdict per surface, and a model that would otherwise
return "nothing here" will fill the slot. `grok-4.5` returned one finding for
each surface it was handed and every premise was invented. The list buys
locatable findings and it buys fabricated ones in the same transaction.

Keep the list, and price the difference in the prompt: say that "no finding on
this surface" is an acceptable and expected answer, and require every finding
to quote the exact text it is objecting to. A quote is checkable with one
`git log -S`. A paraphrase is not, and a paraphrase is what an invented premise
looks like.

## Related

- `pr-006-reviewer-signal-quality.md`, the same question for PR comment bots
- `pr-003-verification-count.md`
