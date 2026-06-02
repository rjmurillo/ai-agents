# ADR-067: validate-pr Check 1 default-flip - change-claim context required

## Status

Proposed

## Date

2026-06-02

## Context

`scripts/validation/pr_description.py` Check 1 ("File mentioned but not in diff") is the BLOCKING gate that compares paths extracted from the PR body against `gh pr view --json files`. Its current default is "every `path.ext` token that looks like a file path is a change claim unless it lives inside a known reference shape (fenced code block, GitHub admonition, contextual H2 heading, bot `<details>` block)."

That default has shipped four narrow patches against the same class of recurrence (issues #1874, #1881, #1923, #2113, and now #2252). Authors who cite reference paths in narrative prose under `## Per-file changes`, `## Testing`, `## Summary`, or other change-context sections trip the gate and get blocked. Examples from the issue analyst's investigation (the issue analyst handoff):

- PR #2214 cited `.claude/commands/spec.md` inside `## Per-file changes` narrative prose describing what the new validator does.
- PR #2225 cited `.claude/skills/security-scan/scripts/scan_vulnerabilities.py` and `.agents/architecture/ADR-035-exit-code-standardization.md` inside `## Testing` prose ("Ran the security-scan skill ...").

Neither file was modified in those PRs. Both authors had to either rewrite the narrative or wait for a bypass label.

The class will keep recurring because:

1. The PR-body template at `.github/PULL_REQUEST_TEMPLATE.md` emits `## Summary`, `## Changes`, `## Testing`, `## Notes for Reviewers`, and `## Related Issues`. Of these, only `## Changes` is a change-claim section by contract. The other H2s carry narrative prose that legitimately cites reference paths.
2. `## Testing` cannot be added to `_CONTEXTUAL_SECTION_NAMES` wholesale because it ALSO carries real change claims when a PR adds or modifies a test file. A heading-level exemption alone cannot disambiguate.
3. AI agents that author PR bodies under `.claude/commands/push-pr.md` adapt the template freely and routinely cite reference paths in any section.

A decision is needed because Part A of this work (sibling implementer task) ships a mechanical fix to the failure message and stripper list, but does not change the default. Without a default-flip, the recurrence treadmill continues.

## Decision

Adopt **Option (c) Hybrid**: keep patterns 1 (bold `**path.ext**`) and 2 (bullet-list `^[-*+] path.ext`) firing in any context. Restrict patterns 0 (inline-backtick `` `path.ext` ``) and 3 (markdown-link `[path.ext](...)`) to fire only inside an explicit change-claim H2 section. The set of change-claim section names is `## Changes`, `## Per-file changes`, `## Files Changed`, `## Changed Files` (case-insensitive, exact match modulo trailing whitespace).

Concretely, in `extract_mentioned_files`:

1. After `_strip_informational_sections`, locate the spans of all H2 headings whose text matches `_CHANGE_CLAIM_SECTION_NAMES`. Each span runs from the heading line to the next H1 or H2 (the same boundary the existing stripper uses).
2. When iterating `FILE_MENTION_PATTERNS`, accept a match from patterns 0 and 3 only when `match.start()` falls inside a change-claim span. Patterns 1 and 2 accept anywhere.

Rationale for the split:

- **Bullet-list pattern 2** is the canonical autonomous-template shape: `- \`path.ext\`: description`. It is unambiguous and rarely appears in narrative prose. Keeping it unrestricted preserves real drift detection in PRs that bulleted their changes outside a `## Changes` heading.
- **Bold pattern 1 (`**path.ext**`)** is rare in narrative prose; it is almost always a deliberate emphasis on a specific changed file. Keeping it unrestricted preserves coverage with negligible false-positive risk.
- **Inline-backtick pattern 0** is the dominant false-positive shape. It fires on every reference, example, doc-link, and tool-name citation. It must be contextually scoped.
- **Markdown-link pattern 3** is overwhelmingly used to link to a file on GitHub (a reference, not a claim). It must be contextually scoped.

## Prior Art Investigation

### What Currently Exists

- **Structure being changed**: `extract_mentioned_files` and `FILE_MENTION_PATTERNS` at `scripts/validation/pr_description.py:144-150` and `pr_description.py:419-441`. Today every pattern fires anywhere not previously masked, and Check 1 (`validate_pr_description:533-547`) flags any extracted path missing from the diff as CRITICAL.
- **When introduced**: Validator predates the current contextual-section list. Patches: #1874 (extension boundary), #1881 (double-extension), #1923 (em-dash detection), #2113 (contextual sections), #2252 (this one).
- **Original author and context**: `scripts/validation/pr_description.py` was added to prevent the drift class "description says we changed X but the diff doesn't show X." It was tuned for terse, hand-written PR bodies where every inline-backtick path token was a change claim.

### Historical Rationale

- **Why was it built this way?** The validator was tuned for short, claim-only PR bodies. The "every backtick path is a claim" default was correct when PR bodies were terse and the only reason to cite a file path was to claim a change. The default-strip list (`_CONTEXTUAL_SECTION_NAMES`, `_REFERENCE_SECTION_PREFIXES`) was added as longer narrative PR bodies emerged.
- **What alternatives were considered?** Per the analyst findings, three options exist: (a) Strict, (b) Permissive, (c) Hybrid. The historical answer was "expand the strip list every time a new false positive shape shows up." That treadmill has run four times.
- **What constraints drove the design?** Concern that flipping the default would silently weaken real drift detection.

### Why Change Now

- **Has the original problem changed?** Yes. PR bodies are now overwhelmingly AI-authored (via `.claude/commands/push-pr.md`), structured against `.github/PULL_REQUEST_TEMPLATE.md`, and rich with narrative prose. The "every backtick path is a claim" assumption no longer matches the input distribution.
- **Is there a better solution now?** Yes. The autonomous PR template emits a stable `## Changes` H2 heading (template line 64). AI-authored bodies that adapt the template routinely emit `## Per-file changes` and `## Files Changed` as the change-claim heading. Restricting context-sensitive patterns to those headings is now feasible.
- **What are the risks of change?** A PR that lists changed files via inline-backtick in `## Summary` (rather than `## Changes`) would no longer be checked under patterns 0 and 3. Patterns 1 and 2 still cover this case if the author uses bold or a bulleted list, which the template encourages. Net coverage loss is small (see Regression Analysis below).

## Autonomous PR-Template Surface Audit

Grepped `.claude/commands/`, `.claude/skills/`, `.github/`, and the merged-PR sample for the change-claim section names actually emitted.

- `.github/PULL_REQUEST_TEMPLATE.md` is the canonical template. It emits `## Changes` at line 64 as the change-claim section, with a bulleted-list scaffold (`-`).
- `.claude/commands/push-pr.md` directs the agent to "Read `@.github/PULL_REQUEST_TEMPLATE.md`" and "adapt every section to your changes." It does not pin the section name; the agent inherits whatever heading the canonical template uses.
- No `.claude/skills/**/templates/**` PR-body template exists. The PR-body shape is entirely template-driven plus agent adaptation.
- 40 merged PRs (last 30 days, random sample) showed the following change-claim H2 headings in PR bodies:

| Heading | Count | Source |
|---|---|---|
| `## Changes` | 32 | canonical template |
| `## Per-file changes` | 4 | agent adaptation |
| `## Summary` | 40 | template (narrative, not change claim) |
| `## Testing` | 38 | template (narrative, not change claim) |

`## Files Changed` and `## Changed Files` did not appear in this sample but are common in hand-written PR bodies in other codebases. Including them defensively costs nothing and avoids a future patch when an author uses them.

The set of canonical change-claim section names is:

```
## Changes
## Per-file changes
## Files Changed
## Changed Files
```

The validator MUST match these case-insensitively at H2 with no other text on the heading line (modulo trailing whitespace), the same anchor used by `_CONTEXTUAL_SECTION_NAMES`.

## Regression Analysis (sample of 40 merged PRs)

Method: 40 PRs sampled uniformly at random (seed 2252) from the 208 PRs merged into `rjmurillo/ai-agents` between 2026-05-03 and 2026-06-02. For each PR, ran the current `extract_mentioned_files` and `validate_pr_description` Check 1 against the actual `pulls/{n}/files` list under four policies:

| Policy | Total CRITICAL Check-1 findings across 40 PRs |
|---|---|
| Baseline (current default) | 4 |
| Strict (only pattern 2, only in change-claim section) | 1 |
| Permissive (all 4 patterns, only in change-claim section) | 1 |
| Hybrid (chosen - patterns 0,3 context-restricted; 1,2 anywhere) | 1 |

All three candidate defaults remove the same 3 findings. Detail of removed findings:

| PR | Removed file | Spot-check verdict |
|---|---|---|
| #1873 | `.gemini/styleguide.md` | False positive. Cited inside `## Author Pre-flight` (`Code follows project style guidelines (.gemini/styleguide.md; ...)`) as a reference to the canonical style file, not a change claim. The PR did not modify `.gemini/styleguide.md`. |
| #1873 | `scripts/eval/README.md` | False positive. Cited inside `## Open Follow-ups (intentional deferral)` as a TODO note for a future PR, not a claim that this PR modified it. The PR did not modify it. |
| #1903 | `SOUL.md` | False positive. Cited inside `## Scope` as part of an "out of scope" enumeration (`Putting session-specific state in SOUL.md (it's the cornerstone, not a scratchpad)`). The PR did not modify `SOUL.md`. |

Zero true drift findings were removed. The one finding kept under all three policies (PR #1873 reference to `.agents/specs/{interviews,requirements,design,tasks}/...-1854-...md`) is itself an extraction artifact (brace-expansion shell notation, not a real file path) and is unaffected by the default-flip; it would require a separate stripping rule.

**Hybrid was chosen over Strict** because Strict drops bold and markdown-link patterns entirely (pattern 1 and 3 removed) for anywhere outside `## Changes`. While the regression sample shows zero loss for Strict, the sample is small (40 PRs, 4 baseline CRITICALs) and Hybrid preserves more drift-detection surface for the cost of zero added false positives in this sample.

**Hybrid was chosen over Permissive** because Permissive restricts pattern 2 (bullet-list) to the change-claim section. That gives up coverage of `Files modified:\n- foo.py\n- bar.py` shapes appearing in `## Summary`, which are reasonable hand-written claim forms. Hybrid keeps that coverage.

Confidence: MEDIUM. Sample size is small enough that rare false-positive shapes (e.g. inline-backtick claims authored outside `## Changes`) may not have surfaced. The rollback plan below addresses this.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|---|---|---|---|
| (a) Strict: only pattern 2, only in change-claim section | Simplest contract; smallest false-positive surface | Drops bold and markdown-link entirely; over-rotates to single canonical shape | Sample size too small to justify dropping two patterns wholesale |
| (b) Permissive: all 4 patterns, only in change-claim section | Single rule, easy to explain | Drops bullet-list coverage in `## Summary` (real hand-written claim form) | Loses real drift-detection surface for hand-written PR bodies |
| **(c) Hybrid: split by pattern** | Keeps unambiguous shapes anywhere; restricts ambiguous shapes | Two-rule contract slightly more complex | Best false-positive / true-positive tradeoff for the observed distribution |
| (d) Status quo + expanded strip list | Smallest diff | Already on patch 5; treadmill continues | Demonstrated four-patch failure mode |
| (e) Remove Check 1 entirely | Eliminates class | Loses all drift detection | Real drift IS a class worth catching |

### Trade-offs

- **Smaller false-positive surface, marginally smaller true-positive surface.** Inline-backtick claims in non-`## Changes` H2 sections will no longer trip the gate. The mitigation is the autonomous template: it scaffolds a `## Changes` bulleted list, and agents adapting it tend to put change claims there. Hand-authored PRs that diverge can use bold (`**path.ext**`) or a bullet list to keep coverage.
- **Two-rule contract.** Authors and reviewers must remember that "inline-backtick `path.ext` is informational unless it's under `## Changes`." This is documented in the new failure message (Part A) and in a SKILL pointer (see Implementation Notes).
- **Rollback is fast.** The change is a single function-level change in `extract_mentioned_files` plus a small new constant. Reverting restores the baseline.

## Consequences

### Positive

- Removes the #2252 recurrence and the entire class. PR #2214 / #2225 / similar narrative-prose citations stop tripping the gate.
- Eliminates the "expand the strip list" treadmill (issues #1874, #1881, #1923, #2113, #2252) for the inline-backtick / markdown-link shape.
- Aligns the validator with the actual PR-template contract: `## Changes` is where change claims live.
- Failure message authored in Part A now has a single rule to reference: "Move the path under `## Changes`, or use a bullet/bold, or wrap in a code fence."

### Negative

- Loses inline-backtick drift detection outside `## Changes`. A PR whose `## Summary` contains "Updated `foo.py` to fix bug" would no longer be checked under pattern 0. Mitigation: pattern 2 (bullet-list) and pattern 1 (bold) still fire; the canonical template encourages those shapes.
- Two-rule contract slightly more complex than "every backtick path is a claim." Mitigation: the failure message names the rule explicitly; the SKILL pointer documents it.
- Small sample (40 PRs, 4 baseline CRITICALs) leaves residual uncertainty. Mitigation: rollback plan below.

### Neutral

- The set of change-claim section names is a new constant. It is small (4 entries) and stable (no new entries needed for the observed template surface). It MUST live next to `_CONTEXTUAL_SECTION_NAMES` for discoverability.
- Sibling Part A's `Related Files` addition to `_CONTEXTUAL_SECTION_NAMES` is still useful: it provides defense in depth for PRs that explicitly call out reference files in their own section.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|---|---|---|---|
| `scripts/validation/pr_description.py` | Direct | Add `_CHANGE_CLAIM_SECTION_NAMES` constant; add `_change_claim_regions()` helper; thread region check into `extract_mentioned_files` loop | Low |
| `tests/test_validation_pr_description.py` | Direct | Add regression tests for PR #2214 / #2225 / #1873 / #1903 body shapes; add coverage for the four change-claim heading variants; add coverage for the "inline-backtick under `## Changes` IS still a claim" case | Low |
| `tests/test_pr_description.py` | Direct | Same as above (both test files import from the same module) | Low |
| `.github/workflows/pr-validation.yml` | Indirect | None. Check 1 still emits CRITICAL; only the extraction policy changes | Low |
| `.github/PULL_REQUEST_TEMPLATE.md` | Indirect | None. Template already emits `## Changes` as the change-claim section | None |
| `.claude/commands/push-pr.md` | Indirect | Optional: add a one-line note that "change claims belong under `## Changes`." Not required for correctness | Low |
| Failure message text (Part A) | Direct | Part A's actionable message MUST cite the new rule: "Inline-backtick file paths outside `## Changes` are informational." | Low - coordinated via follow-up implementer task |
| ADR-035 (exit codes) | Indirect | None. Validator still exits 0/1/2 per ADR-035 | None |

## Implementation Notes

The follow-up implementer task (spawned as a child of this kanban task) MUST:

1. Add `_CHANGE_CLAIM_SECTION_NAMES: tuple[str, ...] = (r"Changes", r"Per[- \t]?file[ \t]+changes", r"Files[ \t]+Changed", r"Changed[ \t]+Files")` next to `_CONTEXTUAL_SECTION_NAMES`.
2. Add `_change_claim_regions(cleaned: str) -> list[tuple[int, int]]` that returns the spans of each matching H2 section, using the same terminator regex as the existing stripper (`(?=^#{1,2}(?!#)|\Z)`).
3. In `extract_mentioned_files`, after `_strip_informational_sections`, compute regions once. In the per-pattern loop, accept matches for `FILE_MENTION_PATTERNS[0]` (inline-backtick) and `FILE_MENTION_PATTERNS[3]` (markdown-link) only when `match.start()` is inside a region. Patterns 1 and 2 unchanged.
4. Tests MUST cover:
   - PR #2214 body shape (inline-backtick `.claude/commands/spec.md` in `## Per-file changes` narrative). Asserts: not flagged.
   - PR #2225 body shape (inline-backtick under `## Testing`). Asserts: not flagged.
   - PR #1873 body shape (inline-backtick `.gemini/styleguide.md` in `## Author Pre-flight`). Asserts: not flagged.
   - "Inline-backtick `foo.py` IS still a claim when it appears under `## Changes`." Asserts: flagged if not in diff.
   - "Bold `**foo.py**` in `## Summary` IS still a claim." Asserts: flagged if not in diff.
   - "Bullet-list `- bar.py` in `## Summary` IS still a claim." Asserts: flagged if not in diff.
   - All four `_CHANGE_CLAIM_SECTION_NAMES` variants accepted case-insensitively.
5. The failure-message text from Part A MUST be amended to name the rule: "Inline-backtick file paths outside `## Changes` / `## Per-file changes` / `## Files Changed` / `## Changed Files` are informational. Move the path under one of those headings, use a bullet (`- path.ext`) or bold (`**path.ext**`), or wrap in a code fence."
6. The implementer MUST run the regression simulator at `.agents/analysis/2252-pr-description-default-flip-regression-sim.py` (sample-of-40 PRs) after the change and confirm baseline -> hybrid totals match this ADR.

### Rollback Plan

If the new default produces a regression (a real drift that the old default would have caught), the rollback is a single PR that:

1. Reverts the `_CHANGE_CLAIM_SECTION_NAMES` constant and the `_change_claim_regions()` helper.
2. Reverts the per-pattern region check inside `extract_mentioned_files`.
3. Leaves the test cases in place but inverts the assertions on the "not flagged" cases.

Detection signal: any merged PR whose post-merge `gh pr view --json files` shows a file that was claimed in the body but NOT modified, where the body shape would have been caught by baseline but not by hybrid. The `description-validation-bypass` label usage rate is a leading indicator: a spike post-ship is a signal that the new default is too permissive. Sibling Part A's actionable failure message already surfaces the bypass label, so usage is observable.

## Related Decisions

- **ADR-035** - Exit code standardization. This ADR does not change exit code behavior.
- **Sibling kanban task** - Part A mechanical fix (kanban `t_f23fc721`): adds `Related Files` to the contextual-section list and makes Check 1's failure message actionable. Part A ships first as a low-risk patch; Part B (this ADR's follow-up) ships after ADR review.
- Prior recurrence patches: PR/issue #1874, #1881, #1923, #2113.

## References

- Analyst findings: the issue analyst handoff
- Issue #2252 (rjmurillo/ai-agents)
- PR #2214, PR #2225 (false-positive recurrences)
- `scripts/validation/pr_description.py` (the validator)
- `.github/PULL_REQUEST_TEMPLATE.md` (canonical PR-body template)
- `.claude/commands/push-pr.md` (autonomous PR-body author)
- Regression simulator: `.agents/analysis/2252-pr-description-default-flip-regression-sim.py` (40-PR sample, seed 2252)

---

*Template Version: 1.1*
