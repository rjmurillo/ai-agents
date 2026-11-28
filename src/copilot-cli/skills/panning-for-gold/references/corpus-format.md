# Session corpus format

`pan.py prefilter` reads one JSONL file. Each line is one message from an agent session. This file is the whole contract between a producer and panning-for-gold. No code is shared, so any tool that writes the format works.

## Row schema

One JSON object per line, UTF-8, `\n` line ends. Blank lines are skipped.

| Key | Type | Meaning |
|---|---|---|
| `source` | string | Harness name, such as `claude`, `codex`, `copilot`, `t3`, or `gemini`. |
| `session` | string | Session or thread id. |
| `path` | string | Where the message came from: a file path, or a label such as `t3:<thread-id>`. |
| `line` | integer or string | Physical line in `path` for JSONL file sources. A message id for T3. A 1-based message index for Warp, Hermes, and ZCode. Never assume an integer. |
| `ts` | string | ISO 8601 timestamp, or `""` when the source has none. |
| `role` | string | `user` or `assistant`. The prefilter ignores other roles. |
| `text` | string | The full message text. No truncation. |

All seven keys must be present. A missing key, a non-object line, or a non-string `text` or `role` fails the run with exit code 1 and names the line.

## Producers

### skill-doctor

The skill-doctor skill reads local agent session stores. Its collector writes this format:

```text
python3 collect_sessions.py --all-conversations --days 90 --export-corpus <corpus.jsonl> --out <report-dir>
```

- It writes user and assistant messages of every collected session, selected by its usual harness, repository, and time-window flags.
- Text is whole: no per-message truncation and no head and tail buffer.
- Token-shaped strings are replaced with `[REDACTED]`: `sk-` keys, GitHub tokens (`ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_`), AWS key ids, JWTs, Slack tokens, and bearer or `Authorization: token` headers.
- T3 and Gemini antigravity sessions record no repository path, so they export only with `--all-conversations`.
- Run it outside any git repository, or point `--export-corpus` at a path your VCS ignores. The file holds the full text of your conversations.

### Any other producer

Hermes and other installs do not ship skill-doctor. Bring your own file. Write one object per message with the seven keys above, and apply your own secret redaction. The prefilter redacts the same token shapes again, but it cannot find a secret in a shape it does not know.

## What the prefilter does with it

```text
python3 pan.py prefilter --corpus <corpus.jsonl> --lens contradiction --out <batch-dir>
```

- Drops text a harness injected (system reminders, task notices, environment blocks).
- Keeps windows with a surprise signal plus a number. Two weaker signals plus a number also pass. A single weaker signal needs a stated belief, a contrast, and a comparison of two numbers.
- Removes duplicates by a hash of the whole normalized window (case and punctuation folded, decimal points kept). Two windows that differ in any digit or decimal point both stay.
- Writes `batch-NNN.jsonl` files and `manifest.json`. Each batch row adds `hid` (`<batch>-<index>`), `tier`, `score`, `key`, and a window `text` of at most 1100 characters.

The ids are stable for the same corpus and options. Use a fresh `--out` directory for each run: the command refuses a directory that already holds batch files, and it refuses a `--corpus` that is a `batch-*.jsonl` or `manifest.json` file inside `--out`. Batch files and `manifest.json` are written readable by the owner only (mode 0600).

## Locators and proof lookup

The verify step in `references/contradiction-lens.md` searches the source transcript with `grep`. That works only when `path` is a readable JSONL file and `line` is a physical line in it. A row whose `path` is a label such as `t3:<thread-id>`, or a database file, has no text file to search. Its candidates end in `cannot_verify`, not `no_measurement`, unless the producer also supplies a text transcript. The row `text` is still enough for the judge step.

The batches are transcript-derived text. Keep them out of version control.
