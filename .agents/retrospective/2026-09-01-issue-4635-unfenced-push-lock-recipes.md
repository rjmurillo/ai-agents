# Retrospective: issue-4635

## Session Info
- **Date**: 2026-09-01
- **Agents**: Claude Code (implementer)
- **Task Type**: Bug
- **Outcome**: Success

## Phase 0: Data Gathering
Observe: `scan_text` reported a variable-held lock path inside a fence and
returned nothing for the same three lines outside one. Measured on
origin/main before any edit: fenced returned `[(2, '/var/locks/branch.lock')]`,
unfenced returned `[]`.

Respond: Grouped unfenced prose into paragraph-sized runs and passed each run
through the same `_lock_targets` resolver the fenced path already used, rather
than duplicating the variable, redirect, and continuation logic.

Analyze: Two design choices could not be settled by reading the code, so both
were measured against the 3518 tracked Markdown files before the fix was
written. Reporting the "names no canonical path" finding on unfenced runs
fired on 13 files that only mention `flock`, including this rule's own mirror.
Suppressing it fired on 1 file, the 2026-08-02 census paragraph, which is
evidence rather than a recipe.

Apply: Measure the blast radius of a detection widening before writing it, not
after the corpus test goes red. The measurement chose the design; it did not
merely confirm it.

Execution trace:
1. `ce4c1e4c9` marked the census paragraph historical.
2. `d0d9c7961` scanned unfenced runs with the fenced resolver.
3. `cc2888a97` corrected the rule text and regenerated its mirror.
4. `ffb35fe08` scoped the citation gate off a tmp-repo fixture path.

Outcome classification: Glad that the corpus probe ran before the design was
committed, because it inverted the approach the issue's own PRD proposed. Sad
that the first placement of the citation-gate marker was three lines above the
citing line and failed a gate that documents the one-line rule plainly. No
lasting failure remained.

## Phase 1: Insights Generated
Five Whys:
1. A non-canonical lock path could ship unnoticed in unfenced Markdown.
2. The unfenced path scanned one line at a time.
3. A line-level scan cannot see an assignment and its use together.
4. Variable resolution was added to `_scan_block` for fences and never reached
   the unfenced fallback.
5. The two paths were written as different units, so a feature added to one
   silently did not exist in the other.

Root cause: One behavior lived in two code paths with no shared resolver, so
the paths drifted. This is failure mode 2, Partial Coverage, because the gate
reported success while an entire input shape went unexamined.

Patterns and shifts: The fix removed the second path rather than teaching it
the same tricks. Two units now differ only in the one place where they must,
the missing-path finding, and that asymmetry is pinned by a test on each side.

Learning matrix: Keep the shared-resolver structure. Add a corpus probe before
widening a detector. Drop the assumption that a documented plan has measured
its own corpus claim.

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Measure both candidate designs over the corpus before coding | 13 files vs 1 file, probe run pre-fix | 9 | 90% |
| Route both units through one resolver | `d0d9c7961` | 9 | 90% |
| Negative control on the scanner alone | 8 new tests red, 40 pre-existing green | 9 | 95% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Placed the citation-gate marker three lines above its citation | Contract misread | Marker rule is one line, not one comment block | Read the gate's own message before placing a marker | 85% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| The issue's PRD proposed delegating unfenced runs straight to `_scan_block` | Corpus probe showed it fires on 13 files and contradicts an existing test | A plan's design section is a hypothesis, not a measurement |
| Test file crossed the 500-line taste limit | Split along the same seam the scanner has, shared builders extracted | Fix the count, do not raise the baseline |

## Phase 3: Decisions

### Action Classification
| Class | Action | Owner | Reference |
|-------|--------|-------|-----------|
| Keep | One resolver behind both scan units | Issue #4635 implementation | `d0d9c7961` |
| Add | Corpus probe before widening a detector | Future implementers | This retrospective |
| Modify | Mark historical prose, do not rewrite the record | Issue #4635 implementation | `ce4c1e4c9` |
| Drop | Line-level unfenced fallback | Issue #4635 implementation | `d0d9c7961` |

### SMART Validation
The probe action is specific to detector widenings, measurable as a count of
newly flagged tracked files per candidate design, achievable with the checker's
own `scan_text`, relevant because a widening that fires on the corpus cannot
merge, and applied before the implementation is written rather than after.

### Action Sequence
1. Write the candidate detection as a probe against the existing module.
2. Count newly flagged tracked files for each candidate design.
3. Choose the design from that count, then implement it.
4. Triage any remaining true positives with the sanctioned opt-out.

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Measure a detector widening against the corpus before choosing its design, not after the corpus test fails.
- **Atomicity Score**: 90%
- **Evidence**: The two candidates differed 13 files to 1; the count, not taste, selected the shipped design.
- **Skill Operation**: TAG
- **Target Skill ID**: empirical-probe-toolkit

### Learning 2
- **Statement**: When one behavior has two code paths, a feature added to one is absent from the other until a shared resolver forces agreement.
- **Atomicity Score**: 90%
- **Evidence**: Variable resolution existed in `_scan_block` for fences and nowhere else; `d0d9c7961` removes the second path.
- **Skill Operation**: TAG
- **Target Skill ID**: code-qualities-assessment

## Skillbook Updates

### ADD
```json
{}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| None | None | None | Executable tests own these task-specific contracts |

### TAG

| Skill ID | Tag | Reason |
|----------|-----|--------|
| empirical-probe-toolkit | corpus-probe-before-widening | Counted blast radius chose the design |
| code-qualities-assessment | one-behavior-one-path | Duplicate paths drift silently |
