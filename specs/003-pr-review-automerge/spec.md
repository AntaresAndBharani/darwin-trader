# Feature Specification: Automated PR Review Auto-Merge, Self-Cancellation Prevention & Self-Healing Label Governance

**Feature Branch**: `feat/003-pr-review-automerge`

**Created**: 2026-10-23

**Status**: Approved

**Input**: User description: "Fix the automated PR review and auto-merge pipeline gap so that Pull Requests approved by automated review (including those where automated fixes are pushed) reliably apply labels, create follow-up issues, verify checks on the exact latest commit, squash-merge without self-cancellation, recover stranded approved PRs with zero redundant review cost, and close completed parent stories."

## Clarifications

### Session 2026-10-23

- Q: How should responsibility be structured between the automated review workflow and the separate merge workflow so they do not race or duplicate merge logic? → A: Consolidate auto-merge and parent-story closure inside the automated review workflow and retire the separate merge workflow so one pipeline owns the full Review -> Auto-Fix -> Verify Checks -> Merge lifecycle.
- Q: How should the pipeline handle concurrency when pushing automated fixes and recovering open PRs that already have an approved auto-fix commit? → A: Disable self-cancellation on the per-PR concurrency group and add a merge-only fast-path when the latest commit is an automated review fix commit with an approved verdict so stranded or re-dispatched PRs merge immediately with zero AI review cost.
- Q: How should repository labels be managed so missing labels never crash auto-merge or follow-up issue creation? → A: Provision the standard pipeline labels in the repository and make the workflow idempotently ensure any required PR or issue label exists before applying it.
- Q: How should the workflow verify continuous integration status on the target commit and handle a check failure or timeout? → A: Poll verification status strictly for the exact target commit (up to 10 minutes), gate merge on an explicit pass confirmation, and if checks fail or time out, transition the PR label to changes-requested and post a diagnostic comment.
- Q: What should happen to the separate label-triggered merge workflow once auto-merge and story-closing are consolidated? → A: Delete the separate merge workflow and move parent-story closing logic into the unified review workflow so applying the approved label never triggers a duplicate workflow run.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - End-to-End Automated Review, Fix, and Merge Without Self-Cancellation (Priority: P1)

As a project maintainer, when I open or update a Pull Request and the automated reviewer approves it—including when the reviewer commits and pushes in-place code fixes—I want the pipeline to complete the entire lifecycle (posting the verdict, ensuring and applying labels, creating non-blocking follow-up backlog issues, verifying continuous integration checks on the exact latest commit, squash-merging the Pull Request, and closing any completed parent story) without crashing on missing labels or cancelling itself mid-execution.

**Why this priority**: This is the primary defect that blocked Pull Request #138 from merging after automated review and auto-fix completion. Without end-to-end completion, approved Pull Requests remain stranded and follow-up backlog items are lost.

**Independent Test**: Can be fully tested by opening a Pull Request where the automated reviewer pushes a fix and issues an `APPROVED` verdict in a repository with or without pre-existing review labels, verifying that labels and follow-up issues are created, checks for the new commit are awaited, and the Pull Request is merged automatically.

**Acceptance Scenarios**:

1. **Given** an open non-draft Pull Request where the automated reviewer applies in-place code fixes and outputs an `APPROVED` verdict, **When** the post-review step pushes the auto-fix commit, **Then** the resulting synchronization event queues behind the active run rather than cancelling it, all required labels are ensured before application, follow-up backlog issues are created, checks on the new commit SHA are verified green, and the Pull Request is squash-merged with its source branch deleted.
2. **Given** a repository where `review:approved`, `review:changes-requested`, `status:needs-po-input`, `status:done`, or `tech-debt` labels have not yet been created, **When** the workflow applies any of those labels to a Pull Request or follow-up issue, **Then** the workflow idempotently creates the missing label first and applies it without error.
3. **Given** a Pull Request linked to a subtask issue whose parent story has no other open subtasks remaining, **When** the Pull Request is merged by the workflow, **Then** the parent story is commented on, updated to `status:done`, and closed automatically.

---

### User Story 2 - Zero-Cost Recovery Merge for Approved Auto-Fix Commits (Priority: P2)

