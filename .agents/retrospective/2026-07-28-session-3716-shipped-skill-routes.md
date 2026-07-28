# A shipped plugin routed users to a skill it deliberately does not contain

Session 3716. Branch `fix/autoplan-dangling-skill-route`. One route fixed, one
gate added.

- Issue: #3716
- Starting commit: `95da12691b`
- Artifacts: `scripts/validation/check_shipped_skill_routes.py`, its tests, the
  routing fix in both trees, and registration in the local and CI gates

## What this was

The wiki concept "Coordination Drift Is an Architecture Risk" makes a testable
claim: parallel discovery systems disagree about what is active while each
passes its own tests. This repository maintains two skill trees. Auditing the
claim against them found a live defect in a shipped plugin.

`src/copilot-cli/skills/autoplan/SKILL.md` line 93 routed merge-conflict work
to `Skill: merge-resolver`. The Copilot toolkit does not contain that skill. A
consumer who installed project-toolkit and hit a merge conflict was sent to a
route that does not resolve.

## Nobody made a mistake

That is the interesting part. Both edits were correct in isolation.

Issue #2026 dropped `merge-resolver` from the Copilot shipping set on purpose.
The skill is hard-wired to this repository's layout: `gh`, `.agents/sessions`,
`.serena`, session-protocol scripts. Shipping it to a consumer repo would give
them a skill that fails on first use. The exclusion is right, and
`templates/platforms/copilot-cli.yaml` line 18 records the reasoning.

The routing table is also right, in the tree it was written for. `.claude/`
has the skill. The Copilot copy is byte-identical to its canonical source,
which is what the generation-drift gates check and what they found.

Two control planes. Each internally consistent. Each passing its own tests.
Disagreeing about what is reachable.

## Why every gate passed

The gates ask whether the shipped copy matches its source. That is a real
question and the answer was yes. It is not the same question as whether the
shipped copy's references resolve in the shipped tree.

No gate compared a tree's routes against that same tree's contents. The defect
lived exactly in the space between two correct checks. Adding a stricter
version of either existing gate would not have found it.

## What I got wrong on the way

The first test file used importlib to load the validator. It failed at
collection with an `AttributeError` inside `@dataclass`, because the module is
absent from `sys.modules` when the decorator runs. I had written the tests to
the shape I expected rather than reading how this repository tests validators.
`tests/validation/test_check_adr_uniqueness.py` uses subprocess, which also
exercises the CLI exit contract that TESTING-RIGOR requires. Rewriting to match
was strictly better, not merely conformant.

The lesson generalizes past this file: when a test harness fights you, check
the local convention before inventing around the friction.

## Two closed loops, both broken deliberately

The tests validate a validator written in the same session. That is one closed
loop, and a green suite proves nothing about it.

Two controls broke the loop. A mutation control neutered the gate's failure
branch and confirmed exactly the four negative tests fail while the ten others
stay green, so the negatives are load-bearing. A negative control stashed the
routing fix to restore the real historical defect, not a synthetic one, and
confirmed the gate exits non-zero with the precise file, line, and missing
path, then exits zero again when the fix returns.

The second control matters more. A synthetic fixture proves the regex works. A
replay of the actual incident proves the gate would have caught the thing it
was built for.

## Precision by allowlist was the wrong instinct

A bare `Skill: <word>` scan false-positives on a checklist line where `create`
follows the label as an English verb. My first fix reported a name only when it
also existed as a skill in the canonical tree, and I wrote a defense of that
choice: it states the drift signature directly, and an unknown name is prose or
a typo, a different defect class.

That argument was motivated reasoning. The allowlist bought precision by
discarding a defect class, and I described the discarded class as out of scope
rather than as a cost. Two reviewers on different model families said so
independently.

The replacement gets precision from structure instead: scan only markdown table
rows. Routing lives in tables by construction, so inside a table cell a `Skill:`
token is a route and nothing else. Measured, it finds all 17 live routes per
root with zero false positives, and because it no longer needs an allowlist it
catches typos too. Same precision, strictly more recall, less code.

The lesson generalizes. When a filter has to discard a defect class to buy
precision, look for a structural scope that buys the same precision for free.

## Two review rounds, both load-bearing

The first round found five defects in a gate I had already committed with a
message claiming it was verified: a lowercase-only regex blind to the live
`Skill: SkillForge` route, a swallowed `OSError` that let an unreadable file
pass silently, a vacuous `[PASS]` when the skills directory was renamed, fence
tracking that a nested or longer fence would end early, and a hardcoded tree
list.

None of those were caught by my own 14 tests, because I wrote the tests and the
gate together against the same mental model. The mutation control I ran proved
the tests had teeth against the failure I had imagined, not against the failures
I had not.

What made the second round trustworthy was refusing to settle disagreement by
vote. One reviewer declared the fix sound for consumers after checking that the
agent existed. The other checked whether the agent could actually run, and found
it could not. I verified that claim by hand before accepting it. Cross-model
agreement is a signal; independent verification is the decision.

The rewrite now carries 27 tests, and ten independent mutations each fail at
least one of them, including one that reintroduces the exact lowercase blindness
review found.

## Do not discover plugin roots with a recursive glob

A reviewer proposed replacing the hardcoded tree list with a recursive glob for
`.claude-plugin/plugin.json`. Measuring it first was what saved it: this
repository keeps dozens of full working copies under `.cache/worktrees/`,
`.claude/worktrees/` and `.wt/`, each with its own manifests. The glob matched
all of them.

