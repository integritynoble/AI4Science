# Full-suite evidence policy

The full-suite gate requires independent pytest collection (`scripts.ci_collect`),
a JUnit report, and the captured pytest exit code. IDs must be unique, every
collected test must be reported, and at least 1,000 unique cases must execute.
Skipped cases, collection errors, known-red failures and missing private
coverage make this full-suite status nonpassing. `known_red.txt` is an inventory,
not an authorization to waive failures; the owner must approve any future
exception policy explicitly. Synthetic gate tests cover skipped/duplicate-only
reports, omissions, missing-package classification and abnormal termination.

Fork and same-repository PR jobs do not receive the private read token or build
private code. They publish diagnostic evidence and remain nonpassing if private
coverage is unavailable. On a trusted main push, the owner must configure
`CONTROL_PLANE_REV` as an independently reviewed 40-character commit SHA and
`CONTROL_PLANE_READ_TOKEN` as a read-only token scoped only to that repository.
Private checkout uses the SHA and disables persisted credentials. No reviewed
private revision or token was available locally, so private coverage and the
hosted workflow have not been validated. Require successful trusted private
coverage before describing the suite as complete.
