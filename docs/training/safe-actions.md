# Safe agent actions

## Goal

You run agents that can write to your repository. This page shows how the toolkit keeps them inside their authority. It also shows how to read what they report.

By the end you will have seen five things on your own machine:

1. A deny rule that stops a forced push.
2. A decision brief that the checker rejects, then accepts.
3. A delete that the gate approves, then blocks.
4. An inflated "two reviewers confirmed it" claim that the classifier refuses.
5. A long command whose output stays out of the agent's context.

The one result to check at the end: the destructive gate prints `PASS` for a three-file delete, and the evidence classifier prints `CORROBORATED` for a claim backed by one independent test.

## Before you start

You need:

- A clean checkout of this repository, on `main`, with your shell at the repository root.
- `python3` and `git` on your PATH.
- `uv`, only if you run the optional test in step 1.

Read these two records first if you have five minutes. We link to them instead of copying them.

- [ADR-112, risk-tiered action boundaries](../../.project-toolkit/architecture/ADR-112-risk-tiered-action-boundaries.md)
- [ADR-105, terminal-state completion contract](../../.project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md)

Set up the shell variables once. Every step uses them.

```bash
REPO="$(pwd)"
WORK="$(mktemp -d)"
DQ="$REPO/.claude/skills/decision-question/scripts/decision_question.py"
GATE="$REPO/.claude/skills/destructive-change-safety/scripts/destructive_gate.py"
CLS="$REPO/.claude/skills/evidence-provenance/scripts/classify_lineage.py"
RWR="$REPO/scripts/run_with_receipt.py"
```

## Steps

### Step 1: See which actions need a person

ADR-112 sorts every agent action into one of four tiers.

| Tier | Example | Who acts |
|---|---|---|
| Read-only | `git diff`, search | The agent |
| Reversible local | Edit a file in a worktree, run tests | The agent |
| Shared repository | Push a branch, open or merge a PR | The agent, through a skill script, with server rules behind it |
| Consequential | Force push, `--no-verify`, recursive delete, repository delete, secrets | You |

The agent cannot run a consequential command. The harness denies it. You run it in your own shell, or with the `!` prefix inside Claude Code.

Check that two of the deny rules are in the rendered settings.

```bash
python3 -c "import json; d = json.load(open('.claude/settings.json'))['permissions']['deny']; print('Bash(rm -rf *)' in d, 'Bash(git push -f *)' in d)"
```

```text
True True
```

### Step 2: Ask only when the choice is yours

An agent should not ask you about things it can decide. `decision-question` is the skill that sets the bar. It asks only when a real decision belongs to you, and it asks with a complete brief.

Make a scratch folder and three briefs.

```bash
mkdir -p "$WORK/briefs" && cd "$WORK/briefs"
cat > incomplete.json <<'EOF'
{"context": {"material_decision": true},
 "decisions": [{"id": "D1", "statement": "Choose the session store."}]}
EOF
cat > complete.json <<'EOF'
{
  "context": {"material_decision": true},
  "decisions": [
    {
      "id": "D1",
      "statement": "Choose the session store for the new auth service.",
      "why_now": "Blocks the auth service skeleton; the store shapes every read path.",
      "options": [
        {"id": "redis", "label": "Redis", "consequence": "Auth check drops to about 2ms; adds a second store to operate."},
        {"id": "postgres", "label": "Postgres", "consequence": "One store to operate; auth check stays near 40ms."}
      ],
      "recommendation": "postgres",
      "recommendation_reason": "Traffic is far below the point where 40ms matters; one store lowers operating load."
    }
  ]
}
EOF
echo '{"context": {"material_decision": false}, "decisions": []}' > delegated.json
```

Run the incomplete brief first.

```bash
python3 "$DQ" --brief incomplete.json; echo "exit=$?"
```

```text
{
  "should_ask": true,
  "reason": "material unresolved user decision; present a bounded decision brief",
  "max_presented_options": 4,
  "harness_limit_observed": true,
  "deferred": [],
  "pruned": [],
  "status": "incomplete",
  "decision_id": "D1",
  "missing": [
    "why_now",
    "at_least_two_options",
    "recommendation_or_explicit_none"
  ]
}
exit=2
```

The checker refuses to let the agent ask half a question. Now run the other two.

```bash
python3 "$DQ" --brief complete.json > out.json; echo "exit=$?"; grep '"status"' out.json
python3 "$DQ" --brief delegated.json > out.json; echo "exit=$?"; grep '"status"' out.json
```

