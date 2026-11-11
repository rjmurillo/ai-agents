# Review a branch and answer feedback

## Goal

You review a small branch with `/review`, fix one finding, and prove the review
still binds your code. Then you answer and resolve one review thread.

You know it worked when two things are true:

- `validate_review_marker.py` prints `[PASS]` for your branch.
- `get_unresolved_review_threads.py` reports `"unresolved_count": 0` for your PR.

## Before you start

- A clone of `rjmurillo/ai-agents` with `origin` fetched, and `uv` installed.
- `gh auth status` shows you are signed in.
- Claude Code with the `project-toolkit` plugin, or this repository open in it.
- A pull request of yours that has at least one review thread. Step 7 uses it.
  Open any small PR and leave one comment on a line of your own diff.

Put worktrees outside your clone, in `~/worktrees/<repo>/<branch>`. Never put
one under `/tmp`. A reboot deletes its unpushed commits.

## Steps

### 1. Make a practice branch

```bash
git fetch origin
git worktree add -b practice/review-tutorial ~/worktrees/ai-agents/practice-review-tutorial origin/main
cd ~/worktrees/ai-agents/practice-review-tutorial
```

### 2. Add a page that has a flaw

```bash
mkdir -p docs/practice
printf '# Practice page\n\n### Skipped a level\n\nRun the checker with `python3 scripts/validation/check_hello_world.py`.\n' > docs/practice/notes.md
git add docs/practice/notes.md
git commit -m "docs(practice): add notes page"
```

The page skips from a level 1 heading to level 3. It also names a script that
does not exist.

### 3. See which review axes will run

`/review` does not run every reviewer on every change. It picks axes from the
changed paths and the effects in the diff. This command shows the pick:

```bash
python3 .claude/skills/review/scripts/select_axes.py --changed-path docs/practice/notes.md \
  | jq -c '{canonical_selected, local_selected, matched_categories, fail_closed}'
```

You see:

```json
{"canonical_selected":["analyst"],"local_selected":["doc-accuracy"],"matched_categories":["docs-and-instructions"],"fail_closed":false}
```

A docs-only change gets the `analyst` axis and the `doc-accuracy` check. Add
`--deep` to the command and all 11 canonical axes run.

### 4. Run the review

In Claude Code, run:

```text
/review
```

The Stage-1 `spec-compliance` gate runs first. Then the selected axes run. You
get a table with one row per axis and a final verdict: `PASS`, `WARN`,
`CRITICAL_FAIL`, or `UNKNOWN`. `UNKNOWN` means an axis did not evaluate. It is
never a silent pass.

The findings differ from run to run. Fix any one finding the review reports. If
it reports none, the next step gives you a finding you can fix.

### 5. Fix one finding

The repository's Markdown lint catches the skipped heading every time:

```bash
uv run python scripts/validation/pre_pr.py --markdown-lint-only docs/practice/notes.md
```

You see:

<!-- citation-freshness: ignore -- sample lint output for a practice file the reader creates in step 2 -->
```text
[FAIL] Markdown linting failed (exit code 1)
stderr:
  docs/practice/notes.md:3 error MD001/heading-increment Heading levels should only increment by one level at a time [Expected: h2; Actual: h3]
```

Change `### Skipped a level` to `## Skipped a level`, then run the same command
again. It exits 0. Commit the fix:

```bash
git add docs/practice/notes.md
git commit -m "docs(practice): fix heading level"
```

### 6. Bind the review to your code

When the final verdict is `PASS`, `/review` adds an empty commit on top of your
branch. It is the review marker. Its `Reviewed-By` trailer names the exact commit
it reviewed. Check it:

```bash
python3 .claude/skills/review/scripts/validate_review_marker.py
```

You see a line like this. The SHA and the axis list are yours:

```text
[PASS] reviewed: /review@spec-compliance,analyst binds 38b0caa6b863 (2 axis/axes)
```

Now change the code. Any new commit voids the marker:

```bash
printf '\nOne more line.\n' >> docs/practice/notes.md
git add docs/practice/notes.md
git commit -m "docs(practice): add a line"
python3 .claude/skills/review/scripts/validate_review_marker.py
```

You see a failure, and the command exits 1:

```text
[FAIL] HEAD (29bc040d151a) changes files; a review marker must be an empty commit whose Reviewed-By trailer names its parent. Re-run /review after the code tip is ready.
```

That is the point of the marker. It proves a specific commit was reviewed. It
does not vouch for code written after. Merging a clean `origin/main` above the
marker keeps it valid. Any other new code needs a new `/review`.

### 7. Answer one thread

Switch to your PR's branch. List its open threads:

```bash
python3 .claude/skills/github/scripts/pr/get_unresolved_review_threads.py --pull-request <PR> --output-format json
```

Each entry in `threads` has an `id` that starts with `PRRT_`. A PR with no open
threads prints this, so you can tell the two cases apart:

```json
{
  "success": true,
  "pull_request": 7255,
  "owner": "rjmurillo",
  "repo": "ai-agents",
  "unresolved_count": 0,
  "fetched_pages_complete": true,
  "api_error": false,
  "threads": []
}
```

Fix what the thread asks for, push, and note the commit SHA. Then reply and
resolve in one call. The script refuses to resolve if the PR head moved since you
read it:

```bash
python3 .claude/skills/github/scripts/pr/add_pr_review_thread_reply.py \
  --thread-id <PRRT_id> --pull-request <PR> --expected-head-sha <40-hex head SHA> \
  --body "Fixed in <commit SHA>: <one line on what changed>." --resolve
```

A reply alone does not resolve a thread. The `--resolve` flag does.

## Check your result

Bots can open new threads 30 to 120 seconds after a push. A single zero reading
can be wrong. This command waits for three zero readings, 180 seconds apart:

```bash
python3 .claude/skills/github/scripts/pr/wait_for_unresolved_zero.py --pull-request <PR>
```

It exits 0 when the count stays at zero. It exits 1 if it runs out of time
(20 minutes by default).

You are done when:

- Step 6 printed `[PASS]` before you added the extra line.
- The wait command exits 0 for your PR.

## If it fails

| What you see | What it means | What to do |
|---|---|---|
| `fail_closed: true` in step 3 | The selector could not classify a path, so it picked every axis. | Nothing is wrong. Expect a longer review. |
| `UNKNOWN` verdict in step 4 | An axis could not run or its output could not be read. | Read the row for the axis. Fix the cause and re-run `/review`. |
| `[FAIL]` from the marker check | The marker is missing or stale. | Re-run `/review` on the final code. |
| Reply script refuses to resolve | The PR head moved after you read it. | Read the PR again, then pass the new head SHA. |
| HTTP 403 from every GitHub script | The session blocks `gh` for a reason unrelated to your PR. | Treat it as unknown, not as a verdict. See [pr-review](how-to-pr-review.md). |

## Clean up

```bash
cd ~
git -C <your clone> worktree remove ~/worktrees/ai-agents/practice-review-tutorial
git -C <your clone> branch -D practice/review-tutorial
```

## Next

- [Run /review](how-to-review.md)
- [Respond to review threads](how-to-respond-to-review-threads.md)
- [Run /pr-review for a verdict](how-to-pr-review.md)
- [Let pr-autofix drive a PR](how-to-pr-autofix.md)
- [Get a maintainer decision](how-to-maintainer-review.md)
