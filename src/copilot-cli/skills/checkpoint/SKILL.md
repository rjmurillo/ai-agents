---
name: checkpoint
description: Write a timestamped mid-session checkpoint snapshot of decisions, progress, and next actions to .agents/checkpoints/. Use when you want a human-triggered save point during a long session.
argument-hint: optional-short-label
allowed-tools: Bash(date:*), Write
user-invocable: true
---

# Checkpoint Command

Capture the current state of work as a durable, timestamped snapshot. Use this
mid-session when you want a recoverable save point before a risky change, at the
end of a working block, or whenever the user asks to "checkpoint" progress. The
file is the human-readable record; it is not a substitute for the session log.

Optional label for this checkpoint: $ARGUMENTS

## Your task

1. Get the current UTC timestamp for the filename and the file body:

   ```bash
   date -u +%Y%m%d-%H%M%S
   ```

   Use the output as `YYYYMMDD-HHMMSS`. Also record the full ISO 8601 UTC time
   (`date -u +%Y-%m-%dT%H:%M:%SZ`) for the body.

2. Build the filename slug from `$ARGUMENTS`:

   - Lowercase the label, replace every run of non-alphanumeric characters with a
     single hyphen, and strip leading and trailing hyphens.
   - Truncate the slug to 40 characters.
   - If `$ARGUMENTS` is empty after trimming, omit the slug entirely.
   - Filename with a label: `CHECKPOINT-YYYYMMDD-HHMMSS-<slug>.md`.
   - Filename without a label: `CHECKPOINT-YYYYMMDD-HHMMSS.md`.

3. Write the checkpoint to `.agents/checkpoints/<filename>` using the Write tool.
   The directory already exists (tracked via `.gitkeep`). Do not overwrite an
   existing file; the timestamp makes collisions unlikely, but if the exact path
   exists, append a `-2` (then `-3`, and so on) before `.md`.

4. Use this exact section structure. Fill each section from the current
   conversation and git state. Write "None" under a heading when a section has no
   content; never leave a heading empty.

   ```markdown
   # Checkpoint YYYYMMDD-HHMMSS

   - Created: <ISO 8601 UTC>
   - Label: <the raw label, or "none">
   - Branch: <current git branch>

   ## Decisions

   Decisions made so far this session and the reasoning behind each.

   ## Completed

   Work finished and verified, with file paths or commit SHAs as evidence.

   ## Pending

   Work started but not finished, and work known to remain.

   ## Open Questions

   Unresolved questions, ambiguities, or blockers needing a human decision.

   ## Next Action

   The single next concrete step to take when work resumes.

   ## Context References

   Files, issues, PRs, ADRs, session logs, and memories a reader needs to resume.
   ```

5. Do not redact by default, but never paste credentials, tokens, or PII into the
   body. The checkpoint lands in git history; treat it as durable. If a value you
   would record looks like a secret, summarize it instead of copying it verbatim.

6. Report the path you wrote and a one-line summary of what the checkpoint
   captured. Do not commit the file; leave that to the user or the session-end
   flow.

This command only writes a snapshot file. It does not change session state, does
not touch the session log, and does not push or commit. Keep it to the steps
above.
