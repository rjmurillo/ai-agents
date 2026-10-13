# A New Worktree Has No .env

## Statement

`.env` is gitignored, so a new worktree under `~/worktrees/ai-agents/` does not
have one. `.gitignore:148` ignores `.env*`. Only the tracked `.env.example`
arrives with the checkout.

## When it matters

Scripts that read a repo-root `.env` for API keys miss it. Examples:
`_read_env_key` in `scripts/eval/_http_providers.py:56-76` and `load_api_key` in
`scripts/metrics/sg_reference_ab_api.py:144-150`. Each checks the process
environment first, so exporting the variable avoids the file entirely.

## Do this

1. Prefer exporting the needed variable in the shell that runs the script, for
   example `ANTHROPIC_API_KEY`.
2. If the script needs the file, copy `.env` from the main checkout into the
   worktree root. Do not symlink it. Both readers ignore a symlinked `.env` and
   report the key as missing, with no hint that the symlink caused it.
3. Never print the file, never `git add -f` it, and never paste its contents
   into a commit, PR body, or log. The `.env*` ignore rule blocks a plain
   `git add`.

## Caveat

The main checkout may have no `.env`. On 2026-10-13 it held only `.env.example`,
so there was nothing to copy. Creating `.env` from the example is not enough:
`.env.example` lists `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`,
`TAVILY_API_KEY`, and `YDC_API_KEY` with empty values. Fill in the key the
script needs, or the same failure repeats.

## Evidence

Verified 2026-10-13. `git check-ignore -v .env` reports `.gitignore:148:.env*`.
`rg -n "is_symlink" scripts/eval/_http_providers.py scripts/metrics/sg_reference_ab_api.py`
shows the symlink skip at `_http_providers.py:74` and `sg_reference_ab_api.py:150`.

Source: Hindsight page "Multi-agent run playbook"
(kp-5ad73a597d6a4cb69a6a3dd731fad139), section "Local Development Setup for
Subagents", REF dc0d7a23. That page names the copy step; the symlink and
missing-main-checkout points come from the repository checks above.
