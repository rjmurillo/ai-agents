# ADR-008 Claims Ledger: Amendment 2026-11-20, second entry

Claims in the "retrospective lookup guide" amendment and its three table
cells. Each row was re-run on branch `feat/session-start-retro-pointer`
(base `origin/main` `15c13340a`, 2026-11-20) with the working tree as the
subject.

| # | Claim | Kind | Command | Result |
|---|---|---|---|---|
| 1 | The guide is the `RETRO_LOOKUP_GUIDE` constant and runs 770 bytes at `122d56c74` | count | `python -c "import invoke_context_loader as m; print(len(m.RETRO_LOOKUP_GUIDE.encode()))"` from `.claude/hooks/SessionStart` | VERIFIED: 770 bytes, 770 characters at `122d56c74` (754 at `c035b6d86`, before the review changed the memory-tool line) |
| 2 | It prints only when the retrospective directory is real, with no symlinked component | behavior | `pytest tests/hooks/test_context_loader_no_injection.py::test_main_prints_no_guide_behind_a_symlinked_retrospective_dir ::test_main_emits_nothing_when_retro_dir_is_missing` | VERIFIED: both pass; `_retro_dir_is_trusted` reuses `_has_symlink_component` |
| 3 | No filename, title, or body text from the directory reaches the output | behavior | `pytest ...::test_main_guide_carries_no_filename_from_the_directory ::test_main_does_not_inject_retrospective_content` | VERIFIED: output equals the constant plus one LF |
| 4 | A pending reminder prints first; the audit log records `pending-retros:N`, `retro-guide`, or `(none)` | behavior | `pytest ...::test_main_reminder_carries_no_retrospective_content ::test_main_audit_log_records_pending_count ::test_main_audit_log_records_guide_when_retro_dir_exists` | VERIFIED |
| 5 | The previous entry's sentence "The hook now prints only the pending-retro-skeleton reminder" no longer holds | quote | `grep -n "The hook now prints only the pending-retro-skeleton reminder" ADR-008...md` | VERIFIED: line 207, prefix of a sentence that continues "and nothing at all when no skeleton is pending" |
| 6 | At `15c13340a` the directory held 244 Markdown files | count | `git ls-tree --name-only 15c13340a -- .project-toolkit/retrospective/ \| grep -c '\.md$'` | VERIFIED: 244, `INDEX.md` included (HEAD also 244) |
| 7 | 117 filenames carry a number; 21 of them name an ADR or session | count | Filename regex `(?:^\|-)(?:pr-?\|issue-?)?(\d{3,5})(?:-\|$)` on the slug after the leading date, excluding a bare year, over the step 6 listing; ADR or session by `(adr\|session)-\d` | VERIFIED: 117, of which 21 match ADR or session. Earlier wording "issue or PR number" was REFUTED by the architect seat and corrected |
| 8 | The scorer's floor is 0.5 | path | `grep -n "^_MIN_RELEVANCE" scripts/memory_enhancement/hooks/user_prompt_submit_memory.py` | VERIFIED: line 104 |
| 9 | 3 of 25 issue-title prompts recalled the named retrospective at the 0.5 floor | behavior | Sample: 30 of the 117 numbered files, `random.seed(7470)`; titles fetched with `get_issue_context.py` (29 of 30 returned). Each title through `_extract_query`, then `search_memories(..., max_results=3, min_relevance=0.5)` on the retrospective directory | VERIFIED on the 2026-11-20 run, recounted by kind: 3 of 25 issue or PR files, 0 of 4 ADR or session files (a hit is impossible there). Same harness, all 29: floor 0.75 gave 1/29, floor 1.0 gave 0/29 |
| 10 | 1 of 40 recent issue titles whose number names no retrospective injected one | behavior | Negatives: the 40 most recent closed issues from `list_issues.py --state closed --limit 40`, none in the numbered set; same search | VERIFIED: 1/40 at 0.5; 0/40 at 0.75 and 1.0 |
| 11 | Each search took a median 0.68 seconds | count | `time.perf_counter()` around each `search_memories` call in the step 9 and 10 runs, 69 calls | VERIFIED: median 0.68 s, p90 0.74 s, max 0.75 s at floor 0.5; one machine, one run |
| 12 | The dropped injection was 4,000 characters | path | `git show b12beeae6:templates/hooks/SessionStart/invoke_context_loader.py \| grep -n "MAX_RETRO_CHARS = "` | VERIFIED: line 67, `MAX_RETRO_CHARS = 4000` |
| 13 | 770 bytes is under a fifth of 4,000; about 190 tokens | count | 770 / 4000 = 0.193; 770 / 4 = 192.5 at a 4-characters-per-token estimate | VERIFIED as arithmetic; the token figure is an estimate, not a tokenizer count |
| 14 | `INDEX.md` is a curated subset | quote | `grep -n "curated subset" .project-toolkit/retrospective/INDEX.md` | VERIFIED: line 6 |
| 15 | The `memory-search` skill exists in this repository | path | `ls -d .claude/skills/memory-search` | VERIFIED |
| 16 | No eval has measured whether the guide changes a session | absence | `grep -rln "retrospective-guide\|RETRO_LOOKUP_GUIDE" scripts/eval evals tests/evals` | VERIFIED: no hits |
| 17 | #7471 names a counterfactual delta as the influence signal | quote | `get_issue_comments.py --issue 7471`, verdict comment | VERIFIED: "Current `main` answers it with one signal: a counterfactual delta." #7471 is CLOSED |
| 18 | The tests pin output equal to the constant, four required strings, an 800-character ceiling, the symlink refusal, and the absence of directory text | path | `grep -n "GUIDE_MAX_CHARS = \|def test_" tests/hooks/test_context_loader_no_injection.py` | VERIFIED: `GUIDE_MAX_CHARS = 800`, line 31; tests named in rows 2 to 4 |
| 19 | The owner directed the guide-only shape | behavior | Decision briefs D1 (owner picked per-prompt recall) and D2 (after the row 9 to 11 numbers, owner picked guide only) in the authoring session | VERIFIED from the session record; not a repository artifact |
| 20 | The hook ships to no Copilot or plugin consumer | absence | `grep -c context_loader src/claude/hooks/hooks.json src/copilot-cli/hooks/hooks.json`; `ls src/claude/hooks/SessionStart` | VERIFIED: 0 and 0; no SessionStart directory in the plugin tree (`binplace.yaml` lists `SessionStart` under `repo_only`) |
| 21 | The symlink test asserts the `(none)` audit line | path | `grep -n "Loaded: (none)" tests/hooks/test_context_loader_no_injection.py` | VERIFIED at `122d56c74` |

