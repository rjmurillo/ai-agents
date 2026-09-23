# Retrospective: PR #3076 hook performance remediation

## Session Info
- **Date**: 2026-07-16
- **Agents**: Copilot CLI, GPT-5.6 Sol, Copilot reviewer, CodeRabbit, Cursor Bugbot
- **Task Type**: Bug
- **Outcome**: Success

## Phase 0: Data Gathering

### 4-Step Debrief

- **Observe**: Windows Defender amplified the cost of broad hooks. The baseline trace recorded 355 process starts and 5,586.946 ms of direct wrapper lifetime.
- **Respond**: Removed repeated advisory registrations, narrowed four shell gates, repaired Windows hook failures, and hardened generated-file publication.
- **Analyze**: Host-side filtering removed 23 causal process starts. Safety dispatchers remained active. Review then exposed transaction, backup, locking, and stale-shim gaps before merge.
- **Apply**: Keep policy gates at protected boundaries. Publish generated hook artifacts through one locked transaction. Reject files absent from the manifest.

### Execution Trace

1. Measured Copilot CLI 1.0.70 with GPT-5.6 Sol under Windows Defender.
2. Removed one repeated advisory hook. Process starts fell from 355 to 352.
3. Scoped four shell matchers. Final traces recorded 334 and 332 starts, with zero direct wrappers.
4. Rejected an unsafe Claude-side multiplexer after contract review.
5. Added token matchers, loader error handling, and generated companion integrity.
6. Added a run-wide filesystem transaction, cross-process lock, immutable first backup, and metadata-preserving replacement.
7. Removed 20 stale generated matcher shims. Added a reverse manifest test.
8. Closed all review threads through commit-specific replies.

### Outcome Classification

- **Glad**: The delivered change removed 23 causal process starts without disabling safety gates.
- **Sad**: The first multiplexer prototype optimized a different protocol and had to be reverted.
- **Mad**: Generated output had no reverse ownership check, so renamed matcher shims remained shipped.

