# Skill: Attributing a missed change to the right agent-parity gate (90%)

## Statement

Two different gates guard the six copies of a shared agent, and they split the
work in a way that leaves a documented seam. Blaming the wrong one wastes an
investigation and can produce a duplicate issue against intentional behavior.

The six copies of a shared agent `<n>`:

```
templates/agents/<n>.shared.md          generated source
.claude/agents/<n>.md                   hand-maintained
.github/agents/<n>.agent.md             hand-maintained
src/claude/<n>.md                       hand-maintained
src/copilot-cli/agents/<n>.agent.md     GENERATED from the template
src/vs-code-agents/<n>.agent.md         GENERATED from the template
```

`build/AGENTS.md` states the split outright:

> `validate_install_parity.py`: when one member of a shared-agent group changes,
> every other member must change in the same diff. **It does NOT check content
> similarity.**
> `detect_agent_drift.py`: adds the semantic-similarity check that parity
> enforcement omits.

So parity answers "were they all touched", drift answers "do they still say the
same thing". Neither answers "did THIS addition reach all six".

## The trap

`_added_sections` and `_missing_siblings_already_current` in
`validate_install_parity.py` look like the culprit: `_added_sections` returns
`None` for a preamble edit, a removed or renamed section, or a body edit to a
section that already existed at base.

**They are not.** Read the caller before blaming them. Both FAIL CLOSED:
`_missing_siblings_already_current` returns `False` whenever the answer cannot
be established, and its own docstring says so. They form a carve-out that only
ever RELAXES the gate, and only when it can prove the missing siblings already
carry the content. A `None` from `_added_sections` makes the gate stricter, not
weaker.

## What actually lets a change reach one copy

`.claude/agents/`, `.github/agents/`, and `src/claude/` are classified
hand-maintained, and parity **skips a diff that touches only those paths**. The
exemption is deliberate, from issue #2882, to unblock catch-up backfills.

The comparison that would notice, `.claude/agents` versus `.github/agents`, is
ADVISORY by default and threshold based at 80 percent similarity, so a small
addition to a large file cannot trip it.

Measured instance, PR #4280 at `c0428c19229ee0`: a mandatory "PR identity gate"
landed in `.claude/agents/analyst.md` alone. `templates/agents/analyst.shared.md`
exists, so all six were in scope. All six had zero occurrences of the new text on
`main`, so it was not a backfill. `Agent Drift Detection: SUCCESS` anyway.

Tracked in issue #4082 (OPEN). Do not file a duplicate.

## Recipe

```bash
# Is this a shared agent at all?
ls templates/agents/<n>.shared.md

# How many of the six did the PR touch?
gh pr view <pr> --json files -q '.files[].path' | grep -i <n>

# Do the untouched copies already carry the content, or is this real divergence?
for f in templates/agents/<n>.shared.md .claude/agents/<n>.md \
         .github/agents/<n>.agent.md src/claude/<n>.md \
         src/copilot-cli/agents/<n>.agent.md src/vs-code-agents/<n>.agent.md; do
  printf "%-48s %s\n" "$f" "$(git show origin/main:$f | grep -c '<marker>')"
done
```

When propagating, edit `templates/agents/<n>.shared.md` and regenerate with
`uv run --frozen python build/generate_agents.py` (NOT
`build/scripts/generate_agents.py`, which does not exist). Hand-edit only the
three hand-maintained copies. The six are not byte identical by design: the
`.claude` copy writes `mcp__context7__*` where others write `Context7`, so match
local style rather than pasting one body into all six.

## Generalization

When a gate misses something, find the code path that actually ran before
indicting the one that looks guilty. A fail-closed helper cannot be the reason
something passed. Check the exemption list first: most "the gate missed it"
findings are an exemption doing exactly what it was written to do, and the
governing documentation usually says so.
