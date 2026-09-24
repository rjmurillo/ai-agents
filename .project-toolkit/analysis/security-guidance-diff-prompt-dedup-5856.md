# Security-guidance diff prompts: can artifact references replace inline diffs?

**Issue**: [#5856](https://github.com/rjmurillo/ai-agents/issues/5856)
**Spec**: `.project-toolkit/specs/SPEC-5856-security-guidance-diff-prompt-dedup.md`

**Verdict: reject artifact references at this prompt boundary.**
The reviewer must read every `+` and `-` line, so a reference only moves the diff
from the prompt into a tool result. In live runs the referenced mode cost one extra
turn and more input tokens in 5 of 6 comparable cells. It saved nothing a user pays for.
The repeated blocks in local reports come from repeated reviews, not repeated prompts.
The canonical owner is the upstream plugin. The smallest safe follow-up there is a
content-hash review dedupe for commit and push reviews, which the Stop hook already has.

## Provenance

| Item | Value |
|------|-------|
| Plugin | `security-guidance@claude-plugins-official` 2.0.8 |
| Marketplace commit | `55b58ec6e5649104f926ba7558b567dc8d33c5ff` (`~/.claude/plugins/installed_plugins.json`) |
| Install path | `~/.claude/plugins/cache/claude-plugins-official/security-guidance/2.0.8` |
| `hooks/llm.py` SHA-256 | `12cf5daeae80c7b5b9248dcdf9dc48498e5ae97e99d696517038fbe0ea2aa2ef` |
| `hooks/review_api.py` SHA-256 | `b5e5ee59787e174998adb70a53e0b06252449c6e96f2d52e735f8ad5cbe4e319` |
| `hooks/security_reminder_hook.py` SHA-256 | `b3cbbb546d8f28d7efdd23968446cf049e62a48dcbcedd004aec034788991c54` |
| `hooks/diffstate.py` SHA-256 | `161c0720caa77b60505deb3301ac96f799684f929dec85d01e202d65b7844073` |
| Measured on | 2026-09-24, Linux, Claude Code CLI with the plugin installed at user scope |

The plugin was not edited. All line numbers below refer to these hashes.

## Producer-to-prompt call graph

```text
hooks.json PostToolUse Bash, `if` = git commit | git -C * commit * | git push
  security_reminder_hook.py:2252 main()
    :2330-2340 Bash dispatch
      :761  _claim_bash_hook_once()        dedupes one tool_use_id across matchers
      :1028 handle_commit_review_posttooluse()
              :1116 _load_reviewed_shas()  dedupe by commit SHA only
              :1292 git show -p <sha>      builds diff_files
              :1395 _agentic_review_with_race()  (:959)
      :1549 handle_push_sweep_posttooluse()
              :1725 _load_reviewed_shas()  dedupe by commit SHA only
              :1796 _agentic_review_with_race()

_agentic_review_with_race (:959)
  thread A: llm.py:1140 agentic_review()
    llm.py:226  _cap_files_for_prompt()   80,000 B per file, 400,000 B total, markers inline
    llm.py:1202 context_note               "The DIFF below is authoritative" when
                                           SG_AGENTIC_CONTEXT_DIR differs from repo_dir
    llm.py:1210 diff_text join, :1213 user_prompt
    llm.py:1276 _arun() -> :1348 query()   spawns child `claude`, cwd=context_dir (:1285)
      CHILD SESSION 1: investigate (writes a transcript under ~/.claude/projects)
    llm.py:1421 iter2_prompt = user_prompt + exclusions   (only when 1-2 candidates)
      CHILD SESSION 2: full diff again, fresh session
    llm.py:1526 refute_prompt = candidates + diff_text[:8000]
      CHILD SESSION 3: first 8,000 chars of the diff again
  thread B: after SG_AGENTIC_RACE_DELAY_S (180 s) if A has not finished
    llm.py:790 analyze_code_security()     HTTP, :818 re-caps the same diff, no transcript
security_reminder_hook.py:1402 agentic_fallback -> analyze_code_security() again, no transcript

hooks.json Stop | SubagentStop
  security_reminder_hook.py:1899 handle_stop_hook()
    :2043-2046 reviewed_diff_hash          dedupe by SHA-256 of the diff text
    :2082 analyze_code_security()          HTTP; on Bedrock, Vertex, or Foundry it routes
                                           through llm.py:342 _call_claude_via_sdk (child session)
```

Two findings from the trace correct the issue text.

1. `review_api.py:156-175` `build_investigate_prompt` has no caller inside the plugin.
   Its docstring names it the public API for external harnesses.
   The hook path builds its own copy at `llm.py:1210-1222`.
   The copy omits `extensibility.guidance_block()`, so the two producers already diverge.
2. Only the agentic commit and push path writes local transcripts.
   The Stop hook and every fallback call the HTTP API directly, so they repeat the diff
   on the wire but never appear in a transcript-based report.

## Transcript audit

Command: `uv run python -m scripts.metrics.sg_prompt_audit --since 2026-08-22 --until 2026-09-20`.
The tool emits hashes, sizes, paths, cap state, and usage. It never emits diff content.
The earliest child transcript on disk is dated 2026-09-10, so the issue window holds 11 days of data.

| Metric | Issue window (to 2026-09-20) | All transcripts (to 2026-09-24) |
|--------|------------------------------|---------------------------------|
| Child sessions | 223 (216 investigate, 6 iter2, 1 refute) | 328 (319, 8, 1) |
| Prompt bytes | 5,475,987 | 7,426,324 |
| Estimated tokens (bytes / 4) | 1,368,996 | 1,856,581 |
| Repeated whole-diff groups | 14 | 19 |
| Redundant whole-diff bytes | 1,725,629 | 1,757,354 |
| Failed sessions | 15 (12 no structured output, 3 no assistant turn) | 23 (20, 3) |

The issue's largest block is reproduced exactly.
`src/claude/lib/github_core/api.py` has one 58,922-byte diff block, about 14,730 tokens,
in five child sessions of one project. The next two are `ai_review_common/verdict.py`
(23,234 B, five sessions) and `github_core/workflow_event_subscriptions.py` (22,516 B, five sessions).

The 14 repeated whole-diff groups fall into two causes.

- **Designed repeats (6 groups).** Investigate plus iter2 or refute on the same review.
  Iter2 is a fresh child session, so its first turn re-creates the prompt cache for the diff.
  Measured first-turn usage: `cache_read` stays at the 21,092-token shared prefix, and
  `cache_creation` is 5,351 to 16,240 tokens per iter2 session.
- **Duplicate reviews (8 groups, 660,787 redundant bytes, about 165,000 tokens, 12.1% of window bytes).**
  Two investigate sessions reviewed byte-identical diffs 4.5 to 1,001 seconds apart, seven
  in one checkout and one across two checkouts. The commit and push handlers dedupe by
  commit SHA (`:1116`, `:1725`), so identical content under a new SHA is reviewed again.
  INFERRED: amend, rebase, cherry-pick, and a repeated commit in a sibling worktree all
  produce that shape. The transcripts do not record which one happened.

Inside each child session the diff is not paid once. The session re-reads its context
every turn (median 7 assistant messages, max 34). Across all 328 sessions the usage
fields sum to 101,814,587 cache-read tokens and 23,954,128 cache-creation tokens.
A reference does not change this: once the reviewer reads the artifact, the diff sits
in a tool result and is re-read every turn the same way.

## Reference model and safety fixtures

`scripts/metrics/sg_diff_reference.py` and `scripts/metrics/sg_diff_artifact.py` model the
candidate design. They are evaluation code, not wired to any hook.

| Property | Rule |
|----------|------|
| Identity | SHA-256 and byte length of the exact capped diff text, plus repository identity (SHA-256 of `git rev-parse --git-common-dir` realpath and `remote.origin.url`), reviewed `HEAD`, and SHA-256 of the path order |
| Storage | `<store>/<repo_id>/<sha256>.diff`, directory mode 0700, file mode 0600, atomic replace |
| Retention | `prune(store, max_age_s)` deletes artifacts older than the window |
| Access | Only the `read_diff_artifact` tool resolves a reference; symlinked artifacts are refused |
| Mismatch | `invalid_ref`, `cross_repo`, `stale`, `missing`, `unreadable`, and `tampered` all fall back |

The tests assert each acceptance criterion deterministically:

- Every failure reason returns a prompt byte-equal to the plugin's inline prompt.
- The read-time tool re-verifies and serves the exact inline diff on failure.
- A `../` traversal reference is refused before any path is built.
- Inline and resolved texts have identical per-file `+` and `-` line multisets for the
  repeated-diff, changed-paths (rename, delete, new file), truncation, and checkout-mismatch fixtures.
- The authoritative-diff warning appears verbatim in both prompt modes.
- The inline builder matches the plugin's capping byte for byte when the plugin is installed.

The model shows a reference can be made safe. It also shows the cost of safety: the
producer must hold the exact inline text for fallback, and the reader must re-hash on every read.

## Live A/B

Command: `uv run python -m scripts.metrics.sg_reference_ab --runs N --model M`.
Each run is a Messages API tool loop with the plugin's `AGENTIC_INVESTIGATE_SYSTEM` and
`FINDINGS_SCHEMA` loaded from the installed plugin. Tools are `read_file`, `grep`, and,
in referenced mode, `read_diff_artifact`. Each fixture seeds one new vulnerability in `+`
lines and one pre-existing vulnerability in context lines only.
Harness gap: this is not the plugin's child CLI, so absolute token counts differ from
production. The comparison between modes is the result that matters.

Valid runs only. Runs that failed with the API billing error
(`invalid_request_error: credit balance is too low`) are excluded; they never reached the model.

| Model | Fixture | Mode | Runs | Prompt B | Median input tokens | Median latency s | Median turns | Seeded found | Pre-existing flagged |
|-------|---------|------|------|----------|---------------------|------------------|--------------|--------------|----------------------|
| Sonnet 5 | f_repeat | inline | 5 | 528 | 14,784 | 13.1 | 3 | 5 | 5 |
| Sonnet 5 | f_repeat | referenced | 5 | 667 | 20,817 | 12.8 | 4 | 5 | 1 |
| Sonnet 5 | f_paths | inline | 5 | 751 | 15,325 | 12.0 | 3 | 5 | 3 |
| Sonnet 5 | f_paths | referenced | 5 | 749 | 15,728 | 11.7 | 3 | 5 | 2 |
| Sonnet 5 | f_trunc | inline | 5 | 6,654 | 21,713 | 10.4 | 2 | 5 | 1 |
| Sonnet 5 | f_trunc | referenced | 1 | 736 | 27,647 | 13.2 | 3 | 1 | 1 |
| Opus 4.7 | f_repeat | inline | 3 | 528 | 15,892 | 18.5 | 3 | 3 | 0 |
| Opus 4.7 | f_repeat | referenced | 3 | 667 | 22,283 | 17.3 | 4 | 3 | 0 |
| Opus 4.7 | f_paths | inline | 3 | 751 | 16,255 | 17.0 | 3 | 3 | 0 |
| Opus 4.7 | f_paths | referenced | 3 | 749 | 23,392 | 19.8 | 4 | 3 | 0 |
| Opus 4.7 | f_trunc | inline | 3 | 6,654 | 34,010 | 13.9 | 3 | 1 | 0 |
| Opus 4.7 | f_trunc | referenced | 3 | 736 | 28,630 | 13.9 | 3 | 0 | 0 |
| Opus 4.7 | f_mismatch | inline | 2 | 797 | 16,205 | 17.5 | 3 | 2 | 0 |
| Opus 4.7 | f_mismatch | referenced | 0 | | | | | | |

`claude-opus-4-7` is the plugin's default agentic model (`llm.py:1192`). Sonnet 5 is this
repository's default eval model.

What the runs show:

- **Tokens.** Referenced mode used more input tokens in 5 of 6 cells with a valid pair
  (+3% to +44%). The one saving (Opus `f_trunc`, -16%) came with the seeded finding
  missed in all three referenced runs.
- **Turns and latency.** The reference adds a fetch turn in 4 of 6 cells. Median latency
  moved between -1.2 and +2.8 seconds, inside run-to-run noise.
- **Failures.** No model-side failure in any valid run. Every reviewer called
  `read_diff_artifact` when it was offered (20 of 20 valid referenced runs).
- **Findings.** Seeded detection matched in every cell except Opus `f_trunc` (1 of 3 inline,
  0 of 3 referenced). Finding sets differ only by category wording, such as
  "Command Injection" and "OS Command Injection". The sample is too small to claim equivalence.
- **Prompt size.** On fixtures this small the pointer block can be larger than the diff
  (528 B to 667 B). Prompt bytes only shrink for large diffs, and those bytes return as a tool result.

Gap: the checkout-mismatch fixture has no referenced run and only two inline runs. The live
API key ran out of credit mid-run, and the 1Password fallback prompt was dismissed twice.
The deterministic tests cover the mismatch warning and fallback. The live mismatch cell
is unmeasured.

## Options compared

| Option | Wire tokens | Transcript bytes | Correctness risk | Verdict |
|--------|-------------|------------------|------------------|---------|
| Inline diff (today) | Baseline | Baseline | None added | Keep |
| Session-local artifact | Same or higher, plus a turn | Lower in the prompt, same in the tool result | Stale and cross-session reads; needs fallback | Reject |
| Content-addressed artifact | Same or higher, plus a turn | Same as session-local | Needs identity, retention, and tamper checks, all modeled here | Reject |
| Content-hash review dedupe | Removes a whole review per duplicate | Removes a whole child session per duplicate | Must key on capped diff text plus repo identity and reviewed `HEAD` | Adopt, upstream |
| Resume investigate session for iter2 | Iter2 reads the diff from cache | Iter2 lands in the same transcript | Changes the iter2 isolation the plugin chose | Defer, upstream |

## Decision

- **Canonical owner**: the upstream `security-guidance` plugin in
  `anthropics/claude-plugins-official`. Every producer and every repeat path lives there.
  This repository only consumes the plugin. #5851 owns raw tool-output containment and
  #4871 owns always-on context measurement; neither owns this boundary.
- **Artifact references**: reject. The measured cost is higher, the safety rules add a
  second source of truth for the diff, and no user-visible saving remains once the
  reviewer reads the artifact.
- **Smallest safe follow-up**, for the upstream owner: key the commit and push dedupe on
  SHA-256 of the capped diff text plus repository identity and reviewed `HEAD`, alongside
  the commit SHA. The Stop hook already does this with `reviewed_diff_hash`
  (`security_reminder_hook.py:2043-2046`). In the issue window this would have removed 8
  child sessions and about 165,000 prompt tokens before per-turn re-reads.
  The follow-up has not been filed. Filing on an external repository is the maintainer's decision.

## Noticed, outside this issue

- `review_api.build_investigate_prompt` and `llm.py:1210-1222` are two copies of one prompt,
  and only the first appends the extensibility guidance block. Upstream owner.
- 46 of 328 child review sessions contain a `Bash` tool call, although
  `allowed_tools` is `Read`, `Grep`, `Glob` (`llm.py:1287`). The transcripts do not
  show whether those calls were approved. Upstream owner; worth a security look.
- 23 of 328 child sessions ended without structured output; 3 of them have no assistant
  turn at all. A failed investigate falls back to the HTTP reviewer, which re-sends the diff.
  A failed iter2 adds no candidates (`llm.py:1433-1449`). Both are cost repeats, not hidden failures.

## Reproduce

```bash
uv run python -m scripts.metrics.sg_prompt_audit --since 2026-08-22 --until 2026-09-20
uv run python -m scripts.metrics.sg_reference_ab --runs 5 --output ab-sonnet5.json
uv run python -m scripts.metrics.sg_reference_ab --runs 3 --model claude-opus-4-7 --output ab-opus47.json
uv run pytest tests/metrics/test_sg_*.py -q
```
