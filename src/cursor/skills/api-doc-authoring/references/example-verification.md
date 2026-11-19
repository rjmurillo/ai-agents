# Example Verification

Read this when you mark an example runnable or investigate a stale one.

## Syntax

An executable example is a fenced `http` block with `example=<id>` and
`expect=<status>`. A `json` block with `response=<id>` documents what comes
back. The runner sends the request exactly as the document shows it.

````text
```http example=create-order expect=201
POST /orders
Content-Type: application/json

{"sku": "A-1", "qty": 2}
```

```json response=create-order
{"id": "<id>", "status": "pending"}
```
````

- Paths are relative. The base URL is a `run` argument, not part of the doc.
- An `<angle>` placeholder matches any string. Any other value must match.
- Extra keys in the real response are allowed. Documented keys must exist.
- An `http` block with neither `example` nor `expect` is illustration only and is not run.
- Examples run top to bottom in each file. The runner sends each request exactly as written and never substitutes values from earlier responses. Paste concrete ids into later requests.
- Do not put secrets in a doc. `Authorization`, `Cookie`, and `X-API-Key` header
  values are redacted in the evidence file anyway.

See `worked-example.md` for a full page. The skill's tests run it.

## Where examples run

A local server, a test environment, or a mock. `run` accepts loopback hosts by
default and refuses others, because a documented `DELETE` is a real `DELETE`.
`--allow-remote` is for a disposable test environment. Production calls are out
of scope.

An executable contract test is an alternative to a live call when the repo has
one. Cite the test and keep its output as the evidence.

## Evidence

`run --evidence <file>` writes, per example: id, doc and line, method, URL,
redacted headers, request body hash, expected and actual status, response hash,
verdict, and mismatches. The file also holds the base URL, Python version,
timestamp, and a hash of each document. Anyone can re-run it from the doc and
the base URL.

Quote the verdict and the evidence path in the PR body. A verdict of `UNVERIFIED`
(exit `2`) means nothing was proved.

## Stale examples

When the API changes, find the examples that touch it, then re-run them:

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/api-doc-authoring/scripts/api_examples.py list docs/ --touching /orders; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

A failing example is a doc bug or an unannounced contract change. Decide which,
fix the doc or raise the contract change, and re-run. Do not edit `expect=` or
the response block to match a response you did not understand.

## Mutation control

To show verification is load-bearing, change one thing and watch it fail:
rename a request field in the doc, or change `expect=`. If the run still
passes, the example never reached the API.

## Lifecycle

Documentation changed by this skill flows through the existing gates:

| Gate | What it adds |
|------|--------------|
| `test` Gate 5, `skills/test/references/doc-accuracy-gate.md` | `doc-accuracy` on the changed docs (#5398) |
| `review` `doc-accuracy` axis (category `docs-and-instructions`) | Claim review of the same diff |
| This skill's `lint` and `run` | Example structure and execution evidence |

The last row proves examples run. It does not replace the first two.
