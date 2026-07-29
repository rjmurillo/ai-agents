# Plugin roots must resolve their own routes

A routing table inside a plugin root may only name skills that same root ships.
Checking that a shipped copy matches its canonical source is a different
question and will not catch a violation.

## The incident

Issue #2026 removed `merge-resolver` from the Copilot shipping set. The skill
is hard-wired to this repository (`gh`, `.agents/sessions`, `.serena`,
session-protocol scripts) and fails on first use in a consumer repo. The
exclusion lives in `templates/platforms/copilot-cli.yaml`:

```yaml
excludeFilenames: ["AGENTS.md", "CLAUDE.md", "merge-resolver"]
```

`autoplan` kept routing merge-conflict work to `Skill: merge-resolver`. A
consumer who installed project-toolkit and hit a conflict was sent to a route
their install does not contain. This survived from #2026 until #3716.

## Why no gate caught it

Two control planes, each internally consistent:

1. The packaging exclusion is correct. The skill is absent on purpose.
2. The routing table is byte-identical to `.claude/skills/autoplan/SKILL.md`,
   where the route is correct because that tree has the skill.

Generation-drift gates ask "does the shipped copy match its source". The answer
was yes. Nothing asked "do the shipped copy's references resolve in the shipped
tree". The defect lived between two correct checks, so tightening either one
would not have found it.

Same class as `.claude/rules/plugin-self-containment.md`: anything referenced
from inside a plugin root must be encapsulated there. That rule covers
frontmatter paths. This covers body routing tables.

## The fix pattern

When a skill is excluded from a platform on purpose, route to the agent
instead:

```markdown
| Merge conflicts | Task(subagent_type="merge-resolver") |
```

`build/scripts/copilot_body_translation.py` rewrites `subagent_type="X"` to
`` `agent_type: "project-toolkit:X"` `` generically. It resolves to
`.claude/agents/merge-resolver.md` on Claude and to the shipped
`merge-resolver.agent.md` on Copilot. Agents ship even when their skill does
not, so the capability survives the exclusion. No generator change is needed.
The autoplan table already used this form for its orchestrator row.

## The gate

`scripts/validation/check_shipped_skill_routes.py`. Registered in
`scripts/validation/checks_plugin.py` for the pre-push path and as a step in
`.github/workflows/validate-generated-agents.yml`. Runs in roughly 2.8s.

The invariant is symmetric and carries no allowlist: every plugin root must
resolve its own `Skill: <name>` routes to `<root>/skills/<name>/SKILL.md`. A
route naming a skill that exists nowhere (a typo) fails the same way as one
naming a skill that packaging dropped.

Precision comes from parsing, not from an allowlist and not from a regex. The
scan asks the CommonMark parser which cells belong to a table and reads only
those. Routing lives in tables by construction, so inside a table cell a
`Skill:` token is a route and nothing else. Measured over both populated
roots: table scoping finds all 17 live routes per root with zero false
positives, while an unscoped scan adds six prose hits per root (five example
headings in `SkillForge/references/evolution-scoring.md`, one checklist item
where `create` is an English verb).

## Do not hand-roll a markdown scanner

The first three revisions of this gate hand-rolled table detection: a regex for
pipe-shaped lines, then fence tracking, then HTML comment stripping and
inline-code masking on top. Every round of adversarial review found another
hole, because a pipe-shaped-line regex is not a Markdown model. It misses
tables written without outer pipes, inside a blockquote, or indented under a
list item, and it matches pipe-shaped prose that renders as a paragraph
because it has no delimiter row.

`markdown-it-py` is already a declared first-party dependency, and
`scripts/utils/markdown_parser.py` already existed to replace "fragile regex
patterns" with an AST. Reusing it deleted about ninety lines and closed every
outstanding finding at once. Search the repository before writing the first
regex.

The same wrong model had infected the tests: fixtures omitted the `| --- |`
delimiter row, so they rendered as paragraphs and the suite passed for the
wrong reason. A mutation battery is what surfaced it; eight vacuous fixtures
were rewritten to carry real tables.

An earlier revision instead suppressed those false positives with a canonical
allowlist. Two cross-vendor adversarial reviews showed that design was
structurally unable to catch a typo, and that its lowercase-only name regex was
blind to the live `Skill: SkillForge` route. Prefer structural scoping over an
allowlist when both would work: the allowlist buys precision by discarding a
whole defect class.

Not covered: a route written outside a table, for example a bullet reading
`- Skill: foo`. Deliberate trade, and no live route takes that shape today.

## Do not discover plugin roots with a recursive glob

Roots come from a bounded candidate set: repo-root `.claude` plus direct
children of `src/`, filtered to those with `.claude-plugin/plugin.json`. This
repository keeps dozens of full working copies under `.cache/worktrees/`,
`.claude/worktrees/` and `.wt/`, each containing its own plugin manifests. A
recursive `**/.claude-plugin/plugin.json` glob matches all of them and reports
drift in trees nobody ships. Any tree walk here must also prune those directory
names in place during the walk, not filter afterward: pruning during the walk
took this check from 11.4s to 0.16s.

