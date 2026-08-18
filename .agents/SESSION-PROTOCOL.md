# Session Protocol
<!-- # taste-lint: ignore file-size, canonical protocol must remain one document for validators and agents. -->

> **Status**: Canonical Source of Truth
> **Last Updated**: 2026-08-16
> **Protocol Version**: 3.0
> **RFC 2119**: This document uses RFC 2119 key words to indicate requirement levels.

This document defines active session requirements. Committed JSON session logs
are optional. No session-start, session-end, commit, push, or pull request gate
requires a log to exist or be complete.

---

## RFC 2119 Key Words

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" are interpreted
as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

| Key Word | Meaning |
|----------|---------|
| **MUST** / **REQUIRED** / **SHALL** | Absolute requirement |
| **MUST NOT** / **SHALL NOT** | Absolute prohibition |
| **SHOULD** / **RECOMMENDED** | Strong recommendation |
| **MAY** / **OPTIONAL** | Optional, no justification needed |

---

## Protocol Enforcement Model

Active requirements use observable evidence. Evidence may live in the session
transcript, a pull request, a per-issue handoff, Serena memory, or an optional
session log. A committed session log is never the sole accepted evidence sink.

| Requirement Type | Accepted Evidence |
|------------------|-------------------|
| Tool calls | Session transcript |
| File reads and writes | Transcript, git diff, or pull request |
| Git operations | Git status, log, or pull request |
| Continuity | Per-issue handoff and Serena memory |
| Optional session log | Valid JSON when staged or explicitly supplied |

Labels such as "MANDATORY" are not enforcement. Each active requirement must
name evidence that exists without requiring a committed session log.

---

## Session Start Protocol

### Phase 0: Get Oriented (BLOCKING)

1. The agent MUST run `git branch --show-current`.
2. The agent MUST verify the branch matches the intended work.
3. The agent MUST NOT modify `main` or `master` directly.
4. The agent MUST inspect recent commits and current worktree state.

### Phase 1: Serena Initialization

When Serena MCP tools are available, the agent MUST activate the project and
load initial instructions before repository work. When unavailable, the agent
MAY use committed Serena memories and repository search.

Evidence is the transcript or the retrieved memory content.

### Phase 2: Context Retrieval (BLOCKING)

1. Read `.agents/HANDOFF.md` as a read-only project dashboard.
2. Search memory indexes before loading full memories.
3. Load only task-relevant Serena memories.
4. Read the latest per-issue handoff before modifying files when issue context
   exists.
5. Read project constraints and path-scoped instructions.

The latest per-issue handoff and Serena memory carry continuity. The transcript
records what was retrieved. An optional session log MAY duplicate this
evidence, but nothing requires that duplication.

### Phase 3: Skill Validation (BLOCKING)

Before using raw repository or GitHub operations, check for an existing skill.
Read `.agents/governance/PROJECT-CONSTRAINTS.md` and the applicable skill
instructions.

### Phase 4: Branch Verification (BLOCKING)

Verify the branch before each commit, push, or pull request operation. Evidence
is the command output. A branch name does not need to be copied into a session
log.

### Phase 5: Optional Session Log

Session logs under `.agents/sessions/*.json` are optional records. Use
`session-init` only when an operator explicitly wants a committed session log.
Use `session-end` only to complete or validate an existing log.

If a JSON log is staged or explicitly supplied to
`scripts/validate_session_json.py`, it MUST satisfy the retained schema and
validator. A malformed or incomplete supplied log fails validation. When no
log is staged or supplied, session-log validation passes without one.

Historical logs, schemas, validators, extracted episodes, and accepted ADR
history remain supported.

### Session Start Checklist

Use this checklist in the transcript, a task tracker, or an optional log:

- [ ] Branch and worktree verified.
- [ ] Project instructions loaded.
- [ ] Relevant memory searched and loaded.
- [ ] Latest per-issue handoff read when one exists.
- [ ] Required skills loaded.

---

## Session Mid Protocol

### Commit Count Monitoring

Run `git rev-list --count HEAD ^origin/main` during extended work. Warn at 10
commits, prepare to wrap at 15, and stop adding scope above the active limit
reported by `scripts/validation/pr_commit_count.py`.

### Tier-Based Coordination

Agent delegation follows the tier hierarchy in `.agents/AGENT-SYSTEM.md`.
Record material routing decisions in the transcript, task tracker, per-issue
handoff, or Serena memory. Parallel writers must own separate files or
worktrees.

### Continuity During Long Work

Persist decisions, blockers, changed state, open questions, and next steps.
Use the per-issue handoff for unfinished issue work. Store durable,
cross-session knowledge in Serena memory. Do not rely on an optional log as the
only continuation path.

---

## Session End Protocol

### Phase 1: Documentation Update

1. The agent MUST NOT update `.agents/HANDOFF.md`.
2. When issue work remains incomplete, update the per-issue handoff under
   `.agents/sessions/handoffs/`.
3. Store durable, reusable findings in Serena memory.
4. Update directly related project documentation when behavior changed.
5. If an optional session log exists, the agent MAY complete it with
   `session-end`.

