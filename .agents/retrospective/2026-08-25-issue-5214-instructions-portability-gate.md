# Retrospective: Issue #5214 instructions/ portability coverage gap

## Session Info
- **Date**: 2026-08-25
- **Agents**: Claude (autoplan router, direct implementation)
- **Task Type**: Bug (governance gate coverage gap)
- **Outcome**: Success

## Phase 0: Data Gathering

**4-Step Debrief**

- Observe: Issue #5214 reported that `src/copilot-cli/instructions/ci-scripts.instructions.md`
  named six upstream-only paths (`scripts/validation/pre_pr.py`, the `scripts/ci/` count
  ratchets, etc.) with no `vendor-portability` declaration, violating
  `.claude/rules/plugin-self-containment.md` MUST 1. A bare `.claude/skills/<name>` reference
  in the same file also violated MUST 2 (plugin-root env-var form).
- Respond: read the issue's own "why the generator cannot fix this" analysis, then read
  `plugin-self-containment.md` and `check_skill_md_portability.py` to find the actual coverage
  boundary rather than trusting the issue's framing at face value.
- Analyze: confirmed the existing ratchet (`check_skill_md_portability.py`) scans plugin
  `skills/` trees plus `.claude/commands` and `templates/agents` (`EXTRA_SCAN_ROOTS`), but never
  the sibling `<root>/instructions/` directories the rules generator writes. Neither the
  plugin-root scan (wrong subtree) nor the generator's `_INTERNAL_PATH_PREFIXES` filter
  (`applyTo` globs only, not body prose) covered it. This is a genuine, previously-invisible
  gate gap, not a one-off content bug.
- Apply: fixed the specific file (declaration + reword) AND closed the gate gap (extended
  `EXTRA_SCAN_ROOTS`), per the issue's acceptance criteria requiring both.

**Execution Trace**: fetched issue -> read `plugin-self-containment.md`,
`ci-scripts.md`, `check_skill_md_portability.py` -> edited canonical rule source
(declaration + reword) -> regenerated mirrors -> extended `EXTRA_SCAN_ROOTS` ->
ran gate, found 14 pre-existing offending files in the newly-scanned root ->
iterated the marker text against `marker_path_drift` until it reached 0 findings
(first attempt declared 6 exact-file paths and left 8 stale/undeclared findings
because several matched only inside fenced code blocks, which the drift
extractor strips) -> added 6 tests -> updated the ratchet baseline
(`--allow-marker-grow`) to grandfather the pre-existing debt -> ran the full
test file (240 tests) and `pre_pr.py` (57 validators) -> committed in two
atomic commits -> pushed (required an unshallow fetch and a retrospective
artifact per repo push gates).

**Outcome Classification**:
- Glad: the `marker_path_drift` iteration loop (declare -> run -> read exact
  findings -> refine) converged in two rounds because the tooling reports
  precise stale/undeclared/existence findings rather than an aggregate count.
- Sad: nothing; no rework beyond the expected marker-declaration iteration.
- Mad: nothing.

## Phase 1: Insights Generated

**Learning Matrix**

| Category | Insight |
|---|---|
| Keep doing | Reading the target script's source before writing a fix, rather than trusting the issue body's framing of "why the generator cannot fix this" verbatim. The issue was accurate, but confirming it against `check_skill_md_portability.py` directly found the exact extension point (`EXTRA_SCAN_ROOTS`) instead of guessing at a new mechanism. |
| Keep doing | Verifying a `vendor-portability` marker's precision against `marker_path_drift()` directly (a small Python one-liner) instead of trusting that "the marker suppresses everything" is good enough. The ratchet's marker/drift baselines are a distinct, exact-count contract from the count ratchet. |
| Start doing | When extending a scan scope that will surface pre-existing debt, run the gate once *before* touching the baseline to see the real shape of what will be grandfathered, and diff the baseline file afterward to confirm only the intended keys changed. |
| Stop doing | Assuming a repo-specific pre-push gate failure (staleness, retrospective) is a bug in the change under test before checking whether it is a documented repo policy that resolves once the natural next step (commit, in this case) happens. |

## Phase 2: Diagnosis

No failures occurred in this session; the diagnosis section is limited to near
misses.

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Extend the existing `EXTRA_SCAN_ROOTS` list instead of writing a new checker | One three-line tuple addition plus a docstring update closed the coverage gap; zero new script files | 8 | 85% |
| Grandfather pre-existing debt via `--update-baseline --allow-marker-grow` rather than hand-fixing 14 unrelated files | Kept the change scoped to issue #5214's acceptance criteria; avoided an unbounded "ocean" | 7 | 80% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|---------------------|----------|----------|
| First `vendor-portability` marker draft declared six exact file paths (e.g. `scripts/ci/ruff_count_ratchet.py`), three of which appeared only inside a fenced code block in the rule body | `marker_path_drift()` reported the exact stale/undeclared paths; switched to directory-level declarations (`scripts/ci`, `scripts/validation`, etc.) that cover descendants via component-prefix matching | The drift extractor strips fenced code before matching, so a marker that names an example-only path goes stale; prefer directory-level declarations for a rule whose body legitimately names many files. |
| `build/audit/GENERATION-AUDIT.md` almost got declared as a bare `build/audit` directory prefix | Checked the filesystem: `build/audit/` does not exist in a clean checkout (only the exact file is exempted in `_GENERATED_ARTIFACTS`); declared the exact file path instead | A directory-prefix declaration must itself resolve on disk unless the exact path is in the generated-artifacts exemption list; check existence before choosing prefix granularity. |