## Routing to an agent does not prove the agent runs

The fix redirects the merge-conflict row to the `merge-resolver` agent, which
does ship on Copilot. Review then found that agent has no `shell` tool
(`templates/agents/merge-resolver.shared.md` uses `$toolset:editor`, never
`$toolset:executor`), so its Phase 0 precondition returns `[BLOCKED]`
immediately. Unchanged since #1280, so it has never worked on Copilot. Issue
#3719.

The redirect is still a strict improvement, a precise diagnostic beats a silent
dead end, but it does not restore working merge resolution. When you reroute to
a target, check that the target can do the work, not merely that it resolves.

## When this matters

Before excluding anything from a platform shipping set, grep the shipped tree
for references to the excluded name. The exclusion and the references are
edited in different files, usually in different sessions, and every gate stays
green in between.

## Rendering is the contract, not source bytes

A source-text prefilter that skipped any file whose bytes lacked the literal
word `Skill` cut the run from 2.8s to 1.3s and looked free. It was not.
`Sk&#105;ll: ghost` renders as a route, contains no literal `Skill`, and passed
silently. The filter is deleted. What a consumer reads is the rendered document,
so the gate reads the rendered document.

The same reasoning retired a mutation that "survived by design". A surviving
mutation means no test covers the case. It never means the code is neutral.

## False positives are the expensive failure

For a push-blocking gate, wrongly blocking valid prose costs more than missing
one drifted route. The author's only recourse is to reword text that was
correct. Round three found three of these and one false negative:

- `` Skill: `merge-resolver` `` was reported malformed because every code span
  was dropped from the cell text. The shared parser now yields segments tagged
  code or text; the validator blanks a code span only when that span carries a
  whole route, so `` `Skill: x` `` stays documentation and `` Skill: `x` `` <!-- orphan-ref-ignore -->
  stays a route. Policy belongs to the caller, not to `markdown_parser.py`.
- `"Skill: x"` and `[Skill: x]` kept their punctuation. `_TRAILING` now strips
  quotes, brackets and braces.
- `Meta-Skill:` and `Task/Skill:` matched. The lookbehind is
  `(?<![\w./\\-])`. The live tree carries 148 compound forms.

## Fail closed on anything unscannable

`Path.is_file` and `Path.is_dir` answer False for a path the process cannot
stat, which silently dropped a whole plugin root and left its siblings to carry
the pass. Discovery uses `stat()` and treats only `FileNotFoundError` and
`NotADirectoryError` as absent; every other `OSError` is exit 2. Discovery also
runs inside the config-error boundary so a permission error is exit 2 rather
than a traceback.

`os.walk` does not descend into a symlinked directory, so a drifted route
behind one passed. The gate refuses such a directory rather than setting
`followlinks=True`: a symlink cycle costs dozens of redundant walks before the
OS limit stops it, and a file reachable two ways is reported twice. No plugin
root ships one today.

## Pruning must be path-shaped, not name-shaped

Pruning worktree container names at the walk root only, chosen so a real skill
named `worktrees` would still be scanned, left `node_modules` and `.venv`
inside a skill in the scan. That reads third-party prose as drift and trips the
symlink refusal on the interpreter links every virtualenv carries, which exits
2 and blocks every push in the repository. Pruning the same names at every
depth without an exemption hides a real skill whose name collides.

The rule that holds both: prune by name at every depth, exempting directories
directly under `<root>/skills`. A skill is always a direct child of the skills
namespace, so the exemption covers every legitimate collision, and everything
deeper is tooling output.

Measured before changing it: zero `venv`, `.venv` and `node_modules`
directories exist in the three live plugin roots, and no skill directory is
named any pruned name. Both the old and new rules therefore yield the same 906
files today. Cost asymmetry decided the design rather than prevalence: a stray
virtualenv blocks every push, while a content directory named `venv` only skips
a check.

## Separate the stat that asserts from the stat that sifts

One `_present(path, *, directory)` served two questions and got one wrong.
Raising when a path exists with the wrong kind is right for a manifest, whose
kind is part of the contract; it is wrong for sifting `src/*` children, where
`src/AGENTS.md` sits beside the roots and a non-directory is an ordinary
answer. The split is `_stat_mode` for the single fail-closed stat, `_present`
to assert a required kind, `_is_directory` to sift. Applying the assertion form
at the sifting site broke root discovery on the live repository immediately.

`os.walk` follows its own starting path, so a symlinked plugin root was walked
while symlinked directories inside a root were refused. One policy must cover
the whole tree, so the root is rejected before the walk begins.

## An optional capture group can erase what it matched

`_ROUTE_RE` makes the name group optional so a bare `Skill:` is reported
malformed rather than skipped. That made the pattern match a code span holding
only the keyword, as in `` `Skill:` ghost ``, so the span was blanked as syntax
documentation, the keyword vanished, and the dangling route went unreported.
Blank only when a name was actually captured. Any predicate built on a regex
with an optional group must test the group, not the match.

Strip wrapping punctuation from both ends. `_TRAILING` alone left
`Skill: (autoplan)` reported malformed, a false positive that blocks the push.

## The bare keyword needs cell context, not span context

