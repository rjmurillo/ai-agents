# Exact code-quality review approvals

<!-- vendor-portability: scripts/validation/check_code_quality_review_approval.py
     lives in the pinned integration commit of the ai-agents repository.
     Other repositories use the ordinary review procedure. -->

This procedure applies to the ai-agents repository and its main branch.
It keeps the raw assessor output and uses one trusted run for review.
Use it only for an owner-approved exit 10 with comparable regressions.
The assessor admits a shared-module import or a shorter file on its own (issue #7525).
Those runs exit 0, so this procedure does not apply to them.
This procedure pins review scope from step 1 through marker creation.
Its assessment and verdict replace the code-quality parts of steps 5 and 6.

## Activate the verifier

Merge this verifier before requesting approval for the readiness branch.
Load the updated review procedure from the trusted integration branch.
Use a trusted POSIX environment and its locked parser dependencies.
Use trusted PowerShell on PATH when the assessor needs it.

## Capture the candidate assessment

Confirm origin points to the canonical GitHub repository rjmurillo/ai-agents.
Fetch origin before collecting review evidence.
Pin the integration tip and reviewed head before collecting the diff.
Use the pinned commit range for diff collection, axis selection, and depth classification.
Run checkout-dependent helpers in a disposable checkout at the pinned head.
Set its local origin/main to the pinned integration commit for helpers that resolve it.
Load review prompts and executable review helpers from the pinned integration tree.
Use the disposable checkout as input for those helpers.
Preserve the ordinary evidence requirements for every other axis.
Restart the review if either commit changes before the marker is written.
The assessor compares scores against the merge base of those pins.
Set `QUALITY_PYTHON` to the interpreter from a trusted integration environment.
Choose an absolute scratch path for `QUALITY_ASSESSMENT`.
Use those pinned SHAs as `quality_base` and `quality_head`.
Extract `scripts/validation/check_code_quality_review_approval.py` from the pinned integration commit.

```sh
quality_verifier=$(mktemp)
git --no-replace-objects show "$quality_base:scripts/validation/check_code_quality_review_approval.py" > "$quality_verifier" &&
  "$QUALITY_PYTHON" -I "$quality_verifier" \
    --base "$quality_base" --head "$quality_head" --assessment "$QUALITY_ASSESSMENT"
```

The inventory includes both commits, the reported regressions, and an approval digest.
Prepare the inventory and justify every regression locally.
Before requesting approval, record the inventory and evidence in the tracking issue.
Publish only with user authorization.
Otherwise, have the owner record the evidence and supply the links.
Keep the axis blocking when any regression lacks justification.
The owner approves the inventory by posting a new comment with exactly this body.

```text
Code-quality review approval SHA256: <approval_sha256 from the inventory>
```

## Verify the approval during review

Use the same command and add `--issue NUMBER --comment ID`.
The verifier uses committed files and the trusted assessor configuration.
It checks the owner comment from the canonical GitHub repository.
An edited comment, unavailable API, or revision mismatch blocks approval.

Use `raw_exit`, `QUALITY_ASSESSMENT`, and its `.stderr` companion as raw evidence.
The verifier appends `.stderr` to the assessment path.
Process stderr carries verifier diagnostics.
An approval denial preserves raw exit 10 or 11 as FAIL.
Missing raw evidence leaves the axis UNKNOWN and prevents a marker.
Do not use output from a separate run as the approved assessment.
Use WARN only when exit is 0 and the result states `verdict: WARN`.
Check both returned pins against the review scope and before marking.
Prepare the raw JSON and stderr locally.
Publish review evidence only when the user authorized that shared-repository write.
Otherwise use evidence links supplied by the owner.
Match the linked raw files to `assessment_sha256` and `stderr_sha256` from this run.
Show the evidence links and inventory in the review output before writing a marker.
Record both pins, raw exit, digest, and approval comment link in the marker body.
Keep these fields outside the validated report block.
Require normal warning acknowledgement and the SHA-bound review marker.

A missing approval leaves the ordinary quality gate in force.
Absolute threshold failures and evidence loss cannot qualify.
Nonregular entries and external Go module context cannot qualify.
Checkout bytes must match their committed blobs before assessment.
Deleting or editing the comment prevents approval on fresh review runs.
Existing markers attest to the verdict of the review that wrote them.
The ordinary marker reader also accepts eligible clean merges above those markers.
