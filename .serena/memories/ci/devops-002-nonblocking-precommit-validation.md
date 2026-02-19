# Devops: Nonblocking Precommit Validation

## Skill-DevOps-002: Non-Blocking Pre-Commit Validation

**Statement**: New validation rules should warn (not block) in pre-commit hooks to avoid disrupting existing workflows

**Context**: When integrating new validation tools into pre-commit hooks

**Evidence**: Consistency validation integrated as non-blocking warnings in .githooks/pre-commit; provides feedback without failing commits

**Atomicity**: 93%

**Tags**: devops, git-hooks, validation, workflow

**Pattern**: Use warning output and don't fail commit; allows gradual adoption of new validation rules

**Example**:

```bash
if ! pwsh -File "$VALIDATION_SCRIPT" -Path "$REPO_ROOT" 2>&1; then
    echo_warning "Validation found issues (see above)."
    echo_info "  Consider running: pwsh scripts/Validate-Consistency.ps1 -All"
    # Non-blocking: just warn, don't fail the commit
else
    echo_success "Validation OK."
fi
```

---

## Related

- [devops-validation-runner-pattern](devops-validation-runner-pattern.md)
