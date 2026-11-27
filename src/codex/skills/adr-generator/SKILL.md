---
name: adr-generator
version: 1.1.0
description: Invoke before you write or edit any ADR file, even when nobody names an ADR. Creates or amends Architectural Decision Records, then hands off to adr-review. Use when a plan step needs an ADR, or for "draft ADR-NNN", "amend ADR-NNN", "supersede ADR-NNN", "write an ADR", "document these design choices", or "record why we chose this". Do NOT use to review an ADR or apply findings in an open debate round (use adr-review).
license: Apache-2.0
user-invocable: true
metadata:
  domains: [architecture, documentation, governance, decision-records]
  capability:
    kind: specialized-implementation
    status: active
  inputs:
    decision-description:
      source: user
    decision-context:
      source: user
    decision-alternatives:
      source: user
  outputs:
    adr:
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan routes requests to document a decision to adr-generator
    user-facing: true
    intents:
      - write adr
      - create adr
      - draft adr
      - new adr
      - amend adr
      - supersede adr
      - write architecture decision record
      - create architecture decision record
      - amend architecture decision record
      - supersede architecture decision record
      - document decision
      - document design choices
      - record why chose
---

# ADR Generator

Create well-structured Architectural Decision Records that document technical decisions with clear context, rationale, consequences, and alternatives.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `write an ADR` | Full ADR generation workflow |
| `write an architecture decision record` | Full ADR generation workflow |
| `create an ADR` | Full ADR generation workflow |
| `generate ADR for` | Full ADR generation workflow |
| `document these design choices` | Capture rationale for durable architecture or design decisions |
| draft ADR-NNN, or a plan step that needs a new ADR with no trigger phrase | Full ADR generation workflow |
| amend ADR-NNN, or supersede ADR-NNN | Amend mode |

**Selection rule.** Invoke this skill before the first write to an ADR file.
Hand-writing an ADR by copying a sibling record's format skips Phase G2
numbering, the G3 frontmatter defaults, the G4 checklist, and the G6 index
refresh. Reading a sibling ADR is not a substitute for this skill.

---

## Quick Start

```text
# These all work:
write an ADR for the event model
write an architecture decision record for database selection
create an ADR for database selection
new ADR for authentication strategy
document this architecture decision about event sourcing
generate ADR for switching from REST to gRPC
document these design choices for future us to revisit as models change
record why we chose this instruction-file structure for future maintainers
```

---

## When to Use

| Situation | Use This Skill? |
|-----------|----------------|
| New architectural decision needs documenting | Yes |
| Durable design choices or rationale need capturing for future readers | Yes |
| Changing an existing system or pattern | Yes (includes Prior Art Investigation) |
| A plan, spec, or task step says an ADR is needed | Yes, before writing the file |
| Amending or superseding an existing ADR | Yes, Amend mode |
| Changing an ADR's status after a review closes | No, `adr-review` sets it |
| Reviewing or validating an existing ADR | No, use `adr-review` skill |
| Applying findings inside an open `adr-review` debate round | No, `adr-review` owns those edits |
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

Discover the ADR destination, naming convention, numbering, and template by exploring the codebase.

#### Step 1: Locate ADR directory

Explore the codebase to find where ADRs live. Do not assume a fixed location.

1. **Search broadly**: Use glob/grep to find files matching ADR patterns (`ADR-*.md`, `adr-*.md`, `0*-*.md` in directories named `decisions`, `adr`, `architecture`)
2. **Check common locations**: `.project-toolkit/architecture/`, `docs/adr/`, `docs/architecture/`, `docs/decisions/`, `architecture/decisions/`
3. **Check for ADR tooling config**: Look for `.adr-dir` files (used by `adr-tools`) or ADR references in README, CONTRIBUTING, or project documentation
4. **If user specifies a location**: Use that, regardless of what exists elsewhere

Note: `.project-toolkit/architecture/`, `docs/adr/`, `docs/architecture/`, `docs/decisions/`, and `architecture/decisions/` are monitored by `adr-review` for auto-triggered review when the platform honors file triggers. Invoke `adr-review` manually if automatic review does not fire.

