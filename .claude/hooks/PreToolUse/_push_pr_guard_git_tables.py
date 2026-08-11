"""Git command tables for the push-pr identity guard (issue #4764).

Data only: Git built-ins, the options and operands that can reach an
execution position, the read-only ``git config`` surface, and the
subcommands that never run a repository hook. Split out of
``invoke_push_pr_script_identity_guard.py`` so each module of the guard stays
inside the 500-line taste ceiling.

Consumed by :mod:`_push_pr_guard_git` and :mod:`_push_pr_guard_scope`.
"""

from __future__ import annotations

_GIT_COMMAND_ENVIRONMENT = frozenset(
    {
        "EDITOR",
        "GIT_ASKPASS",
        "GIT_ALLOW_PROTOCOL",
        "GIT_COMMON_DIR",
        "GIT_DIR",
        "GIT_EDITOR",
        "GIT_EXEC_PATH",
        "GIT_EXTERNAL_DIFF",
        "GIT_PAGER",
        "GIT_PROTOCOL_FROM_USER",
        "GIT_PROXY_COMMAND",
        "GIT_SEQUENCE_EDITOR",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_TEMPLATE_DIR",
        "GIT_WORK_TREE",
        "HOME",
        "PAGER",
        "PATH",
        "SSH_ASKPASS",
        "VISUAL",
        "XDG_CONFIG_HOME",
    }
)


_GIT_BUILTIN_COMMANDS = frozenset(
    {
        "add",
        "am",
        "annotate",
        "apply",
        "archive",
        "bisect",
        "blame",
        "branch",
        "bundle",
        "checkout",
        "cherry",
        "cherry-pick",
        "clean",
        "clone",
        "commit",
        "config",
        "count-objects",
        "describe",
        "diagnose",
        "diff",
        "fetch",
        "format-patch",
        "fsck",
        "gc",
        "grep",
        "hash-object",
        "init",
        "log",
        "ls-files",
        "ls-remote",
        "ls-tree",
        "maintenance",
        "merge",
        "merge-base",
        "merge-tree",
        "mv",
        "name-rev",
        "notes",
        "pack-objects",
        "pack-refs",
        "patch-id",
        "prune",
        "pull",
        "push",
        "range-diff",
        "read-tree",
        "reflog",
        "repack",
        "replace",
        "request-pull",
        "rerere",
        "reset",
        "restore",
        "rev-list",
        "rev-parse",
        "revert",
        "rm",
        "shortlog",
        "show",
        "show-branch",
        "show-ref",
        "sparse-checkout",
        "stage",
        "stash",
        "status",
        "switch",
        "symbol-ref",
        "tag",
        "update-index",
        "update-ref",
        "var",
        "verify-commit",
        "verify-tag",
        "version",
        "whatchanged",
        "worktree",
        "write-tree",
    }
)


_GIT_GLOBAL_EXECUTION_OPTIONS = frozenset(
    {
        "-C",
        "-p",
        "--attr-source",
        "--bare",
        "--config-env",
        "--git-dir",
        "--namespace",
        "--paginate",
        "--work-tree",
    }
)


_GIT_GLOBAL_EXECUTION_PREFIXES = (
    "--attr-source=",
    "--config-env=",
    "--exec-path=",
    "--git-dir=",
    "--namespace=",
    "--work-tree=",
)


_GIT_EXECUTION_OPTIONS_BY_SUBCOMMAND = {
    "archive": frozenset({"--exec"}),
    "clone": frozenset({"-c", "-u", "--config", "--template", "--upload-pack"}),
    "diff": frozenset({"--ext-diff"}),
    "difftool": frozenset({"-x", "--extcmd"}),
    "fetch": frozenset({"--upload-pack"}),
    # Every filter option takes a shell command Git runs once per commit.
    "filter-branch": frozenset(
        {
            "--commit-filter",
            "--env-filter",
            "--index-filter",
            "--msg-filter",
            "--parent-filter",
            "--subdirectory-filter",
            "--tag-name-filter",
            "--tree-filter",
        }
    ),
    "grep": frozenset({"-O", "--open-files-in-pager"}),
    "ls-remote": frozenset({"--upload-pack"}),
    "merge": frozenset({"-s", "--strategy"}),
    "mergetool": frozenset({"-x", "--extcmd"}),
    "pull": frozenset({"-s", "--strategy", "--upload-pack"}),
    "push": frozenset({"--exec", "--receive-pack"}),
    "rebase": frozenset({"-x", "--exec"}),
    # --smtp-server accepts a program path instead of a host, and the *-cmd
    # options are programs Git runs to produce recipients or headers.
    "send-email": frozenset({"--cc-cmd", "--header-cmd", "--smtp-server", "--to-cmd"}),
}


_GIT_OPTION_OPERANDS_BY_SUBCOMMAND = {
    "clone": frozenset(
        {
            "-b",
            "-c",
            "-o",
            "-u",
            "--branch",
            "--config",
            "--origin",
            "--template",
            "--upload-pack",
        }
    ),
    "fetch": frozenset({"-j", "--jobs", "--server-option", "--upload-pack"}),
    "ls-remote": frozenset({"--server-option", "--upload-pack"}),
    "pull": frozenset({"-j", "--jobs", "--server-option", "--upload-pack"}),
    "push": frozenset({"-o", "--push-option", "--receive-pack", "--repo"}),
}


# Operands that turn a subcommand into a command runner: every word after one
# of these is the command line Git executes. Unlike the option tables above,
# the operand carries no leading dash, so `_matches_git_option` cannot see it.
_GIT_EXECUTION_OPERANDS_BY_SUBCOMMAND = {
    "bisect": frozenset({"run"}),
    "submodule": frozenset({"foreach"}),
}


_GIT_SHORT_CLUSTER_OPERANDS_BY_SUBCOMMAND = {
    "grep": frozenset({"A", "B", "C", "e", "f", "m"}),
}


_GIT_SAFE_REMOTE_SCHEMES = frozenset({"git", "http", "https", "ssh"})


_GIT_REMOTE_SUBCOMMANDS = frozenset({"clone", "fetch", "ls-remote", "pull", "push"})


_GIT_CONFIG_READ_ACTIONS = frozenset(
    {
        "--get",
        "--get-all",
        "--get-regexp",
        "--list",
        "-l",
        "get",
        "get-all",
        "get-regexp",
        "list",
    }
)


_GIT_HOOK_FREE_SUBCOMMANDS = frozenset(
    {
        "annotate",
        "blame",
        "config",
        "count-objects",
        "describe",
        "diff",
        "fsck",
        "grep",
        "log",
        "ls-files",
        "ls-remote",
        "ls-tree",
        "merge-base",
        "merge-tree",
        "name-rev",
        "patch-id",
        "range-diff",
        "rev-list",
        "rev-parse",
        "shortlog",
        "show",
        "show-branch",
        "status",
        "verify-commit",
        "verify-tag",
        "whatchanged",
    }
)


_GIT_CONFIG_READ_MODIFIERS = frozenset(
    {
        "--fixed-value",
        "--includes",
        "--local",
        "--name-only",
        "--no-includes",
        "--show-names",
        "--show-origin",
        "--show-scope",
        "--system",
        "--type",
        "--worktree",
        "--global",
    }
)
