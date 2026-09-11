---
name: checkpoint
version: 1.0.0
description: Write a timestamped, secret-redacted snapshot of decisions, progress and next actions to the checkpoints directory, then link it from the active session log. Use when you say `checkpoint this`, `save a recovery point`, or `snapshot where we are` before a risky change or at the end of a working block. Do NOT use to commit or push (it never does either), and do NOT use to write a retrospective (use retro).
license: MIT
allowed-tools: Bash(date:*), Bash(git branch:*), Bash(python3 -m json.tool:*), Bash(python3 scripts/redact_secrets.py:*), Glob, Read, Edit, Write
argument-hint: optional-short-label
user-invocable: true
---

# Checkpoint

<!-- vendor-portability: the redactor this skill pipes every checkpoint body
     through is scripts/redact_secrets.py, which lives upstream in the
     rjmurillo/ai-agents repo and ships in no plugin root. The checkpoint and
     session directories it reads and writes are the CONSUMER's own agent
     artifacts, resolved rather than hard-coded (ADR-083, issue #5632). -->

<!-- vendor-portability-exec: the redaction step invokes
     scripts/redact_secrets.py, which lives upstream in the rjmurillo/ai-agents
     repo. A prose declaration does not exempt an executable invocation, which
     migrates independently (issue #2838), so it is declared here too. -->

Migrated from the checkpoint command under ADR-064, which makes skills the
single user-invocable surface. The command file is gone, so its path is named
here in plain text rather than as a citation to something a reader could open.

## The checkpoint and session directories

Resolve them the way `paths.artifact_dir` does, then take its `checkpoints/` and
`sessions/` subdirectories. Do not hard-code an agent-artifacts path: the tree
this skill writes into lives in the CONSUMER's workspace, and its root differs
between an upstream checkout and a plugin install. Every `{checkpoints-dir}` and
`{sessions-dir}` below means those resolved directories.

Capture the current state of work as a durable, timestamped snapshot. Use this
mid-session when you want a recoverable save point before a risky change, at the
end of a working block, or whenever the user asks to "checkpoint" progress. The
file is the human-readable record; the session log keeps a reference to it.

## Triggers

| Trigger | Effect |
| --- | --- |
| `/checkpoint` | Write a timestamped checkpoint and link it from the active session log. |
| `/checkpoint label` | Write a labeled checkpoint and link it from the active session log. |

## Arguments

Optional label for this checkpoint: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

## Process

### Phase 1: Build checkpoint path

Resolve the timestamp, active session log, label, slug, and collision-safe
checkpoint path.

### Phase 2: Build and redact checkpoint

Render the checkpoint body and run it through the secret redactor before any
Write call.

### Phase 3: Persist and link

Write the redacted checkpoint to a path that does not already exist. Append
checkpoint metadata to the active JSON session log when one exists, then validate
the JSON.

When a checkpoint file is later committed, the commit message still follows the repository convention.
Commit messages MUST follow `<type>(<scope>): <desc>` and include a `Co-Authored-By:` trailer when authored with an AI agent.

## Steps

The three phases expand into eight steps: resolve the timestamp and branch, find
the active session log, build the path, render the body, redact it, write it to a
path that does not exist, link and validate the session log, then report. Each
step, with its exact commands and failure handling, is in
`references/steps.md`. Read it before writing anything; the redaction and
validate-before-edit ordering is the part that matters.

## Verification

A gate is any check whose failure would falsify your conclusion. Only a current result on the exact state and scope clears it. Failure, timeout, stale run, skip, or subset leaves the claim unproved. Say what ran and what returned. If blocked, name who can clear it.

- [ ] Checkpoint file path did not already exist before Write.
- [ ] Checkpoint body was redacted with `scripts/redact_secrets.py` before Write.
- [ ] Active session log was updated, or the "no active session log" reason was reported.
- [ ] Updated session log JSON was validated before editing the original file.
- [ ] Updated session log passed `python3 -m json.tool` when a log was modified.

## Anti-Patterns

- Do not overwrite an existing checkpoint path.
- Do not write unredacted durable text when the redactor fails.
- Do not create or guess a session log when no active branch-matching log exists.
- Do not edit a session log before validating the complete updated JSON string.
- Do not commit, push, or merge from this command.

## Extension Points

- Add a restore command separately. Checkpoint only writes and links snapshots.
- Add automatic checkpointing separately. This command stays human-triggered.

This command writes a snapshot file and records a reference in the active session
log when one exists. It does not push or commit. Keep it to the steps above.