#### Step 2: Detect template from existing ADRs

If the directory contains existing ADRs:

- Read 2-3 existing ADRs to infer the template in use (section headings, frontmatter style, naming convention, case convention)
- Match against known templates in the [ADR templates catalog](references/adr-templates-catalog.md)
- Adopt the detected template, naming convention (e.g., `ADR-NNN-slug.md` vs `0NNN-slug.md`), and section structure
- Note: `adr-review` auto-triggers only match uppercase `ADR-*.md` patterns. If existing ADRs use lowercase, warn the user that auto-review will not trigger
- Check for a template file (e.g., `ADR-TEMPLATE.md`, `template.md`) in the same directory or a parent

#### Step 3: Handle no existing ADRs

If no ADRs or template files exist anywhere in the codebase:

- Prompt the user to choose a template from the [catalog](references/adr-templates-catalog.md)
- Suggest the **Project Canonical** template as the default (if `.project-toolkit/architecture/ADR-TEMPLATE.md` exists) or **MADR** as a widely-adopted alternative
- Ask the user to confirm or specify the target directory

#### Step 4: Determine next number

- Scan files matching the detected naming pattern in the destination directory
- Determine the next sequential number (zero-padded to match existing convention)
- Verify no collision with existing files in that directory

For this repo's canonical `.project-toolkit/architecture/` location, use the
deterministic helper instead of eyeballing the directory (it also accounts
for the allowlist of pre-existing duplicates):

```bash
python3 scripts/validation/check_adr_uniqueness.py --print-next
```

The same script is enforced as a merge-time CI gate
(`.github/workflows/validate-adr-number-uniqueness.yml`), so a
PR that picked a number which has since been merged by another branch will
fail with a remediation message naming the next free value. Re-run
`--print-next` and rename the file, the `# ADR-NNN:` heading, and any
references before pushing.

### Phase G3: Generate

Populate the detected template with gathered content:

- Use precise, unambiguous language
- Include both positive and negative consequences
- Document all alternatives with pros/cons table and clear rejection rationale
- Include Prior Art Investigation section when changing existing systems
- Structure for both machine parsing and human reference
- Match the style and conventions of existing ADRs at the destination

**Lifecycle frontmatter (ADR-073, Phase 1)**: when the destination uses this
repo's canonical template (`.project-toolkit/architecture/ADR-TEMPLATE.md`), emit the
<!-- vendor-portability: declared. adr-generator reads the canonical ADR template under .project-toolkit/architecture/ and, in Amend mode, the latest debate log under .project-toolkit/critique/; a consumer repo without it falls back to the bundled references/adr-template.md. Phase G6 runs build/scripts/generate_adr_index.py to refresh the generated ADR index only in the rjmurillo/ai-agents repository; any other checkout skips the step, even one that holds a script of that name. -->
machine-readable YAML frontmatter block above the `# ADR-NNN:` heading with
these safe defaults:

```yaml
---
id: ADR-NNN              # match the number chosen in Step 4
status: proposed         # always proposed on a new ADR (never accepted)
date: YYYY-MM-DD         # today, last-updated
decision-makers: []
supersedes: []           # ADR ids this record supersedes, if any
superseded-by: null
explainer: null          # display-only link; NEVER auto-fetch (CWE-918 SSRF)
implemented: false       # flips true at the first merged change
review-by: YYYY-MM-DD    # required while proposed: the date the decision must be made
---
```

Rules the generator MUST honor:

- `status` is always `proposed` on a new ADR. Only `adr-review` consensus
  changes it (see Phase G5 and the Anti-Patterns table).
- `implemented` is always `false` on a new ADR; it flips at first merged change.
- `superseded-by` defaults to `null`; `supersedes` defaults to `[]`.
- `explainer` defaults to `null`. If the author supplies one, record the literal
  string only. MUST NOT fetch, resolve, or follow the URL (it is a poisoning and
  SSRF surface, CWE-918). It is display-only metadata for human click-through.
