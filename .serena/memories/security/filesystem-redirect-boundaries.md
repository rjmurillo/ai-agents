# Filesystem Redirect Boundaries

## Rule

Treat symlinks and Windows junctions as the same trust-boundary risk. Validate
every ancestor between the target and repository root before mutation.

## Evidence

PR #4670 secured portability baseline replacement. A symlink-only check still
allowed Windows junctions to redirect access. The final implementation checks
both redirect types and removes the fixed ancestor-depth limit.

For writes on POSIX, validation alone is not enough. Pin the repository and
parent directories with descriptors, traverse with `O_NOFOLLOW`, and replace
relative to the pinned parent descriptor.

## Scope

Apply this rule where an external or repository-controlled path selects a
filesystem mutation target. It does not require repeated checks inside trusted
pure helpers.
