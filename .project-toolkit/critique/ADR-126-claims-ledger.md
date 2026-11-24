# ADR-126 Claims Ledger

Every factual claim in ADR-126, checked against the working tree on branch
`t3/7cbd5e13` on 2026-11-23. Rows 4, 5, and 12 to 15 were re-read after the
round 2 revision.

| # | Claim | Kind | Command | Result |
|---|-------|------|---------|--------|
| 1 | ADR-106 is accepted, dated 2026-09-08 | quote | `sed -n 3,4p` on ADR-106 | VERIFIED: `status: accepted`, `date: 2026-09-08` |
| 2 | ADR-106 Decision 2 makes Serena the only backend under `.serena/memories/` | quote | `sed -n 87,88p` on ADR-106 | VERIFIED: "Serena is the only memory backend. Committed markdown under `.serena/memories/`" |
| 3 | ADR-106 Decision 5 makes identity the path under `.serena/memories/` | quote | `sed -n 123,126p` on ADR-106 | VERIFIED |
| 4 | `repository_memory_dir` is at `scripts/memory_enhancement/__init__.py:58`; Serena first, notes second, else `None` | path | `grep -n "^def repository_memory_dir"`; read the body | VERIFIED |
| 5 | Root rule: `__init__.py:24`, `search_memory.py:311`, `memory_router.py:91`. Store rule: `__init__.py:58`, `search_memory.py:340`, `memory_router.py:98` | path | `grep -n` for each definition | VERIFIED |
| 6 | Recall and SessionEnd hooks use the package copies; the CLI uses `repository_memory_dir` with `--repo-root` | behavior | `grep -ln "find_memory_root\|repository_memory_dir"` over hooks and `__main__.py` | VERIFIED after correction. First draft said the CLI used `find_memory_root`; it does not |
| 7 | Root parity test covers four layouts; store parity test covers five | count | `LAYOUTS` and `STORE_LAYOUTS` in the test | VERIFIED |
| 8 | `search_memory.py` and `memory_router.py` are stdlib-only at import | behavior | `grep -n "^import\|^from"` | VERIFIED |
| 9 | ADR-038 and ADR-063 exist | path | `ls .project-toolkit/architecture` | VERIFIED |
| 10 | The prompt recall hook does not ship to plugin installs | absence | `grep -c UserPromptSubmit` on `src/claude/hooks/hooks.json` and `src/copilot-cli/hooks/hooks.json` | VERIFIED: 0 and 0 |
| 11 | The recall hook frames excerpts as data and collapses them to one line | behavior | `user_prompt_submit_memory.py:206,231`; `test_recall_field_cannot_forge_a_heading_or_source_line` | VERIFIED. A mutation removing the collapse failed that test (1 failed, 11 passed) |
| 12 | Eight maintenance scripts default to `.serena/memories` | count | `grep -c '\.serena/memories'` in each named script | VERIFIED: each has at least one occurrence |
| 13 | Search and SessionEnd name the `git mv` step for shadowed notes | behavior | `test_search_names_the_git_mv_step_for_shadowed_notes`, `test_session_end_names_shadowed_notes` | VERIFIED: both pass |
| 14 | The router starts from `CLAUDE_PROJECT_DIR` | behavior | `test_router_prefers_the_project_directory_over_the_current_directory`; mutation to `Path.cwd()` | VERIFIED: mutation failed the test (1 failed, 30 passed) |
| 15 | Every Confirmation test name exists | path | `grep -c "^def <name>"` over the seven newest names | VERIFIED: 7 of 7 |

## Gate results

- Claims ledger: VERIFIED, 15 rows, 1 corrected before hand-off.
- Self-consistency: VERIFIED. Decision 1 (one store) agrees with Decision 6
  (ADR-106 Decision 3 stands), with Decision 2's list of Serena-layout scripts,
  and with the Negative consequences on shadowed notes.
- Documentation accuracy: covered by rows 4 to 8 and 11 to 15.
- Refuting seat (analyst, haiku): 10 rows confirmed, row 11 partial (the seat
  did not run the mutation; the writer did). Three body findings, all fixed
  before hand-off: the Prior Art line omitted the `None` case; the CLI default
  for a repository with no store was `.serena/memories`, contrary to Decision 1,
  and the code now names the notes folder; the parity-test sentence overstated
  its coverage. One finding concerns ADR-106 itself: its line 95 cites
  `search_memory.py:296` for the `search_episodes` call, which has moved.
  ADR-106's body is not edited here.
