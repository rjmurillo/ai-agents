"""Shell and interpreter tables for the push-pr identity guard (issue #4764).

Data only: the command names, option shapes, and environment variables the
guard classifies. Split out of ``invoke_push_pr_script_identity_guard.py`` so
each module of the guard stays inside the 500-line taste ceiling. Every entry
is verbatim from that file; the tables carry their original rationale
comments, which is where the evidence for each name lives.

Consumed by :mod:`_push_pr_guard_commands`, :mod:`_push_pr_guard_evaluators`,
and :mod:`_push_pr_guard_scope`.
"""

from __future__ import annotations

_SHELL_EVALUATORS = frozenset(
    {
        "ash",
        "bash",
        "cmd",
        "cmd.exe",
        "csh",
        "dash",
        "elvish",
        "es",
        "eval",
        "fish",
        "ksh",
        "mksh",
        "nu",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "rc",
        "rbash",
        "rksh",
        "rzsh",
        "sh",
        "tcsh",
        "xonsh",
        "yash",
        "zsh",
    }
)


_DYNAMIC_EVALUATORS = frozenset(
    {
        "awk",
        "bpftrace",
        "bb",
        "bun",
        "clisp",
        "clojure",
        "dc",
        "deno",
        "dotnet-script",
        "ed",
        "elixir",
        "emacs",
        "escript",
        "ex",
        "expect",
        "gawk",
        "ghci",
        "gmake",
        "groovy",
        "guile",
        "js",
        "jsc",
        "jshell",
        "julia",
        "kotlin",
        "less",
        "lua",
        "luajit",
        "make",
        "mawk",
        "man",
        "mariadb",
        "mysql",
        "nawk",
        "nim",
        "node",
        "nodejs",
        "nvim",
        "ocaml",
        "perl",
        "php",
        "psql",
        "qjs",
        "r",
        "racket",
        "raku",
        "ruby",
        "rscript",
        "sbcl",
        "scala",
        "sed",
        "sqlite3",
        "swift",
        "tclsh",
        "ts-node",
        "tsx",
        "vi",
        "view",
        "vim",
        "wish",
    }
)


_ENV_COMMANDS = frozenset({"env", "env.exe"})


_BUSYBOX_COMMANDS = frozenset({"busybox", "busybox.exe"})


_EXPANSION_SAFE_COMMANDS = frozenset({"printf"})


_COMMAND_DELEGATORS = frozenset(
    {
        "chrt",
        "chroot",
        "catchsegv",
        "doas",
        "flock",
        "i386",
        "i486",
        "i586",
        "i686",
        "ionice",
        "linux32",
        "linux64",
        "ltrace",
        "nsenter",
        "ncat",
        "nc",
        "numactl",
        "parallel",
        "perf",
        "prlimit",
        "proot",
        "rsync",
        "runuser",
        "scp",
        "script",
        "setarch",
        "setpriv",
        "sftp",
        "slogin",
        "socat",
        "ssh",
        "sshpass",
        "strace",
        "su",
        "sudo",
        "taskset",
        "torify",
        "uname26",
        "unshare",
        "valgrind",
        "watch",
        "x86_64",
        "xargs",
    }
)


_DEBUG_EVALUATORS = frozenset({"gdb", "lldb"})


_COMMAND_DELEGATION_ENVIRONMENT = {
    "tar": frozenset({"PATH", "TAR_OPTIONS"}),
}


_COMMAND_DELEGATION_OPTIONS = {
    "find": frozenset({"-exec", "-execdir", "-ok", "-okdir"}),
    "tar": frozenset(
        {
            "-F",
            "-I",
            "--checkpoint-action",
            "--info-script",
            "--new-volume-script",
            "--rsh-command",
            "--to-command",
            "--use-compress-program",
        }
    ),
}


_PROCESS_WRAPPER_OPERAND_OPTIONS = {
    "nice": frozenset({"-n", "--adjustment"}),
    "stdbuf": frozenset({"-e", "-i", "-o", "--error", "--input", "--output"}),
    "time": frozenset({"-f", "-o", "--format", "--output"}),
    "timeout": frozenset({"-k", "-s", "--kill-after", "--signal"}),
}


_PROCESS_WRAPPER_FLAG_OPTIONS = {
    "nice": frozenset(),
    "nohup": frozenset(),
    "setsid": frozenset({"-c", "-f", "-w", "--ctty", "--fork", "--keep-groups", "--wait"}),
    "stdbuf": frozenset(),
    "time": frozenset(
        {"-a", "-p", "-q", "-v", "--append", "--portability", "--quiet", "--verbose"}
    ),
    "timeout": frozenset({"-v", "--foreground", "--preserve-status", "--verbose"}),
}


_DANGEROUS_LOADER_ENVIRONMENT = frozenset(
    {
        "CORECLR_ENABLE_PROFILING",
        "CORECLR_PROFILER",
        "COR_ENABLE_PROFILING",
        "COR_PROFILER",
        "DOTNET_STARTUP_HOOKS",
        "LD_AUDIT",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "NODE_OPTIONS",
        "PERL5OPT",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "RUBYOPT",
    }
)


# Assignments whose VALUE names a program the shell or interpreter executes,
# beyond the loader set above. Relevance inspects these because such a variable
# runs its value without the path ever appearing as a command operand
# (issue #4764).
# Commands that exist to RUN another program named in their arguments. Their
# operands are never data, so relevance keeps a new_pr.py reference in scope
# (issue #4764). Interpreters, shells, and evaluators are covered by the
# existing evaluator sets; this list is the remaining launchers.
#
# Omission fails closed only when the launcher is also unresolvable, so keep it
# current: a resolvable launcher missing from this list would let
# `<launcher> new_pr.py` read as data. `uv` is here because `uv run
# tools/copy.py` executes a renamed copy of new_pr.py, which is a measured
# vector in tests/hooks/test_push_pr_script_identity_guard.py.
_LAUNCHER_COMMANDS = frozenset(
    {
        "conda",
        "doas",
        "hatch",
        "micromamba",
        "nix-shell",
        "parallel",
        "pdm",
        "pipenv",
        "pipx",
        "pixi",
        "poetry",
        "rye",
        "sudo",
        "tox",
        "uv",
        "uvx",
        "xargs",
    }
)


_EXECUTION_INFLUENCING_VARIABLES = frozenset(
    {
        "BASH_ENV",
        "ENV",
        "PAGER",
        "PUSH_PR_SCRIPT",
        "SHELL",
        "VISUAL",
    }
)
