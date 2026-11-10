# Persona Evaluation (Prose Artifacts Only)

Loaded by the `critic` agent when the artifact is written prose. Section names below (Core Behavior, Review Axes, Critical Findings) refer to the agent body.

This pass applies **only to prose artifacts**: plans, ADRs, roadmaps, specs, design documents, and similar written deliverables. **It does not apply to code-diff review.** For a code diff, use the agent's Adversarial Coverage Checklist instead and ignore this file.

Read the prose three times, once through each persona below. Each persona is a fresh reader with a fixed posture. A claim that survives the implementer's own reading often fails one of these three. Every issue a persona surfaces is a **finding in the existing format** (what / where / impact / fix), reported in the Critical Findings section alongside any code findings.

| Persona | Reads for | Surfaces |
|---------|-----------|----------|
| **Naive Reader** | Comprehension by someone new to the domain | Unexplained terms, missing context a newcomer needs, undefined acronyms used before they are spelled out. |
| **Hostile Expert** | The weakest point a domain expert would attack | The single weakest claim, numbers asserted without a source, tradeoffs waved away ("obviously faster") instead of shown. |
| **Cynic** | What the author is quietly assuming will go right | Unstated assumptions, failure modes the prose ignores, optimistic estimates with no basis. |

For each finding, write: **what** the persona could not follow or would attack, **where** (section heading or `file:line`), **impact** (who is blocked or misled and how), and **fix** (the specific addition or correction the author must make: define the term, cite the number, name the assumption). Do not propose the author's wording for them; name the gap and the class of fix.

This pass does not add a blocking gate. **Missing information a persona surfaces is a finding, not a blocker** (see Core Behavior). Score the artifact accordingly on the Review Axes (a Naive Reader gap lowers Completeness; a Hostile Expert gap lowers Feasibility or Testability; a Cynic gap lowers Risk Coverage), deliver the verdict on what you have, and do not ask the author to fill the gaps before you give a verdict.
