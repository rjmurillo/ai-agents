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
| 20 | The recall hook shares the root rule and recalls only when that root holds `.git`; it notes an escaping Serena folder | behavior | `test_hook_and_skill_choose_the_same_root` (hook column), `test_hook_recalls_notes_only_inside_a_checkout`, and the two `test_memory_recall_limits.py` tests | VERIFIED: all pass with and without `CLAUDE_PROJECT_DIR`; widening the check to any ancestor `.git` fails 1 test |
| 21 | `memory_enhancement` with `stores.py` ships in the Claude plugin lib | path | `ls src/claude/lib/memory_enhancement/` | VERIFIED: `stores.py` present |
| 22 | ADR-109 carries an `**Amended by**:` footer naming ADR-126 | path | `tail` of ADR-109 | VERIFIED on 2026-11-23 |
| 23 | Besides `src/claude`, the memory skill ships to five trees with no `memory_enhancement` package: `src/codex`, `src/copilot-cli`, `src/cursor`, `src/muse`, and `src/hermes/project-toolkit-knowledge` | path | `ls -d src/*/skills/memory src/hermes/*/skills/memory`; `ls src/*/lib/memory_enhancement` | VERIFIED on 2026-11-23 |
| 24 | Linked memory files count only inside their own store, in the search script, router, and loader | behavior | `tests/skills/memory/test_memory_store_containment.py` and `test_repository_corpus_links.py` | VERIFIED: removing the router filter fails 1 test; removing the loader bound fails 7 |
| 25 | `memory-consolidate` and `curating-memories` drive `memory_git_targets.py` and `supersession_sweep.py` | path | `grep -n` for both script names in their `SKILL.md.tmpl` files | VERIFIED on 2026-11-24: `memory-consolidate.SKILL.md.tmpl:126`, `curating-memories.SKILL.md.tmpl:72` |
| 26 | In a notes-only repository `supersession_sweep.py` stops with `root not found: .serena/memories` | behavior | run the script in a temporary repository holding only the notes folder | VERIFIED on 2026-11-24 |
| 27 | The corpus walk does not enter a linked folder | behavior | `Path.rglob("*.md")` over a store holding a folder symlink, Python 3.14.8 and 3.15.0 | VERIFIED: empty list on both |
| 28 | Recall caps are 8000 characters and 3 results | path | `grep -n "MAX_BLOCK_CHARS =\|_MAX_RECALL_RESULTS ="` in the recall hook | VERIFIED: lines 107 and 95 |
| 29 | A memory root with no `.git` prints a `recall skipped` note | behavior | `test_hook_recalls_notes_only_inside_a_checkout`; mutation removing the note | VERIFIED: mutation failed 1 test |
| 30 | A resolve error in store lookup never fails a prompt | behavior | `test_recall_fails_open_when_store_resolution_raises`; mutation moving lookup outside the guard | VERIFIED: mutation failed 1 test |
| 31 | A `.git` file counts as a checkout for recall | behavior | `test_recall_accepts_a_git_file_as_in_a_linked_worktree`; mutation `.exists()` to `.is_dir()` | VERIFIED on 2026-11-24: mutation failed 1 test |
| 32 | Commit `3ed94c402` (2026-11-24) changed `store_resolution.py` | path | `git show -s --format='%h %ad %s' --date=short 3ed94c402`; `git show --stat` | VERIFIED on 2026-11-25: 51 lines per tree, 6 trees |
| 33 | `store_resolution.py` imports `STORE_DIRS`, `contained_stores`, `find_memory_root`, and `project_start` from `memory_core.memory_store` after a skill-root `sys.path` insert | quote | `sed -n 19,27p src/claude/skills/memory/scripts/store_resolution.py` | VERIFIED on 2026-11-25 |
| 34 | The root and store rules exist in two source copies | absence | `git grep -nE "^def (find_memory_root|repository_memory_dir|resolve_memory_store|contained_stores)|^(MEMORY_)?STORE_DIRS"` over the repo, excluding the generated harness trees and `src/claude/lib` | VERIFIED on 2026-11-25: `scripts/memory_enhancement/stores.py:16,23,40` (`MEMORY_STORE_DIRS`, `find_memory_root`, `repository_memory_dir`) and `memory_core/memory_store.py:15,19,27,48` (`STORE_DIRS`, `find_memory_root`, `contained_stores`, `resolve_memory_store`). The names differ; the rules match. `src/claude/lib/memory_enhancement/stores.py` is the build mirror of the first. The first grep used `^STORE_DIRS` and missed `MEMORY_STORE_DIRS`; the refuting seat caught it |
| 35 | The import-closure gate accepts a folder the file puts on `sys.path` through the `dirname` idiom | quote | `sed -n 25,31p build/scripts/import_closure.py`; `grep -n "def sys_path_inserts" build/scripts/import_closure_paths.py` (line 59) | VERIFIED on 2026-11-25 |
| 36 | The gate passes with this import in place | behavior | `uv run python build/scripts/check_surface_parity.py`; `pytest -k closure tests/build_scripts` | VERIFIED on 2026-11-25: exit 0; 67 passed |
| 37 | The parity tests hold both copies and `store_resolution` together | behavior | `pytest -q tests/skills/memory/test_memory_root_parity.py` | VERIFIED on 2026-11-25: 32 passed |

## Gate results

- Claims ledger: VERIFIED, 24 rows, 3 corrected after review.
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

### Amendment 2026-11-25 gates (rows 32 to 37)

- Claims ledger: VERIFIED, rows 32 to 37.
- Documentation accuracy: covered by rows 33 to 35, read from the working tree.
- Self-consistency: VERIFIED. Forces, Decision 4, Negative consequences,
  Security, and Confirmation all say two copies. Decision 4 still names the
  lib bootstrap failure as the reason the skill copy is not in `lib/`.
- Refuting seat (analyst, haiku), two runs. Run 1 read line numbers as row
  ids, so it checked rows 24 to 29. Its one body finding was false. It said
  `scripts/memory_enhancement/stores.py` is missing, but `ls` shows the file.
  Run 2 checked rows 32 to 37: rows 33 and 35 confirmed, rows 32, 36, and 37
  NOT RUN (no shell), row 34 refuted as worded. Row 34 now uses a grep that
  matches both naming schemes. The writer ran rows 32, 36, and 37.