### Row 7 matcher, exact

The critic seat reran a paraphrase of row 7's regex and got 120 to 125. The
count depends on applying the regex to the slug after the leading date and
excluding only a captured bare year. This is the exact command:

```bash
git ls-tree --name-only 15c13340a -- .project-toolkit/retrospective/ | sed 's#.*/##' | python3 -c "
import re, sys
n = adr = 0
for f in sys.stdin.read().split():
    m = re.match(r'\d{4}-\d{2}-\d{2}-(.*)\.md$', f)
    if not m:
        continue
    x = re.search(r'(?:^|-)(?:pr-?|issue-?)?(\d{3,5})(?:-|$)', m.group(1))
    if x and not re.fullmatch(r'20\d\d', x.group(1)):
        n += 1
        adr += bool(re.search(r'(adr|session)-\d', f))
print(n, adr)"
```

It prints `117 21`. The ADR states the count as "by the matcher in the claims
ledger" for this reason.

The step 9 to 11 harness is a scratch script (gitignored). It is not
committed because it is a one-off measurement, not a check anyone reruns.

## Exit gate results

| Gate | Result | Notes |
|---|---|---|
| 1. Claims ledger | VERIFIED | This file, 19 rows |
| 2. Documentation accuracy (Phase 4, one Sonnet agent, code read first) | VERIFIED after fixes | 0 critical, 0 major, 5 minor. Fixed: audit-log claim named one of three tokens; "pins the guide text" overstated a self-comparison; supersession note named one of three stale statements; "no filename reaches the output" now scoped to the guide; a test comment said "an order of magnitude", corrected to a fifth |
| 3. Self-consistency | VERIFIED | Decision items unchanged. The amendment names the three statements in the previous entry it overrides, and the three table cells match it |
| 4. Refuting seat (analyst, haiku) | VERIFIED after fixes | No claim refuted. Seven overstatements fixed: counts lacked a same-line SHA (MUST 9); token figure stated as fact; latency dropped its one-run caveat; "exact and cheap" had no cost measurement; "does not find" overstated 3 of 29; the memory-hook comparison named a plugin outside this repository; the revert claim was unchecked. The seat had no shell, so rows 1, 6, 7, 12, and 17 were UNAVAILABLE to it; this session ran them |
