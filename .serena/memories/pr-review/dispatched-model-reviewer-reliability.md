# Dispatched Model Reviewer Reliability

`pr-006-reviewer-signal-quality.md` rates the bots that comment on a PR:
cursor, Copilot, coderabbitai, gemini-code-assist. This memory covers the
other population, the models you dispatch yourself through the task tool to
review work before it ships. Their failure modes are different and the bot
signal rates do not transfer.

## Verify every number a dispatched reviewer gives you

Treat a reviewer's factual claims as unverified until you run the command
yourself. Fabrication here is not rare and it does not look like fabrication.

Measured on the guards in PR #4485. `grok-4.5` filed four High findings. Two
were real, one of those excellent. One asserted that a documented byte figure
was wrong and supplied 96,848 as the true value. The real measured figure was
96,785, which is what the document already said. The finding was specific,
confidently worded, carried a plausible number, and was wrong.

The cost of accepting it would have been editing a correct document to hold a
fabricated figure, then pinning that figure in a test. The cost of checking was
one command.

This cuts both ways. In the same review round `gemini-3.1-pro-preview` filed
two findings on the same branch and both were real: a self-shape assertion that
could never fail, and an import convention deviation. Verify does not mean
distrust. It means the verdict comes from the command, not the reviewer.

## Recall is worth more than precision here

A reviewer that files four findings where two are false is still worth running,
because the two real ones were invisible to the author. Do not stop dispatching
a model because it has fabricated before. Change what you do with its output:
read every finding, verify each independently, discard the ones that do not
reproduce, and do not argue with the model about it.

## Model selection for the `code-review` agent type

Observed repeatedly in this repository, across many dispatches in one session:

* `gpt-5.6-terra` hangs on `code-review` here. Multiple dispatches ran past
  four and six hours with zero turns completed and never returned. Do not
  assign it to `code-review` on this repository. It occupies an agent slot for
  the rest of the session and produces nothing.
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

## Related

- `pr-006-reviewer-signal-quality.md`, the same question for PR comment bots
- `pr-003-verification-count.md`
