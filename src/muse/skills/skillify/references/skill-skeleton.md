# Skill Skeleton and Destination Rules

Detail for the `skillify` skill. Load it at the destination and write steps.

## Destination: four questions

Answer all four before any path string enters the skill:

1. Where is the skill installed? A user-scope or project skills root. The skill
   must not assume a working directory.
2. Where is it invoked from? Anywhere. Resolve per call; never bake it in.
3. Where does it read? Env vars, the working directory, explicit user paths.
   Pick one priority order and write it down.
4. Where does it write? Same order. Writes cost more when wrong.

Default order, deviate only with a stated reason:

1. Explicit user instruction.
2. An applicable env var, when the skill targets a known shape.
3. Detection from the working directory.
4. Otherwise stop and ask once. Never guess.

If a procedure names a path before its own destination step resolves one, go
back. When the skill assumes a shape ("the notes folder has a `raw/` dir"),
state the assumption and give the dependent step a clean skip path.

## Frontmatter

```yaml
---
name: <kebab-case, at most 64 characters, equal to the directory name>
description: <action, domain noun, and the real trigger phrase in the first 200 characters>
---
```

Add `user-invocable: true` only for skills a user types by name.

## Body sections, in order

1. Framing paragraph: the problem, why it exists.
2. Triggers: phrases a user really says.
3. Contract: what is true when it finishes, observable and checkable. Promise
   nothing the procedure does not produce.
4. Procedure: numbered steps from the action map. Each has input, a concrete
   branch rule (`if X then Y, else Z`), output evidence, and state boundary.
   Mark optional recovery paths as optional.
5. Anti-patterns: at least two, the failures that motivated the skill.
6. Pitfalls: at least two, environment quirks and undocumented behavior.
7. Verification: a checklist that proves it ran.

## Gates to carry over

Draft, review, confirmation, and approval steps before an external or public
action stay in the generated procedure, in the same order, with the same
trigger. Say what is shown to the user and what the user must answer.

Tag every numbered Procedure step that acts on an external or public system
with the literal `(external)`, and the step that asks the user with
`(approval)`, for example `3. Show the draft and ask the user (approval).`
then `4. Post the summary to the channel (external).` Tags are
case-insensitive. Each `(external)` step needs an `(approval)` step strictly
before it, and no step carries both. Fenced commands belong to the step above
them. `verify` fails an untagged step or a line outside the steps that looks
external, so tag it or move it into a numbered step.

`verify` is a read-back lint for skills written by this procedure, not a sandbox against a hostile author, and it reads CommonMark basics only.
