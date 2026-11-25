# ADR Debate Log: re-anchor ADR citations of rules cut by trigger widening

## Summary

- **Rounds**: 2 of 10
- **Outcome**: Consensus after round 2 fixes
- **Final Status**: unchanged for every ADR. ADR-083, 084, 097, 102, and 108 stay accepted. ADR-110 stays proposed.
- **Scope**: citations of six cut rules in ADR-083, ADR-084, ADR-097, ADR-102, ADR-108, and ADR-110.
- **Cut rules**: push-lock, security, tool-use-hook-bar, python, retros, and testing.
- **Panel**: reduced panel, architect and critic.
- **Why reduced**: five ADRs change citations only. ADR-110 records an owner move the repo owner decided. No gate logic changes.
- **Base**: `ce18cc4d70`.

An eval on 2026-11-24 showed six rules route as well through skills as the loaded rule.
The report is `evals/reports/rule-activation-trigger-widening-2026-11-24.md`.
Each rule now lives as a skill reference under `.claude/skills/<skill>/references/`.

## Method

- Same method as `context-diet-rule-citation-reanchor-2026-11-24-debate-log.md`.
- A cut rule's citation reads "the former `X` rule (now at `<successor path>`)".
- Text that describes the old file keeps that meaning, because it names the former rule.
- Every successor path uses the `.claude/skills/...` form.

## Owner decision (ADR-110)

- The `security` rule owned the capability `untrusted-content-handling`.
- `check_capability_graph.py` reads canonical owners only from `templates/`.
- A skill reference file is not a graph node, so it cannot own a capability.
- Owning it in the `security-review` skill template pushed the F6 fixture over its ceiling.
- Richard chose `templates/rules/universal.md` as the new owner on 2026-11-24.
- `universal.md` gains a `metadata.capability` block of six frontmatter lines.
- ADR-110 records the move as a dated amendment in section 7 and Implementation Notes.

## Round 1

Critic verdict: REVISE. Architect verdict: ACCEPT-WITH-CHANGES.

### Accepted

- ADR-097:294 claimed the successor "already states" a quote it does not hold. It now reads as history, with a note.
- ADR-097:358 put a possessive after a closing parenthesis. The section is now named first.
- ADR-097:459 had nested parentheses. It now uses commas.
- ADR-110 moved the owner with no date, decision-maker, or reason. Both owner lines are now dated amendments.
- ADR-110 now says the owner loads on every path.
- ADR-084:276 now says the cost model loads only through the `skillforge` skill.
- `templates/rules/universal.md:93` credited the deleted security rule. It now points at `rule-security.md`.
- `rule-testing.md:46` shipped a template escape `$\{{` in a plain file. It now reads `${{`.

### Resolved between the seats

- **Path prefix.** The critic asked for `src/claude/skills/...`. The architect asked for `.claude/skills/...`.
- Resolved toward `.claude/skills/...` for consistency with the other five ADRs.
- ADR-110:120-123 classes both `src/claude/` and `.claude/` as projections. Either path is a pointer, not an owner.
- **ADR-097:388.** The critic asked to rewrite the row. The architect cited the precedent method.
- The row describes the old file, so it stays as history.

## Round 2

Critic verdict: REVISE. Architect verdict: ACCEPT-WITH-CHANGES.

### Accepted

- ADR-097:458-459 left a line that opened with a comma. The comma moved up a line.
- ADR-110 said the graph check "scans only `templates/` trees". It reads projection trees too. The text now cites the canonical globs.
- ADR-110 called the reference a consumer. It has no capability block. The text now says it is not a graph node.
- ADR-110 Implementation Notes cited the deleted `templates/rules/security.md`. It now names the former rule.
- ADR-110 section 7 let the partials list read as what the security rule held. The sentence now names the files first.
- ADR-097:388 read as if the successor had generated mirrors. It now reads "then with generated mirrors".

### Noted, not changed

- Eight other ADRs still cite the old paths in Context, Prior Art, Impact, or References sections.
- `check_adr_lifecycle.py` does not read those sections, so they stay as history.

## Gates

- `check_adr_lifecycle.py`: exit 0. ADR-097 sits at its 500-line cap.
- `check_capability_graph.py`: exit 0.
- `tests/validation/test_untrusted_content_partial_parity.py`: 5 passed.
