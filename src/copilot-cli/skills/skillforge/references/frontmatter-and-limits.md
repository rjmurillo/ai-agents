# Frontmatter Shapes, Size Limits, and Routing Phrases

Read this before you write or edit a skill's frontmatter, add a routing intent, or trim a
`SKILL.md` to fit a limit. Every rule here has a deterministic check in
`lint_skill_frontmatter.py`. Run it; do not rely on reading. The command, with the
plugin-root locator, is in [scripts-and-validation.md](scripts-and-validation.md)
under "Frontmatter lint". Add `--strict` to fail on SHOULD warnings too, and `--list`
to print the rules.

Exit 0 means no MUST failure. Exit 1 means a MUST failed, or `--strict` saw a SHOULD
warning. Exit 2 is a usage error. `skillopt apply` runs the same lint and refuses a
candidate that adds a MUST failure.

## 1. Write frontmatter the stdlib parser can read (`fm.subset-parse`)

This skill's `_conformance_parse.py` reads frontmatter without PyYAML, so a verdict never
depends on what a consumer installed. It reads block mappings, block lists of plain
scalars, quoted and plain scalars, block scalars, and short flow lists of plain scalars.
It refuses everything else. A refused frontmatter makes conformance report every MUST
rule `NOT_EVALUATED`.

PyYAML accepts the refused shapes, so a PyYAML-based check passes them. Do not trust one.

| Refused | Write instead |
|---|---|
| `capability: {kind: orchestrator, status: active}` | a block mapping, one key per line |
| `inputs: [{artifact: spec}]` (flow list of mappings) | a mapping keyed by name |
| `- artifact: spec` (mapping inside a block list) | a mapping keyed by name |
| `"quoted-key": value` | a plain key |

Key a list of records by name. The name becomes the key, the options become a nested
mapping, and an entry with no options has nothing after the colon:

```yaml
metadata:
  inputs:
    implementation-change:
    requirements-spec:
      required: false
  outputs:
    execution-plan:
      path: plans/active/
```

YAML keys are unique, so a repeated record fails to parse instead of passing silently.
Write nothing after the colon for an empty entry. The stdlib parser reads `~` and `null`
as text. It also reads `true` and `false` as text, so a typed check must read the core
type, not the string.

Measured: one change used flow lists for these declarations and broke conformance on 16
of 110 skills in a single commit. Every PyYAML-based gate stayed green.

## 2. Stay under the byte cap with room for mirrors (`fm.size.bytes`, `fm.size.headroom`)

A rendered `SKILL.md` caps at 24576 bytes and 500 lines. Generated mirrors for other
harnesses rewrite tool names and paths, so they render larger than the canonical file:
about 100 bytes was measured for the Copilot CLI copy. A canonical file that fits by
50 bytes can put its mirror over the cap. Keep 256 bytes of headroom.

When a file is near the cap:

1. Move procedure, tables, and examples into `references/`, and link them.
2. Remove text that another section of the same file repeats. A principle that restates
   an anti-pattern row is the usual case.
3. Before you delete a sentence, search the tests for it (`git grep -F "<sentence>"`).
   A contract test may pin the exact words.
4. Re-measure the canonical file and every mirror after the change.

A skill that must stay large declares `size-exception: true` and carries a rationale
comment near the top. Treat that as debt, not a target.

Some hosts also budget the bytes an agent loads for a scenario: always-on files, scoped
rules, the entry skill, and every `capability.depends-on` owner it pulls in. In the
rjmurillo/ai-agents repository the pre-PR gate `Instruction Bytes (per-fixture)`
measures six task shapes. Adding a `depends-on` can load a whole second skill, and a
52-byte autoplan table row once pushed a fixture over its ceiling. Measure before and
after, and add a dependency only where the body actually invokes the owner.

## 3. Make every quoted trigger phrase routable (`fm.routing.phrases-routable`)

A phrase in double quotes or backticks, before the first `Do NOT`, with two or more
words and no `/` or `.`, is an advertised trigger. A slash command or a path is not
something a user says, so it is skipped.

An intent router matches a request against each skill's `metadata.routing.intents`. The
autoplan resolver lowercases, drops stop words (`this`, `the`, `to`, and others), strips
one trailing `s`, and then requires the intent's tokens **in order**, within a span of the
intent's length plus two. So `schema design` does not match `design this schema`.

- Each advertised phrase must match at least one of the skill's own intents.
- No phrase may resolve to a sibling, and a front door that advertises phrases must
  declare `intents`. In the rjmurillo/ai-agents repository the pre-PR ratchet
  `Skill Trigger Phrase Resolution (ratchet)` checks all three against the whole
  catalog; this lint checks only the first, because a consumer has no catalog.
- Write intents as two or more tokens. A bare noun like `adr` also matches "review
  this ADR" and steals the sibling's request. Use `draft adr` or `amend adr`.
- Avoid generic pairs too. `pr review` caught "do a PR review of my branch", which
  belongs to a code-review skill. Prefer the specific action and object, and add a
  negative routing case for the nearest sibling.
- A changed autoplan table row needs a routing scenario whose `expected_route` names
  the row's target.

`intents` are only valid on a `front-door` skill (`fm.routing.intents-role`).

## 4. Write a short description that names its sibling (`fm.description.redirect`)

Every description loads on every turn, so a long one taxes every task. Write the
shortest description that routes. One measured fix went from 839 to 435 characters
and gained triggers. In the rjmurillo/ai-agents repository the pre-PR gate
`Skill Description Budget` caps the sum per skill root.

- **Lead with the invocation condition.** Put the trigger situation first, for
  example "Invoke before you write or edit any ADR file, even when nobody names an
  ADR." Agents often reach a skill's work through a plan step, not a phrase.
- **Name the sibling it is not.** When two skills share words, a model picks wrong
  unless one description says which to use instead. End with
  `Do NOT use for X (use Y).`, naming the sibling a reader is most likely to confuse
  with this skill. Write it in both directions, and agree on who owns the edge
  cases, such as edits made inside an open review round.

## 5. Declare hand-offs the same way (`fm.artifacts.shape`, `fm.handoff.shape`)

A skill that hands a file to another skill declares it under `metadata.outputs`, and the
skill that reads it declares it under `metadata.inputs`, keyed by artifact name as in
section 1. Output options: `path`, relative to the artifact root, lowercase, with no `..`.
Input options: `source` (`skill`, `user`, or `repo`; default `skill`) and `required`
(default `true`).

A skill may close with a one-line hand-off. When a `## Handoff` section starts with
`Writes:`, it must read exactly:

```markdown
## Handoff

Writes: `execution-plan`. Next: `/build`.
```

Use `none` in either slot when there is nothing to write or no next step.

## 6. Keep a capability block inside the closed key set (`fm.capability.shape`)

`metadata.capability` accepts `kind`, `owns`, `depends-on`, `status`, `replaced-by`,
`replacement-platform`, `replacement-owner`, and `validation`. `kind` is one of
`orchestrator`, `specialized-implementation`, `reusable-primitive`, or
`cross-cutting-rule`. Write it as a block mapping.
