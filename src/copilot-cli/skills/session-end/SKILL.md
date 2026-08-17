---
name: session-end
description: Validate and complete an existing optional session log. Auto-populates
  end evidence and runs validation. Use only when an opted-in log exists. Do NOT
  use merely because a session is ending or a commit is pending. Do NOT use to
  create a new log (use session-init) or repair a rejected log (use session-log-fixer).
version: 1.0.0
license: MIT
metadata:
  domains:
    - session-protocol
    - compliance
    - automation
  type: completion
---

# Session End

Validate and complete an existing optional session log.

---

## Quick Start

### Automated (Recommended)

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/session-end/scripts/complete_session_log.py"
```

The script will:

1. Find the current session log automatically
2. Auto-populate session end evidence from git state
3. Run markdown lint on changed files
4. Validate with validate_session_json.py
5. Report pass/fail with actionable next steps

### Preview Changes First

```bash
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/session-end/scripts/complete_session_log.py" --dry-run
```

---

## Triggers

| Phrase | Action |
|--------|--------|
| `/session-end` | Complete and validate current session log |
| `complete session` | Natural language activation |
| `finalize session` | Alternative trigger |
| `validate session end` | Alternative trigger |
| `finish session` | Alternative trigger |

| Input | Output | Quality Gate |
|-------|--------|--------------|
| Session log (auto-detected or specified) | Validated, completed session log | Exit code 0 from validation |

---

## When to Use

Use this skill only after a contributor explicitly opted into a session log and
wants to complete or validate that artifact. Ending work, committing, pushing,
or opening a PR does not require a session log.

Specifically:

- An opted-in session log needs end evidence populated
- An existing log should be validated before it is committed
- A previously committed log needs a targeted correction

Use [session-init](../session-init/SKILL.md) instead when:

- A contributor explicitly chooses to create a new optional session log

Use [session-log-fixer](../session-log-fixer/SKILL.md) instead when:

- Validation of an existing log failed with a specific error
- Working with an opted-in log from a previous PR

---

## Process Overview

```text
User Request: /session-end
    |
    v
+---------------------------------------------+
| Phase 1: FIND SESSION LOG                    |
| - Auto-detect most recent session JSON       |
| - Prefer today's sessions                    |
| - Accept explicit -SessionPath               |
+---------------------------------------------+
    |
    v
+---------------------------------------------+
| Phase 2: GATHER EVIDENCE                     |
| - Ending commit SHA (git rev-parse)          |
| - HANDOFF.md modification check              |
| - Serena memory update check                 |
| - Run markdown lint on changed files         |
| - Check for uncommitted changes              |
+---------------------------------------------+
    |
    v
+---------------------------------------------+
| Phase 3: UPDATE SESSION LOG                  |
| - Auto-populate evidence fields              |
| - Mark completed items                       |
| - Evaluate checklist completeness            |
| - Write updated JSON                         |
+---------------------------------------------+
    |
    v
+---------------------------------------------+
| Phase 4: VALIDATE                            |
| - Run validate_session_json.py               |
| - Update validationPassed field              |
| - Report pass/fail with details              |
+---------------------------------------------+
    |
    v
Completed Session Log (or actionable errors)
```

---

## What Gets Auto-Populated

| Field | Source | Level |
|-------|--------|-------|
| `endingCommit` | Current HEAD when empty, or with explicit refresh | Top-level |
| `handoffNotUpdated` | Check git diff for HANDOFF.md | MUST NOT |
| `serenaMemoryUpdated` | Check .serena/memories/ changes | MUST |
| `markdownLintRun` | Run markdownlint on changed .md files | MUST |
| `changesCommitted` | Check git status for uncommitted changes | MUST |
| `checklistComplete` | Evaluate all MUST items | MUST |
| `validationPassed` | Run validate_session_json.py | MUST |

### What You Must Provide Manually

- Serena memory updates (create/edit .serena/memories/ files before running)
- Commit your changes (run git commit before running)
- Work log entries in the session JSON

---

## Workflow

### Step 1: Complete Your Work

Before running this skill, ensure you have:

- Finished implementation tasks
- Updated Serena memories if applicable
- Staged and committed your changes

### Step 2: Run Session End

```bash
# Auto-detect and complete
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/session-end/scripts/complete_session_log.py"

# Or specify session explicitly
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/session-end/scripts/complete_session_log.py" --session-path ".agents/sessions/2026-02-07-session-05.json"

# Preview only
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/session-end/scripts/complete_session_log.py" --dry-run

# Replace a stale endingCommit after the final work commit
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/session-end/scripts/complete_session_log.py" --session-path ".agents/sessions/2026-02-07-session-05.json" --refresh-ending-commit

# Recheck committed Markdown while repairing session evidence
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/session-end/scripts/complete_session_log.py" --session-path ".agents/sessions/2026-02-07-session-05.json" --markdown-files docs/changed.md .serena/memories/memory-index.md

# Record completed QA evidence through the session owner
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/session-end/scripts/complete_session_log.py" --session-path ".agents/sessions/2026-02-07-session-05.json" --qa-report .agents/qa/feature-validation.md

