# Semgrep PowerShell parser errors

Semgrep 1.170.0 can emit code-2 Internal matching errors or code-3 PartialParsing warnings when Bash-only GitHub Actions rules parse PowerShell `run` steps. The two affected rules are `yaml.github-actions.security.curl-eval.curl-eval` and `yaml.github-actions.security.gha-curl-pipe-shell.gha-curl-pipe-shell`.

`scripts/validation/git_hook_policy.py` accepts only those exact warning shapes. Code-2 errors require the reported snippet to map only to PowerShell YAML run scalars. Code-3 warnings require exact rule-clause parsing, matching target paths, complete ordered source spans, and full containment inside one PowerShell ScalarNode. Mixed-shell ambiguity, malformed records, decode failures, and real Bash findings fail closed.

Regression coverage is in `tests/test_lefthook_integration.py`, including real Semgrep mixed-shell checks, attacker-controlled filenames, cross-shell spans, aliases, truncated snippets, and repeated Unicode input. Commit `24298fe68d1efe8f45e72c0579b0685024db381b` finalized the hardening for PR #3259.