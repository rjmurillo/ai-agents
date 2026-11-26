# adr-generator

Writes a new Architecture Decision Record (ADR) for a decision you describe. It finds where your ADRs live, copies their template and numbering, drafts the record, and runs exit gates before it hands the file to `adr-review`.

## When to use it

- You need to document a technical decision, with its context, alternatives, and consequences.
- You want to capture the rationale so future maintainers can revisit a choice.
- You are creating an ADR-like file under `.project-toolkit/architecture/`, `docs/adr/`, `docs/architecture/`, `docs/decisions/`, or `architecture/decisions/`.
- You are about to write or edit any ADR file, even when nobody named an ADR, such as a plan step that needs one.
- You say `draft ADR-NNN`, `amend ADR-NNN`, `supersede ADR-NNN`, `write an ADR`, `document these design choices`, or `record why we chose this`.

## When not to use it

- You want to review an ADR, or apply findings inside an open debate round: use [`adr-review`](adr-review.md) instead.
- The decision is a minor implementation detail, trivially reversible, and local. The skill suggests you skip the ADR.
- You are changing an existing system and need its history first: run [`chestertons-fence`](chestertons-fence.md), which this skill also calls for prior art.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:adr-generator write an ADR for switching from REST to gRPC
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/adr-generator`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /adr-generator skill to ...`.

The skill asks for any missing input: title, context, the decision with its rationale, at least two alternatives, and stakeholders. It then writes the ADR file and runs the exit gates.

## What you get

- One ADR file in the destination directory, named to match the existing ADRs (for example `ADR-053-authentication-strategy.md` or `0053-authentication-strategy.md`). The slug is lowercase kebab-case, three to five words.
- Status set to `proposed`. Only an `adr-review` consensus changes it.
- Alternatives with pros and cons, and at least one negative consequence.
- A claims ledger at `.project-toolkit/critique/ADR-NNN-claims-ledger.md`, written during the exit gates.

When the destination uses this repository's canonical template, the file starts with YAML frontmatter:

| Field | New ADR value |
| --- | --- |
| `id` | `ADR-NNN`, the number the skill picked |
| `status` | `proposed` |
| `date` | Today, last-updated |
| `decision-makers` | `[]` |
| `supersedes` | `[]` |
| `superseded-by` | `null` |
| `explainer` | `null`. The skill records a supplied link as text and never fetches it. |
| `implemented` | `false`. It flips to `true` at the first merged change. |
| `review-by` | The date the decision is due, also written in the prose. Required while `status` is `proposed`; the lifecycle gate fails a new proposed record without it. Three older records are held in its baseline. Ask the owner for the date: once it passes, the gate blocks every branch. |

## Advanced use

The skill runs six phases.

| Phase | What happens |
| --- | --- |
| G1 Gather | Collects the inputs. Runs the ASR significance test and the START definition of ready. Starts prior art research when the decision changes an existing system. |
| G2 Research | Finds the ADR directory, reads two or three existing ADRs to detect the template, and picks the next number. |
| G3 Generate | Fills the detected template. |
| G4 Validate | Checks the draft against the quality checklist. |
| G5 Save | Writes the file with the matching name and number. |
| G6 Hand off | Refreshes the ADR index, then passes the ADR and ledger to `adr-review`. |

