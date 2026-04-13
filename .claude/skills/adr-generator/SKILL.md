---
name: adr-generator
version: 1.0.0
model: claude-opus-4-6
description: Create comprehensive Architectural Decision Records (ADRs). Researches the destination directory to detect existing template conventions, gathers context, determines next ADR number, generates the ADR, validates completeness, and saves. Supports multiple ADR formats (MADR, Nygard, Alexandrian, project canonical). Use when documenting technical decisions or creating new ADR files.
license: MIT
user-invocable: true
metadata:
  domains: [architecture, documentation, governance, decision-records]
  type: generator
  inputs: [decision-description, context, alternatives]
  outputs: [adr-markdown-file]
---

# ADR Generator

Create well-structured Architectural Decision Records that document technical decisions with clear context, rationale, consequences, and alternatives.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `create an ADR` | Full ADR generation workflow |
| `generate ADR` | Full ADR generation workflow |
| `write an architecture decision record` | Full ADR generation workflow |
| `new ADR for` | Targeted ADR for a specific decision |
| `document this architecture decision` | Full ADR generation workflow |

---

## Quick Start

```text
# These all work:
create an ADR for database selection
new ADR for authentication strategy
document this architecture decision about event sourcing
generate ADR for switching from REST to gRPC
```

---

## When to Use

| Situation | Use This Skill? |
|-----------|----------------|
| New architectural decision needs documenting | Yes |
| Changing an existing system or pattern | Yes (includes Prior Art Investigation) |
| Reviewing or validating an existing ADR | No, use `adr-review` skill |
| Minor implementation detail, not architectural | No |

---

## Process

### Phase G1: Gather

Collect required information from the user:

- **Decision Title**: Clear, concise name
- **Context**: Problem statement, technical constraints, business requirements
- **Decision**: Chosen solution with rationale
- **Alternatives**: Options considered (at least 2) and rejection reasons
- **Stakeholders**: People or teams involved

If any required information is missing, ask the user before proceeding.

**Significance check**: Before proceeding, quickly assess whether the decision warrants an ADR using the [ASR Test](references/ad-quality-frameworks.md). If the decision is trivially reversible, purely local, and has no stakeholder concern, suggest skipping the ADR.

**Readiness check**: Verify the decision passes the [START Definition of Ready](references/ad-quality-frameworks.md): Stakeholders known, Time (Most Responsible Moment) has come, Alternatives exist, Requirements understood, Template will be determined in G2.

If the decision changes an existing system, trigger **Prior Art Investigation** using the `chestertons-fence` skill or manually gather: what exists, why it was built that way, and why change now.

### Phase G2: Research

Discover the ADR destination, naming convention, numbering, and template by inspecting the target location.

#### Step 1: Locate ADR directory

Search for existing ADRs in common locations (in priority order):