As a project maintainer, when an open Pull Request's latest commit is already an automated review fix commit (`[skip pr-review]`) accompanied by an `APPROVED` review verdict comment, I want any subsequent synchronization or manual workflow dispatch to skip redundant AI code review and proceed directly to ensuring the approval label, verifying checks on the head commit, and merging the Pull Request.

**Why this priority**: Enables immediate zero-token recovery for already-reviewed Pull Requests (such as PR #138) and guarantees idempotency if a network hiccup or manual re-run occurs after auto-fixes have already been pushed.

**Independent Test**: Can be tested independently by triggering the review workflow on an open Pull Request whose latest commit contains `[skip pr-review]` and has an `APPROVED` verdict comment, confirming that AI review is bypassed and the Pull Request merges once checks on the head commit pass.

**Acceptance Scenarios**:

1. **Given** an open Pull Request whose `HEAD` commit message contains `[skip pr-review]` and whose latest review verdict comment is `APPROVED`, **When** the review workflow runs via `synchronize` or `workflow_dispatch`, **Then** the workflow enters `merge_only` mode, skips environment setup and AI review (consuming zero AI tokens), ensures the `review:approved` label is applied, verifies checks on `HEAD`, and squash-merges the Pull Request.
2. **Given** a Pull Request whose `HEAD` commit message contains `[skip pr-review]` and that is already merged or does not have an `APPROVED` verdict comment, **When** the review workflow runs, **Then** the workflow exits cleanly as a no-op without invoking AI review or attempting a merge.

---

### User Story 3 - Exact-Commit Verification Gating & Single-Workflow Ownership (Priority: P3)

As a project maintainer, I want pre-merge verification polling to match the exact commit SHA being merged, block merging if checks fail or time out within 10 minutes, transition failed Pull Requests to `review:changes-requested` with a clear diagnostic comment, and eliminate the duplicate label-triggered merge workflow.

**Why this priority**: Prevents race conditions where a previous commit's passing status allows an untested auto-fix commit to merge, prevents silent timeout fallthroughs, and eliminates duplicate merge attempts across multiple workflows.

**Independent Test**: Can be tested by simulating a commit whose verification run fails or times out during the pre-merge wait and verifying that merge is aborted, the label transitions from `review:approved` to `review:changes-requested`, a diagnostic comment is posted, and no secondary merge workflow is triggered.

**Acceptance Scenarios**:

1. **Given** an approved Pull Request at target commit `CURRENT_SHA`, **When** the workflow polls verification checks before merging, **Then** it only accepts a `completed:success` result for a verification run matching `CURRENT_SHA` (polling up to 10 minutes) and never merges based on an earlier commit's run or a loop timeout fallthrough.
2. **Given** an approved Pull Request at target commit `CURRENT_SHA`, **When** the verification run for `CURRENT_SHA` fails, is cancelled, or does not complete within 10 minutes, **Then** the workflow does not merge the Pull Request, removes `review:approved`, applies `review:changes-requested`, posts a diagnostic comment identifying `CURRENT_SHA` and the check status, and exits with a failure status.
3. **Given** the separate label-triggered merge workflow is retired, **When** `review:approved` is applied to a Pull Request, **Then** no secondary workflow run is spawned to compete with the unified review-and-merge workflow.

### Edge Cases

- **Missing repository labels on first run**: Any label referenced by the workflow (`review:approved`, `review:changes-requested`, `status:needs-po-input`, `status:ready`, `status:done`, `tech-debt`, or custom follow-up labels) is ensured idempotently before use so label operations cannot abort the pipeline.
- **Verification run not yet registered immediately after auto-fix push**: When an auto-fix commit is pushed, the new verification run for `CURRENT_SHA` may take several seconds to appear; polling strictly by `CURRENT_SHA` treats an empty result as pending rather than reading the previous commit's completed run.
- **Synchronize event queued during active auto-fix merge**: Because `cancel-in-progress` is disabled, the `synchronize` run triggered by pushing `[skip pr-review]` waits in queue until the active run completes the merge; when the queued run starts, it observes the Pull Request state is `MERGED` and exits immediately in `steps.meta`.
- **Pull Request without linked issue or parent story**: After squash-merging a Pull Request that does not reference a closing issue or whose linked issue has no parent story, the story-closure check logs that no parent story applies and exits `0` cleanly.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The automated review pipeline MUST set `cancel-in-progress: false` on its per-Pull-Request concurrency group so that pushing an automated fix commit never cancels the active workflow run.
- **FR-002**: When the latest commit on an open Pull Request contains `[skip pr-review]` and the most recent review verdict comment on the Pull Request is `APPROVED`, the pre-flight metadata step MUST activate a `merge_only` fast-path that bypasses dependency installation and AI review and proceeds directly to label synchronization, commit-level verification polling, squash-merge, and parent-story closure.
- **FR-003**: Before applying any label to a Pull Request (`review:approved`, `review:changes-requested`, `status:needs-po-input`) or to a parent story (`status:done`) or to any generated follow-up backlog issue, the workflow MUST idempotently ensure the label exists in the repository so missing labels never cause a command failure.
- **FR-004**: During a full review run, the workflow MUST create all non-blocking `followup_backlog_issues` returned in the review output without allowing label errors to abort issue creation or subsequent merge steps.
- **FR-005**: Before merging an approved Pull Request, the workflow MUST poll verification runs filtered strictly by the exact target commit SHA (`CURRENT_SHA`) for up to 10 minutes (60 attempts at 10-second intervals) and MUST require an explicit pass confirmation (`CI_PASSED=true`) before executing the merge.
- **FR-006**: If the verification run for `CURRENT_SHA` concludes with failure, cancellation, or does not succeed within the 10-minute polling window, the workflow MUST abort the merge, remove `review:approved`, apply `review:changes-requested`, post a diagnostic comment on the Pull Request referencing `CURRENT_SHA`, and exit with a non-zero status code.
- **FR-007**: Upon confirming `CI_PASSED=true` on an open Pull Request, the workflow MUST squash-merge the Pull Request, delete its head branch, and evaluate whether a linked subtask issue's parent story has zero remaining open subtasks—automatically commenting on, relabeling (`status:done`), and closing the parent story when complete.
- **FR-008**: The separate label-triggered merge workflow MUST be removed from the repository so that applying `review:approved` does not spawn a duplicate or competing merge workflow.

### Key Entities

- **Review Verdict Record**: Structured review outcome containing `verdict` (`APPROVED` or `CHANGES_REQUESTED`), `fixes_applied`, `summary`, `pr_comment_markdown`, `blocking_issues`, and `followup_backlog_issues`.
- **Pipeline Execution Mode**: Pre-flight routing state determined in `steps.meta` (`skip=true` for closed/draft/unapproved-skip PRs, `merge_only=true` for open `[skip pr-review]` PRs with an existing `APPROVED` verdict comment, or full review mode when `skip=false` and `merge_only=false`).
- **Target Commit Verification Gate**: Commit-scoped verification check status bound strictly to `CURRENT_SHA` requiring `completed:success` within 60 polling intervals before squash-merge execution.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of open Pull Requests that receive an `APPROVED` automated review verdict (with or without pushed auto-fixes) complete label assignment, follow-up backlog issue creation, commit-specific verification gating, and squash-merging without self-cancellation or missing-label crashes.
- **SC-002**: 100% of already-approved open Pull Requests whose head commit carries `[skip pr-review]` (including Pull Request #138) merge automatically via the `merge_only` fast-path while consuming 0 AI review tokens.
- **SC-003**: 0 Pull Requests are merged based on a stale commit's verification status or after a verification polling timeout, and 100% of post-review verification failures transition the Pull Request label to `review:changes-requested` with a diagnostic comment.
- **SC-004**: 0 duplicate merge workflow runs are triggered when the `review:approved` label is applied to a Pull Request.

## Assumptions

- The repository has `ORCHESTRATION_PAT` (or equivalent token with `contents: write`, `pull-requests: write`, and `issues: write` permissions) and `CLAUDE_CODE_OAUTH_TOKEN` configured in repository secrets.
- The primary continuous integration workflow is named `CI` and triggers on `push` and `pull_request` events across feature branches.
- Squash-merge (`--squash --delete-branch`) is enabled in the repository settings.