### Phase 1.5: Per-Issue Handoff

When an associated issue remains incomplete, write or update
`.agents/sessions/handoffs/{YYYY-MM-DD}-{ISSUE_NUMBER}-handoff.md` from
`.agents/templates/HANDOFF.md`.

The handoff records status, files modified, decisions, blockers, next steps,
resume checks, and related work. It must contain no template placeholders.
The pull request, transcript, or handoff itself supplies evidence. A session
log reference is optional.

### Phase 2: Quality Checks

Run checks that cover the changed behavior. Use scoped markdown lint for
changed Markdown files. Run `scripts/validation/pre_pr.py` before opening a
pull request. Do not claim a check passed when it selected no files.

### Phase 2.5: QA Validation

Route feature changes through QA unless an existing exemption applies. Evidence
may be test output, a QA artifact, a pull request check, or transcript output.
No QA decision depends on session-log presence.

### Phase 2.7: Pre-PR Validation

Run:

```bash
uv run python scripts/validation/pre_pr.py
```

The command validates repository readiness. It MUST pass when no branch session
log exists. If a log is present in the relevant change set, the retained
validator MAY validate that log.

### Phase 3: Git Operations

1. Re-verify the branch before commit, push, or pull request operations.
2. Use conventional commits.
3. Do not bypass hooks.
4. Do not force-push shared branches.
5. Stage only intended files.

No git operation requires creating, staging, or completing a session log.

### Phase 4: Retrospective

Use a retrospective when the work produced durable learning. This is
independent of session-log use.

### Session End Checklist

Use this checklist in the transcript, a task tracker, a handoff, or an optional
log:

- [ ] Intended work and tests complete.
- [ ] Per-issue handoff updated when work remains.
- [ ] Durable learning stored in Serena memory when applicable.
- [ ] Changed documentation and generated artifacts synchronized.
- [ ] Required validation passed.
- [ ] Branch state verified.
- [ ] Existing optional log validated when one is staged or supplied.

---

## Unattended Execution Protocol

Unattended work follows the same evidence contract:

1. Use task tracking and specialist routing for multi-step work.
2. Run QA after code changes.
3. Run critic review before an external merge action.
4. Require security review for security findings.
5. Record unfinished issue state in the per-issue handoff.
6. Store durable findings in Serena memory.
7. Keep evidence in the transcript, pull request, handoff, or optional log.

Unattended execution does not require a session log. Recovery from a missed
requirement repairs the missing evidence or action. It does not create a log
unless the operator opted into one.

---

## Validation Tooling

`scripts/validate_session_json.py` validates a JSON log supplied on its command
line. The `session-policy` pre-commit hook validates staged session logs. Both
are validate-if-present controls.

```bash
uv run python scripts/validate_session_json.py \
  .agents/sessions/2026-08-16-session-01.json
```

Validation checks the retained schema, protocol fields, evidence, and commit
metadata. Absence of a log is not a validation error.

---

## Optional Appendix: JSON Session Log Template

Use this appendix only when an operator opts into a committed log. The schema
at `.agents/schemas/session-log.schema.json` is authoritative.

Create a log:

```bash
uv run python .claude/skills/session-init/scripts/new_session_log.py
```

Complete an existing log:

```bash
/session-end
```

Validate a supplied log:

```bash
uv run python scripts/validate_session_json.py <session-log>.json
```

Minimal shape:

```json
{
  "schemaVersion": "1.0",
  "session": {
    "number": 1,
    "date": "2026-08-16",
    "branch": "fix/example",
    "startingCommit": "abc1234",
    "objective": "Describe the opted-in record"
  },
  "protocolCompliance": {
    "sessionStart": {},
    "sessionEnd": {}
  },
  "workLog": [],
  "endingCommit": "",
  "nextSteps": []
}
```

Once created, the file must satisfy the schema and validator before staging.
Historical log formats remain readable by retained compatibility code.

---

## ADR Cross-Reference

| ADR | Requirement Summary | Protocol Section |
|-----|---------------------|------------------|
| ADR-001 | Markdown lint configuration | Session End, Phase 2 |
| ADR-007 | Memory-first retrieval | Session Start, Phase 2 |
| ADR-014 | Read-only dashboard and distributed continuity | Session End, Phase 1.5 |
| ADR-033 | Current routing gates | Protocol Enforcement Model |
| ADR-034 | Investigation QA exemption | Session End, Phase 2.5 |
| ADR-035 | Script exit codes | Git Operations |
| ADR-042 | Python for new scripts | Quality Checks |
| ADR-043 | Scoped tool execution | Quality Checks |
| ADR-050 | ADR-to-protocol sync | This section |

---

## Related Documents

- [AGENTS.md](../AGENTS.md)
- [PROJECT-CONSTRAINTS.md](governance/PROJECT-CONSTRAINTS.md)
- [HANDOFF.md](HANDOFF.md)
- [Per-Issue Handoffs](sessions/handoffs/README.md)
- [Search, Don't Load](../docs/search-dont-load.md)
