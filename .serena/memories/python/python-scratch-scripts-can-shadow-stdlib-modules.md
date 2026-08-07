# A scratch script named after a stdlib module runs when you least expect it

Scratch scripts live in `~/src/scratch`, and scripts are run from that directory. Python
puts the script's own directory first on `sys.path`. So a file named `queue.py`,
`types.py`, `select.py`, `token.py`, `json.py`, or `logging.py` in that directory
**shadows the standard library module of the same name**.

Shadowing alone would be a manageable import error. The trap is worse: the shadowing file
is **executed** when something imports that name, so its module-level code runs and its
output appears in your terminal, attributed to nothing.

## What this looks like

2026-08-04. A leftover `~/src/scratch/queue.py` (an old PR-queue-state script) was on
disk. A brand-new script did:

```python
from concurrent.futures import ThreadPoolExecutor
```

`concurrent.futures.thread` imports `queue`. Python found the scratch file, ran its whole
body (which printed a full formatted PR report), then failed:

```
AttributeError: module 'queue' has no attribute 'SimpleQueue'
```

The terminal showed a complete, plausible, correctly formatted report followed by a
traceback from a script that had produced none of it. Reading that output naively means
attributing another program's results to the one you just wrote.

Python's own error message names the cause, which is the only reason this was cheap:

> consider renaming '~/src/scratch/queue.py' since it has the same name as
> the standard library module named 'queue'

(The real message prints an absolute path; it is shown here home-relative because a
repository hook rejects literal home directories in committed files.)

Read the tail of the traceback before theorizing.

## The rule

Never name a scratch script after a stdlib module. Prefix by purpose and issue number
instead: `pr_queue_state.py`, `diag4567.py`, `probe_ratchet.py`.

Sweep periodically. Any hit is a live landmine:

```bash
uv run --frozen python - <<'EOF'
import pathlib, sys
d = pathlib.Path.home() / "src/scratch"
std = set(sys.stdlib_module_names)
print([p.name for p in d.glob("*.py") if p.stem in std])
EOF
```

## Why this bites agents specifically

An agent accumulates dozens of throwaway probe scripts in one flat directory over a long
session, names them for what they inspect (`queue`, `types`, `select` are all natural
names for probes), and never revisits them. The collision surfaces sessions later inside
an unrelated script, which makes the cause look like anything except a filename.

## Related

- `.serena/memories/patterns/patterns-powershell-pitfalls.md` (variable shadowing, same
  class of failure in a different language)
