# Full-scan corpus asymmetry in the skill validators

## Question

Why did `skill_size.py` and `skill_frontmatter.py` report a whole-repository verdict after reading less than half the repository?

## Conventional answer

A validator with a tuple named `_SKILL_TREE_PREFIXES` (or `_SKILL_FILE_PATTERN`) reads every tree in that tuple. Reviewing the constant is enough to know the corpus.

## First-principles position

The constant only bound the staged and changed-files branches. The full-scan branch fell through to a separate `--path` argument whose default was a single tree, so the two discovery paths measured different corpora. The constant is not the corpus; the discovery branch is. Read the branch that actually runs.

## Evidence

- `.claude/skills` holds 98 `SKILL.md` files; `src/copilot-cli/skills` holds 111. The default audit opened 98 of 209 and printed "All skill files within size limits."
- Both validators are invoked only two ways: `lefthook.yml:149` runs `skill_size.py --staged-only --ci` (correct, both trees), and no workflow calls the full scan at all. `skill_frontmatter.py` has no gate caller, so its default full scan was its only invocation path.
- Both trees scan green today, so widening the corpus did not red anything. Issue #4015.

## Related trap in `check_vendor_portability.py`

`_is_raw_string_regex` keyed on a literal `\.` in the token body. That signal works only for prefixes that start with a dot (`.agents`, `.claude/lib`). When PR #4029 added the dotless `scripts/` prefix, no regex matching it could ever carry `\.`, so the exemption was unreachable for the entire new prefix class and nine baseline entries were false positives. Lesson: an exemption predicate written against one prefix shape silently fails when a differently-shaped prefix joins the list. Key the predicate on the matched prefix, not on a global heuristic. Issue #4046.

## Decision

`default_corpus_files()` in both validators builds the full-scan corpus from the shared prefix tuple, anchored on `_PROJECT_ROOT` so the result is the same from any working directory. `--path` and `SKILL_PATH` stay as the explicit narrowing override. Each validator prints the trees it actually scanned and names any absent tree, because a vendored install legitimately ships one tree.