# Record a policy-approved investigation-only QA exemption
uv run python "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/session-end/scripts/complete_session_log.py" --session-path ".agents/sessions/2026-02-07-session-05.json" --qa-skip-reason investigation-only
```

QA evidence files live under .agents/qa/ in the upstream repository.
Each report must start with this machine-readable frontmatter:

```yaml
---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-02-07-session-05.json
qaCommit: 0123456789abcdef0123456789abcdef01234567
---
```

`qaSessionLog` must match the exact session log path. `qaCommit` must be the full
40-character commit validated by QA. Only `PASS` satisfies mandatory QA.
Deferred, failed, stale, abbreviated, or unrelated evidence is rejected.
The owner supports `investigation-only` after its policy checker verifies every
changed path. Docs-only exemptions still require separate measured evidence.

### Step 3: Address Any Failures

If validation fails, the output shows exactly what is missing:

```text
[TODO] Serena memory not updated - update .serena/memories/ before completing
[TODO] Uncommitted changes exist - commit before completing
```

Fix the issues and re-run the skill.

### Step 4: Commit Final State

After the skill reports PASS, commit the updated session log:

```powershell
git add .agents/sessions/*.json
git commit -m "docs: complete session log"
```

---

## Verification Checklist

Before reporting success, the script verifies:

- [ ] Session log found and readable
- [ ] Valid JSON structure
- [ ] Ending commit SHA populated
- [ ] HANDOFF.md NOT modified
- [ ] Serena memory updated (or flagged)
- [ ] Markdown lint passed on changed files
- [ ] All changes committed (or flagged)
- [ ] Validation script passes (exit code 0)

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Skipping session-end before commit | Validation only catches errors at CI time | Run `/session-end` before every commit |
| Manually editing session end fields | Error-prone, misses evidence | Let the script auto-populate |
| Running without committing first | changesCommitted will fail | Commit work, then run session-end |
| Ignoring TODO warnings | Session will fail CI validation | Address each TODO before final commit |

---

## Example Output

**Success**:

```text
Auto-detected session log: .agents/sessions/2026-02-07-session-05.json

=== Session End Completion ===
File: .agents/sessions/2026-02-07-session-05.json

Running markdown lint...

--- Changes ---
  Set endingCommit: abc1234
  Confirmed HANDOFF.md not modified
  Confirmed Serena memory updated
  Markdown lint: 3 files linted
  All changes committed

Updated: .agents/sessions/2026-02-07-session-05.json

Running validation...

=== Session Validation ===
File: .agents/sessions/2026-02-07-session-05.json

[PASS] Session log is valid

[PASS] Session log completed and validated
```

**Failure**:

```text
=== Session End Completion ===

--- Changes ---
  Set endingCommit: abc1234
  Confirmed HANDOFF.md not modified
  [TODO] Serena memory not updated - update .serena/memories/ before completing
  Markdown lint: 2 files linted
  [TODO] Uncommitted changes exist - commit before completing

[FAIL] Session validation failed. Fix issues above and re-run.
```

---

## Scripts

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| [complete_session_log.py](scripts/complete_session_log.py) | Auto-populate and validate session end | 0=success, 1=validation failed |

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `--session-path` | string | No | Path to session log. Auto-detects if omitted. |
| `--dry-run` | flag | No | Preview changes without writing to file. |
| `--refresh-ending-commit` | flag | No | Replace a stale value with current HEAD. |
| `--markdown-files` | strings | No | Lint explicit Markdown paths. |
| `--qa-report` | string | No | Record a completed report under the configured QA artifact root. |
| `--qa-skip-reason` | enum | No | Verify and record an `investigation-only` QA exemption. |

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| [session-init](../session-init/) | Creates session logs (this skill completes them) |
| [session-log-fixer](../session-log-fixer/) | Reactive fix after CI failure (this skill prevents the need) |
| [session](../session/) | Session management utilities |

---

## Vendored install

<!-- vendor-portability: declared. This skill writes session logs under .agents/sessions/ and records QA reports under .agents/qa/. A consumer repo without the session path gets "[FAIL] No session log found in .agents/sessions/", not a silent no-op. The --qa-report option rejects reports outside the configured QA artifact root. It also cites .agents/SESSION-PROTOCOL.md and scripts/validate_session_json.py as references. Issue #2050. -->

This skill depends on upstream-only paths. In a vendored install (a consumer
repo that is not `rjmurillo/ai-agents`) these paths do not exist:

| Path | Direction | Behavior when absent |
|------|-----------|----------------------|
| `.agents/sessions/` | write (session logs) | The completion script reports the missing session directory and exits non-zero. Create the directory or set the session path explicitly. |
| `.agents/SESSION-PROTOCOL.md` | reference only | The protocol reference link is informational; absence does not block the skill. |

The HTML comment above is the machine-readable declaration the
`check_skill_md_portability.py` validator (Issue #2050) reads to confirm this
skill has disclosed its path dependencies instead of hiding them in prose.

## References

Backticked paths below are in the `rjmurillo/ai-agents` repository. They do not ship with this skill; a consumer install cannot resolve them.

- `.agents/SESSION-PROTOCOL.md` - Session end requirements
- `scripts/validate_session_json.py` - Validation script
- [new_session_log_json.py](../session-init/scripts/new_session_log_json.py) - Session creation script

---

## Pattern: Shift-Left Validation

This skill follows the shift-left principle: catch errors at development time, not CI time.

| Aspect | Without Skill | With Skill |
|--------|---------------|------------|
| **When errors found** | CI pipeline (minutes later) | Before commit (immediately) |
| **Feedback loop** | Push, wait, read logs, fix, push again | Run script, see errors, fix, done |
| **Cost** | CI minutes + developer context switch | Seconds of local validation |
| **Reliability** | Same script as CI | Same script as CI |