Blanking a code span only when it captured a name fixed the vanishing route
and created a false positive: `` `Skill:` `` alone became an empty malformed
name and blocked the push over documentation. The span alone cannot decide.
What follows it in the cell can: `` `Skill:` x `` styles the label of a real
route whose name sits outside the span, `` `Skill:` `` alone documents the
keyword.

Scan the following segments including code ones. Reading only plain text there
would let `` `Skill:` `ghost` `` pass. The invariant to hold is that the plain
and backticked forms of the same cell always return the same verdict; if they
diverge, backticks become a way to silence a drift report.

## Unwrapping a name must be balanced

Stripping leading punctuation blindly turned `Skill: ((autoplan` into an
installed skill and reported a pass. Strip an opener only when its own closer
is at the other end, alternated with a trailing strip so `(autoplan).` reduces
fully. Closers are still stripped unconditionally because `[Skill: autoplan]`
puts only the closing half inside the capture.

## Prune by marker, not by location

Exempting `<root>/skills` from pruning so a skill named `venv` stays scanned
also exempts a real `.venv` created there, and its interpreter symlinks trip
the symlink refusal at exit 2, which blocks every push in the repository. The
exemption needs the `SKILL.md` marker, which is the same question `skill_names`
asks. Both sites read `SKILL_FILE` so a directory cannot count as a skill in
one place and as tooling in the other.

## Reviewer verdicts weigh what they executed

Five adversarial rounds, five do-not-ship verdicts, and round five ran two
model families that returned opposite conclusions. The approving reviewer
reached all three real defects and reasoned past each one, describing the false
positive as correct behaviour, placing a child of `skills/` "exactly at"
`skills_dir`, and calling the fail-open parse "safe". The refusing reviewer
attached an executed fixture to each finding. Every one of the three was
confirmed by running it.

Ask a reviewer for the fixture, not the conclusion. This suite ships
`tests/validation/shipped_skill_routes_helpers.py` precisely so a claim about
this gate costs about a minute to check.

## A fix earns its own adversarial round

Two of the five round-four fixes introduced new defects and a third was
fail-open, and each had passed a battery. The batteries tested the defect being
closed, never the shape being opened. Probe what a fix made newly possible, not
only what it repaired.

Corollary for mutation batteries: a surviving mutation may be a bad mutation.
The unbalanced-strip mutation stripped both ends and mangled the name so it
failed for the wrong reason, which read as a coverage gap. Check that the
mutation reproduces the defect it names before believing the survival. A
missing anchor must fail the run: a mutation that never ran otherwise reports
as caught.

## Two suites became three, on a real seam

The filesystem suite crossed the same 500-line lint the source file crossed
earlier, and the decision went the other way. The source file was suppressed
because it holds many cases of one concern. The test file was split because it
held two: `test_check_shipped_skill_routes.py` now answers "was this route
resolved correctly" and `test_check_shipped_skill_routes_paths.py` answers "was
this route read at all", with
`test_check_shipped_skill_routes_markdown.py` still answering "is this text a
route". Every round-six fail-open was in the second category and none was
visible from a routing assertion.

Split when a file holds two concerns. Suppress when it holds many cases of one.
The line count starts the conversation and does not settle it.

## A broken symlink is not an absent file

Two round-six fail-opens shared one root cause: a dangling symlink read as
genuine absence.

- `_stat_mode` mapped the `FileNotFoundError` from a dangling manifest link to
  "no manifest here", which silently removed an entire plugin root from the
  scan while the run still printed PASS. It now raises when the path is a link
  that does not resolve.
- `skill_names()` globbed a dangling `SKILL.md` link, because `scandir` lists
  it, while the pruner read the same path as absent. The inventory credited a
  skill whose directory the walk then refused to enter. Both call sites now go
  through the same `_present` call, so they cannot diverge.

Scope the strictness to paths the gate would read. A dangling `.md` link exits
2; a dangling `note.lnk` is ignored. Refusing every broken link anywhere under
a root would block pushes over litter.

## Strip a captured name outermost first

A captured route name is stripped right to left, so the first closer it meets
is the outermost one. Spending the owed-closer stack from the back
(innermost first) reports a correctly nested route as malformed. Spend from the
front. One character, caught by probing rather than by any test.

## Prove neutrality against the artifact

To claim a fix changes nothing in the live repository, instrument both the
committed version and the fixed version to record every file they open, then
diff the sets. Both read the identical 906 files here. A matching route count
is weaker evidence: it cannot distinguish "read the same files" from "read
different files and got lucky".

## A reviewer that probes can still misdiagnose

Round six's second reviewer spent 198 tool calls and attached fixtures to both
findings, and both root causes were wrong or pathological. A fixture proves the
behaviour, not the explanation. Verify the named cause independently: here,
anchoring the search it blamed produced the identical capture, and the
plain-text form of the same cell produced the identical exit code, which moved
the finding from "code-span defect" to "fail-closed on ambiguous input".

And check what a proposed fix costs before adopting it. The name pattern that
reviewer suggested rejects every one-character skill name. Run the proposed
change against the inputs that currently pass.