Template detection supports MADR, Nygard, Alexandrian, and the project canonical template by name. G2 compares your existing ADRs against every template in the catalog, so other catalog formats can match too. If no ADRs exist, the skill asks you to pick one from the catalog. If you name a location, the skill uses it. [ADR template types](#adr-template-types) lists every format and how much of it the catalog carries.

> [!NOTE]
> `adr-review` auto-triggers only on uppercase `ADR-*.md` file names. If your existing ADRs use lowercase names, the skill warns you that automatic review will not fire.

In this repository, find the next free number with the helper the skill names. The same check runs as a merge-time CI gate:

```bash
uv run python scripts/validation/check_adr_uniqueness.py --print-next
```

The exit gates run in order against the saved draft. Each result is `VERIFIED`, `NOT RUN`, `UNAVAILABLE`, or `FAILED`.

1. Claims ledger: one row per factual claim, with kind, command, and result.
2. Documentation accuracy: the [`doc-accuracy`](doc-accuracy.md) skill, Phase 4.
3. Self-consistency: each Decision item against the others and against Consequences.
4. Refuting seat: one `analyst` agent refutes only the claims ledger against the repository tree.
5. ADR review hand-off: the ledger path and contents go to `adr-review`.

The skill bundles no scripts. The index refresh in G6 runs only in a checkout of `rjmurillo/ai-agents`. Any other checkout skips it.

### ADR terms

These terms come from the [ADR GitHub organization](https://adr.github.io/) home page.

| Term | Meaning |
| --- | --- |
| Architectural Decision (AD) | A justified design choice that answers an ASR. [Wikipedia](https://en.wikipedia.org/wiki/Architectural_decision) adds that ADs are hard to make or costly to change. |
| Architecturally Significant Requirement (ASR) | A requirement with a measurable effect on the architecture and quality of a system. |
| Architectural Decision Record (ADR) | One file that captures one AD, its rationale, its trade-offs, and its consequences. |
| Decision log | The set of ADRs a project keeps. |
| Architectural Knowledge Management (AKM) | The field that covers all of the above. |
| Any decision record | The same format used for design or process choices that are not architectural. |

### ADR template types

The [ADR Templates](https://adr.github.io/adr-templates/) page groups formats into four types: MADR, Nygard, Y-statement, and other. The "other" set comes mostly from [Joel Parker Henderson's collection](https://github.com/joelparkerhenderson/architecture-decision-record).

The skill matches your existing ADRs against its [catalog](../../src/claude/skills/adr-generator/references/adr-templates-catalog.md). The last column says how much of each format the catalog carries:

- **Full text**: the catalog has the whole template.
- **Fields**: the catalog lists the field names only.
- **Row**: the catalog has one comparison row and no body.
- **Not in catalog**: the catalog has no template text for it. Point the skill at existing ADRs in that format, and G2 copies their structure.

| Template | Sections or fields | Pick it when | Catalog |
| --- | --- | --- | --- |
| Project canonical | YAML frontmatter, Context, Decision, Prior Art, Rationale with alternatives, Consequences, Implementation Notes | You write ADRs in this repository | Full text, default |
| [MADR 4.0.0](https://adr.github.io/madr/) | Context and Problem Statement, Decision Drivers, Considered Options, Decision Outcome, Consequences, Confirmation, Pros and Cons of the Options, More Information | You weigh several options against named drivers | Full text |
| [Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions) | Title, Status, Context, Decision, Consequences | The decision is small and the team wants speed | Full text |
| Y-statement | One sentence: context, concern, choice, quality, downside | You need a one-line summary or a fast capture | Full text (short form) |
| [Alexandrian](https://github.com/joelparkerhenderson/architecture-decision-record/tree/main/locales/en-001/templates/decision-record-template-for-alexandrian-pattern) | Prologue (a Y-statement), Discussion, Solution, Consequences | Your team thinks in patterns and forces | Full text |
| [Tyree and Akerman](https://github.com/joelparkerhenderson/architecture-decision-record/tree/main/locales/en-001/templates/decision-record-template-by-jeff-tyree-and-art-akerman) | Issue, Decision, Status, Group, Assumptions, Constraints, Positions, Argument, Implications, and related decisions, requirements, artifacts, and principles, Notes | Auditors need traceability to requirements | Fields |
| [Planguage](https://github.com/joelparkerhenderson/architecture-decision-record/tree/main/locales/en-001/templates/decision-record-template-using-planguage) | Tag, Gist, Requirement, Rationale, Priority, Stakeholders, Status, Owner, Author, Revision, Date, Assumptions, Risks, Defined | The decision centers on a quality target | Fields |
| [Paulo Merson](https://github.com/pmerson/ADR-template) | Title, Decision, Rationale (with rejected options), Status, Consequences | You want Nygard plus explicit rationale | Row |
| [EdgeX](https://github.com/joelparkerhenderson/architecture-decision-record/tree/main/locales/en-001/templates/decision-record-template-by-edgex) | Submitters, Change Log, Referenced Use Cases, Context, Proposed Design, Considerations, Decision, Other Related ADRs, References | A design proposal goes through community review | Row |
| [arc42](https://github.com/joelparkerhenderson/architecture-decision-record/tree/main/locales/en-001/templates/decision-record-template-by-arc42) | The full arc42 document. Decisions live in section 9. | Your architecture docs already use arc42 | Row |
| [Business case](https://github.com/joelparkerhenderson/architecture-decision-record/tree/main/locales/en-001/templates/decision-record-template-for-business-case) | Title, Status, Evaluation criteria, Candidates, per-candidate research (criteria fit, cost, SWOT, opinions), Recommendation | Cost and vendor choice drive the decision | Row |
| [Gareth Morgan](https://github.com/joelparkerhenderson/architecture-decision-record/tree/main/locales/en-001/templates/decision-record-template-by-gareth-morgan) | Status, Context, Decided Approach, Consequences, Governance, Options Analysis | You want governance stated next to the outcome | Not in catalog |
| [GIG Cymru NHS Wales](https://github.com/joelparkerhenderson/architecture-decision-record/tree/main/locales/en-001/templates/decision-record-template-by-gig-cymru-nhs-wales) | Summary, Drivers, Options, Options Analysis, Recommendation, Consequences, Confirmation, More Information | You want MADR content in a recommendation shape | Not in catalog |
| [Important Technical Decision (ITD)](https://github.com/joelparkerhenderson/architecture-decision-record/tree/main/locales/en-001/templates/decision-record-template-for-important-technical-decisions) | Title states the decision, The Problem, Options Considered, Rationale, Notes | Executives must scan and challenge the choice fast | Not in catalog |
| [ISO/IEC/IEEE 42010 Appendix A](http://www.iso-architecture.org/42010/templates/) | Nine information items (listed below) | You write a standards-based architecture description | Not in catalog |

**MADR variants.** MADR 4.0.0 ships four template files: full and minimal, each in an annotated form (with guidance text) and a bare form (empty headings). The minimal form keeps Context and Problem Statement, Considered Options, Decision Outcome, and an optional Consequences. Only the full form has frontmatter, and all its fields (`status`, `date`, `decision-makers`, `consulted`, `informed`) are optional. See the [MADR template folder](https://github.com/adr/madr/tree/4.0.0/template) and the [MADR primer](https://www.ozimmer.ch/practices/2022/11/22/MADRTemplatePrimer.html).

**Y-statement forms.** The short form:

```text
In the context of <use case/user story>, facing <concern>
we decided for <option> to achieve <quality>, accepting <downside>.
```

The long form adds the rejected options and extra rationale:

```text
In the context of <use case/user story>, facing <concern>,
we decided for <option> and neglected <other options>,
to achieve <system qualities/desired consequences>,
accepting <downside/undesired consequences>,
because <additional rationale>.
```

**ISO/IEC/IEEE 42010 items.** Appendix A of the 42010 template says a decision record should consider nine items. It marks them as advice, not a requirement of the standard:

1. A unique identifier.
2. The decision statement.
3. Links to the concerns it addresses.
4. The decision owner.
5. Links to the architecture description elements it affects.
6. The rationale.
7. Forces and constraints.
8. Assumptions.
9. The options considered and their consequences.

**Status values differ by template.** Nygard's post defines `proposed`, `accepted`, `deprecated`, and `superseded`. MADR adds `rejected`. GIG Cymru NHS Wales adds `Under Review`. EdgeX uses `pending`, `approved`, `amended`, and `deprecated`. Tyree and Akerman suggest `pending`, `decided`, or `approved`. The skill sets every new record to `proposed` and leaves later changes to `adr-review`. If your template has no `proposed` value, check the status after the skill saves the file.

### Quality checks behind the skill

The skill applies these practices from [AD Practices](https://adr.github.io/ad-practices/). The [quality frameworks reference](../../src/claude/skills/adr-generator/references/ad-quality-frameworks.md) holds the full checklists.

| Practice | Where the skill uses it |
| --- | --- |
| [ASR test](https://www.ozimmer.ch/practices/2020/09/24/ASRTestECSADecisions.html): seven criteria such as business value or risk, a key stakeholder, cross-cutting impact, and first-of-a-kind work | G1. A decision that is trivially reversible, local, and of no stakeholder concern gets a suggestion to skip the ADR. |
| [START definition of ready](https://ozimmer.ch/practices/2023/12/01/ADDefinitionOfReady.html): Stakeholders known, Time has come, Alternatives (at least two), Requirements known, Template chosen | G1, with the template settled in G2. |
| [Creation anti-patterns](https://www.ozimmer.ch/practices/2023/04/03/ADRCreation.html): Fairy Tale, Sales Pitch, Free Lunch Coupon, Dummy Alternative, Sprint (Rush), Tunnel Vision, Maze, Mega-ADR, and others | G4 requires at least one negative consequence, at least two alternatives, and precise active-voice language. The skill's anti-pattern table also warns against Sales Pitch and Dummy Alternative. |
| [ecADR definition of done](https://www.ozimmer.ch/practices/2020/05/22/ADDefinitionOfDone.html): Evidence, Criteria, Agreement, Documentation, Realization and review plan | Not a skill gate. The skill covers two items: G4 checks for two alternatives, and G5 saves the record. Agreement and acceptance happen in `adr-review`. |

Give the skill a rationale that a reviewer accepts. [Zimmermann's history of decision records](https://www.ozimmer.ch/practices/2020/04/27/ArchitectureDecisionMaking.html) lists good reasons: past success in a similar context, a proof of concept, or skills available in the hiring market. Weak reasons include "everybody does it", "we have always done it like that", and "it looks good on my resume".

Not every choice needs an ADR. [Fabian Kleiser's post](https://www.fabian-kleiser.de/blog/documenting-architecture-decisions/) contrasts "framework X or Y" (record it) with "button left or right" (skip it). It suggests one question at the end of each meeting: did we just make an architectural decision worth recording?

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`adr-review`](adr-review.md): validates the ADR this skill writes, through a multi-agent debate.
- [`chestertons-fence`](chestertons-fence.md): investigates why an existing system looks the way it does.
- [`doc-accuracy`](doc-accuracy.md): checks documentation claims against source in exit gate 2.
- [`analyst`](../agents/analyst.md): runs the refuting seat in exit gate 4.
- Source: [`SKILL.md`](../../src/claude/skills/adr-generator/SKILL.md)
- References: [`adr-templates-catalog.md`](../../src/claude/skills/adr-generator/references/adr-templates-catalog.md), [`quality-checklist.md`](../../src/claude/skills/adr-generator/references/quality-checklist.md), [`ad-quality-frameworks.md`](../../src/claude/skills/adr-generator/references/ad-quality-frameworks.md), [`adr-best-practices.md`](../../src/claude/skills/adr-generator/references/adr-best-practices.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
- External sources:
  - [adr.github.io](https://adr.github.io/): definitions, [templates](https://adr.github.io/adr-templates/), [practices](https://adr.github.io/ad-practices/), and [tools](https://adr.github.io/adr-tooling/).
  - [Architecturally significant requirements](https://en.wikipedia.org/wiki/Architecturally_significant_requirements) on Wikipedia.
  - [AWS Prescriptive Guidance on ADRs](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/introduction.html): an owner, review, and supersede process for teams.
  - [An adoption model for AD making and capturing](https://ozimmer.ch/practices/2023/04/21/ADAdoptionModel.html): five maturity levels across seven dimensions.