1. `.agents/architecture/` (this project's canonical location)
2. `docs/adr/`, `docs/architecture/`, `docs/decisions/`
3. `architecture/decisions/`, `adr/`

Use the first directory that contains existing `ADR-*.md` or `adr-*.md` files. If the user specifies a location, use that instead.

#### Step 2: Detect template from existing ADRs

If the directory contains existing ADRs:

- Read 2-3 existing ADRs to infer the template in use (section headings, frontmatter style, naming convention, case convention)
- Match against known templates in the [ADR templates catalog](references/adr-templates-catalog.md)
- Adopt the detected template, naming convention (e.g., `ADR-NNN-slug.md` vs `adr-NNN-slug.md`), and section structure
- Check for a template file (e.g., `ADR-TEMPLATE.md`, `template.md`) in the same directory or a parent

#### Step 3: Handle no existing ADRs

If no ADRs or template files exist at the destination:

- Prompt the user to choose a template from the [catalog](references/adr-templates-catalog.md)
- Suggest the **Project Canonical** template as the default (if `.agents/architecture/ADR-TEMPLATE.md` exists) or **MADR** as a widely-adopted alternative
- Ask the user to confirm or specify the target directory

#### Step 4: Determine next number

- Scan files matching the detected naming pattern
- Determine the next sequential number (zero-padded to match existing convention)
- Verify no collision with existing files

### Phase G3: Generate

Populate the detected template with gathered content:

- Use precise, unambiguous language
- Include both positive and negative consequences
- Document all alternatives with pros/cons table and clear rejection rationale
- Include Prior Art Investigation section when changing existing systems
- Structure for both machine parsing and human reference
- Match the style and conventions of existing ADRs at the destination

### Phase G4: Validate

Self-check against the [quality checklist](references/quality-checklist.md) before saving. All structural and content checks must pass.

### Phase G5: Save

Write the file to the destination directory determined in Phase G2:

| Rule | Example |
|------|---------|
| Match existing naming convention | `ADR-053-authentication-strategy.md` or `0053-authentication-strategy.md` |
| Zero-pad number to match existing pattern | `ADR-001`, `0001`, etc. |
| Lowercase kebab-case slug (3-5 words) | `database-selection`, `event-sourcing-pattern` |
| Status always set to `Proposed` | Changed only after `adr-review` debate |

After saving, recommend the user invoke the `adr-review` skill for multi-agent validation.

---

## Anti-Patterns

Avoid these when creating ADRs. Full catalog with 11+ creation and 7 review anti-patterns in [AD Quality Frameworks](references/ad-quality-frameworks.md).

| Avoid | Why | Instead |
|-------|-----|---------|
| Skipping alternatives section | Decisions without alternatives lack rigor | Document at least 2 alternatives with pros/cons |
| Setting status to `Accepted` | ADRs require review before acceptance | Always use `Proposed`, let `adr-review` change it |
| Duplicating an existing ADR | Causes governance confusion | Scan existing ADRs in G2, supersede if needed |
| Context that describes the solution | Context should explain the problem | Keep context focused on forces and constraints |
| Omitting negative consequences | Dishonest trade-off analysis ("Free Lunch Coupon") | Include at least 1 negative consequence |
| Skipping Prior Art when changing systems | Risk of removing structures without understanding | Use `chestertons-fence` skill |
| Sales Pitch language | Marketing language erodes trust | Use precise, quantifiable language |
| Dummy alternatives | Fake options to make preferred choice shine | Present genuine alternatives with honest pros/cons |
| Ignoring the template at the destination | Inconsistent ADR log | Detect template from existing ADRs in Phase G2 |

---

## Style

- No sycophancy, AI filler phrases, or hedging language
- Active voice, direct address
- Replace adjectives with data (quantify impact)
- Short sentences (15-20 words), Grade 9 reading level

---

## Verification

Before delivering, confirm all items in the [quality checklist](references/quality-checklist.md) pass:

- [ ] All required sections present
- [ ] ADR number is unique
- [ ] Status is `Proposed`
- [ ] Context explains the problem, not the solution
- [ ] At least 2 alternatives with pros/cons
- [ ] At least 1 negative consequence documented
- [ ] File saved to `.agents/architecture/`

---

## Related Skills

| Skill | Responsibility |
|-------|---------------|
| `adr-generator` | **Creates** a new ADR from scratch (Phases G1-G5) |
| `adr-review` | **Validates** an existing ADR via 6-agent debate |
| `chestertons-fence` | **Investigates** historical context before changing existing systems |

---

## References

- [ADR Template](references/adr-template.md) — This project's canonical ADR document structure
- [ADR Templates Catalog](references/adr-templates-catalog.md) — Comparison of Nygard, MADR, Alexandrian, Tyree & Akerman, and other formats
- [AD Quality Frameworks](references/ad-quality-frameworks.md) — ASR Test, START (DoR), ecADR (DoD), anti-patterns, review checklist (Zimmermann)
- [ADR Best Practices](references/adr-best-practices.md) — Writing guidance, lifecycle, naming conventions, teamwork advice
- [Quality Checklist](references/quality-checklist.md) — Validation checklist for Phase G4
