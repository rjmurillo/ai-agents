Fixed in commit 4d9b8b49 (rebased to current head). Source-side hardening of `.claude/skills/chestertons-fence/scripts/investigate.py`:

- `run_git()` now validates `args[0]` against `_GIT_FLAG_ALLOWLIST` (read-only verbs only: `log`, `grep`, `show`, `diff`, `rev-parse`, `rev-list`, `ls-files`, `cat-file`). Future destructive verbs (`push`, `reset`, `fetch`) are rejected at the boundary with `ValueError`.
- Tokens beginning with `--upload-pack=` or `--exec=` are explicitly rejected (git's two known argv-level RCE vectors that survive list-form `subprocess.run`).
- Inline `# nosemgrep` annotation on the call site cites the full defense-in-depth: list-form blocks CWE-78 shell injection at the OS level, the verb allowlist blocks git-level abuse, the transport-flag denylist blocks the two known RCE vectors, and the 30s timeout bounds blocking.
- The second `subprocess.run` in `find_dependents()` is annotated with rationale: `-e` and `--` separators block flag interpretation; `search_term` is used as a literal regex needle, not as a path.

Verified: invoking `run_git(["rm", "-rf", "/"])` raises `ValueError: subcommand 'rm' not in allowlist`. Invoking `run_git(["log", "--upload-pack=evil"])` raises `ValueError: forbidden git option '--upload-pack=evil'`.

Resolving.
