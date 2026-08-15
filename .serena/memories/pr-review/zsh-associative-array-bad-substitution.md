# zsh associative-array iteration fails with "bad substitution" in Bash tool

**Statement**: The Bash tool's default shell in this environment is zsh (per env
banner "Shell: zsh"). Bash-style associative-array syntax `declare -A MAP=(...)`
followed by `"${!MAP[@]}"` to iterate keys fails with `bad substitution` in zsh,
even though the same script runs fine under `bash`.

**Evidence**: Session responding to PR #5062 review threads. A loop meant to
reply to and resolve 10 GitHub review threads used
`declare -A THREADS=([id1]=file1 ...)` then `for tid in "${!THREADS[@]}"`.
Failed immediately with `(eval):18: bad substitution`, exit code 1, before any
API call ran.

**Fix**: Do not use bash associative arrays for key/value iteration in this
harness's Bash tool. Either:
1. Write a small shell function (`run_reply() { local tid="$1" bodyfile="$2"; ... }`)
   and call it once per pair with explicit positional arguments, or
2. Use zsh-native syntax (`typeset -A` plus `${(k)MAP}` for keys), or
3. Prefix the command with `bash -c '...'` to force bash semantics.

Option 1 is simplest and was used to unblock the session: replaced the
associative-array loop with 10 explicit `run_reply <thread_id> <bodyfile>` calls.

**Applies to**: any future Bash tool usage in this repository/environment that
needs key-value iteration (batch API calls, per-file mappings, etc).
