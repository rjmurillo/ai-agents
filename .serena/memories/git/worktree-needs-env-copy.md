# A New Worktree Has No .env

## Statement

`.env` is gitignored, so a new worktree under `~/worktrees/ai-agents/` does not
have one. `.gitignore:148` ignores `.env*`. Only the tracked `.env.example`
arrives with the checkout.

## When it matters

Scripts that read a repo-root `.env` for API keys fail or fall back when the
file is missing. Examples read on 2026-10-13: `scripts/eval/_http_providers.py:65-73`
and `scripts/metrics/sg_reference_ab_api.py:145-149`. Each checks the process
environment first, so exporting the variable avoids the file entirely.

## Do this

1. Prefer exporting the needed variable in the shell that runs the script.
2. If the script needs the file, copy `.env` from the main checkout into the
   worktree root. Do not symlink it: both scripts refuse a symlinked `.env`
   (CWE-22 guard).
3. Never print the file, never `git add` it, and never paste its contents into
   a commit, PR body, or log. `.gitignore` already blocks `git add .`.

## Caveat

The main checkout may have no `.env`. On 2026-10-13 `ai-agents2` held only
`.env.example`, so there was nothing to copy. Then use step 1, or create `.env`
from `.env.example`.

## Evidence

Verified 2026-10-13: `git check-ignore -v .env` reports `.gitignore:148:.env*`;
the readers above exist at the cited lines.

Source: Hindsight page "Failure modes and environment traps"
(kp-c894bd79e0c241449ec771d88f345354), REF dc0d7a23.