```text
exit=0
  "status": "ask",
exit=0
  "status": "skip"
```

`ask` means the brief is complete and the agent may put it to you through `AskUserQuestion`. `skip` means no decision is yours, so the agent acts and does not ask.

The skill has more: split chains for five or more options, a `Hold` answer, and a pre-ask review for irreversible choices. Read [the skill](../../src/claude/skills/decision-question/SKILL.md) and [its protocol](../../src/claude/skills/decision-question/references/decision-brief-protocol.md) for those.

### Step 3: Prove a delete before it runs

`destructive-change-safety` makes an agent show the blast radius and the way back before it deletes anything. The gate decides. It fails closed.

Build a small repository with a cleanup script and three temp files.

```bash
mkdir -p "$WORK/cleanup-demo/tmp" && cd "$WORK/cleanup-demo"
git init -q
cat > cleanup.py <<'EOF'
import os
from pathlib import Path


def remove_stale(root):
    for path in Path(root).glob("tmp/*.tmp"):
        os.remove(path)


def main():
    remove_stale(".")


if __name__ == "__main__":
    main()
EOF
for n in a b c; do echo "$n" > "tmp/$n.tmp"; done
git add -A
git -c user.name=demo -c user.email=demo@example.com commit -q -m "demo: cleanup script and tmp files"
```

Scan for destructive sinks. Say which function you edited.

```bash
python3 "$GATE" scan . --base . --changed remove_stale > scan.json; echo "exit=$?"; cat scan.json
```

```text
exit=0
{
  "decision": "activate",
  "sinks": [
    {
      "callers_unknown": false,
      "chains": [
        "<module> -> main -> remove_stale"
      ],
      "flags": [],
      "function": "remove_stale",
      "kind": "delete",
      "label": "os.remove",
      "location": "cleanup.py:7",
      "reached_from_changed": "remove_stale"
    }
  ],
  "unparsed": [],
  "unscanned": []
}
```

The scan found `os.remove` at `cleanup.py:7` and traced it from `main`. Next, count what the delete would touch, without touching it.

```bash
python3 "$GATE" preview-files --root . --pattern 'tmp/*.tmp'
```

```text
{
  "count": 3,
  "files": [
    "tmp/a.tmp",
    "tmp/b.tmp",
    "tmp/c.tmp"
  ],
  "kind": "files",
  "root": "<your demo folder>"
}
```

Your `root` line shows the real path of your demo folder. Everything else matches.

Run the check that covers the sink and record its real exit code. Then write the evidence file. The rollback is the commit you just made.

```bash
python3 -m py_compile cleanup.py; echo "exit=$?"
cat > evidence.json <<EOF
{
  "sinks": [{"location": "cleanup.py:7", "trace": ["main", "remove_stale"]}],
  "preflight": {"command": "preview-files --root . --pattern tmp/*.tmp", "exit_code": 0, "measured": 3},
  "expected": 3,
  "rollback": {"kind": "version", "ref": "$(git rev-parse HEAD)"},
  "checks": [{"command": "python3 -m py_compile cleanup.py", "exit_code": 0}]
}
EOF
```

```text
exit=0
```

Run the gate.

```bash
python3 "$GATE" gate --evidence evidence.json --scan scan.json; echo "exit=$?"
```

```text
{
  "reasons": [],
  "verdict": "PASS"
}
exit=0
```

Now claim the delete will hit two files, not three, and run the gate again.

```bash
sed 's/"expected": 3/"expected": 2/' evidence.json > evidence-wrong-count.json
python3 "$GATE" gate --evidence evidence-wrong-count.json --scan scan.json; echo "exit=$?"
```

```text
{
  "reasons": [
    "unexpected cardinality: measured 3, expected 2"
  ],
  "verdict": "BLOCK"
}
exit=1
```

The gate also blocks when the rollback is missing, the preflight did not run, or a check failed. A rollback of kind `irreversible` needs a human approval in the evidence. An agent never approves its own irreversible step, and the gate has no override. [The skill](../../src/claude/skills/destructive-change-safety/SKILL.md) lists every block reason and the `backup` and `snapshot` rollback kinds.

### Step 4: Count independent proof, not files

An agent that writes code and then writes the test for it has made one loop of evidence. Both artifacts share one reading of the requirement. `evidence-provenance` counts loops, not files, and gives every named check one of four states: `VERIFIED`, `NOT RUN`, `UNAVAILABLE`, or `FAILED`.

Make a helper that prints the parts of the result you care about.

