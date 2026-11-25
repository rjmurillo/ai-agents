# Frontmatter evaluation probes

Reproduces the library-semantics claims in
`.project-toolkit/analysis/frontmatter-parser-build-vs-buy.md` (issue #5275).

Run it from the repository root:

```bash
uv run python .project-toolkit/analysis/frontmatter-probes/probe_library_semantics.py
```

| Probe | Produces |
|---|---|
| `probe_library_semantics.py` | Hazards H1 to H6: state collapse, body stripping, raise-vs-None, the `Loader=` metadata-injection footgun, and `dumps()` round-trip infidelity |

Two probes were retired when every parser moved onto
`scripts/hook_utilities/frontmatter_block.py`. `probe_divergence_matrix.py` and
`probe_corpus_scan.py` compared parsers that no longer exist. Recover them with
`git show 15c13340a:.project-toolkit/analysis/frontmatter-probes/<name>`.

These are evaluation instruments, not gates. The standing parity check is
`tests/test_frontmatter_block.py`, which pins the shared parser to the
installed `python-frontmatter` library.