- The frontmatter `status` enum is authoritative for tooling. A prose `## Status`
  section is optional: add it only for nuance the enum cannot carry, never to
  restate the enum (ADR-073, amended 2026-09-29).

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
| Frontmatter `status: proposed`, `implemented: false`, `explainer: null` | Phase 1 defaults (ADR-073); `explainer` never auto-fetched (CWE-918) |
| Frontmatter `review-by: YYYY-MM-DD`, also stated in the prose | When the destination uses this repository's ADR template: required while `proposed` (ADR-073), and the lifecycle gate fails a new `proposed` record without it. Ask the owner for the date: once it passes, the gate blocks every branch. Other templates keep their own fields |

### Amend Mode

Use Amend mode to change an existing ADR outside an open `adr-review` debate
round. Examples: an amendment section or a superseding record. Status changes
belong to `adr-review`, which sets status when a review closes.

1. **G1 Gather**: read the existing ADR and its latest debate log under
   `.project-toolkit/critique/`. Record what changes, why, and the evidence.
2. **G2 Research**: keep the existing number and path. A superseding decision
   is a new ADR: run the full workflow, set `supersedes: [ADR-NNN]` on the new
   record, and set `superseded-by` on the old one.
3. **G3 Generate**: edit in place. Date an amendment heading
   (`## Amendment YYYY-MM-DD`). Update frontmatter `date`. Leave `status`
   alone unless an `adr-review` consensus or the user set it.
4. **G4 Validate** and **G5 Save** as for a new ADR.
5. **G6 Hand Off**: a non-frontmatter edit needs a new debate log. Hand the ADR
   to `adr-review`, which opens `ADR-NNN-debate-log-2.md` (or the next number).

## Mandatory Exit Gates

**Delegation on each host.** "Delegate to the `X` agent" means the host's subagent tool: Claude Code `Task` with `subagent_type="X"`; Copilot CLI `task` with `agent_type="project-toolkit:X"`; Codex `spawn_agent` with `agent_type="X"`, plus `fork_turns="none"` when the agent reviews or judges work (the default hands it your whole history); Muse Code `subagent_spawn` with `role="X"` and an `objective`, plus `worktree_isolation: true` for an agent that writes files. If the host has no subagent tool, or no `X` agent is installed, run the step yourself in this session.

Run these five gates in order against the saved draft before handing it to
`adr-review`. They are a measured pilot, not a permanent policy: use one fixed
ADR cohort before and after the pilot, then retain them only when avoided writer
rework exceeds maintenance and runtime cost. Record factual-finding share in
round one, rounds to consensus, writer correction time, total model cost, false
blocks, gate escapes, model, harness version, and wall time. The abort condition
is false blocks or gate escapes increasing without lower writer correction time.

Every gate result is `VERIFIED`, `NOT RUN`, `UNAVAILABLE`, or `FAILED`. Do not
invent a correction when evidence is unavailable or a claim remains uncertain.

1. **Claims ledger.** Create one row for every factual claim: claim text, kind
   (`path`, `count`, `absence`, `behavior`, or `quote`), command, and result.
   Store it as `.project-toolkit/critique/ADR-NNN-claims-ledger.md` beside the debate log.
   An absence row needs a whole-repository search. For each `path:line` row,
   read the cited range directly from the working tree and record the observed
   text. Do not use `check_citation_freshness.py` or `citation_reverse_pass.py`;
   both read committed revisions only.
2. **Documentation accuracy.** Run `Skill(skill="doc-accuracy")` Phase 4 with
   the saved ADR as the documentation file and its mapped source files as the
   source input. Do not use `--diff-base`; it scans committed changes and cannot
   select this uncommitted ADR.

3. **Self-consistency.** Compare every Decision item with every other Decision
   item and with Consequences. Record contradictions or the `VERIFIED` result.
