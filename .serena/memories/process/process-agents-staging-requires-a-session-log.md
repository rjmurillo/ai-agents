# Staging any file under `.agents/` requires a valid JSON session log in the same commit

## Question

A commit touches one file under `.agents/`, for example a retrospective or an
ADR. What else does the commit need?

## Conventional answer

Nothing. It is a documentation change. Stage the file and commit.

## First-principles position

The commit is rejected. `check_sessions` in
`scripts/validation/git_hook_policy.py` fails any commit that stages a path
under `.agents/` without also staging a session log, with:

```
ERROR: staged .agents changes require a JSON session log
```

The log path must match:

```
^\.agents/sessions/\d{4}-\d{2}-\d{2}-session-\d+.*\.json$
```

and the file must validate against `.agents/schemas/session-log.schema.json`.

The expensive part is not the requirement, it is that the schema errors surface
**one layer at a time**. Each failed commit reports a single missing key, so a
log written from scratch costs one round trip per level of nesting. This cost
six attempts on 2026-08-02.

## Decision

Do not iterate through the commit hook. Copy an existing log and edit it, then
validate before staging:

```
uv run --frozen python scripts/validate_session_json.py <path> --pre-commit
```

Silence means pass. Any output means the commit will be rejected.

Required shape, so a log can be written correctly on the first attempt:

| Key | Required members |
|---|---|
| top level | `schemaVersion`, `session`, `protocolCompliance`, `workLog`, `endingCommit`, `nextSteps` |
| `session` | `number`, `date`, `branch`, `startingCommit`, `objective` |
| `protocolCompliance` | `sessionStart`, `sessionEnd`, each a map of gate name to `{Evidence, Complete, level}` |
| `outcomes.deliverables[]` | `type`, `path`, `description` |
| `outcomes.decisions[]` | `decision`, `rationale`, `impact` |
| `learnings.patterns[]` | `pattern`, `context`, `application` |
| `learnings.avoidances[]` | `antipattern`, `consequence`, `correction` |
| `workLog[]`, `nextSteps[]` | free-form strings accepted |

## Evidence

Observed 2026-08-02 while committing a retrospective artifact to
`.agents/retrospective/`. Six commit attempts, each rejected with a different
single missing key, before the log validated. Working example committed at
`.agents/sessions/2026-08-02-session-4310-retro-phase5.json`.

Session numbers are not sequential and not enforced against a registry; the
highest observed at the time was 4256, and 4310 was accepted. There are more
than a thousand logs in the tree, most of them under
`.agents/archive/sessions/`, so search the archive rather than the live
directory when looking for a template.

## Related

`endingCommit` must be reachable from the current branch. When a branch was
squash-merged, the recorded commit stops being reachable and the validator
reports the failure as an amend or rebase, which names the wrong cause. That
misleading diagnostic is tracked as issue #4312.