## Phase 3: Decisions

### Action Classification

| Action | Classification |
|---|---|
| Extend `check_skill_md_portability.py` `EXTRA_SCAN_ROOTS` | Add (shipped this session) |
| Fix `ci-scripts.md` declaration + reword | Add (shipped this session) |
| Widen the same gate to `.claude/rules/*.md` itself (also a shipped plugin surface, currently unscanned) | Defer; out of scope for #5214, no acceptance criterion named it. Flagged as a follow-up below. |

### Action Sequence

1. Canonical source fix -> regenerate mirrors (must precede the gate extension so the gate
   measures the corrected file, not the pre-fix one).
2. Gate extension -> baseline update (must run after the source fix so the new baseline
   grandfathers only genuinely pre-existing debt, not the issue's own defect).
3. Tests -> full suite -> `pre_pr.py` -> commit -> push.

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: A vendor-portability marker's declared paths must match prose outside fenced code blocks.
- **Atomicity Score**: 82%
- **Evidence**: `marker_path_drift()` in `scripts/validation/check_skill_md_drift.py` strips fenced/indented code before extracting prose paths, so a declared path that appears only inside a ```bash block reports as stale.
- **Skill Operation**: TAG
- **Target Skill ID**: N/A (repo-mechanics fact, not an agent behavior pattern; recorded here rather than skillbook)

### Learning 2
- **Statement**: A directory-prefix vendor-portability declaration must itself resolve on disk.
- **Atomicity Score**: 78%
- **Evidence**: `marker_path_drift()`'s existence check (class c) resolves every declared and prose path against the repo root; `build/audit` (the bare directory) does not exist, only `build/audit/GENERATION-AUDIT.md` does, and only the exact file is exempted via `_GENERATED_ARTIFACTS`.
- **Skill Operation**: TAG
- **Target Skill ID**: N/A

## Skillbook Updates

### ADD

None. Both learnings are narrow repo-mechanics facts about one validator's extraction regex, not generalizable agent behavior patterns worth a skillbook entry.

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| (none proposed) | n/a | n/a | n/a |

## Phase 5: Persist and Close

### Memory Persistence

| Learning | Atomicity | Existing Match | Result |
|----------|-----------|----------------|--------|
| Marker declarations must match non-fenced prose | 82% | None found (searched `marker_path_drift`, `vendor-portability`) | Recorded in this retrospective only; below the generalizability bar for a standalone Serena memory entry (repo-internal, single-validator mechanic already documented in `check_skill_md_drift.py`'s own docstring) |
| Directory-prefix declarations must resolve on disk | 78% | None found | Same as above |

### +/Delta

#### + Keep
- Reading the actual scanner source (`check_skill_md_portability.py`,
  `check_skill_md_drift.py`) before deciding how to extend it, rather than
  guessing at the mechanism from the issue body alone.
- Verifying the new gate against the full corpus before updating the baseline,
  so the baseline diff could be inspected and confirmed to add only the
  expected keys.

#### Delta Change
- Could have checked `marker_path_drift()`'s extraction behavior (fenced-code
  stripping, existence checks) before drafting the first marker, rather than
  iterating once against real output.

### Delta Triage

#### Actionable Items Identified

| Delta Item | Category | Priority | Destination | Reference |
|------------|----------|----------|-------------|-----------|
| `.claude/rules/*.md` itself ships as part of the `.claude/` plugin root but is not scanned by `check_skill_md_portability.py` (only `<root>/skills/`, `.claude/commands`, `templates/agents`, and now `src/copilot-cli/instructions` are) | Tool Gap | P3 | Skip | Out of scope for #5214; would grandfather a much larger, unmeasured debt corpus across every rule file. Worth its own issue if it matters. |

#### Issues Created

None. The one delta item above is P3 and skipped rather than filed, per the triage above.

#### Backlog Items Stored

None.

#### Skipped Items

| Item | Reason |
|------|--------|
| Widen the portability gate to `.claude/rules/*.md` | Out of scope for #5214; not named in its acceptance criteria; unmeasured blast radius |

### ROTI Assessment

**Score**: 3

**Benefits Received**:
- Closed a real, previously-invisible gate coverage gap (not just the one reported file).
- Left a precise, evidence-based follow-up note (not filed as a new issue, since it is P3 and speculative) instead of silently expanding scope.

**Time Invested**: One session, two commits.

**Verdict**: Continue

### Helped, Hindered, Hypothesis

#### Helped
- Direct access to run the scanner's Python functions ad hoc
  (`marker_path_drift`, `count_marker_suppressed_refs`) to get exact,
  itemized findings instead of guessing from aggregate counts.

#### Hindered
- Nothing significant; the push-time gates (unshallow fetch, retrospective
  evidence) were undocumented in-session but resolved on the first read of
  their own error output.

#### Hypothesis
- For a future vendor-portability marker on a file with many named example
  paths, draft the marker with directory-level prefixes from the start
  (matching the existing plugin-self-containment.md pattern) rather than
  enumerating exact files, to avoid the fenced-code staleness trap entirely.
