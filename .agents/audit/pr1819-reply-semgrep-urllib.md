Fixed in commit 4d9b8b49 (rebased to current head). Source-side hardening:

- New `_validate_http_url(endpoint)` helper rejects any non-`http`/`https` scheme via `urlparse`. The `file://`, `ftp://`, `gopher://`, and similar schemes that `urllib.request.urlopen` accepts by default are no longer reachable through this code path. CWE-918 (SSRF) and CWE-22 (file:// local file read) blocked at the boundary.
- The validator runs once before any network call. On rejection it returns `[]`/error rather than attempting urlopen.
- Both warmup and measured-iteration `urlopen` call sites are annotated with `# nosemgrep: request-with-tainted-url-from-urllib` plus inline rationale citing the upstream validation.
- Same pattern applied to `memory_router.invoke_forgetful_search()`.

Source files updated: `.claude/skills/memory/scripts/measure_memory_performance.py`, `.claude/skills/memory/memory_core/memory_router.py`. Generated copies under `src/copilot-cli/skills/` regenerated via `build_all.py`.

Resolving.
