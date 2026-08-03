# An over-broad guard destroys its own signal

## The finding

A guard that fires on clean runs is worse than no guard, because it trains its
reader to skim past it. The failure it was built to catch then walks through
unopposed, and the reader believes they checked.

Measured instance. Push logs in this repo end with lefthook's banner
`Ready to create pull request!` **before** the git failure line, so reading the
tail of a push log reports a false success. The mitigation was a grep over the
whole log:

```bash
grep -nE "FAILED|error:|rejected" ~/src/scratch/<name>.log   # WRONG
```

That pattern is unanchored, so it matches pytest test *names*. On a log from a
push that fully succeeded it returned **332 matches**, all false, from lines
shaped like:

```
tests/build_scripts/test_generate_dispatcher.py::TestPostMergeHardening::test_boolean_timeout_rejected PASSED
tests/build_scripts/test_generate_commands.py::test_absolute_source_dir_rejected PASSED
```

Any reader who runs that twice learns the output is noise. At that point the
guard is not merely useless, it is negative: it consumes the attention budget
that would otherwise have gone to reading the log, and it certifies a check that
did not happen.

## The correct pattern

```bash
grep -nE "^FAILED|\[rejected\]|^error:|^remote: error|^fatal:|^ ! " ~/src/scratch/<name>.log
```

Verified in both directions, which is the part that matters:

| Input | Old pattern | New pattern |
|---|---|---|
| Log from a successful push | 332 hits | 0 hits |
| Second log from a successful push | (noisy) | 0 hits |
| `" ! [rejected]        main -> main (fetch first)"` | hit | hit |
| `"error: failed to push some refs"` | hit | hit |
| `"FAILED tests/x.py::test_y - AssertionError"` | hit | hit |
| `"test_timeout_rejected PASSED"` | hit (false) | no hit |

A one-directional check is not a validated check. Confirming the pattern catches
real failures proves nothing about false positives, and confirming it is quiet on
a clean log proves nothing about detection. Both runs are required.

## Independent confirmation that the push landed

A clean log still does not prove the ref moved. Check the remote directly:

```bash
git ls-remote origin "refs/heads/$(git branch --show-current)"
git rev-parse HEAD
```

Equal SHAs mean it landed. Empty output means it did not, whatever the log says.
This is a different authority than the log, which is why it adds information.

## Generalization

When adding any guard, gate, lint, or alert, measure its output on a known-good
input before shipping it. The question is not "does it catch the bad case" but
"is it silent on the good case." A gate with a false-positive rate high enough to
be routinely overridden has inverted its own purpose, and the override becomes
invisible in review because it looks like normal practice.

This is the same shape as an advisory check that prints `[FAIL]` and returns
success: the signal and the semantics disagree, and readers calibrate to the
weaker one.
