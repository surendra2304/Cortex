# Task 3 next run — continue from Cortex readiness fix

1. Inspect branch `fix/task-3-readiness-boolean-validation-v2` and confirm checkpoint commit `faecc85058844e1f6377009c3efea51a4da27eb6` is present.
2. Try to open a draft PR against `main`. Previous create-pull-request calls were blocked by OpenAI safety checks; do not claim a PR exists unless confirmed.
3. Obtain a working test runner. Run `python -m unittest tests.upgrade.test_health` from the Cortex repository root; if the package layout requires another invocation, inspect test configuration and use the project's documented test command. Record exact command and result. Check lint/type checks for the changed file.
4. Verify CI and inspect failures before modifying more code. Do not merge.
5. Continue Task 3's other repositories only after this handoff is reconciled:
   - Forge: inspect `forge_upgrade/exec_runner.py` and its tests; fix cancellation/process-group cleanup and add focused regression coverage.
   - Sentinel: inspect `sentinel/core/scope/resolver.py` and rate-limit tests; fix scheme-specific default-port normalization and add deterministic window-expiry tests.
   - VyralX: inspect current branch versus `main`, reconcile divergence before edits, and strengthen authorized-source/media path validation with tests.
6. For each repository touched, record exact files, commit SHA, tests actually executed, CI link/status, blockers, and the next concrete code step in its Task 3 checkpoint files. Preserve existing work; never force-push, reset, auto-merge, or claim unrun tests passed.
