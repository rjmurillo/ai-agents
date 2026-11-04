"""Environment variables that steer a git child away from the repository it was given."""

from __future__ import annotations

#: Every repo-local variable ``git rev-parse --local-env-vars`` reports. Each
#: one redirects, rewrites, or hides history for a child that ``-C`` should
#: have pointed at one repository (``GIT_GRAFT_FILE`` and ``GIT_SHALLOW_FILE``
#: hide commits, ``GIT_REPLACE_REF_BASE`` and ``GIT_NO_REPLACE_OBJECTS`` swap them).
GIT_ENV_KEYS = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR",
    # Not in the rev-parse list, but each one still steers git away from ``-C``.
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
)
#: Numbered config injection variables (``GIT_CONFIG_KEY_0``, ``GIT_CONFIG_VALUE_0``).
GIT_ENV_PREFIXES = ("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
