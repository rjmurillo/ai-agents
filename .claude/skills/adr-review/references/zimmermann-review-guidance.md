# ADR Review Guidance (Zimmermann)

Review practices, anti-patterns, and checklists adapted from Olaf Zimmermann's "How to Review ADRs — and How Not To" (2023, updated 2025).

## Three Review Perspectives

| Perspective | Goal | Rigor | When to Use |
|-------------|------|-------|-------------|
| **Peer/Coach** | Early feedback to improve content | Low — friendly, constructive | During drafting, before wider sharing |
| **Stakeholder** | Confirm AD is adequate, seek agreement | Medium — official | Ready for team consensus |
| **Design Authority** | Formal approval/sign-off | High — formal | Final acceptance, governance gate |

Choose reviewers based on review goals. Rigor increases with audience breadth. This skill's 6-agent debate maps to the **Stakeholder** perspective by default, with the **high-level-advisor** agent serving as Design Authority when needed.

## 14 Good Review Practices

### Scope (3 practices)

1. **Deliver what is asked for.** Read only ADRs marked ready for review. Agree on specific review areas (content review vs. template conformance).
2. **Prioritize comments by urgency and importance.** Use H/M/L or severity 1/2/3. Be ready to discuss and adjust.
3. **Document scope and goals.** List artifacts studied with version numbers. Make assumptions explicit.

### Content (3 practices)

4. **Justify comments by referencing desired qualities.** Cite readability, consistency, completeness. Finding gaps is harder than commenting on present content — it takes dedication.
5. **Acknowledge context and requirements at decision time.** Give benefit of doubt. Put yourself in the AD maker's shoes.
6. **Be concrete and factual in option judgments.** Prefer "I suggest evaluating O1's performance in more depth" over "O1 needs work."

### Style (5 practices)

7. **Comment in a problem- and solution-oriented way.** Use workshop-conversation style. Avoid direct confrontation. Lead with questions: "have you tried O2?" not "you must use O2!"
8. **Report perceptions, do not interpret or guess.** Do not analyze presumed root causes. Ask for clarification.
9. **Be at least as factual and thorough as the ADR reviewed.**
10. **Criticize as needed, but also motivate.** Comment on sound parts, not only weak ones. "Everything I don't complain about is ok" is unacceptable.
11. **Be fair and polite.** Modest wording, no offenses. Prefer "argument B2 might benefit from more explanation" over "your writing is poor."

### Actionability (3 practices)

12. **Make feedback resolvable.** Provide finding-recommendation pairs. Tag as "FYI" vs "action required."
13. **Offer help with resolution.** Say what you would do. Provide examples for missing content.
14. **Review your own review comments** before sending. Check: could you resolve the findings yourself from reading your own comments?

## Seven Review Anti-Patterns

| # | Anti-Pattern | Problem | Detection Signal |
|---|-------------|---------|-----------------|
| 1 | **Pass Through** | Few or no comments; document barely skimmed. Variant: **Over-Friendliness** — all comments positive and shallow | Agent produces no substantive findings |
| 2 | **Copy Edit** | Focuses solely on wording/grammar, ignoring content | Findings are all editorial, none architectural |
| 3 | **Siding/Dead End** | Comments switch topic unexpectedly, deviate from ADR content, stop without advice | Agent response drifts from the decision at hand |
| 4 | **Self Promotion** | Comments mostly recommend reviewer's own work or preferred solution | Agent pushes specific technology without objective rationale |
| 5 | **Power Game** | Threatens authors rather than providing technical arguments; brags about experience | Agent uses authority claims instead of evidence |
| 6 | **Offended Reaction** | Defends a criticized position subjectively. Variant: "Hate To Say I Told You So" | Agent reacts emotionally to the ADR's rationale |
| 7 | **Groundhog Day** | Same message repeated without progress | Agent re-raises resolved issues across rounds |

**Application to this skill**: Each agent in the 6-agent debate should self-check against these anti-patterns. The consolidation phase (Phase 2) should flag any agent whose output matches an anti-pattern and request re-review with more depth.

## ADR Review Checklist (7 Questions)

Use during Phase 1 (Independent Review). Every agent should address these:

1. Is the problem relevant enough to be solved and recorded in an ADR?
2. Do the options have a chance to solve the problem? Are valid options missing?
3. Are the decision drivers (criteria) mutually exclusive and collectively exhaustive?
4. If criteria conflict with each other, are they prioritized?
5. Does the chosen solution solve the problem? Is the rationale sound and convincing?
6. Are consequences reported as objectively as possible?
7. Is the solution described actionably? Traceable to requirements? Has a validity period or review date?

**Also check**: vocabulary precision (no subjective language, ambiguity, or loopholes) and whether the decision meets [ecADR Definition of Done](../../adr-generator/references/ad-quality-frameworks.md) criteria.

## Reviewer Pledge

Five commitments for every reviewing agent:

1. Apply proven practices for scope, content, and professional feedback style
2. Avoid (or spot and overcome) the seven review anti-patterns
3. Use checklists to make reviews repeatable and reproducible
4. Make comments actionable with concrete recommendations and examples
5. **Review like you want to be reviewed**

## ADR Benefits Reminder (CALM)

ADRs keep you CALM:

- **C**ollaborative content creation is enabled
- **A**ccountability is supported
- **L**earning opportunities are provided (newcomers and experienced)
- **M**anagement appreciates them (familiar decision-making pattern)

Done well, ADRs also produce: productivity increase (traceable community assets), longer-lasting designs (community involvement), and risk reduction (checklist effect of templates).

## Sources

- Zimmermann, O. (2023, updated 2025). "How to Review ADRs — and How Not To." <https://www.ozimmer.ch/practices/2023/04/05/ADRReview.html>
- Zimmermann, O. (2023). "How to Create ADRs — and How Not To." <https://www.ozimmer.ch/practices/2023/04/03/ADRCreation.html>
- Craske, A. "How To Make Architecture Reviews That Feel Like Peer Reviews." <https://medium.com/qe-unit/how-to-make-architecture-reviews-that-feel-like-peer-reviews-ca1316b4f17d>
