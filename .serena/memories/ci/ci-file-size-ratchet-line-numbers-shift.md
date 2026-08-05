# Skill: Isolating which file broke the taste count ratchet (95%)

## Statement

`taste_count_ratchet.py` reports a delta and never names the file:

```
taste count ratchet: REGRESSION. 602 violations > baseline 601 (+1).
```

The obvious next step, enumerate violations on both refs and diff the two
lists, produces a **false answer** if you diff them naively. On a real +1
regression the naive diff showed **six** new violations and **five**
disappeared.

The cause: the `file-size` rule reports at the line where the file crosses the
ceiling, so its reported line number moves whenever the file grows or shrinks
anywhere above that point. Five of the six were the same violation on the same
file at a shifted line. Only one was real.

## Recipe

Enumerate error-severity violations on both refs, then diff **on file plus
rule, dropping the line number**:

```bash
# in each checkout
uv run --frozen python - <<'PY' > ~/src/scratch/taste-<ref>.txt
import json,subprocess,sys,pathlib
files=[f for f in subprocess.run(["git","ls-files"],capture_output=True,text=True,
                                 encoding="utf-8",errors="replace").stdout.split()
       if pathlib.Path(f).exists()]
out=set()
for i in range(0,len(files),400):
    p=subprocess.run([sys.executable,".claude/skills/taste-lints/scripts/taste_lints.py",
                      "--format","json","--",*files[i:i+400]],
                     capture_output=True,text=True,encoding="utf-8",errors="replace")
    if p.returncode not in (0,10):
        continue
    for v in json.loads(p.stdout).get("violations",[]):
        if str(v.get("severity","")).lower()=="error":
            out.add(f"{v.get('file')}:{v.get('rule')}")   # NO line number
for k in sorted(out): print(k)
PY

LC_ALL=C sort ~/src/scratch/taste-main.txt > ~/src/scratch/a && LC_ALL=C sort ~/src/scratch/taste-branch.txt > ~/src/scratch/b
LC_ALL=C comm -13 ~/src/scratch/a ~/src/scratch/b     # genuinely new
```

`LC_ALL=C` on both `sort` calls is required. Python's string sort and the
shell's locale collation disagree, and `comm` prints `file 1 is not in sorted
order` and then silently returns wrong rows.

The taste linter exits **10** when it finds violations, not 1, so a `check=True`
subprocess call throws on a normal run. Accept `{0, 10}`.

Both `subprocess.run` calls pair `encoding="utf-8"` with `errors="replace"`.
That pairing is the house pattern enforced by
`scripts/validation/check_subprocess_encoding.py`, whose docstring requires a
call setting `encoding="utf-8"` plus text mode to "also pass
`errors="replace"`". Without it, a child that emits a byte invalid for UTF-8
raises `UnicodeDecodeError` on the calling side, hiding the real failure.
`git ls-files` can emit such bytes in a path. Keep the argument when you copy
this recipe; a copy pasted under `scripts/` without it fails that gate.

Expect the key count to be **lower** than the ratchet count: dropping the line
number collapses several violations of the same rule in the same file into one
key. On the measured run the ratchet said 601 and 602 while the key sets held
581 and 582. That is correct behavior, not a broken enumeration. The keys
answer "which file regressed", not "how many violations exist". Keep the
line-numbered lists too if you need to locate the violation inside the file
once you know which file it is.

## Generalization

A violation identifier that embeds a position is not stable under edits
elsewhere in the file. Diff on the stable part of the key. The same shape
applies to any diff of ruff, mypy, or semgrep output across two refs: strip the
line number before comparing, or you will chase moved rows as new ones.

Related: `.serena/memories/ci/ci-count-ratchet-never-names-the-offending-file.md`