```bash
mkdir -p "$WORK/evidence" && cd "$WORK/evidence"
cat > show.py <<'EOF'
import json
import sys

d = json.load(open(sys.argv[1]))
print(d["verdict"], d["independent_loops"], d["violations"], d["warnings"])
EOF
```

First record: an agent wrote the fix and its own test. A reviewer was handed the agent's conclusion. The agent wants to report two confirmations.

```bash
cat > inflated.json <<'EOF'
{
  "claim": "The retry loop handles timeouts.",
  "subject": {"artifact": "retry.py", "revision": "abc123", "premises": ["my-reading-of-the-ticket"]},
  "claimed_independent": 2,
  "evidence": [
    {"id": "my-test", "state": "VERIFIED", "origin": "same-loop", "authority": "executable-runtime",
     "premises": ["my-reading-of-the-ticket"]},
    {"id": "reviewer", "state": "VERIFIED", "origin": "independent-reviewer", "authority": "heuristic",
     "premises": ["review-notes"], "inherits_from": ["subject"]}
  ]
}
EOF
python3 "$CLS" inflated.json > out.json; echo "exit=$?"; python3 show.py out.json
```

```text
exit=1
SINGLE_LOOP 0 [{'rule': 'inflated-confidence', 'subject': '2>0'}] []
```

Both items sit in the fix's own loop, so the count is zero. The claim of two is refused.

Second record: the same fix, plus a test that existed before the change, was red, and is now green. It came from the original bug report, not from the agent's reading. The agent claims one confirmation.

```bash
cat > corroborated.json <<'EOF'
{
  "claim": "The retry loop handles timeouts.",
  "subject": {"artifact": "retry.py", "revision": "abc123", "premises": ["my-reading-of-the-ticket"]},
  "claimed_independent": 1,
  "evidence": [
    {"id": "my-test", "state": "VERIFIED", "origin": "same-loop", "authority": "executable-runtime",
     "premises": ["my-reading-of-the-ticket"]},
    {"id": "old-red-test", "state": "VERIFIED", "origin": "pre-existing", "created": "pre-existing",
     "authority": "executable-runtime", "environment": "real", "premises": ["original-bug-report"]}
  ]
}
EOF
python3 "$CLS" corroborated.json > out.json; echo "exit=$?"; python3 show.py out.json
```

```text
exit=0
CORROBORATED 1 [] []
```

One independent loop exists, and the claim cites one. Exit `0` here means the record was classified. It does not mean every record passes, so read the verdict.

Now the four states. This record names four checks.

```bash
cat > states.json <<'EOF'
{
  "claim": "The retry loop handles timeouts.",
  "subject": {"artifact": "retry.py", "revision": "abc123", "premises": ["my-reading-of-the-ticket"]},
  "evidence": [
    {"id": "my-test", "state": "VERIFIED", "origin": "same-loop", "authority": "executable-runtime",
     "premises": ["my-reading-of-the-ticket"]}
  ],
  "checks": [
    {"check": "unit tests", "state": "VERIFIED"},
    {"check": "lint", "state": "NOT RUN", "cheap": true, "available": true},
    {"check": "smoke test on Codex", "state": "UNAVAILABLE", "available": false},
    {"check": "type check", "state": "FAILED"}
  ]
}
EOF
python3 "$CLS" states.json > out.json; echo "exit=$?"; python3 show.py out.json
```

```text
exit=0
SINGLE_LOOP 0 [] [{'rule': 'cheap-gate-not-run', 'subject': 'lint'}]
```

Lint is cheap and available, and nobody ran it. The classifier warns. If the report leaned on that unrun check (`"used_as_support": true`), the classifier would exit `1` with `unverified-support`. A `NOT RUN` check cannot back a conclusion. A check named with no state, or with words like "should run" or "pending", is also a violation. Expensive or credentialed checks are never required. The duty is to report their state honestly. The skill carries the full model: [SKILL.md](../../src/claude/skills/evidence-provenance/SKILL.md) and [the lineage model](../../src/claude/skills/evidence-provenance/references/lineage-model.md).

### Step 5: Keep long output out of the agent's context

`run_with_receipt.py` is opt-in. Nothing wraps your commands for you, because no tool-use hook may intercept output. An agent calls the wrapper on purpose when a command will print thousands of lines.

Run it from the repository root. The cap here is low so you can see a receipt.

```bash
cd "$REPO"
python3 "$RWR" run --max-inline-bytes 1024 -- seq 1 2000 > "$WORK/receipt.txt"; echo "exit=$?"
grep -E '^(command|exit_code|total_bytes|exposed_bytes|truncated)' "$WORK/receipt.txt"
```

