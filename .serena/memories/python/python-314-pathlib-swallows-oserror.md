# Python 3.14 Path.is_dir and is_file swallow every OSError

On Python 3.14, `Path.is_dir()` and `Path.is_file()` return False for any
`OSError`, not only a missing path. A permission error or an I/O error reads as
"not a directory". When the error matters, call `Path.stat()` and handle the
exception, then test the mode with `stat.S_ISDIR` or `S_ISREG`.

A related dead branch: `_run_command` already catches `OSError`. Wrapping a call
to it in `except FileNotFoundError` never fires. Delete the wrapper rather than
keep an unreachable handler.

Evidence: PRs #6065 to #6068.
