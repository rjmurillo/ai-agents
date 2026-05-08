# Reply-body staging for batch thread resolution

**Confidence**: HIGH — operational constraint, captured 2026-05-08

## Rule

Stage PR review reply bodies as files under `.pytest_tmp/pr<num>/` (or another gitignored path inside the repo root), then dispatch them to `add_pr_review_thread_reply.py --body-file` in a batch. Do NOT stage reply bodies under `/tmp/` or any path outside the repo working tree.

## Why

The github skill's `add_pr_review_thread_reply.py` validates the `--body-file` path through `scripts/github_core/validation.py::is_safe_file_path`, which rejects paths outside `get_repo_root()` (CWE-22 path-traversal defense). A `--body-file /tmp/...` invocation fails with `Body file path traversal not allowed: /tmp/...` before the GraphQL call.

Conflict with the standing memory rule "Stage scratch artifacts outside the working tree": the project's path-traversal validator overrides that rule for github-skill invocations. The compromise is `.pytest_tmp/` — gitignored (per `.gitignore`), inside repo root (so the validator accepts it), and project-conventional for ephemeral files.

## How to apply

1. Create `.pytest_tmp/pr<num>/` as the staging dir for a multi-thread reply batch.
2. Write each reply body as a separate `.md` file with a stable, descriptive name (e.g. `r7_asymmetry.md`, `r7_semgrep_fixed.md`).
3. Dispatch with a single bash loop:
   ```bash
   for thread_id body_file in <pairs>; do
     python3 .claude/skills/github/scripts/pr/add_pr_review_thread_reply.py \
       --thread-id "$thread_id" --body-file "$body_file" --resolve
   done
   ```
4. Verify by re-querying unresolved threads with `get_pr_review_threads.py --unresolved-only`.

## When this fails to help

- Single-thread replies do not need staging; `--body "<inline string>"` is fine for short replies under ~500 chars.
- If the PR description itself needs editing (not a thread), use `gh pr edit --body-file <path>` directly; the path-traversal validator does not apply to that command.
