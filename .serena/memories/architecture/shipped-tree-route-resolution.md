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
  whole route, so `` `Skill: x` `` stays documentation and `` Skill: `x` ``
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