Evidence: [PR #3076](https://github.com/rjmurillo/ai-agents/pull/3076), [issue #3075](https://github.com/rjmurillo/ai-agents/issues/3075), [matcher commit](https://github.com/rjmurillo/ai-agents/commit/0077a4b3), [transaction commit](https://github.com/rjmurillo/ai-agents/commit/a4ac9b91), and [stale-shim guard commit](https://github.com/rjmurillo/ai-agents/commit/e187157d).

## Phase 1: Insights Generated

### Five Whys: unsafe multiplexer

1. Why was the prototype reverted? It concatenated protocol outputs and serialized host-concurrent hooks.
2. Why did it change the protocol? It treated process reduction as the primary contract.
3. Why was process reduction primary? The prototype lacked explicit merge and blocking semantics.
4. Why were those semantics absent? It measured speed before proving parity with the host contract.
5. Why was parity not proved first? The implementation started from the desired mechanism, not runtime evidence.

**Root cause**: FM-9, confident-incorrectness recurrence. The prototype asserted parity from partial signals.

### Five Whys: repeated generation review findings

1. Why did review find several rollback defects? Publication initially protected only part of the generated set.
2. Why was the set partial? Dispatcher artifacts followed a separate direct-write path.
3. Why did that path exist? The generator modeled files as independent outputs.
4. Why was independence unsafe? A failed run could expose mixed versions to customers.
5. Why did tests miss this first? Tests asserted file writes, not whole-run atomicity.

**Root cause**: Test-Implementation Drift. This was an FM-11 near miss, caught before a customer-facing generated artifact shipped.

### Fishbone Analysis

| Factor | Contribution |
| --- | --- |
| Process | Per-file publication hid the run-wide consistency boundary. |
| Design | Backup lifetime and repeated publication were not explicit invariants. |
| Testing | Early tests covered rollback paths without hard-link and partial-replacement controls. |
| Environment | Windows Defender made each extra process and replacement path expensive. |
| Tooling | The generator had no reverse manifest check for stale outputs. |

### Patterns and Shifts

- Shifted from counting registered hooks to tracing actual process subtrees.
- Shifted from per-file rollback to one transaction over every generated hook artifact.
- Shifted from forward-only generation checks to forward and reverse ownership checks.
- Kept model-tier profiles analytical because no controlled cross-model test exists.

### Learning Matrix

| | Worked | Did Not Work |
| --- | --- | --- |
| Expected | Host-side matchers skipped unrelated commands before process creation. | Broad advisory hooks repeated context on compliant calls. |
| Unexpected | Windows named-stream tests proved the original file object preserves security metadata. | Direct dispatcher writes mutated hard-linked rollback backups. |

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Filter commands before process creation | Final traces removed 23 causal starts and all direct wrappers | 10 | 95% |
| Keep Python policy checks authoritative | Wrapped, chained, path-qualified, and piped cases stayed covered | 9 | 95% |
| Publish generated outputs transactionally | 133 generator tests covered commit, rollback, replacement, and locking | 10 | 95% |
| Add a reverse manifest guard | Zero unregistered matcher shims remained after 20 stale files were removed | 9 | 95% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Claude-side multiplexer prototype | FM-9 confident-incorrectness recurrence | Speed was measured before protocol parity | Prove runtime and merge contracts before optimizing process topology | 95% |
| Per-file generator publication | Test-Implementation Drift | Tests omitted the run-wide consistency invariant | Stage every output, then publish under one transaction and lock | 95% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Windows replacement could mutate a file before returning failure | Detect API-created backups and restore the original object | Model documented partial failures in negative tests |
| Repeated publication could overwrite the original rollback backup | Keep the first backup immutable and use disposable API backups | Backup lifetime is part of transaction state |
| Concurrent failed runs could restore older output over newer output | Hold one cross-process lock through backup, commit, and rollback | Lock the full transaction, not each file |
| Stale generated shims remained after matcher renames | Remove 20 shims and compare directory contents to the manifest | Generation requires a reverse ownership check |

## Phase 3: Decisions

### Action Classification

| Category | Finding | Action |
| --- | --- | --- |
| Keep | Host-side command-family matching | Retain the matchers and their positive, negative, and edge tests. |
| Drop | Direct per-file dispatcher publication | Route dispatchers through the same transaction as scripts and configuration. |
| Add | Reverse manifest validation | Reject generated matcher shims absent from the dispatcher manifest. |
| Modify | Windows hook performance memory | Record the transaction, immutable backup, and stale-shim prevention rules. |

### SMART Validation

| Learning | Specific | Measurable | Attainable | Relevant | Timely |
| --- | --- | --- | --- | --- | --- |
| Filter unrelated shell calls before starting PowerShell, Python, or Git. | Yes | 23 causal starts removed | Yes | Windows hook calls | Before wrapper launch |
| Stage generated dispatchers before publishing any hook artifact transaction. | Yes | Generator rollback tests | Yes | Generated hook builds | Before publication |
| Keep the first rollback backup immutable across repeated generated-file publications. | Yes | Repeated-publication tests | Yes | Transaction rollback | At first backup |
| Reject unregistered generated matcher shims with a reverse manifest test. | Yes | Zero stale shims | Yes | Matcher generation | During validation |

### Action Sequence

| Order | Action | Depends On | Blocks |
|-------|--------|------------|--------|
| 1 | Define one run-wide artifact transaction | None | Actions 2 and 3 |
| 2 | Stage dispatcher artifacts off-tree | Action 1 | Action 4 |
| 3 | Preserve first backup and lock transaction | Action 1 | Action 4 |
| 4 | Add rollback and concurrency negative tests | Actions 2 and 3 | Action 5 |
| 5 | Remove stale shims and add reverse validation | Action 4 | Merge |

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Filter unrelated shell calls before starting PowerShell, Python, or Git.
- **Atomicity Score**: 95%
- **Evidence**: Traces fell from 355 starts to 332 and 334, with 23 causal starts removed.
- **Skill Operation**: TAG
- **Target Skill ID**: hook-performance-windows

### Learning 2
- **Statement**: Stage generated dispatchers before publishing any hook artifact transaction.
- **Atomicity Score**: 95%
- **Evidence**: Off-tree staging prevents direct writes from corrupting transaction backups.
- **Skill Operation**: TAG
- **Target Skill ID**: hook-performance-windows

### Learning 3
- **Statement**: Keep the first rollback backup immutable across repeated generated-file publications.
- **Atomicity Score**: 95%
- **Evidence**: Repeated-publication tests caught original-backup overwrite and proved the disposable-backup design.
- **Skill Operation**: TAG
- **Target Skill ID**: hook-performance-windows

### Learning 4
- **Statement**: Reject unregistered generated matcher shims with a reverse manifest test.
- **Atomicity Score**: 95%
- **Evidence**: The guard exposed 20 stale shims and now reports zero unregistered files.
- **Skill Operation**: TAG
- **Target Skill ID**: hook-performance-windows

## Skillbook Updates

### ADD

None. The existing hook performance memory owns these learnings.

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| hook-performance-windows | Matcher and Windows failure evidence | Add transaction, immutable backup, locking, and reverse manifest rules | Keeps one source for PR #3076 lessons |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| hook-performance-windows | helpful | 23 causal process starts removed | High |
| hook-performance-windows | helpful | 412 hook tests and 133 generator tests passed | High |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| None | No stored skill became invalid | Deduplication retained one owner memory |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| Host-side shell filtering | hook-performance-windows | 95% | Update existing memory |
| Transactional hook publication | feedback-generated-artifact-runtime-verification | 70% | Update hook-specific memory |
| Immutable rollback backup | hook-performance-windows | 85% | Update existing memory |
| Reverse matcher manifest | feedback-generated-artifact-runtime-verification | 75% | Update hook-specific memory |
