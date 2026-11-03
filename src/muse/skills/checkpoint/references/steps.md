# Checkpoint steps

<!-- vendor-portability: this reference is the checkpoint skill's step detail and
     inherits its audience. The redactor every checkpoint body is piped through is
     scripts/redact_secrets.py, which lives upstream in the rjmurillo/ai-agents repo
     and ships in no plugin root, so this is a contributor-facing procedure rather
     than a plugin-consumer one (ADR-083, issue #5632). -->

<!-- vendor-portability-exec: the redaction step invokes
     scripts/redact_secrets.py, which lives upstream in the rjmurillo/ai-agents
     repo. A prose declaration does not exempt an executable invocation, which
     migrates independently (issue #2838), so it is declared here too. -->

The eight-step procedure the checkpoint skill's three phases expand into.
Held here rather than in `SKILL.md` so the body states the workflow once and
stays readable; ADR-064 (issue #5632) made this a skill, which is what gave it
a `references/` directory to put them in.

1. Get the current UTC timestamp for the filename and the file body:

   ```bash
   date -u +%Y%m%d-%H%M%S
   ```

   Use the output as `YYYYMMDD-HHMMSS`. Also record the full ISO 8601 UTC time
   (`date -u +%Y-%m-%dT%H:%M:%SZ`) for the body.

2. Identify the active session log and default label:

   - Get the current branch with `git branch --show-current`.
   - Find ``*.json`in the sessions directory` files and sort by filename descending. The
    filename order is the canonical "newest" order because session logs are
    named with `YYYY-MM-DD-session-NN`.
   - Read candidates in that order until you find the first log whose normalized
    `session.branch` equals the current branch. Normalize `session.branch` by
    trimming whitespace and removing one matching pair of surrounding backticks.
    That file is the active session log.
   - If `$ARGUMENTS` is empty after trimming, derive the label from the active
    session log's `session.objective`. If no active session log exists, derive
    it from the current branch. If that is empty, use `checkpoint`.

3. Build the filename slug from the label:

   - Lowercase the label, replace every run of non-alphanumeric characters with a
     single hyphen, and strip leading and trailing hyphens.
   - Truncate the slug to 40 characters.
   - Filename: `CHECKPOINT-YYYYMMDD-HHMMSS-<slug>.md`.
   - If slug generation returns an empty string, use `checkpoint` as the slug.

4. Select the checkpoint path. The directory already exists (tracked via
   `.gitkeep`). Do not overwrite an existing file. Use this collision loop before
   writing:

   - Start with `CHECKPOINT-YYYYMMDD-HHMMSS-<slug>.md`.
   - Check whether `{checkpoints-dir}/<candidate>` already exists with Glob.
   - If it exists, try `CHECKPOINT-YYYYMMDD-HHMMSS-<slug>-2.md`, then `-3`, and
    continue until Glob returns no match.
   - Select the first path that does not already exist, but do not use Write yet.

5. Use this exact section structure. Fill each section from the current
   conversation and git state. Write "(none)" under a heading when a section has
   no content; never leave a heading empty.

   ```markdown
   # Checkpoint YYYYMMDD-HHMMSS

   - Created: <ISO 8601 UTC>
   - Label: <the raw label, or "none">
   - Branch: <current git branch>

   ## Decisions

   Decisions made so far this session and the reasoning behind each.

   ## Completed

   Work finished and verified, with file paths or short commit SHAs (7-12
   characters) as evidence.

   ## Pending

   Work started but not finished, and work known to remain.

   ## Open Questions

   Unresolved questions, ambiguities, or blockers needing a human decision.

   ## Next Action

   The single next concrete step to take when work resumes.

   ## Context References

   Files, issues, PRs, ADRs, session logs, and memories a reader needs to resume.
   ```

6. Redact secrets before writing, then write the checkpoint. The checkpoint lands in git history; treat it
   as durable. Do not paste live credentials, tokens, or PII. Before using Write,
   run the checkpoint body through `python3 scripts/redact_secrets.py` and write
   the redacted output. If the redactor is unavailable or fails, stop and report
   the failure instead of writing unredacted durable text. Only after redaction
   succeeds, use Write on the collision-free path from step 4. Use short commit
   SHAs rather than full 40-character SHAs because the redactor masks long hex
   strings.

7. Link the checkpoint from the active session log:

   - If no active session log was found in step 2, report that no active session
     log was found. Do not invent or modify a log.
   - If the active session log exists, read the full original JSON first. Build
     the complete updated JSON in memory with a top-level `checkpoints` array.
     Create the array when it is absent. Append an object with `path`, `created`,
     `label`, and `branch` fields for this checkpoint.
   - Validate the complete updated JSON string before editing the file. Use a JSON
     parser that reads the full candidate from stdin, such as
     `python3 -m json.tool`. Never pass the JSON payload as a shell argument. If
     your harness cannot validate the candidate without writing a scratch file,
     leave the original session log unchanged and report that the session-log
     link was skipped.
   - Persist the updated JSON only after the validate-first step succeeds.
   - Run `python3 -m json.tool <session-log-path>` after editing. If JSON
     validation fails, report the failure and do not claim the checkpoint was
     linked from the session log.

8. Report the path you wrote, the session log path you updated or the reason no
   log was updated, and a one-line summary of what the checkpoint captured. Do
   not commit the file; leave that to the user or the session-end flow.
