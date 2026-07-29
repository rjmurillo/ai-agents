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

## The fix for one review round opened the hole found in the next

Round three flagged that pruning worktree container names at every depth would
hide a real skill named `worktrees`. The fix scoped pruning to the walk root
and a test pinned it. Round four then found that root-only pruning walks a
`node_modules` or `.venv` inside a skill, and that the interpreter symlinks a
virtualenv carries trip the gate's own symlink refusal at exit 2. The round
three fix turned a hidden-content risk into a blocks-every-push risk.

Both reviewers had probed pruning. One declared it correct after testing a
nested worktree symlink, which the symlink refusal does catch. The other found
the hole with a nested real `node_modules`. Same surface, different probe,
opposite verdicts. Neither reviewer was wrong; the surface needed both probes.

The corrected rule is path-shaped rather than name-shaped: prune by name at
every depth, exempting directories directly under `<root>/skills`. A skill is
always a direct child of that namespace, so every legitimate name collision is
covered and everything deeper is tooling output. Both constraints hold at once
because they were never actually in conflict; the name-shaped framing made them
look like they were.

## Deleting a test to make a fix pass, defensibly

The G2 fix failed a round-three test asserting that a `venv` nested inside a
skill is scanned. Changing a test to make a fix pass is how defects ship, so
the burden is on the change.

What made it defensible: measurement first, cost asymmetry second. Zero `venv`,
`.venv` and `node_modules` directories exist in the three live plugin roots, and
no skill directory is named any pruned name, so both the old test's scenario
and the new one are hypothetical. With prevalence tied at zero, the asymmetry
decides: a stray virtualenv blocks every push in the repository, while a content
directory named `venv` only skips a check. The replacement tests keep the old
test's real protective intent at the level where it is right, that a skill
directory named `venv` is still scanned, and add the policy the old test denied.

A test that pins a defect is not a guarantee worth keeping. Say so in the test
body, with the measurement, so the next reader can re-litigate it on evidence.

## Verify that your own fix did not shrink the scan

The pruning change could have silently reduced coverage, which is the same
fail-open class the gate exists to prevent. Counting scanned files before and
after, 906 both ways, is what separates a fix from a hopeful edit. A gate's own
changes need the gate's own discipline.

The same discipline caught a vacuous check elsewhere in the session: a PR
description validation returned clean for both the real body and a poisoned
control. A passing check is worthless until a control that should fail does.

## An optional capture group can erase what it matched

The route pattern makes the name optional so a bare `Skill:` is reported
malformed rather than skipped. That same optionality made the pattern match a
code span holding only the keyword, so the span was blanked as syntax
documentation and the route's keyword disappeared with it. The predicate tested
the match when it should have tested the group.

Two rounds of review read that line and neither caught it by reading. It took
a fixture. Predicates built on a regex with an optional group need a probe, not
a reading.

## Declining a finding needs the same evidence as accepting one

One round-four finding was real and left unfixed: a route inside a raw HTML
`<code>` tag is read as a route while the same route in a backtick span is
treated as documentation. Zero table cells across the three plugin roots contain
a `<code>` tag, the current behaviour fails closed, and the workaround is one
backtick. Closing it would add HTML token-depth tracking, and a new fail-open
path, to a markdown parser several gates share.

The decision is recorded in the module docstring and pinned by a test that
states the reasoning, so it is a documented trade rather than an oversight. A
finding declined without evidence is indistinguishable from a finding missed.

## A reviewer that approves without a fixture is worth less than one that probes

Round five ran on two model families and they returned opposite verdicts. One
said ship and approved every point. The other said do not ship and attached an
executed fixture to each of four findings. Three of the four were real, and
they were defects the round-four fixes had introduced.

The approving reviewer did not merely miss them. It reached each one and
reasoned past it. It called the bare `Skill:` span "correctly reported as an
empty malformed route", which is the false positive. It placed a `.venv` under
`skills/` "exactly at skills_dir" when the directory is a child of it, which is
the whole bug. It observed that `Skill: ((ghost)` "parses safely to ghost",
which is the fail-open stated as a feature.

Every one of those claims is checkable in about a minute with the fixture
helpers this suite already ships. None was checked. The lesson is not that one
model family is better; it is that a review verdict carries weight in
proportion to the fixtures behind it, and a review that runs nothing is a
second opinion on the reading, not on the code. Round-six prompts now ask for
the fixture, not the conclusion.

## One round's fix is the next round's defect until a probe says otherwise

Three of the five round-four fixes were confirmed correct. Two introduced new
defects and a third was fail-open. Each was a narrow, well-reasoned change to
close a real finding, and each was verified by a battery that passed.

The batteries were not wrong, they were incomplete in the specific direction
the new code opened. Blanking a code span only when it carried a name was
tested against a span that carried a name and a span that did not carry the
keyword, never against a span carrying the keyword alone. Exempting the skills
namespace was tested with a real skill in it, never with real tooling. The
tests covered the defect being closed, not the shape being introduced.

