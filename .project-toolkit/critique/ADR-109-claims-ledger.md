# ADR-109 claims ledger

Verified 2026-11-22 for issue #7493.

| Claim | Kind | Check | Result |
| --- | --- | --- | --- |
| Parser-free recall uses a dated heading on the first body line. | Behavior | Run the copied plugin's registered hook with a dated heading in a fixture memory. | The hook displays the title from the heading. |
| The fallback uses the filename stem. | Behavior | Move the fixture into a nested memory folder and run the registered hook. | The hook displays the stem without the folder. |
| Loaded confidence defaults to zero. Search computes the displayed value. | Behavior | Read the fallback in `serena_integration.py` and the scoring in `search.py`. | The fallback loads zero. The installed hook displays a computed nonzero score. |
| Dispatcher failures report on stderr and preserve the prompt. | Behavior | Move the copied plugin's recall shim aside and run the registered hook. | Exit zero, empty stdout, and two stderr lines. |
| The host has a 15-second registration timeout. | Count | Read the recall registration in `src/claude/hooks/hooks.json`. | The registration sets 15 seconds. Host timeout behavior remains unverified. |
| The dispatcher does not enforce the shim timeout. | Behavior | Read the dispatcher contract and manifest for the recall group. | The manifest sets 10 seconds for the shim. The dispatcher delegates timeout enforcement to the host. |
| The launcher filters PATH and checks Python symlink targets. | Behavior | Run `tests/hooks/test_plugin_memory_recall_runtime.py`. | Checkout candidates were rejected. The external test interpreter ran. |
| Ripgrep ignores inherited configuration. | Behavior | Run `test_rg_returns_paths` in `tests/test_memory_search.py`. | The invoked command includes `--no-config`. |
| The 256 KiB cap applies to the Python loader. | Behavior | Search a fixture with a match beyond 256 KiB, then call `load_memory` with the cap. | Ripgrep and grep found the match. The loader skipped the file. |