The fix is a bounded candidate set, repo-root `.claude` plus direct children of
`src/`, and pruning those directory names during the walk rather than after.
Pruning during the walk took the check from 11.4s to 0.16s. A good suggestion
from a reviewer is still a hypothesis.

## Registered twice, on evidence

Reachability was the first question, because issue #3329 shipped two gates with
green tests and no caller anywhere. The gate now runs in `pre_pr.py`, which
lefthook invokes pre-push, and as a CI step beside its sibling self-containment
gate.

Paying for it in both places needed a number, not an argument. The gate runs in
2.8s. Local feedback saves a push-fail round trip, CI makes the enforcement
durable, and both call the same script, so there is one source of truth.

## Three revisions, because I never searched the repository

Two rounds of cross-vendor adversarial review both returned DO NOT SHIP. The
findings were real and mostly distinct: an HTML comment quoted inside inline
code swallowed a live table, blockquoted rows were skipped, the global vacuity
guard failed open, basename pruning at every depth hid content. I fixed each
one and the surface kept growing.

The second round named the actual problem. A pipe-shaped-line regex is not a
Markdown model. It misses tables written without outer pipes, inside a
blockquote, or indented under a list item, and it matches pipe-shaped prose
that renders as a paragraph because it has no delimiter row. Patching a wrong
model produces a longer wrong model.

Then a Layer 1 search found what should have been the first move:
`markdown-it-py` is already a declared first-party dependency, and
`scripts/utils/markdown_parser.py` already existed, written expressly to
replace "fragile regex patterns" with an AST. The correct fix deleted about
ninety lines of hand-rolled fence, comment, and table machinery and called the
helper. Every outstanding finding closed at once, and five cases my regex got
wrong started passing without being individually handled.

Searching the repository before writing the first regex would have skipped all
three revisions and both review rounds.

## The tests encoded the same wrong model

The core fixtures omitted the `| --- | --- |` delimiter row, so markdown
rendered them as paragraphs rather than tables. The suite was asserting on a
model markdown does not have. A reviewer caught it in the main fixture; a
mutation battery caught eight more that I had missed while claiming to have
fixed them all.

Those eight tests named a defence (fenced block ignored, HTML comment ignored,
inline code ignored) and passed whether or not the defence existed, because
their content was never a table in the first place. Eighteen mutations now back
the suite and every one is caught.

A test that passes for the wrong reason is worse than a missing test, because
it reports coverage it does not have.

## A surviving mutation is a hypothesis, not a proof

One mutation deliberately survived: deleting a source-text prefilter that
skipped any file whose bytes lacked the literal word `Skill`. I wrote that
survival down as proof the filter changed no outcome, and cited the 1.3s
against 2.5s as the reason to keep it.

A reviewer falsified it in one line. `Sk&#105;ll: ghost` renders as a route and
contains no literal `Skill`, so the file was skipped and the drift passed. The
mutation survived because no test covered the case, which is the same thing
every other surviving mutation means. Labelling it "neutral by design" turned
an untested path into a claim.

The filter is gone. The check costs 2.8s instead of 1.3s, which is 0.2% of a
push that already takes twelve minutes, and the invariant a reader has to trust
went from "no construct renders this keyword without spelling it" to nothing.

## The gate blocked more valid prose than invalid prose

Round three found five defects. One was the entity bypass above, a false
negative. Three were false positives: a code-styled name (`` Skill: `x` ``) was
reported malformed because the parser dropped every code span, a quoted or
bracketed name kept its punctuation, and `Meta-Skill:` and `Task/Skill:` were
read as routes. The live tree already carries 148 of that last shape.

For a push-blocking gate this is the worse failure. A missed drift ships a
broken link. A false positive blocks work, and the author's only recourse is to
reword prose that was correct. The fix moved code-span policy out of the shared
parser: it now yields segments tagged as code or text, and the validator decides
that a code span carrying a whole route is documentation while one carrying only
a name is part of the route.

## The worst bug came from testing, not from either reviewer

Probing a reviewer's claim about HTML comments surfaced the inverse defect
nobody had reported: an unterminated `<!--` never matched `<!--.*?-->`, so
commented-out content was scanned as live and failed the build on text no
reader sees. In a push-blocking gate a false positive is worse than a miss. It
blocks every contributor and teaches them the gate is noise.

Verify reviewer findings by execution rather than by vote. One proposed fix
was refuted by a ten-second run against the live repository, one finding was
refuted by the CommonMark spec, and the highest-severity bug of the session
came from testing an adjacent claim.

## What this does not cover

A route written outside a table, say a bullet reading `- Skill: foo`, is
invisible to the gate. That is a deliberate trade and no live route takes that
shape: every non-table `Skill:` hit in either root is prose, and none names a
real skill.

The larger gap is that the fix does not restore working merge resolution on
Copilot. The route now lands on an agent that ships but has no `shell` tool, so
its Phase 0 returns `[BLOCKED]`. A precise diagnostic beats a silent dead end,
but the capability is still broken. Filed as issue #3719 rather than bundled
here, because granting shell to a consumer-facing agent is security-relevant and
needs its own review.

Rerouting to a target proves the target resolves. It does not prove the target
can do the work.