```text
exit=0
command: seq 1 2000
exit_code: 0
total_bytes: 8893
exposed_bytes: 4096
truncated: true
```

The full output went to a file. The agent sees the receipt, a head, and a tail. Page the saved file by byte range.

```bash
ART="$(sed -n 's/^artifact: //p' "$WORK/receipt.txt")"
python3 "$RWR" read "$ART" --offset 0 --length 6
```

```text
1
2
3

[range 0-6 of 8893 bytes; next_offset=6]
```

The `[range ...]` line goes to stderr, so it shows in your terminal but not in a redirected file. Pass `next_offset` as the next `--offset` to keep paging.

The wrapper returns the command's own exit code, so a failing test still looks failed.

```bash
python3 "$RWR" run -- sh -c 'exit 7'; echo "exit=$?"
```

```text
exit=7
```

The wrapper redacts secrets before anything reaches disk. Saved files land in `.project-toolkit/temp/tool-output`, which git ignores. The [script header](../../scripts/run_with_receipt.py) lists the options and the wrapper's own exit codes.

### Step 6: Know when the agent stops

ADR-105 says when work is done. The rule text is short:

> When every requested deliverable satisfies the frozen task contract and no blocker remains, the current task is terminal. Stop autonomous work.

A second rule, the completion-tail audit, shapes the last message. After the agent reports a finished result, it removes any offer or question that only keeps the chat going. "Want me to...?" and "Let me know if..." do not belong there. A real blocking question still does.

Confirm both rules are in your checkout.

```bash
grep '^### Terminal predicate' .claude/rules/builder-ethos.md
grep '^## Completion-Tail Audit' .claude/rules/voice.md
```

```text
### Terminal predicate
## Completion-Tail Audit
```

When you see an agent stop on its result, that is the design. When you want more work, ask for it in a new request.

## Check your result

You finished if you saw all of these:

| Step | You saw |
|---|---|
| 1 | `True True` |
| 2 | `exit=2` with `incomplete`, then `ask`, then `skip` |
| 3 | `PASS` with `exit=0`, then `BLOCK` with `exit=1` and the cardinality reason |
| 4 | `inflated-confidence` with `exit=1`, then `CORROBORATED 1`, then a `cheap-gate-not-run` warning |
| 5 | A receipt with `truncated: true`, a ranged read, and `exit=7` |
| 6 | Two matching headings |

The two results that matter most are the `PASS` in step 3 and the `CORROBORATED` in step 4. Together they show a delete with a measured scope and a rollback, and a claim with one counted independent loop.

## If a step fails

- **A command says `No such file`.** You ran it outside the repository root, or `$REPO` is unset. Run `cd` to your checkout and set the variables again.
- **`decision_question.py` exits 1.** The brief JSON is malformed, an answer is not one of the options, or an ID repeats.
- **`scan` exits 1 with `unknown`.** A file did not parse, or the scan cannot read that language. Read the listed files by hand. Scope unknown is not scope safe.
- **The gate prints `BLOCK` on `version`.** The `ref` must be a 40-character commit that exists in the repository where you run the gate. Run it from inside the demo folder.
- **`classify_lineage.py` exits 2.** The record JSON is wrong. Check required fields against the lineage model.
- **`run_with_receipt.py` exits 2 on `read`.** The path is not a saved artifact under the output folder. Use the `artifact:` line from a receipt.

Clean up by deleting the demo folder printed by `echo "$WORK"`.

## Go deeper

Reference sources. We do not copy them here, so they stay the single owner of each rule.

- Action tiers: [ADR-112](../../.project-toolkit/architecture/ADR-112-risk-tiered-action-boundaries.md), and the deny-rule test `tests/test_action_tier_deny_rules.py`.
- Why the guardrails exist: [Technical Guardrails](../technical-guardrails.md) explains the failure that led to enforcing protocol with automation instead of trust.
- How agent limits are kept explicit: [Agent System Governance](../agent-governance.md), design principle 3.
- Done means done: [ADR-105](../../.project-toolkit/architecture/ADR-105-terminal-state-completion-contract.md).
- Skills: [decision-question](../../src/claude/skills/decision-question/SKILL.md), [destructive-change-safety](../../src/claude/skills/destructive-change-safety/SKILL.md), [evidence-provenance](../../src/claude/skills/evidence-provenance/SKILL.md).

## Next

Return to the [training index](README.md) for the next page.
