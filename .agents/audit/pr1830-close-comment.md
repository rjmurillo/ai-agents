Superseded by commit `cd30f6a6` on `feat/req-003-multi-tool-build`. I adopted this PR's version of `tests/skills/memory/test_url_validation.py` directly (it correctly identified the relative-import + symbol-name bugs in my prior `1ef95938` and added two import-smoke tests I missed).

The branch was CONFLICTING because my earlier fix had already touched the same file with a less-complete approach. Rather than reconcile, I took your version verbatim — same fix, better coverage (19 tests pass).

Thanks for the parallel fix. Closing.
