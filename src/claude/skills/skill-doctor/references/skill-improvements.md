# Skill improvement guidelines

Skill-doctor diagnoses. It does not decide whether a change would improve outcomes.
Diagnosis surfaces candidates. Skillopt measures existing-skill candidates.
Skillforge routes capability gaps before anyone creates a skill.
Skill-doctor never starts either one, and never applies an edit.

## Method

1. Cluster the findings from `failed_conversations` by root cause, across scorers and classifications. Passing conversations add `Cut:` candidates only: an instruction that did not apply, a skill that loaded and went unused, or steps a skill caused that the run still wasted.
2. Verify each finding against the current repository and the agent's configuration. A finding that does not verify is not observed; record it under missing evidence instead of as a fact.
3. For each verified finding, state the candidate mechanism: the behavioral rule, the owning surface, and the smallest change that expresses it. Prefer **replacing** existing guidance over **appending** another paragraph. Before you add an instruction, check whether removing or tightening an existing one fixes the finding: instructions that do not apply, and menus with no default, cause wasted steps.
   A user correction in a failed conversation maps to a `## Gotchas` entry in the target `SKILL.md`: an environment-specific fact that defies a reasonable assumption.
4. Rank candidates by frequency times severity. Ranking orders the list. It never removes a candidate from it.
5. Before you write a proposed `SKILL.md`, check it against the agentskills.io specification (<https://agentskills.io/specification>). `name`: 1-64 lowercase letters, digits, and hyphens, no leading, trailing, or consecutive hyphens, equal to the directory name. `description`: 1-1024 characters, saying what the skill does and when to use it. Body: under 500 lines and about 5,000 tokens. File references: relative, one level deep from `SKILL.md`. A draft that breaks a limit gets fixed before it is written. For authoring rules beyond these limits, cite the `skillforge` skill's `references/skill-content-rules.md`.

Sources: <https://agentskills.io/skill-creation/best-practices> (gotchas, refine with real execution).

## What every supported finding produces

Every supported finding produces a visible candidate, or an explanation of the evidence that is missing.
No static bar suppresses a candidate. Frequency, severity, and instruction attribution rank candidates; they do not filter them.

Each candidate starts with `status: "unevaluated"`.
Only a skillopt run with a scored baseline and a candidate evaluation can set `accepted`, `rejected`, or `inconclusive`, and the suggestion must then cite that baseline and candidate evidence.

Keep three kinds of statement apart:

- **Observed fact**: the failed conversation (or, for a `Cut:` candidate, the passing conversation), the scorer, and what happened. Goes in `evidence`.
- **Hypothesis**: why it happened and what change might help. Goes in `mechanism` and `expected_improvement`.
- **Measured result**: only from skillopt. Goes in `status` and `evaluation`.

## Owners

- `skill`: an existing skill's instructions own the behavior. Name the exact path from `inventory.json`.
- `new-skill`: no installed skill owns the capability. Route through skillforge first.
- `tooling`: a collector, script, product, or infrastructure defect. Name the real owner in `owner_target`. Do not relabel a tool defect as an instruction defect; an instruction candidate for it stays a hypothesis.

A tooling candidate says who owns the fix through `owner` and `owner_target`. It does not claim that no skill change would help: static triage cannot show that, and the renderer refuses the wording.

Skillopt can baseline and patch only an existing skill. The renderer gives `new-skill` and `tooling` candidates a routing note in place of a skillopt run: skillforge first for a new skill, the named code owner for tooling.

## Same-name variants

When the skill name appears in `skill_variants`, the edit target is unresolved.
List every variant path and `sha256` in `variants`, leave `target` empty, and do not draft a diff.
The user selects the edit target. The renderer refuses a drafted diff for an unresolved target.

## Statements the evidence does not support

Static triage cannot show that a change would not help.
An empty `suggestions` list means no candidate was proposed through static triage. It is not evidence against improvement.
Never write "no change is justified", "no beneficial change", or a similar verdict unless skillopt evaluation evidence supports it. The renderer refuses those phrases in `summary` and `top_findings` when no scored evaluation exists.
