# ADR-057 Workflow Reference Normalization: Review Debate

## Subject

A documentation copy-edit to `.agents/architecture/ADR-057-prompt-behavioral-evaluation.md`.
It normalizes three bare references to the workflow file `slash-command-quality.yml`
(on lines 81, 220, and 284) to the full repository path
`.github/workflows/slash-command-quality.yml`. Line 247 already used the full
path and is unchanged. The change touches identifier formatting only. No
decision, driver, acceptance criterion, consequence, or enforcement rule in
ADR-057 is altered.

Origin: the Copilot PR reviewer flagged the 3-to-1 reference-format split as a
consistency nit on PR 3315. This change resolves that nit under the ADR Review
Protocol rather than deferring it.

## Scope of this review (proportionality)

The adr-review skill mandates a six-lens panel (architect, critic,
independent-thinker, security, analyst, high-level-advisor) for ADR decisions.
This change contains no decision. It is a pure reference-format normalization
with zero semantic content. Convening the security, analyst,
independent-thinker, and high-level-advisor lenses on a path-prefix edit would
produce empty "nothing to review" verdicts, which the skill itself names as the
"Pass Through" review anti-pattern.

The two lenses with genuine surface on a documentation copy-edit were convened
as real, independent sub-agent reviews:

- **architect**: document coherence, ADR compliance, governance.
- **critic**: completeness, correctness, and risk of the edit.

The four omitted lenses are recorded here as deliberately not convened, with the
reason (no security surface, no data-model surface, no strategy surface, no
contested-decision surface). This is an honest scoping decision, not a skipped
step.

## Participants

| Lens | Agent | Convened | Verdict |
|------|-------|----------|---------|
| Architect | architect | Yes | ACCEPT |
| Critic | critic | Yes | ACCEPT |
| Independent thinker | independent-thinker | No (no contested decision) | n/a |
| Security | security | No (no security surface) | n/a |
| Analyst | analyst | No (no data or root-cause surface) | n/a |
| High-level advisor | high-level-advisor | No (no strategy surface) | n/a |

## Findings

### Architect (ACCEPT)

1. The three edits are identifier normalization only. No decision driver,
   acceptance criterion, consequence, or enforcement rule is altered. The
   sentences read identically in meaning before and after.
2. Normalizing improves coherence. Line 247 already used the full path; three
   other lines used the bare filename. Four consistent references beat a 3-to-1
   split, and the full path removes ambiguity about where in the tree the file
   lives.
3. No structural or governance concern. Status, date, and frontmatter are
   untouched. No new decision is introduced and no existing decision is
   weakened.

### Critic (ACCEPT)

1. Completeness confirmed by a full scan: exactly four mentions of
   `slash-command-quality.yml` exist in the ADR (lines 81, 220, 247, 284). Three
   were bare and are now normalized; line 247 already used the full path. No
   other workflow file is referenced anywhere in the ADR. The change set is
   complete.
2. Path correctness confirmed: `.github/workflows/slash-command-quality.yml`
   exists at that path in the repository.
3. No formatting or semantic risk. All three insertions sit inside
   backtick-delimited code spans in prose or a table cell. The longer path does
   not break the line 284 table (Markdown tables are content-agnostic on cell
   width). The added prefix narrows ambiguity, which is strictly better.

## Consensus

Both convened lenses return ACCEPT with no revisions and no blockers. The change
is a complete, correct, low-risk documentation normalization that improves
internal consistency of ADR-057 and preserves every decision unchanged.

Verdict: **ACCEPT.**

## Verification performed independently of the sub-agent reports

Before recording this consensus, the reviewer verified the reviewers' factual
claims directly against the working tree rather than trusting the sub-agent
output:

- `.github/workflows/slash-command-quality.yml` exists (confirmed on disk).
- Exactly four references to the file remain in ADR-057, all now full-path.
- Zero bare references remain.
- Zero em-dash or en-dash characters are present in the file.
- The diff is exactly three changed lines.
