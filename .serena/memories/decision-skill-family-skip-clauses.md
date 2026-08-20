# Decision: scope the SKIP-clause rule to real naming families

## Question

`.agents/governance/skill-description-trigger-standard.md` requires a skill that shares a
naming family with a sibling to carry a SKIP clause routing away from that sibling. How
many of the 96 skills actually violate it?

## Conventional answer

A first pass that grepped for descriptions lacking any negative trigger reported a large
number, and a looser pass that tried to resolve the referent of every SKIP clause reported
four more violations: `autoplan`, `benchmark-models`, `steering-matcher`, `stuck-detection`.

## First-principles position

Both passes were over-broad because they ignored where the rule sits in the document. The
SKIP-clause MUST and the "name a real sibling artifact" rule both live under the
`SKIP Clause for Sibling Families` heading. They bind a skill because it has a confusable
sibling, not because it exists. A skill with no sibling has nothing to route away from, so
a positive trigger alone cannot over-trigger across a family.

## Evidence

Parsing the frontmatter description of all 96 skills under `.claude/skills` and grouping by
leading name token gives 8 families with more than one member, covering 37 skills. Exactly
three of those 37 carried no negative trigger: `github`, `session-end`, `session-log-fixer`.

The four extra candidates all sit alone in their family, so the family rule does not reach
them. Their clauses route to an action rather than a named artifact, which is correct for a
skill with no sibling to be confused with. `autoplan` routes to whatever skill the user
named, which cannot be a fixed artifact name by construction.

A fifth candidate, `panning-for-gold`, was flagged only because the check looked for skills
and its clause names `analyst`, which is an agent (`.claude/agents/analyst.md`). Its other
referent, `spec-generator`, is a skill. Both resolve, so it was never a violation. Any
referent check must search agents as well as skills.

## Decision

Scope reduced from seven candidate edits to three real violations. Clauses were written
reciprocally, which the standard requires:

- `github` routes URL reading to `github-url-intercept`, which already routed PR and comment
  work back to `github`.
- `session-log-fixer` routes local completion to `session-end`; `session-end` routes creation
  to `session-init` and CI repair to `session-log-fixer`.
- `session-init` now routes session-end work back to `session-end`. The first draft leaned
  on the chaining-parent escape, arguing that `session-init` pointing at `session` was
  enough. Adversarial review disproved it: the escape requires one sibling to orchestrate
  the others, and `session` does not. Its description covers mid-session compliance checks
  only. A direct back-pointer was the correct fix.

After the edits, zero of the 37 prefix-family members lack a negative clause, and the
`session` family has no non-reciprocal routing edge.

## What this measurement does not cover

The claim above is scoped to one reading of the rule: a family is a set of skills sharing a
leading name token, and the MUST is discharged by having a negative clause. The standard is
broader than that in two ways this change does not address.

It says families share a "prefix or theme", and theme is never defined. Under a theme
reading, `review`, `security-review` and `adr-review` form a family and none routes to a
theme sibling.

It also says the clause must name the sibling, which is stricter than having any clause.
Five members carry a clause that routes somewhere useful but not to a family sibling, and
19 within-family routing edges have no back-pointer: 11 in the 15-member `ai-agents-*`
family, where pairwise reciprocity would need 105 clause pairs and cannot fit the 1024-char
budget, and 8 in the `memory-*` family. The merge-base carried 20. This change closed one
(`github-url-intercept` gained its back-pointer) and introduced none.

That count uses one stated predicate: an edge is a skill named as a routing target inside a
`Do NOT use ...` clause, in one of the three documented forms, where source and target share
a leading `-`-delimited name token. A compound parenthetical counts once per name, so
`memory-search`'s `(use memory or memory-enhancement)` is two edges, not one.

Those are rule-interpretation questions, not defects to patch silently. Filed as issue
#3484 with the measurement script and a proposal to define family membership operationally,
replace pairwise reciprocity with a connectivity requirement, and add a validator so the
standard stops drifting unobserved.

## Transferable lesson

A MUST nested under a scoping heading inherits that scope. Reading the rule text alone and
applying it to every artifact manufactures violations. Before acting on a governance count,
check which section the rule sits in and what that section is about, then re-measure. Here
that check cut the work by more than half and prevented four descriptions from being
rewritten for no reason.

The mirror-image error is just as easy. Scoping the rule correctly and then measuring a
weaker predicate than the rule states produces a compliance claim that is true of the
measurement and false of the rule. State the predicate you measured next to the number, not
just the number.

Ad hoc audit scripts need the same scepticism as the artifacts they audit. Four versions of
this one produced four different counts. The first split negative clauses on `.` and
truncated a clause at `github.com`, hiding a real routing target. The second matched any
skill name inside the clause span and counted the prose phrase "a new session log" as a
route to the `session` skill, inventing two reciprocity violations. The third required the <!-- orphan-ref-ignore -->
name to sit immediately before the closing paren, so it read `(use memory or
memory-enhancement)` as one target and missed the other. The fourth parses the whole
parenthetical and keeps every token that is a real skill name.

The corpus contains exactly one compound parenthetical, which is why three of the four
versions looked right. A single unusual instance is enough to make a count wrong, and a
count that is off by one is indistinguishable from a correct one until someone re-derives
it. Two defences work: assert the script against a handful of cases whose answers are known
by hand before trusting its aggregate, and print the underlying list rather than the total,
because a wrong list is obvious to a reader and a wrong integer is not.

Disagreement between two measurements is a signal to re-measure, not to pick a winner. An
adversarial reviewer here reported a different total, then reconciled it in prose and
concluded no change was needed. Both totals were wrong. The reconciliation was reasoning
about numbers instead of re-running the measurement, which is the same failure the number
was supposed to guard against.

A referent check must also cover every artifact kind the repo can route to. Searching only
skills reports false violations for clauses that correctly name an agent.
