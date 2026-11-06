# Where To Search

Use the cheapest source that answers the question. In order:

1. **This codebase.** `serena` symbol search, `grep`, ADRs in the ADR directory, existing skills among the installed skills. The pattern often already exists here.
2. **Serena memories.** `mcp__serena__find_symbol`, `mcp__serena__read_memory`. Past sessions logged what worked and what failed.
3. **Library docs.** `Context7` (`mcp__context7__resolve-library-id` then `get-library-docs`) for framework, SDK, and API questions. Beats web search on freshness for well-known libraries.
4. **DeepWiki.** `mcp__deepwiki__ask_question` for repo-level questions about a specific GitHub project.
5. **Web search.** WebSearch / Perplexity for novel or recent things not in the above.

**Bound the search.** If three tool calls have not surfaced anything useful, stop searching and switch to first-principles reasoning. Document what you tried (which tool, what query, what came back) so the user can extend the search if the answer matters more than your time budget suggests.
