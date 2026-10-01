# Executable Natural-Language Artifacts

One quality model, many implementation languages. This reference is the single
owner of how the five qualities in `SKILL.md` apply to rules, skills, agents,
and other behavior-driving Markdown. Other capabilities link here and do not
copy it.

## Artifact model

A file is an executable artifact when an agent or runtime reads its text and
changes behavior because of it. These count:

- rules, skills, and agents under the Claude Code tree
- `.github/prompts/**` and loaded instruction Markdown
- the shipped `src/` instruction, skill, and agent surfaces
- any Markdown or structured text read at runtime to decide an action

Historical prose (retros, session notes, research) stays documentation. The
qualities still apply to it where it repeats a mutable claim or acts as an
authority.

## Quality mapping

| Code defect | Natural-language form |
|---|---|
| Duplicate code | A normative paragraph copied into a second authored file |
| Mutable duplicated state | "the three filters", a copied count, a copied list of members |
| Dead code | A skill, rule, or branch no route or scenario ever activates |
| High cyclomatic complexity | Stacked conditions, exceptions to exceptions, nested decision rules |
| Low cohesion | One artifact owns unrelated policies |
| Tight coupling | A consumer depends on another artifact's wording or layout |
| Leaky abstraction | A consumer restates an implementation detail, not the contract |
| Magic number | An unexplained numeric limit in prose |
| Shotgun surgery | One semantic change needs edits in many authored files |
| Untested branch | An instruction path with no activation or effect scenario |
| Generated-code edit | Hand-editing a generated mirror |
| Spec and code disagree | The prose contract differs from executable behavior |
| YAGNI violation | Guidance or an extension point with no present consumer |

The analysis techniques differ by artifact. The qualities do not.

## Minimal-implementation ladder

Walk the rungs in order. Stop at the first adequate rung.

1. Does this need to exist? If no, add nothing.
2. Does the repository already have it? If yes, reuse it. For an artifact,
   find the owning capability and depend on it (ADR-110) instead of restating it.
3. Does the standard library solve it? Use it.
4. Does a native platform or runtime feature solve it? Use it.
5. Does an installed dependency solve it adequately? Use it.
6. Can the requirement be met directly with no new abstraction? Write the
   smallest direct solution.
7. Only then add the minimum new abstraction a present consumer requires.

The ladder removes speculative machinery. It never removes validation, error
handling, security, accessibility, reliability, or observability that the
behavior requires. Minimal means the smallest complete solution, not the fewest
lines. Deleting a required check is negligent omission, not minimalism.

### Review evidence checklist

When a change adds an abstraction, framework, dependency, configuration surface,
extension point, or executable-policy artifact, ask for these answers:

- Which rung did you stop at, and what did the earlier rungs lack?
- Reuse: does an existing helper or owning capability already do this? If so,
  reject the new copy and use the existing one.
- Stdlib or platform: does adequate built-in behavior exist? If so, reject the
  custom implementation.
- Consumer: which present requirement or caller needs this abstraction? If none
  is named, remove it or simplify to the direct solution.
- Safety: which required validation, error handling, security, accessibility,
  reliability, or observability does the change keep? A deletion that drops one
  is rejected.

## Authored versus generated

```text
one authored source -> N generated projections    GOOD
N independently authored equivalent policies      DEFECT
```

Generated and vendor mirrors never own a policy. Edit the template or source,
then run the build. Duplication and fan-out counts cover authored files only.

## Derived prose facts

A count, list, or enum that prose repeats from an authoritative structure is
duplicated state. Default fix: delete the number or point to the structure.

```text
"Run the three filters" -> "Run the filters"
```

Keep a count only when it is the contract, as in "exactly three replicas".

## Change amplification

Change amplification is the number of independently authored locations that
must change when one semantic policy changes. A reusable policy holds steady at 1; generated mirrors are excluded. Ownership and dependencies come from the
`metadata.capability` block, not from a second graph.

## Anti-fragile remediation

Before fixing a recurring defect, classify the proposed fix:

| Class | Meaning | Preference |
|---|---|---|
| Adds a sync obligation | A new check or parity text must stay true | Last |
| Preserves the count | Same number of independent representations | Middle |
| Removes a representation | Fewer copies, or the class cannot recur | First |

Prefer deleting or generating over adding parity prose. Ask whether the defect
can be made structurally impossible.

## Enforcement

`check_nl_structural_debt.py` ratchets authored duplicate
normative blocks and stale derived counts against
`nl_structural_debt_baseline.json`, and reports change
amplification per capability owner with `--report`. Always-on bytes use
`instruction_bytes.py`. Activation coverage uses
`check_rule_activation_coverage.py`. Doctrine in this file is checked by review,
not by the script: the ladder checklist, cohesion, and coupling.
