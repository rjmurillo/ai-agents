# Python and Test Conventions

<!-- vendor-portability: contributor-facing reference for the rjmurillo/ai-agents repo itself. It names upstream-only paths under scripts, tests, src/claude, .claude/hooks, and .github because its audience is repo contributors, not plugin consumers. Declared paths: scripts/AGENTS.md, scripts/ai_review_outputs.py, scripts/ci/adr101_publisher_execute.py, scripts/github_core/not_found.py, scripts/validate_pr_review_config.py, scripts/validation/check_plugin_frontmatter_self_containment.py, scripts/validation/check_subprocess_encoding.py, src/claude/skills/github/scripts/issue/get_issue_comments.py, scripts/validation/check_tmp_worktrees.py -->

Read this before you write or review Python under `scripts/`, `build/`, `.github/scripts/`, or `tests/`.
Each item names a site that does it right, so you can copy a working pattern.
Each one began as a repeated review finding.
The repo verified each item against the code on 2026-11-26.

## Subprocess and I/O

1. **Decode subprocess text as UTF-8 with replacement, in tests too.**
   Pass `text=True, encoding="utf-8", errors="replace"` together.
   `scripts/validation/check_subprocess_encoding.py` enforces this only under `scripts/` (`_collect_sources`).
   Tests under `tests/` get no gate, so follow the pattern there by hand.
   A Windows runner decodes with a legacy code page otherwise.
   Strict decoding is allowed only on purpose.
   End that line with `# subprocess-encoding: strict-ok` and state the reason (`scripts/AGENTS.md`).
2. **Catch `UnicodeDecodeError` next to `OSError` when you read text.**
   `UnicodeDecodeError` is a `ValueError`, not an `OSError`.
   A handler that wraps `read_text()` must catch `(OSError, UnicodeDecodeError)`.
   Otherwise one bad byte crashes the run.
3. **Keep a `--json` stdout clean of child output.**
   When a script prints one JSON document, capture child processes or send their output to stderr.
   A child that inherits stdout breaks the parser that reads it.
   `rule-ci-scripts.md` SHOULD 2 covers the parse contract.
4. **Stat each file on its own when you pick files by mtime.**
   Put `stat()` in a per-file `try`/`except OSError: continue`.
   A file can vanish during the scan, and one bulk `try` loses every file.
   Copy `.claude/hooks/PreCompact/invoke_compact_checkpoint.py` (the `newest_mtime` loop).

## Paths

5. **Check containment with `Path.is_relative_to()`, never `str.startswith()`.**
   Resolve both paths first.
   With `startswith`, `/a/bc` passes a check for `/a/b`.
6. **Treat both sides of a symlink test the same way.**
   `Path.relative_to()` is lexical.
   It raises `ValueError` when one side is resolved and the other is not.
   Resolve both sides, as `tests/build_scripts/test_binplace_links.py` does with `entry.resolve().is_relative_to(plugin.resolve())`.
7. **Compare paths from CLI output as `Path` objects.**
   Wrap the printed path in `Path(...)` before you assert on it.
   A string compare fails on Windows separators.
8. **Find plugin roots with `plugin_roots()`.**
   Call `plugin_roots()` in `scripts/validation/check_plugin_frontmatter_self_containment.py`.
   Do not walk the tree with an unbounded `rglob`.
   It reaches worktrees, caches, and mirror trees.

## Script entry points

9. **Give a script run by path a `sys.path` prologue.**
   Running a script by its file path puts only that script's own directory on `sys.path`.
   A `scripts.*` import then fails unless the script inserts the repo root first.
   `scripts/ai_review_outputs.py` shows the guarded `sys.path.insert(0, ...)` form.
   A plugin-root script run by bare `python3` must stay stdlib-only at import time (`plugin-self-containment.md` MUST 4).
10. **Type-guard YAML nodes before you use them.**
    `yaml.safe_load` can return a scalar, a list, or `None` where you expect a dict.
    Check `isinstance(node, dict)` before you index a node or build CLI args from it.
    Report the bad shape as a finding, not a traceback.
    `scripts/validate_pr_review_config.py` shows the split: exit 2 for a document that is not a mapping, exit 1 for a bad nested field.

## GitHub API payloads

11. **Read a comment author as `(c.get("user") or {}).get("login")`.**
    A deleted account comes back as `"user": null`.
    `c.get("user", {})` returns `None` for that key, and `.get` then raises.
    `src/claude/skills/github/scripts/issue/get_issue_comments.py` guards with `isinstance(user, dict)`.
12. **Classify a missing PR with `github_core.is_pr_not_found()`.**
    Do not match the bare text `Could not resolve`.
    That text also covers a DNS failure and a wrong owner or repo.
    The helper lives in `scripts/github_core/not_found.py`.

## Tests

13. **Scope `sys.path` changes inside a test or fixture.**
    Use `monkeypatch.syspath_prepend`, which undoes the change at teardown.
    A bare insert in a test body leaks into later tests on the same xdist worker.
    `tests/eval/conftest.py` shows the pattern.
    Module-level inserts for repo script dirs stay common and are fine.
14. **Isolate the home directory on Windows too.**
    Windows ignores `HOME`.
    Set `USERPROFILE` and any cache or app-data variable the code reads, such as `LOCALAPPDATA` and `XDG_CACHE_HOME`.
    `tests/codex/conftest.py` sets `USERPROFILE` next to `HOME`.
15. **Pair a configured-set test with its converse.**
    A test that checks each configured item exists must also check each qualifying file on disk is configured.
    Build the on-disk list from `git ls-files` or a fixed directory.
    A walk can race with xdist worktrees.
    `tests/build_scripts/test_agent_target_repo_verification.py` builds an `on_disk` set this way.
16. **Give a child process an allowlisted environment when it runs branch text.**
    Build the child env from an explicit allowlist, not `os.environ` minus a denylist.
    A denylist misses the next secret someone adds.
    Copy `_child_env` and `_CHILD_ENV_ALLOWLIST` in `scripts/ci/adr101_publisher_execute.py`.
17. **Stat a path when an unreadable directory must differ from a missing one.**
    On Python 3.14, `Path.is_dir()` returns False for every `OSError`, so an `except` around it never runs.
    Call `path.stat()`, treat `FileNotFoundError` and `NotADirectoryError` as absent, and other errors as unreadable.
    In tests, patch `Path.stat`, not `Path.is_dir`.
    Copy `directory_state` in `scripts/validation/check_tmp_worktrees.py`.
