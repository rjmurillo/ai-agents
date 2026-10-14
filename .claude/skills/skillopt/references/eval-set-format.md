# Eval set, patch, and results schemas

Three small JSON files drive one optimization step. The bundled
`skillopt.py` reads all of them. The eval set is the contract that makes
the gate real, so build it first.

## 1. Eval manifest (`eval.json`)

Names the tasks and which task ids are held out for the gate.

```json
{
  "skill": "programming-advisor",
  "splits": {
    "train": ["t1", "t2", "t3", "t4", "t5", "t6"],
    "sel": ["t7", "t8", "t9", "t10"]
  },
  "exposed": [],
  "tasks": {
    "t1": {
      "prompt": "Is there a stdlib way to do X in Python?",
      "verifier": "answer names a real stdlib module and cites docs",
      "kind": "semantic"
    }
  }
}
```

- `splits.train`: tasks the optimizer reflects on.
- `splits.sel`: the held-out split. The gate scores only this split. Never
  reflect on `sel` tasks; that is training on the test set.
- `exposed`: optional list of task ids whose prompt, verifier, or outcome the
  candidate author saw before the candidate was frozen. `pair-gate` exits 2
  while any of them is in the split being gated. Move them to `train` and add
  untouched holdout tasks.
- `tasks[id].status`: optional. `"invalid"` or `"exposed"` marks a task that
  cannot count. `pair-gate` exits 2 while such a task is in the gated split.
  Use `"invalid"` for missing inputs, a verifier that demands unsupported
  work, a scope violation, or a rollout run against the wrong artifact.
- `tasks[id].verifier`: how pass or fail is decided. Prefer a deterministic
  check (exit code, exact match, a script) over a judgment. The scripts do not
  run the verifier; you do, and you write the result into the results file.
- `tasks[id].kind`: optional `semantic` or `resource`. A resource task may
  encode a threshold declared up front, such as total bytes reduced by at
  least 15%. Adding a resource objective after seeing the candidate is
  test-set editing.

A manifest with no `sel` split, an empty one, a duplicate id, or a non-string
id makes `score` and `pair-gate` exit 2. No held-out split, no gate.

## 2. Patches (`patches.json`)

A list of atomic edits, capped at the step's budget L_t. An anchor matches a
whole line by its exact, unique content. A missing or ambiguous anchor rejects
the whole batch.

```json
[
  { "op": "append", "text": "## New rule\n\nAlways cite the source." },
  { "op": "insert_after", "anchor": "## When to use", "text": "- case Y" },
  { "op": "replace", "anchor": "old line text", "text": "new line text" },
  { "op": "delete", "anchor": "line to remove" }
]
```

- `append` ignores `anchor` and adds `text` as trailing lines.
- `insert_after`, `replace`, and `delete` require a unique `anchor`.
- `text` may contain `\n` for multi-line insertions.
- Any patch that would change a protected slow section is rejected.
- CRLF documents keep their line endings.

## 3. Results (`*_results.json`)

Per-task outcomes recorded after one rollout. The incumbent, the candidate,
and any null control each get their own file.

```json
{ "t7": true, "t8": false, "t9": true, "t10": "UNVERIFIED" }
```

- Only literal `true` is a pass. `1`, `"yes"`, and other truthy values are
  not passes, so a sloppy verifier cannot inflate the score.
- `score` counts a missing or non-boolean held-out entry as a fail.
- `pair-gate` is stricter. A missing or non-boolean held-out entry in any
  compared file makes the verdict `REJECT_UNVERIFIED`. Write `"UNVERIFIED"`
  for a clipped, missing, or contradictory answer until a full artifact or a
  rerun settles it.
- Keep evidence notes in the pair report or scoring notes, not here.

## Scoring and gating

```bash
python3 skillopt.py pair-gate \
  --eval eval.json \
  --incumbent-results incumbent_results.json \
  --candidate-results candidate_results.json \
  [--null-results null_results.json] [--split sel]
```

The report is JSON on stdout:

| Key | Meaning |
|-----|---------|
| `verdict` | `ACCEPT_PARETO`, `REJECT`, `REJECT_UNVERIFIED`, or `REJECT_NULL_CONTROL` |
| `gains` | Tasks the candidate passes and the incumbent does not |
| `regressions` | Tasks the incumbent passes and the candidate does not |
| `unverified` | Tasks with a missing or non-boolean result in any file |
| `null_gains`, `null_regressions` | Flips a byte-identical rerun of the incumbent produced |
| `genuine_gains` | `gains` minus `null_gains` |

Exit 0 only for `ACCEPT_PARETO`. It needs a gain, zero regressions, no
unverified task, and, with a null control, at least one genuine gain. Exit 1
for every reject. Exit 2 for an invalid manifest or input file.

`score` prints the held-out pass rate. Scalar `gate` compares two numbers and
rejects ties. Neither is the default promotion decision.
