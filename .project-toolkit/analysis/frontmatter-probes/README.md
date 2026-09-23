# Frontmatter evaluation probes

Reproduces every executed claim in
`.project-toolkit/analysis/frontmatter-parser-build-vs-buy.md` (issue #5275).

Run each from the repository root:

```bash
uv run python .project-toolkit/analysis/frontmatter-probes/probe_divergence_matrix.py
uv run python .project-toolkit/analysis/frontmatter-probes/probe_library_semantics.py
uv run python .project-toolkit/analysis/frontmatter-probes/probe_corpus_scan.py
```

| Probe | Produces |
|---|---|
| `probe_divergence_matrix.py` | The 10-case matrix across the four parsers in #5275 plus `python-frontmatter`, and the library's `FM_BOUNDARY` pattern |
| `probe_library_semantics.py` | Hazards H1 to H6: state collapse, body stripping, raise-vs-None, the `Loader=` metadata-injection footgun, and `dumps()` round-trip infidelity |
| `probe_corpus_scan.py` | Parser agreement across every markdown file under `.project-toolkit/architecture`, `.serena/memories`, `.claude/skills`, `src`, and `templates` |

These are evaluation instruments, not gates. The regression tests that #5275's
acceptance criteria call for belong under `tests/` and are step 3 of the rollout.
