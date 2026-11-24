# ADR-126 Claims Ledger

Every factual claim in ADR-126, checked against the working tree on branch
`t3/7cbd5e13` on 2026-11-23. Rows 4, 5, and 12 to 15 were re-read after the
round 2 revision; rows 4, 5, 8, and 16 to 18 after the module move; rows 10, 11, 17, and 19 to 22 after merging #7523.

| # | Claim | Kind | Command | Result |
|---|-------|------|---------|--------|
| 1 | ADR-106 is accepted, dated 2026-09-08 | quote | `sed -n 3,4p` on ADR-106 | VERIFIED: `status: accepted`, `date: 2026-09-08` |
| 2 | ADR-106 Decision 2 makes Serena the only backend under `.serena/memories/` | quote | `sed -n 87,88p` on ADR-106 | VERIFIED: "Serena is the only memory backend. Committed markdown under `.serena/memories/`" |
| 3 | ADR-106 Decision 5 makes identity the path under `.serena/memories/` | quote | `sed -n 123,126p` on ADR-106 | VERIFIED |
| 4 | `repository_memory_dir` in `scripts/memory_enhancement/stores.py` picks Serena first, notes second, else `None` | path | `grep -n "^def repository_memory_dir"`; read the body | VERIFIED on 2026-11-23 after the module move |
| 5 | Root and store rules exist in `scripts/memory_enhancement/stores.py`, `memory_core/memory_store.py`, and `scripts/store_resolution.py` beside `search_memory.py` | path | `grep -n "^def find_memory_root\|^def repository_memory_dir\|^def resolve_memory_store\|^def resolve_stores\|^def shadowed_notes_dir"` in the three files | VERIFIED on 2026-11-23; ADR-126 now names symbols, not line numbers |
| 6 | Recall and SessionEnd hooks use the package copies; the CLI uses `repository_memory_dir` with `--repo-root` | behavior | `grep -ln "find_memory_root\|repository_memory_dir"` over hooks and `__main__.py` | VERIFIED after correction. First draft said the CLI used `find_memory_root`; it does not |
| 7 | Root parity test covers four layouts; store parity test covers five | count | `LAYOUTS` and `STORE_LAYOUTS` in the test | VERIFIED |
| 8 | `search_memory.py`, `store_resolution.py`, `memory_router.py`, and `memory_store.py` import only the standard library or each other | behavior | `grep -E '^(import|from) '` in the four files, 2026-11-23 | VERIFIED: the only non-stdlib imports are `from store_resolution import` and `from .memory_store import` |
| 9 | ADR-038 and ADR-063 exist | path | `ls .project-toolkit/architecture` | VERIFIED |
| 10 | The prompt recall hook ships to Claude plugin installs only, not Copilot | path | `grep -c UserPromptSubmit` on `src/claude/hooks/hooks.json` and `src/copilot-cli/hooks/hooks.json` | VERIFIED on 2026-11-23 after merging #7523: 1 and 0 (the first draft said 0 and 0, before #7523) |
| 11 | The recall hook frames excerpts as data and collapses snippets to one line | behavior | `_PREFACE` and `_format_entry` in `user_prompt_submit_memory.py`; `test_recall_snippet_cannot_forge_a_heading_or_source_line` | VERIFIED on 2026-11-23 |
| 12 | Eight maintenance scripts default to `.serena/memories` | count | `grep -c '\.serena/memories'` in each named script | VERIFIED: each has at least one occurrence |
| 13 | Search and SessionEnd name the `git mv` step for shadowed notes | behavior | `test_search_names_the_git_mv_step_for_shadowed_notes`, `test_session_end_names_shadowed_notes` | VERIFIED: both pass |
| 14 | The router starts from `CLAUDE_PROJECT_DIR` | behavior | `test_router_prefers_the_project_directory_over_the_current_directory`; mutation to `Path.cwd()` | VERIFIED: mutation failed the test (1 failed, 30 passed) |
| 15 | Every Confirmation test name exists | path | `grep -c "^def <name>"` over the seven newest names | VERIFIED: 7 of 7 |
| 16 | A shipped script may import only the standard library, a declared dependency, its tree's `lib/`, or a module beside it | quote | read `build/scripts/import_closure.py` module docstring, "An absolute import resolves when..." | VERIFIED on 2026-11-23 |
| 17 | Every `test_*` name cited in ADR-126 exists | path | `grep -rq "def <name>"` over `tests/` for each backticked `test_*` name | VERIFIED on 2026-11-23 after renaming two stale citations; an earlier VERIFIED here missed one |
| 18 | The shipped lib bootstrap fails when `CLAUDE_PLUGIN_ROOT` names another plugin | behavior | pytest run with the context-mode plugin root exported, 2026-11-23 | VERIFIED: `RuntimeError: Expected portability helper lib directory not found` |
| 19 | ADR-109's 2026-11-20 amendment treats consumer memory as untrusted repository content and says a repository without `.serena/memories/` gets no output | quote | `git show origin/main:` ADR-109, "Trust boundary." and "Consumer impact." paragraphs | VERIFIED on 2026-11-23 at `a6ccc9e6` |
| 20 | The recall hook shares the root rule and recalls only under a `.git` at or above that root; it notes an escaping Serena folder | behavior | `test_hook_and_skill_choose_the_same_root` (hook column), `test_hook_recalls_notes_only_inside_a_checkout`, and the two `test_memory_recall_limits.py` tests | VERIFIED: all pass with and without `CLAUDE_PROJECT_DIR` set; removing the checkout check fails 4 |
| 21 | `memory_enhancement` with `stores.py` ships in the Claude plugin lib | path | `ls src/claude/lib/memory_enhancement/` | VERIFIED: `stores.py` present |
| 22 | ADR-109 carries an `**Amended by**:` footer naming ADR-126 | path | `tail` of ADR-109 | VERIFIED on 2026-11-23 |
| 23 | Besides `src/claude`, the memory skill ships to five trees with no `memory_enhancement` package: `src/codex`, `src/copilot-cli`, `src/cursor`, `src/muse`, and `src/hermes/project-toolkit-knowledge` | path | `ls -d src/*/skills/memory src/hermes/*/skills/memory`; `ls src/*/lib/memory_enhancement` | VERIFIED on 2026-11-23 |

## Gate results

- Claims ledger: VERIFIED, 23 rows, 3 corrected after review.
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
