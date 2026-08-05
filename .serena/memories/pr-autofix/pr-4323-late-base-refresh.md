# PR #4323 late base refresh

On 2026-08-02, PR #4323 merged from head
`554ad4f575cfe614665d527de71e8f10eb53cbde` while nine review comments were
being fixed locally. The next base refresh ran before another live-state check
and produced 12 conflicts on the closed branch.

Recovery required preserving the net review-fix patch, aborting the merge,
creating a follow-up branch from current `origin/main`, and applying the patch
there. Issue #4349 tracks the missing terminal live-state gate.

Recheck live state after any long phase and before base synchronization, not
only before push.
