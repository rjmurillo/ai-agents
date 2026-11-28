# Thread Inventory

Source: `{transcript-or-dump-name}`
Pass: `{pass1 | final}`
Generated: `{YYYY-MM-DD}`

Optional lens fields

The contradiction lens (session corpus mode) adds four optional fields to a thread. Omit them for ordinary transcripts. An inventory without them stays valid.

```markdown
- **Claim**: `{one sentence: what was found}`
- **Conventional view**: `{what usual advice or a prior memory said}`
- **Evidence**: `{numbers or observation, verbatim where possible}`
- **Strength**: `{strong | medium | weak}`
```

`pan.py validate` checks `Strength` only when it is present. `merge` and `synth` carry the fields through.

---

## Thread 1: `{short title}`

- **Signal**: high
- **Quote**: `"{verbatim quote that surfaced this thread}"`
- **Context**: `{one sentence on where this came from}`
- **Initial take**: `{one sentence on why this might matter}`

## Thread 2: `{short title}`

- **Signal**: medium
- **Quote**: `"{verbatim quote that surfaced this thread}"`
- **Context**: `{one sentence on where this came from}`
- **Initial take**: `{one sentence on why this might matter}`
