# Issue 4995: frontmatter module collision fix

`tests/test_validate_skill_structural.py` no longer inserts the SkillForge scripts directory into `sys.path`.

That change stops the structural suite from shadowing the installed `python-frontmatter` package when
`tests/test_validate_skill_structural.py` runs before `tests/test_validate_skill_installation.py` in the same
pytest process.

Verified repro:

```bash
uv run --frozen python -m pytest tests/test_validate_skill_structural.py tests/test_validate_skill_installation.py -q
```

Result: 30 passed.
