# Skill improvement guidelines

Skill-doctor diagnoses. It does not decide whether a change would improve outcomes.
Diagnosis surfaces candidates. Skillopt measures existing-skill candidates.
Skillforge routes capability gaps before anyone creates a skill.
Skill-doctor never starts either one, and never applies an edit.

## Method

1. Cluster the findings from `failed_conversations` by root cause, across scorers and classifications.
2. Verify each finding against the current repository and the agent's configuration. A finding that does not verify is not observed; record it under missing evidence instead of as a fact.
3. For each verified finding, state the candidate mechanism: the behavioral rule, the owning surface, and the smallest change that expresses it. Prefer **replacing** existing guidance over **appending** another paragraph.
4. Rank candidates by frequency times severity. Ranking orders the list. It never removes a candidate from it.

## What every supported finding produces

Every supported finding produces a visible candidate, or an explanation of the evidence that is missing.
No static bar suppresses a candidate. Frequency, severity, and instruction attribution rank candidates; they do not filter them.

Each candidate starts with `status: "unevaluated"`.
Only a skillopt run with a scored baseline and a candidate evaluation can set `accepted`, `rejected`, or `inconclusive`, and the suggestion must then cite that baseline and candidate evidence.

Keep three kinds of statement apart:

- **Observed fact**: the failed conversation, the scorer, and what happened. Goes in `evidence`.
- **Hypothesis**: why it happened and what change might help. Goes in `mechanism` and `expected_improvement`.
- **Measured result**: only from skillopt. Goes in `status` and `evaluation`.

## Owners

- `skill`: an existing skill's instructions own the behavior. Name the exact path from `inventory.json`.
- `new-skill`: no installed skill owns the capability. Route through skillforge first.
- `tooling`: a collector, script, product, or infrastructure defect. Name the real owner in `owner_target`. Do not relabel a tool defect as an instruction defect; an instruction candidate for it stays a hypothesis.

Skillopt can baseline and patch only an existing skill. The renderer gives `new-skill` and `tooling` candidates a routing note in place of a skillopt run: skillforge first for a new skill, the named code owner for tooling.

## Same-name variants

When the skill name appears in `skill_variants`, the edit target is unresolved.
List every variant path and `sha256` in `variants`, leave `target` empty, and do not draft a diff.
The user selects the edit target. The renderer refuses a drafted diff for an unresolved target.

## Statements the evidence does not support

Static triage cannot show that a change would not help.
An empty `suggestions` list means no candidate was proposed through static triage. It is not evidence against improvement.
Never write "no change is justified", "no beneficial change", or a similar verdict unless skillopt evaluation evidence supports it. The renderer refuses those phrases in `summary` and `top_findings` when no scored evaluation exists.
