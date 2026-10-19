---
name: destructive-change-safety
description: Prove blast radius and recovery before a change that deletes, overwrites, drops, or revokes state. Scans for destructive sinks, traces callers and flags, previews scope without mutating, and blocks on unknown scope, bad cardinality, or no rollback. Use when you say `is this delete safe` or `blast radius`. Do NOT use for read-only changes or security review (use security-scan).
metadata:
  capability:
    kind: reusable-primitive
    owns:
      - destructive-change-safety
    depends-on:
      - technical-review
    status: active
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan's long-tail resolver matches a destructive-change or blast-radius request
    user-facing: true
    intents:
      - destructive change safety
      - blast radius
      - is this delete safe
      - rollback plan
      - irreversible migration
---

# Destructive Change Safety

> Trace before mutate. Measure before delete. Recover before execute.

Owns one invariant: before a destructive operation runs or ships, the affected
scope and the recovery path are proven, not discovered after execution. It does
not replace `security-scan`, deployment tooling, migration tooling, or backups.

## Triggers

`is this delete safe`, `blast radius`, `check this destructive change`,
`rollback plan for this change`

## When It Applies

A change can reach a sink that deletes rows, files, or resources, overwrites
canonical state, drops or truncates, force-pushes, or revokes credentials. The
scan decides: `"decision": "skip"` ends the skill. Read-only and pure changes
pay one scan and nothing more.

## Process

All commands run `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/destructive-change-safety/scripts/destructive_gate.py`
with `python3`. Output is one JSON object.

### Phase 1: Identify and trace sinks

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/destructive-change-safety/scripts/destructive_gate.py" scan <dir-or-file> --base . --changed <edited-function> ...
```

Scan the whole package the change lives in, not only the edited file, so
callers and adapters are in the graph. Pass each edited function to
`--changed`.

| Field | Read it as |
|-------|-----------|
| `chains` | Call paths from entry points to the sink. The path through an adapter, config loader, or job is the indirect path. |
| `flags` | CLI flags declared on functions along those chains, or on a function they call directly such as `parse_args`. A new flag is a new way to reach the sink. |
| `reached_from_changed` | Non-empty means an edited function can reach this sink. Empty means the scan found no path, not that none exists. |
| `callers_unknown` | True means the entry point lies outside the scan. Widen the scan or read the real callers by hand; the trace is not done. |

Decision `unknown` (exit 1) means a file did not parse (`unparsed`) or a source
file the scan cannot read went unscanned (`unscanned`): a language such as
PowerShell, JavaScript, C#, or Go, a CI or build definition (YAML, Makefile,
Dockerfile), or any file that starts with a shebang. Scope is unknown; do not treat it as `skip`.
Read each listed file by hand and record what you checked. A scope with no
readable file at all exits 2. The call graph matches by simple name and over-reports
on purpose. For callers outside the scanned set, follow the caller-reading
step of the `review` skill's technical-review reasoning protocol and cite the
call sites checked.

### Phase 2: Measure the blast radius without mutating

| Sink | Preflight |
|------|-----------|
| SQLite DELETE or UPDATE | `preview-sql --database <file> --statement "<sql>"` runs it on an in-memory copy. `count` is rows hit, `total_changes` includes cascades and triggers. |
| Files | `preview-files --root <dir> --pattern "<glob>"` lists what the glob selects (a matched directory counts every file beneath it), refuses patterns that leave the root, and ignores symlinks that do. |
| Other engine, remote resource | Use the system's own dry run, plan, or `SELECT COUNT`. Record the command and its real output. |

A preview that cannot run exits 1 with `scope unknown`. If the platform has no
safe preview, say so and treat scope as unknown. Do not estimate.

### Phase 3: State the rollback contract before execution

Choose one: `backup`, `snapshot`, `version`, or `irreversible`.

- `backup`, `snapshot`, `version`: name the `ref` that restores it. For a file
  overwrite, also give `backup_path` and `source_path`; the gate hashes both.
- `irreversible`: record the human approval. Per the AGENTS.md Autonomy
  Guardrail (irreversible goes to a human), an agent never invents a rollback
  or approves its own irreversible step. Law 2 in the
  `security-scan` skill's `agent-guardrails-template.md` is the same boundary.

### Phase 4: Run the checks, then the gate

Run the tests and checks that cover the sink. Record each command and exit
code from this run, not a prediction. Write the evidence file:

```json
{
  "sinks": [{"location": "<file>:<line>", "trace": ["main", "apply_removals", "remove_worktree"]}],
  "preflight": {"command": "preview-sql ...", "exit_code": 0, "measured": 3},
  "expected": 3,
  "rollback": {"kind": "snapshot", "ref": "snap-id"},
  "approval": {"human": "required only when irreversible"},
  "checks": [{"command": "pytest -q", "exit_code": 0}]
}
```

`expected` is the exact count, or an object with a `max` key. Then:

```bash
python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/destructive-change-safety/scripts/destructive_gate.py" gate --evidence <evidence.json> --scan <scan.json>
```

| Verdict | Exit | Meaning |
|---------|------|---------|
| `PASS` | 0 | A `--scan` report covers every sink it found; evidence may declare more, and each declared sink is held to the same rules. Every sink traced, scope measured and as expected, rollback stated, checks green. Execution may proceed. |
| `SKIP` | 0 | No sink declared, and a `--scan` report with `"decision": "skip"` backs it. |
| `BLOCK` | 1 | `reasons` lists each failure. Fix the evidence, or stop. |

Every verdict needs `--scan`. The gate requires an evidence entry for every
scanned sink, so an agent cannot omit one, and it cannot declare one sink and
leave the rest unscanned. Without a scan report, or with one that has no known
`decision`, the gate blocks. A `SKIP` needs `"decision": "skip"`; an `activate`
report that lists no sink is inconsistent and blocks. Cardinality outside `expected`, a
missing or failed preflight, no rollback, an irreversible step without human
approval, or a failed check blocks. There is no override here; a break-glass
path is a repository policy decision outside this skill.

## Scripts

| Subcommand | Purpose | Exit codes |
|------------|---------|------------|
| `scan` | Sinks, caller chains, flags, forward trace | `0` ran, `1` unparsed or unscanned file, `2` bad path or no scannable file |
| `preview-files` | Files a glob would touch | `0` counted, `1` refused |
| `preview-sql` | Rows a SQLite DELETE or UPDATE would change | `0` counted, `1` refused |
| `gate` | Fail-closed verdict over evidence | `0` PASS or SKIP, `1` BLOCK, `2` bad input |

The scripts are stdlib-only. Python sinks use `ast`; `.sql` and `.sh` files are
scanned by line.

## Verification

- [ ] Scan ran over the package, not only the edited file; `skip` or every sink traced.
- [ ] No sink reports `callers_unknown` without a hand-read of the real callers.
- [ ] Preflight output is from this run and its count matches `expected`.
- [ ] Rollback contract is stated before execution; irreversible has a human approval.
- [ ] Gate returned `PASS` or `SKIP` at the final head, and the verdict is quoted in the PR body.
