# Writing "todo list" in session-log evidence trips the contradiction scanner

## The trap

`scripts/validate_session_json.py` scans every `Evidence` string on a completed
MUST item for words suggesting the item was **not** done. The token list:

```
not available | skipped | N/A | deferred | will validate | will run | TODO | pending | TBD
```

`TODO` matches case-insensitively on a word boundary, so the ordinary sentence
"Todo list updated as each gate ran" reports a contradiction. Nothing about it
is a contradiction. The word "todo" simply appears, and the most natural way to
describe the `tasksUpdated` item is to name the list it tracks.

This is a **warning**, not an error. The log still reports `[PASS]`. It costs a
cycle rather than a push, but a warning that looks like a real finding gets
investigated every time, and in CI output it reads as a problem.

## The part that makes it confusing

Two of the tokens have escape hatches and `TODO` does not, so a fix that works
for one does not work for the other.

`deferred` and `pending` are scope-qualified: an affirmative completion word
(`passed`, `done`, `verified`, `ran`, and similar) followed by a clause boundary
(`.` or `;`) suppresses them, on the theory that the deferral is a note about
different work. `skipped` is suppressed when a bare number precedes it, so
pytest summaries survive.

`TODO`, `TBD`, `N/A`, `will run`, `will validate` and `not available` have no
escape. Measured against `_has_contradiction`:

```
ok     'Task list updated as each gate ran.'
FLAG   'Todo list updated as each gate ran.'
FLAG   'All gates passed. Todo list updated.'      <- affirmative + boundary does NOT help
ok     'All gates passed. Deploy deferred to a later PR.'
ok     'All gates passed. Doc work pending review.'
ok     '123 passed, 2 skipped.'
FLAG   'Lint step skipped.'
```

Line three is the one to remember. Adding "All gates passed." in front rescues
`deferred` and `pending` and does nothing for `todo`.

## Do this instead

Say "task list". It is the same sentence and carries no token:

```json
"tasksUpdated": {
  "level": "MUST", "Complete": true,
  "Evidence": "Task list marked done one gate at a time, as each gate finished."
}
```

The general rule for evidence strings: describe what happened using the
vocabulary of completion, and never name a tracking artifact whose name is one
of the tokens. If you genuinely need to record that something was skipped or
deferred, that item's `Complete` should be `false`, which is what the scanner
exists to catch.

Check a string before committing rather than guessing:

```bash
uv run --frozen python -c "
import importlib.util
s=importlib.util.spec_from_file_location('v','scripts/validate_session_json.py')
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
print(m._has_contradiction('YOUR EVIDENCE STRING'))"
```

## Related

`session/session-validation-reconciliation.md` covers the start-versus-end
coverage gap between the pre-commit hook and CI. This is narrower: one scanner,
one word, inside evidence text that is otherwise correct.
