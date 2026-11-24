# Change admissions

Two change admissions keep a raw drop in the report but stop it from failing
the gate (rjmurillo/ai-agents issue #7525). A non-redundancy drop is admitted
when the change added no duplicated line, as when a file only loses unique
lines. A Python coupling drop is admitted when the change added no
third-party import root, as when local logic moves into a shared first-party
module. This one is off unless the config sets
`"firstPartyCouplingAdmission": {"importRoots": [...]}`. A module counts as
first-party when it sits beside the file, under one of the file's parent
directories, or under an `importRoots` entry. A new third-party import, a new
duplicate, or any other regressed quality still exits 10. Admitted rows are
listed under `change_admissions` on the comparison.

## Fields

Each admitted quality maps to a record under `change_admissions`:

| Quality | Rule | Fields |
| --- | --- | --- |
| `coupling` | `no_new_third_party_import` | `baseThirdParty`, `headThirdParty`: sorted import roots |
| `non_redundancy` | `no_new_duplicate_lines` | `baseDuplicateLines`, `headDuplicateLines`: counts |

Every record also carries `issue: 7525`. A regressed quality with no record still exits 10.
