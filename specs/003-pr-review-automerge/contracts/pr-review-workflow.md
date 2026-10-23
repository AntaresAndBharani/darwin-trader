# Contract: Unified Automated PR Review & Auto-Merge Workflow (`.github/workflows/pr-review.yml`)

## 1. Triggers & Concurrency Contract

- **Workflow Name**: `PR Review`
- **File Path**: `.github/workflows/pr-review.yml` (`.github/workflows/merge.yml` MUST NOT exist)
- **Triggers**:
  - `pull_request`: `types: [opened, synchronize, ready_for_review, reopened]`
  - `workflow_dispatch`: input `pr_number` (`required: true`, `type: string`)
- **Concurrency**:
  ```yaml
  concurrency:
    group: pr-review-${{ github.event.pull_request.number || inputs.pr_number }}
    cancel-in-progress: false
  ```

## 2. Step Execution Contract

1. **`Check PR state, loop cap, and skip markers` (`id: meta`)**:
   - Emits `head_ref`, `head_sha`, `skip`, and `merge_only` to `$GITHUB_OUTPUT`.
   - When `LAST_MSG` contains `[skip pr-review]`:
     - Extracts the last PR comment containing `<!-- pr-review-verdict -->`.
     - If that comment contains `APPROVED`, sets `skip=false` and `merge_only=true`.
     - Otherwise, sets `skip=true` and `merge_only=false`.
2. **Environment & Claude Review Steps**:
   - Guarded by `if: steps.meta.outputs.skip != 'true' && steps.meta.outputs.merge_only != 'true'`.
3. **`Commit auto-fixes, apply verdict, and prepare merge` (`id: verdict_step`)**:
   - Guarded by `if: steps.meta.outputs.skip != 'true' && (steps.meta.outputs.merge_only == 'true' || (steps.claude.outcome == 'success' && hashFiles('pr_review_output.json') != ''))`.
   - In full-review mode (`merge_only != 'true'`):
     - Commits and pushes any working-tree edits as `fix(pr-review): apply Claude Opus 5.5 auto-fixes [skip pr-review]`.
     - Sets `CURRENT_SHA=$(git rev-parse HEAD)`.
     - Posts the `<!-- pr-review-verdict -->` comment.
     - Idempotently creates (`gh label create ... --force`) and applies `review:approved` or `review:changes-requested`.
     - Idempotently creates labels and files each item in `followup_backlog_issues`.
   - In fast-path mode (`merge_only == 'true'`):
     - Sets `CURRENT_SHA=${{ steps.meta.outputs.head_sha }}` and `VERDICT=APPROVED`.
     - Idempotently creates (`gh label create "review:approved" ... --force`) and applies `review:approved` to the PR.
   - Emits `verdict=$VERDICT` and `current_sha=$CURRENT_SHA` to `$GITHUB_OUTPUT`.
4. **`Wait for CI on target commit and auto-merge` (`id: merge_step`)**:
   - Guarded by `if: steps.meta.outputs.skip != 'true' && steps.verdict_step.outputs.verdict == 'APPROVED'`.
   - Polls `gh run list -R "$REPO" --commit "$CURRENT_SHA" -w "CI" -L 1 --json status,conclusion` up to 60 times (10s interval).
   - Sets `CI_PASSED="true"` only on `completed:success`.
   - Breaks immediately on `completed:failure`, `completed:cancelled`, or `completed:timed_out`.
   - If `CI_PASSED != "true"`:
     - Removes `review:approved`, ensures and adds `review:changes-requested`, posts a diagnostic comment on the PR referencing `$CURRENT_SHA` and `$BUILD_STATUS`, and exits `1`.
   - If `CI_PASSED == "true"`:
     - Verifies PR state is `OPEN` and executes `gh pr merge "$PR_NUMBER" -R "$REPO" --squash --delete-branch`.
5. **`Close the parent story once every subtask is done`**:
   - Guarded by `if: steps.meta.outputs.skip != 'true' && steps.verdict_step.outputs.verdict == 'APPROVED' && steps.merge_step.outcome == 'success'`.
   - Parses linked closing issue (`close[sd]?|fixe?[sd]?|resolve[sd]? #N`) from PR body, checks parent story sub-issues via GitHub API, and if `OPEN_SIBLINGS == 0`, ensures `status:done` label exists, removes `status:ready`, adds `status:done`, comments on the parent story, and closes it.
