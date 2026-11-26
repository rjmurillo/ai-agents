# A detached push survives deletion of its log directory mid run, and only a missing directory at launch stops it

**Atomicity**: 90%
**Category**: Git push recipes
**Source**: Agent session sweep, sessions dated 2026-08. Sweep ids E007. State checked on main at 1be533c496 (2026-11-26).

## Question

Does a detached push die when its log directory disappears while it runs?

## Conventional answer

The memory `git-detached-push-dies-if-log-dir-vanishes.md` said the command never starts or dies when the log directory vanishes mid run. Its title line says the process dies when the directory disappears.

## First-principles position

Only launch time state decides. A missing log directory at launch makes the shell redirect fail, so the command never runs. Deleting the directory after launch leaves the process alive, and it finishes normally.

## Evidence with limits

- Launch with a missing log directory (2026-08-02): exit 1, and the marker file the command would create was never created.
- Removing the log directory mid run: the process was still alive 2 seconds later and ran to normal completion.
- Running `ps -p $!` through nohup and setsid printed the bash -c process, so `$!` is usable.
- Limits: One Linux host, bash -c with output redirected to /dev/null. Log appends after the delete go to the unlinked inode, so the log path is unreadable even though the process lives. The recipe at `.serena/memories/git/git-detached-push-dies-if-log-dir-vanishes.md:11` reopens the log path to append `REAL_EXIT`. With the directory gone that redirect fails, so the exit marker is lost even when the push finishes. The 2026-08-02 incident cause is inferred to be a launch time missing directory.
- State on main at 1be533c496 (2026-11-26): still wrong. `.serena/memories/git/git-detached-push-dies-if-log-dir-vanishes.md:14` describes a cleanup during the session. Line 15 says the redirect fails and the command never starts. The title says the process dies when the directory disappears.

## Decision

When the log disappears, use `ps` to check whether the push is still running, and check the remote branch for the result, because the `REAL_EXIT` marker will not appear. Create the log directory with `mkdir -p` before launch. Stop if that command fails.

The wrong state on main is tracked in the GitHub issue linked from the pull request that added this memory.

## Related

- `.serena/memories/git/git-detached-push-dies-if-log-dir-vanishes.md`
- `.serena/memories/git/git-stale-detached-clone-runs-stale-tooling.md`