4. **Refuting seat.** Run one seat, not the panel:
   delegate to the `analyst` agent with the prompt "Refute only the claims ledger
   against the repository tree. Return factual findings and evidence." (Claude
   Code: `model="haiku"`).
   The outcome is `VERIFIED` only when no factual findings remain. Do not invoke
   `adr-review` while this seat reports a factual finding; record unavailable
   evidence as `UNAVAILABLE`, never as a fabricated correction.
   The seat is a bounded experiment, not independent proof. It may use a different
   failure mode or externally grounded evidence; record its cost and wall time.
5. **ADR review hand-off.** Pass the ledger path and contents with the ADR to
   `adr-review`. In Phase 1, record the path in the new debate log before
   evaluating findings. A factual finding already covered by the ledger is a
   gate escape, not proof that the writer must fabricate a same-pass correction.

### Phase G6: Hand Off

After the gates pass, refresh the ADR index, then hand the ADR and its claims
ledger to `adr-review` for multi-agent validation.

<!-- vendor-portability-exec: the refresh step invokes
     build/scripts/generate_adr_index.py, which lives upstream in the
     rjmurillo/ai-agents repo and ships in no plugin root. The step is guarded
     by an origin remote check and skipped in any other checkout, so another
     repository's script is never run. -->

The ADR index (`.project-toolkit/architecture/README.md`) is generated from the
ADR corpus. It lists each record's status, title, and decision
summary. The gates above can edit the title and decision summary; status stays
proposed until `adr-review` reaches consensus. Run the generator after the
gates so the index shows the post-gate draft instead of drifting until the next
unrelated build. Status changes after hand-off need another run.

Run it only in the `rjmurillo/ai-agents` repository. Check first:

```bash
git remote get-url origin | grep -Eq '^((https|ssh)://([^@/]+@)?|[^@/]+@)github\.com[:/]rjmurillo/ai-agents(\.git)?/?$' \
  && test -f build/scripts/generate_adr_index.py \
  && uv run python build/scripts/generate_adr_index.py
```

If the check fails, skip the refresh: either this is another repository (a fork
clone included), or `build/scripts/generate_adr_index.py` does not exist in this
checkout. Another repository's script of that name is that repository's code, and
running it here would execute whatever its branch supplied. The index has not
shipped in a consumer checkout, so nothing needs regenerating. A fork clone of
this repository, or an `origin` that is a mirror or proxy URL of it, fails the check
too: the index stays stale until the next `build_all.py` run regenerates it, so tell
the user to run that. The check
keeps an agent from running an unknown repository's script by accident. It scopes by
repository, not by script content: a branch checked out in this repository runs
its own copy of the script, as `pytest` or `build_all.py` would.

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
- [ ] File saved to destination directory determined in Phase G2
- [ ] Claims ledger records each factual claim and its evidence status
- [ ] Documentation accuracy, self-consistency, and refuting-seat results recorded
- [ ] In the `rjmurillo/ai-agents` repository, `build/scripts/generate_adr_index.py` ran after the gates (Phase G6); in any other checkout it was skipped
- [ ] ADR review hand-off includes the claims ledger path and gate escapes

---

## Related Skills

| Skill | Responsibility |
|-------|---------------|
| `adr-generator` | **Creates** a new ADR (Phases G1-G6) or **amends** one (Amend mode) |
| `adr-review` | **Validates** an ADR via 6-agent debate and applies findings inside its own rounds |
| `chestertons-fence` | **Investigates** historical context before changing existing systems |

---

## References

- [ADR Template](references/adr-template.md): This project's canonical ADR document structure
- [ADR Templates Catalog](references/adr-templates-catalog.md): Comparison of Nygard, MADR, Alexandrian, Tyree & Akerman, and other formats
- [AD Quality Frameworks](references/ad-quality-frameworks.md): ASR Test, START (DoR), ecADR (DoD), anti-patterns, review checklist (Zimmermann)
- [ADR Best Practices](references/adr-best-practices.md): Writing guidance, lifecycle, naming conventions, teamwork advice
- [Quality Checklist](references/quality-checklist.md): Validation checklist for Phase G4
