# Investigation: Issue #2537 — Session-log + Episode Tooling Emits Incomplete Metadata

**Issue:** https://github.com/rjmurillo/ai-agents/issues/2537
**Investigator:** analyst (kanban task t_a46e366f)
**Date:** 2026-06-10
**Confidence:** HIGH
**Base commit:** e02408d8 (origin/main)

## Problem Framing

Across every PR opened in session 2381 (#2528, #2532, #2533, #2534, #2536) the AI review bots (Copilot + AI Quality Gate Analyst) independently flagged the same five session-log and episode-extractor metadata gaps. These artifacts are produced by repo tooling, not by PR authors, so the findings recur on every session PR and the review noise compounds. The goal is to fix the *generators* once so the noise stops, without weakening the protocol.

## Hypotheses (Ranked)

1. **[MOST LIKELY — verified]** Each gap is a separate one- to two-file fix in the session tooling. The generators write a partial document; an out-of-band human/manual step is supposed to fill the rest; that step is unreliable in practice.
2. (Rejected) Validator divergence — a validator change quietly stopped enforcing fields. Verified: the deterministic validator never enforced `schemaVersion` or `endingCommit`. The schema document `session-log.schema.json` *declares* `schemaVersion` but does NOT mark it `required`. The protocol document `.agents/SESSION-PROTOCOL.md` lists `schemaVersion` under "Required top-level fields" (line 949). So the drift is **doc ↔ generator ↔ schema**, present since the JSON schema was introduced.
3. (Rejected) Already fixed upstream. Verified: no open or merged PR on `main` references "Fixes #2537"; PR #2549 is the source RCA that surfaced these patterns.

## Evidence Gathered

### 1. `endingCommit` is empty everywhere

`new_session_log.py` (`.claude/skills/session-init/scripts/new_session_log.py` line 237) initializes `endingCommit = ""`. There is **no post-commit hook**; `grep -rn "post-commit"` finds only a CI workflow comment, not an actual hook file. The session-end backfill script DOES exist (see below) but is invoked manually.

**Empirical sample from session 2381 logs in `.agents/sessions/`:**

| File | `endingCommit` | `changesCommitted.Evidence` | Trailing `\n` | `schemaVersion` |
|------|---|---|---|---|
| `…2381-fix-issue-2348-derive-action.json`        | `""` | `"Committed in this commit (test fix + session log)"` | No  | MISSING |
| `…2381-fix-issue-2519-pr-maintenance-auto…json`  | `""` | `"Done this session"`                                  | No  | MISSING |
| `…2381-fix-issue-2520-workflow-injection.json`   | `""` | `"Done this session"`                                  | Yes | MISSING |

All three sessions were committed to `main` (real SHAs from `git log --all`: 8e077b11, 26834291, 5a1b3213). The information exists; the file just never gets the SHA written back.

### 2. `changesCommitted` Evidence has no SHA

Same row as above. Even when the user writes free-form evidence at session-end, the SHA isn't templated into it. The hidden expectation is `complete_session_log.py` will overwrite this, but only when manually invoked.

### 3. Episode `files_changed` / `commits` / `duration_minutes` are 0

**Root cause confirmed in `.claude/skills/memory/scripts/extract_session_episode.py` line 650–671 (`json_metrics`):**

```python
def json_metrics(data: dict) -> dict:
    commit_count = len(_collect_shas(data, include_starting=False))
    metrics = {
        "duration_minutes": 0,            # never sourced; left zero
        "tool_calls": 0,
        "errors": 0,
        "recoveries": 0,
        "commits": commit_count,           # only counts SHAs already in workLog
        "files_changed": 0,
    }
    for entry in _as_list(data.get("workLog")):
        text = _entry_text(entry)
        fail = _valid_fail_match(text)
        if fail:
            metrics["errors"] += int(fail.group(1))
        files = _FILES_RE.search(text)     # prose pattern: "N files"
        if files:
            metrics["files_changed"] += int(files.group(1))
    return metrics
```

The extractor walks the **session-log workLog prose**, not git. It only finds `files_changed` when an author wrote literally "5 files changed" into a workLog entry — which authors rarely do. Likewise `commits` is the count of SHAs already mentioned in the workLog (plus `endingCommit` when set), so if `endingCommit` is empty AND nobody pasted the SHA into workLog, the count is 0.

**Empirical sample from `.agents/memory/episodes/` (107 episodes total):**

| Episode | `duration_minutes` | `files_changed` | `commits` |
|---|---|---|---|
| `episode-2026-06-07-session-2373.json` | 0 | 0 | 1 |
| `episode-2026-06-10-session-2381-fix-issue-2524-move-tiktoken.json` | 0 | 0 | 0 |
| `episode-2026-06-10-session-2381-fix-issue-2348-derive-action.json` | 0 | 0 | 0 |
| `episode-2026-06-07-session-2374-drive-2499-ready-merge.json` | 0 | 0 | 1 |
| `episode-2026-06-10-session-2381-fix-issue-2525-remove-hardcoded.json` | 0 | 0 | 0 |
| `episode-2026-06-09-session-2380.json` | 0 | 0 | 0 |
| `episode-2026-06-10-session-2381-fix-issue-2521-security-commit.json` | 0 | 0 | 0 |
| `episode-2026-06-10-session-2382-analyze-recent-prs-thrashingchurn-rca.json` | 0 | 0 | 1 |

7 of 8 sampled episodes report `commits=0` or `commits=1`; ALL report `files_changed=0` and `duration_minutes=0`. The pre-commit hook (`/.githooks/pre-commit` line 1280–1337) calls the extractor with `--preserve` mode (non-destructive merge) but never passes any git-stat context. The extractor cannot know what was staged.

### 4. Missing `schemaVersion`

`new_session_log.py` `_build_session_data()` (line 191–239) returns a dict with no `schemaVersion` key. `.agents/SESSION-PROTOCOL.md` line 949 says it is required (`"1.0"`). The JSON schema at `.agents/schemas/session-log.schema.json` *defines* the property with description "required for new sessions" but the schema's `required` array is only `["session", "protocolCompliance"]` (line 7). So:

- Doc says required
- Schema implies required but doesn't enforce
- Generator omits it
- Validator (`scripts/validate_session_json.py`) never checks for it (`grep -n "schemaVersion" scripts/validate_session_json.py` → no match)

The review bots are reading the doc and flagging the omission. No tooling stops the omission.

### 5. No trailing newline at EOF

Both writers use `json.dump(data, f, indent=2)` which produces no trailing newline:
- `new_session_log.py` line 265: `content = json.dumps(session_data, indent=2)` → `os.write(fd, content.encode("utf-8"))`
- `complete_session_log.py` lines 475 and 509: `json.dump(session, f, indent=2)`

Trailing-newline rule is POSIX convention and several lint stacks (`prettier`, `eol-last`, `editorconfig`) flag the missing newline. Empirically 2 of 3 sampled session-2381 logs lack the trailing `\n`.

## Findings

### Confirmed true

- All five gaps in the issue body are real and currently present in `main` at e02408d8.
- The root cause is generator-side: `new_session_log.py` omits two fields and writes with no trailing newline; `extract_session_episode.py` reads workLog prose instead of git stats; `complete_session_log.py` exists and *would* backfill `endingCommit` + `changesCommitted` Evidence with the HEAD SHA, but only when manually invoked.
- `complete_session_log.py` is invoked by:
  - The Copilot CLI **Stop** hook (`src/copilot-cli/hooks/SessionEnd/invoke_session_validator.py` line 271, 282) — *but only as a printed reminder, not enforced*.
  - The orchestrator agent prompt (`src/copilot-cli/agents/orchestrator.agent.md` line 171, `src/claude/orchestrator.md` line 172) — *prose instruction only*.
  - SKILL.md documentation — *manual invocation*.
  None of these is a hard gate; sessions that commit without explicitly running `session-end` produce the partial logs we see.

### Unknown / Open Questions

- **Should `endingCommit` ever be writable pre-commit?** A pre-commit hook cannot know its own resulting SHA. A post-commit hook can, but it would mutate a file that's already in the commit (creating either an uncommitted diff or a follow-up "fix endingCommit" commit). The cleanest fix is to drop the field-as-presented from the per-commit log entirely OR to accept that it lives in a separate post-commit-written sidecar file. The issue body suggests "back-fill by a session-end step" — that's what `complete_session_log.py` already does when invoked. The unresolved question is whether to make that invocation **mandatory** (e.g. via a pre-push hook) or to **rewrite the protocol** so an empty `endingCommit` is no longer flagged.
- **Should episode metrics use `git diff --cached --numstat` (pre-commit) or `git show --stat <SHA>` (post-commit)?** The pre-commit hook has access to the staged diff. If we change `extract_session_episode.py` to accept a `--git-stats` flag and pipe the numstat through, the metric becomes accurate for staged-file extraction. But the same script is also called manually on historical logs, where the SHA must come from `endingCommit` (which loops back to gap #1).

### Contradictions to resolve

- Protocol doc lists `schemaVersion` as required, schema description says "required for new sessions", schema `required[]` does not include it, validator never checks it. **All four sources must align.**

## Root Cause (5 Whys)

**Why are reviewers flagging the same fields on every PR?**
→ Because the session JSON in those PRs has empty `endingCommit`, no `schemaVersion`, missing SHA in `changesCommitted` evidence, zero metrics, and no trailing newline.

**Why is the data missing?**
→ Because the generators (`new_session_log.py`, `extract_session_episode.py`) emit a partial document that requires a manual second step (`complete_session_log.py`) to finish.

**Why doesn't the second step always run?**
→ Because it's a printed reminder in the Stop hook, not a hard gate. Sessions that commit and push without invoking `session-end` ship the partial log.

**Why is there no hard gate?**
→ Because the cleanest gate (post-commit hook that mutates the just-committed file) would create either an uncommitted-after-commit diff or a follow-up commit, both of which complicate the git history.

**Why hasn't this been fixed before?**
→ Because each gap is small enough on its own to dismiss as "the author's checklist," but together they constitute a systemic tooling gap that produces noise on every session PR. PR #2549's churn RCA is what made the recurrence pattern legible.

## Recommendation

**Spawn child task assigned to `implementer`** with the following minimum scope. The fixes split into three commits to keep each diff < 5 files (ADR-008):

### Commit 1 — `new_session_log.py` one-liners (gaps #4, #5)
- Add `"schemaVersion": "1.0"` to the top-level dict in `_build_session_data()` (insert at line 202, before `"session"`).
- Change `_write_session_file()` line 265–266 to write `json.dumps(session_data, indent=2) + "\n"`.
- Add unit test in `.claude/skills/session-init/tests/test_session_init.py` asserting both `schemaVersion == "1.0"` and the file ends with `\n`.
- Update `.agents/schemas/session-log.schema.json`: add `"schemaVersion"` to top-level `required` array.
- Update `scripts/validate_session_json.py`: add `schemaVersion` check (string matching `^\d+\.\d+$`).
- Run validator against existing session logs to confirm none break (existing logs lack the field; either backfill them in the same commit or accept transient validator failures for archived logs).

### Commit 2 — `complete_session_log.py` trailing newline + preserve `schemaVersion` (gap #5 secondary)
- Both `json.dump(...)` calls on lines 476 and 510 → switch to `f.write(json.dumps(session, indent=2) + "\n")`.
- Add unit test in `.claude/skills/session-end/tests/test_complete_session_log.py` for trailing-newline invariant.
- The script already handles `endingCommit` and `changesCommitted` Evidence backfill (lines 366–369, 436–441). Verify by test that running it after a real commit produces non-empty values.

### Commit 3 — `extract_session_episode.py` real metrics (gap #3)
- Add `--git-stats` CLI flag to `extract_session_episode.py` that takes optional `<sha>` (or `--staged`) and runs `git show --stat <sha>` / `git diff --cached --numstat` to compute `files_changed` and `commits` from authoritative source.
- Update `/.githooks/pre-commit` line 1298 to pass `--staged` to the extractor.
- Fall back to current prose-scan behavior when neither flag is provided (so manual re-extraction of historical logs still works).
- Document `duration_minutes` as best-effort (the field is unrecoverable for historical logs; for new ones, compute as `now - startingCommit committer date` when the SHA is available).
- Add tests covering: (a) `--staged` pre-commit path produces nonzero `files_changed` when files are staged, (b) `--git-stats <sha>` produces correct counts for an existing commit, (c) prose fallback still works.

### Gate decision (gap #1, #2): protocol clarification needed BEFORE Commit 3 ships
The five-finding pattern won't fully stop unless `endingCommit` and the SHA-in-evidence problem are resolved. Two options:

- **Option A (mechanical):** Add a `pre-push` hook (not pre-commit) that runs `complete_session_log.py` on any staged session log; refuses to push if `endingCommit` is empty. This is what `.githooks/pre-push` is for; the file exists and can grow this check.
- **Option B (protocol):** Update `.agents/SESSION-PROTOCOL.md` to drop `endingCommit` as a required top-level field and instead introduce a sidecar `*.session-end.json` written post-commit (out of band, never re-committed). This removes the rule that reviewers are flagging.

**Recommendation: Option A.** It preserves the existing log shape (no consumer changes), and `pre-push` is the natural cut-point — by the time the user pushes, the commit exists and the SHA is knowable. Option B is a larger schema migration with unclear consumer impact. Suggest the implementer ship Commits 1–3 first, then a follow-up Commit 4 adding the pre-push gate.

### Acceptance verification
- Generate a fresh session log via `new_session_log.py`, confirm `schemaVersion: "1.0"` and trailing `\n`.
- Run a no-op commit, then `complete_session_log.py`, then `extract_session_episode.py --staged HEAD~1..HEAD`; confirm `endingCommit`, `changesCommitted` Evidence SHA, and episode `files_changed`/`commits` are all populated and nonzero.
- Open a follow-up PR (any small one) and verify Copilot + AI Quality Gate Analyst do NOT flag the five fields again.

## Open Questions for the Implementer

1. **Schema migration impact** — existing session logs lack `schemaVersion`. Adding it to `required[]` would invalidate every historical log. Options: (a) backfill all in the same PR, (b) make the validator accept missing `schemaVersion` for files older than commit X. Need a call.
2. **Pre-push hook enforcement** — is there appetite for a pre-push gate that *blocks* a push when `endingCommit == ""` on a staged session log? Or should it just be a warning? The CI workflow `ai-session-protocol.yml` could enforce it server-side instead, which is more reversible.
3. **`duration_minutes` source of truth** — orchestrator/skill tooling could write a `sessionStart.startTimestamp` ISO field and `complete_session_log.py` could compute `(now - startTimestamp).total_minutes()`. Worth adding in this PR or out of scope?

## Handoff

- **Confidence:** HIGH — all five findings empirically verified against the codebase at `e02408d8` and against actual session 2381 artifacts.
- **Recommended next agent:** `implementer` for Commits 1–3 (mechanical fixes). Defer `architect` consultation only if Option B (sidecar schema migration) is chosen instead of Option A.
- **Files to touch (Commit 1 + 2 + 3):**
  - `.claude/skills/session-init/scripts/new_session_log.py`
  - `.claude/skills/session-init/tests/test_session_init.py`
  - `.agents/schemas/session-log.schema.json`
  - `scripts/validate_session_json.py`
  - `.claude/skills/session-end/scripts/complete_session_log.py`
  - `.claude/skills/session-end/tests/test_complete_session_log.py`
  - `.claude/skills/memory/scripts/extract_session_episode.py`
  - `.claude/skills/memory/tests/test_extract_session_episode.py`
  - `/.githooks/pre-commit` (one-line flag change)
  - (mirror copies under `src/copilot-cli/skills/...` — verify with `find . -name "<file>"`)
- **Out-of-band correction to the issue body:** the issue says "no session-end step that back-fills" the endingCommit. **That's wrong** — `complete_session_log.py` exists and back-fills both `endingCommit` AND `changesCommitted` Evidence with the HEAD SHA. The gap is enforcement, not capability. Implementer should reference this correction in the PR description so the issue closer doesn't try to re-build what already exists.
