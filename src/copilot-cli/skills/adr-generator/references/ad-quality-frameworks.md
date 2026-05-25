# AD Quality Frameworks

Quality frameworks for the full ADR lifecycle, based on Olaf Zimmermann's research (2020-2023).

## ASR Test: Is This Decision Worth an ADR?

Before writing an ADR, assess whether the decision is architecturally significant. Score each criterion H/M/L or Y/N. Takes 1-2 minutes per issue.

| # | Criterion | Signal |
|---|-----------|--------|
| 1 | **Business value/risk** | High benefit vs cost, or high business risk |
| 2 | **Key stakeholder concern** | Important stakeholder cares deeply |
| 3 | **Runtime QoS** | Performance needs deviate substantially from current architecture |
| 4 | **External dependencies** | Unpredictable, unreliable, or uncontrollable external behavior |
| 5 | **Cross-cutting** | Affects multiple parts of system (e.g., security, monitoring) |
| 6 | **FOAK** | First-of-a-Kind for this team |
| 7 | **Past trouble** | Caused critical situations or budget overruns before |

If most criteria score low, skip the ADR. If any score high, document it.

## START: Definition of Ready

When is an AD ready to be made? Five criteria gate entry to the decision:

| # | Criterion | Question |
|---|-----------|----------|
| **S** | Stakeholders | Are decision makers and affected parties known? |
| **T** | Time | Has the Most Responsible Moment come? |
| **A** | Alternatives | Do at least 2 options exist with understood pros/cons? |
| **R** | Requirements | Are the context, problem, and decision drivers known? |
| **T** | Template | Has an ADR template been chosen? |

### START Checklist

```markdown
* [ ] Stakeholders are known (decision makers and catchers)
* [ ] Time (most responsible moment) has come
* [ ] Alternatives exist and are understood (at least two)
* [ ] Requirements/criteria and context/problem are known
* [ ] Template for AD recording has been chosen
```

## ecADR: Definition of Done

When can an AD be considered done? Five criteria gate exit from documentation:

| # | Criterion | Question |
|---|-----------|----------|
| **e** | Evidence | Are we confident this design will work? (PoC, spike, trusted voucher) |
| **c** | Criteria | Have we compared at least 2 options semi-systematically? |
| **A** | Agreement | Have we discussed with peers and reached a common view? |
| **D** | Documentation | Have we captured the decision and shared the record? |
| **R** | Realization/Review | Do we know when to implement, review, and possibly revise? |

### ecADR Checklist

```markdown
* [ ] Confident this design will work (evidence exists)
* [ ] Decided between at least two options, compared semi-systematically
* [ ] Discussed among peers, reached common view
* [ ] Captured decision outcome and shared the record
* [ ] Know when to realize, review, and possibly revise
```

## How the Frameworks Fit Together

```text
ASR Test           START              Decision             ecADR
(Is it              (Is it              Making               (Is it
 significant?)       ready?)                                  done?)
     │                  │                  │                    │
     ▼                  ▼                  ▼                    ▼
  Filter  ──────►  Gate In  ──────►  Select Option  ──────►  Gate Out
  issues           to decision          making               from documentation
```

## ADR Author Pledge

Five commitments (Zimmermann, 2023):

1. Prioritize decision topics by **architectural significance**
2. Pick one **template** and stick to it
3. Size ADR adequately: **question, criteria, options, outcome, consequences**
4. Invest in documentation **quality** (thorough, focused, factual, trace to requirements)
5. Be **honest and candid**: disclose confidence level and experience that influenced the decision

## ADR Review Checklist

Seven questions for reviewing ADRs:

1. Is the problem relevant enough for an ADR?
2. Do the options solve the problem? Are valid options missing?
3. Are decision drivers mutually exclusive and collectively exhaustive?
4. If criteria conflict, are they prioritized?
5. Does the chosen solution solve the problem? Is the rationale convincing?
6. Are consequences reported as objectively as possible?
7. Is the solution described actionably? Traceable to requirements? Has a review date?

## ADR Creation Anti-Patterns (Zimmermann)

### Subjectivity

| Anti-Pattern | Problem |
|-------------|---------|
| **Fairy Tale** | Shallow justification — only pros, no cons |
| **Sales Pitch** | Marketing language, exaggerations, unverifiable adjectives |
| **Free Lunch Coupon** | No consequences documented, or only harmless ones |
| **Dummy Alternative** | Fake option to make the preferred one shine |

### Time Dimension

| Anti-Pattern | Problem |
|-------------|---------|
| **Sprint/Rush** | Only one option considered, only short-term effects |
| **Tunnel Vision** | Only local context; operations and maintenance ignored |
| **Maze** | Topic does not match content; discussion derails |

### Size and Content

| Anti-Pattern | Problem |
|-------------|---------|
| **Blueprint/Policy in Disguise** | Cookbook/law style instead of decision journal |
| **Mega-ADR** | Entire system architecture document in one ADR |

### Magic Tricks

| Anti-Pattern | Problem |
|-------------|---------|
| **False Urgency** | Non-existing context to create pseudo-problem |
| **Problem-Solution Mismatch** | Solution seeking a problem; ADR sells a pre-decided choice |
| **Pseudo-Accuracy** | Quantitative scoring where qualities cannot be measured discretely |

## Review Anti-Patterns

| Anti-Pattern | Problem |
|-------------|---------|
| **Pass Through** | Barely read the ADR |
| **Copy Edit** | Grammar corrections only, no substance |
| **Siding/Dead End** | Switches topic away from the actual decision |
| **Self Promotion** | Reviewer uses review to showcase own knowledge |
| **Power Game** | Hierarchical threats instead of constructive feedback |
| **Offended Reaction** | Takes feedback personally, becomes defensive |
| **Groundhog Day** | Same feedback message repeated without progress |

**Core review principle**: *"Review like you want to be reviewed."*

## Sources

- Zimmermann, O. (2023). "Definition of Ready for Architectural Decisions." <https://ozimmer.ch/practices/2023/12/01/ADDefinitionOfReady.html>
- Zimmermann, O. (2020). "A Definition of Done for Architectural Decision Making." <https://www.ozimmer.ch/practices/2020/05/22/ADDefinitionOfDone.html>
- Zimmermann, O. (2020). "Architectural Significance Test." <https://www.ozimmer.ch/practices/2020/09/24/ASRTestECSADecisions.html>
- Zimmermann, O. (2023). "How to Create ADRs — and How Not To." <https://www.ozimmer.ch/practices/2023/04/03/ADRCreation.html>
- Zimmermann, O. (2023). "How to Review ADRs — and How Not To." <https://www.ozimmer.ch/practices/2023/04/05/ADRReview.html>
