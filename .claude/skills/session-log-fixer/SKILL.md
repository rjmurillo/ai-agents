---
name: session-log-fixer
description: Repair an existing JSON session log locally. Use when `validate_session_json.py` rejects a staged or explicitly supplied log, when an opted-in log has invalid schema fields, or when existing log evidence is incomplete. Do NOT use to create a required log, because logs are optional. Do NOT use for CI workflow or job-summary failures.
version: 4.0.0
license: MIT
metadata:
  domains:
  - session-protocol
  - validation
  type: local-fixer
  inputs:
  - session-log-path
  outputs:
  - repaired-session-file
---

# Session Log Fixer

Repair an existing opted-in JSON session log. A session log is optional. This
skill never creates one to satisfy a start, end, commit, push, or pull request
gate.

## Triggers

- `fix this session log`
- `repair existing session JSON`
- `validate_session_json.py failed`
- `fix malformed opted-in session log`

## Process

### Phase 1: Confirm the target

Require an explicit `.agents/sessions/*.json` path or a staged JSON session log.
If no log exists, stop successfully and report that no repair is needed.

### Phase 2: Read retained contracts

Read:

1. The supplied log.
2. `.agents/schemas/session-log.schema.json`.
3. `scripts/validate_session_json.py`.
4. The optional appendix in `.agents/SESSION-PROTOCOL.md`.

Do not infer required fields from historical logs.

### Phase 3: Validate locally

```bash
uv run python scripts/validate_session_json.py \
  .agents/sessions/<existing-log>.json
```

Use the validator output to identify exact schema or evidence failures.

### Phase 4: Repair only the existing record

Correct malformed JSON, schema mismatches, invalid branch or commit metadata,
and incomplete protocol fields. Preserve accurate historical content. Never
fabricate evidence, tool output, commit SHAs, or completed work.

If accurate evidence is unavailable, keep the conservative value accepted by
the schema or report the unresolved validation error. Do not convert missing
evidence into a success-shaped record.

### Phase 5: Revalidate

Run the same validator until it exits 0:

```bash
uv run python scripts/validate_session_json.py \
  .agents/sessions/<existing-log>.json
```

The repaired file is complete only when this exact command passes.

## Verification

- [ ] The target was an existing, explicitly selected session log.
- [ ] The repair introduced no invented evidence or unverified metadata.
- [ ] `scripts/validate_session_json.py` exits 0 for the repaired path.
- [ ] The final diff changes only the intended existing log.

## Common Repairs

| Failure | Repair |
|---------|--------|
| Invalid JSON | Correct syntax without changing factual content |
| Missing schema field | Add the field from authoritative session evidence |
| Placeholder evidence | Replace with real evidence or report the blocker |
| Invalid branch or SHA | Read the repository state and record the verified value |
| Incomplete required item | Complete only when supporting evidence exists |

## Anti-Patterns

| Avoid | Reason |
|-------|--------|
| Creating a log because none exists | Logs are optional |
| Fetching a deleted CI job summary | The session workflow is retired |
| Repairing from memory | The retained schema and validator are authoritative |
| Inventing evidence | Produces a false historical record |
| Editing generated skill mirrors | Regeneration owns those files |

## Vendored Install

<!-- vendor-portability: declared. This skill repairs an existing consumer-owned .agents/sessions JSON record when the consumer provides the path. The upstream schema and validator are repository-local references and may not exist in a vendored install. Issue #2050. -->

When the upstream schema or validator is absent, require the consumer's schema
and validation command. Do not assume the ai-agents contract applies.

## References

- `.agents/schemas/session-log.schema.json`
- `scripts/validate_session_json.py`