A fix is a new hypothesis. It earns its own adversarial round, and the probe
has to target what the fix made newly possible rather than what it repaired.

## A surviving mutation can be a bad mutation

Thirty mutations, one survivor, and the survivor was the battery's fault. The
mutation meant to reproduce the unbalanced-strip fail-open stripped both ends
of the name instead of the leading one, which mangled `((autoplan` into
`autopl`. That still fails to resolve, so the tests still reported drift and
the mutation looked survived.

Rebuilt to strip the opener only, the way the original defect did, it was
caught immediately. A surviving mutation is a hypothesis about coverage; the
first thing to check is whether the mutation reproduces the defect it names.

The same review pass found the battery would print `SKIP anchor` and continue
when a fix had moved the line it targeted. A skipped anchor is a mutation that
never ran, so a battery could report every mutation caught while running fewer
of them each round. Missing anchors now fail the run.

## Measure before splitting a file the lint calls too long

The source file crossed a 500-line lint at 541 lines. The remediation text
asked for a split into helpers, types and constants. Measured first: 304 lines
of code and 237 of prose, where each paragraph of prose records which defect
made a rule exist. A split driven by that count would have moved the fail-open
story that justifies balanced unwrapping into a different file from the balance
test.

Repository precedent settled it. A sibling `check_` validator in the same
directory suppresses the same rule for the same reason, twelve tracked scripts
already exceed the limit and one is 3757 lines, and 49 test files exceed it.
Both files are suppressed with an inline rationale and a revisit condition tied
to the code rather than the prose. A lint that fires on prose is measuring the
wrong thing, but saying so requires the measurement first.

## Round six: the fixture is the finding

Six rounds of adversarial review on a single validator. Round six opened with a
convergence gate written into both prompts: this is the last round, and a
finding changes code only if it arrives with a fixture showing a wrong exit
code. That gate is the first concrete use of the wiki concept
"Self-Improvement Needs a Stop Condition" audited earlier in this session.

The two reviewers diverged again, in the same direction as round five.

One returned four findings, each with an executed fixture and an observed exit
code. All four reproduced and all four were real. Two were fail-open: a broken
manifest symlink removed an entire plugin root from the scan while the run
still printed PASS, and a broken skill marker counted as an installed skill to
the inventory while reading as absent to the pruner, so a directory the
inventory had already credited was never entered.

The other returned two findings, also with fixtures, after 198 tool calls. Both
were declined on measurement rather than on argument. The first named a
code-span defect; anchoring the search it blamed yields the identical capture,
and the plain-text form of the same cell returns the identical exit code, so
the behaviour is the fail-closed default on ambiguous input and is shared by
both forms. The second is real but needs a skill directory literally named
`my.skill.`, and the name pattern it proposed rejects every one-character skill
name. Both are now docstring limitations pinned by tests, including one that
pins the cost of the rejected fix so a future reader cannot adopt it without
seeing what it breaks.

That reviewer had also written, in round five, that the symlink handling "holds
up robustly against adversarial inputs (symlinks...)". That is the exact area
where the other reviewer found two confirmed fail-opens. Two rounds running,
the reviewer that attached executed fixtures was right every time and the
reviewer that reasoned without them certified working code as broken and broken
code as robust. The verdict carries no information. The fixture does.

## A fix earns its own round, again

Probing the round-six fixes caught a false positive that none of the new tests
caught: a route wrapped in nested brackets reported malformed. The owed-closer
stack was spent innermost first, but a captured name is stripped right to left,
so it meets the outermost closer first. One character of ordering.

Third round running that a fix opened a new hole, and the second time probing
found it before the tests did. Tests encode the shapes already thought of.
Probing asks what the fix newly made possible. They are not substitutes.

## Split when a seam exists, suppress when it does not

The filesystem suite crossed the same 500-line lint that the source file
crossed two rounds earlier. The earlier decision was to suppress, on a
measurement showing the file was mostly prose. This time the decision went the
other way, and the difference is the reason.

A real seam existed. Routing verdicts answer "was this route resolved
correctly". Path discipline answers "was this route read at all". Different
failure modes: the first is a wrong answer, the second is a silent absence.
Both round-six fail-opens were in the second category and neither was visible
from a routing assertion. Splitting put that story in one file, 189 and 407
lines, and no suppression was needed.

The rule that reconciles the two decisions: split when the file holds two
concerns, suppress when it holds many cases of one. The line count is what
starts the conversation, not what settles it.

## Prove neutrality against the artifact, not against memory

The claim that the fixes change nothing in the live repository was worth more
than a matching route count. Both the committed version and the fixed version
were instrumented to record every file they open. Both read the identical 906
files and return the identical verdict.

That is a different class of evidence from "the output looks the same". It
holds the fixes to changing behaviour only on the adversarial shapes, which is
what a fix to a fail-open is supposed to do.
