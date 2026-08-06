# The Episode Ratchet Trips Because the Episode Predates the Commit

A push fails with:

```
AssertionError: metrics violations grew to 22 (was 21); new episodes with
commits==0 but files_changed>0 must be fixed
```

The failing test is
`tests/skills/memory/test_extract_session_episode.py::TestValidateModeRejectsUnusableEventIds::test_the_committed_episode_store_is_clean`.

## Why it happens

The `extract-session-episodes` pre-commit hook writes the episode *before* the
commit object exists. `extract_session_episode.py:_collect_shas` reads commit
SHAs from the session log's `endingCommit` first, then from the
`changesCommitted` evidence string. A session log created mid-session by
`.claude/skills/session-init/scripts/new_session_log_json.py` carries
`endingCommit: ""`, because the protocol expects it to be filled after the
commit lands (see `scripts/validate_session_json.py:639`, where a claimed
commit with an empty `endingCommit` is a *warning*, not an error).

Empty `endingCommit` means no SHAs, which means `events: []`, which means
`_count_commit_events` returns 0. Meanwhile `files_changed` is populated from
the staged file count. The result is `commits==0, files_changed>0`, which is
exactly the shape the ratchet rejects.

This is structural rather than incidental. It fires for the first commit of any
session whose log has no ending commit yet, which is why 21 violations were
already in the store when this was diagnosed.

## The fix that works

Do not bump the ratchet ceiling and do not hand-edit the metrics. Record the
commit that actually happened, then re-extract:

```bash
SHA=$(git rev-parse <the commit>)
# set session.endingCommit to the full 40-char SHA in
# .agents/sessions/YYYY-MM-DD-session-NN.json
uv run --frozen python .claude/skills/memory/scripts/extract_session_episode.py \
  .agents/sessions/YYYY-MM-DD-session-NN.json --preserve
```

Then commit the session log and the episode together. The episode records a
commit that exists, so the metric is true rather than patched.

Two traps worth naming:

- `--preserve` alone does **not** repair it. Re-running the extractor against a
  log that still has an empty `endingCommit` returns `commits: 0` and
  `n_events: 0` again. The input is what is wrong, not the extraction.
- `--validate` takes the **episode** path, not the session-log path. Passing the
  session log returns `events must be a list, got NoneType`, which reads like a
  real violation and is not.

Verify with `--validate` against `.agents/memory/episodes` and compare the
violation count to the ratchet baseline, rather than trusting the push.

Related: issue #3972 covers `duration_minutes` and `tool_calls` being zero for
every episode, which is the same class of defect in the same extractor but a
different field.
