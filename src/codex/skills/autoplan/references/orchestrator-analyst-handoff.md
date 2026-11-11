# Analyst Evidence Handoff

Loaded by the `orchestrator` agent before it delegates an investigation that needs shell, git, build, or web evidence. The agent body keeps a short working rule.

Before delegating an investigation that needs shell output, git history, builds,
or unrestricted web research outside the analyst's declared tools:

1. Retrieve shell/git/build output and unrestricted web evidence with your
   execution or research capabilities.
2. Put the exact output, repository identity, branch, and head SHA in the
   analyst delegation context.
3. Name any unavailable evidence as a gap.

The analyst retrieves structured GitHub and CI data directly (PRs, issues,
workflows, job logs) using its own read tools. Do not prefetch GitHub/CI
context; delegate it.

Exception: when the GitHub read tools are not registered in this host, or
the receiving agent has no shell and no GitHub read tool, fetch the issue, PR,
or CI log text yourself, write it to a file, and pass the path in the
delegation context with the repository, head ref, and head SHA. The analyst
returns `[BLOCKED]` at once, naming the missing tool, when it has neither the
tool nor a supplied path.

The analyst has no shell or unrestricted web access.
If it returns `[BLOCKED]` for load-bearing missing context, retrieve the named
evidence and re-delegate once. Do not pass the blocked response through as the
investigation result.
