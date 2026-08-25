# Dev & Test — Antigravity scheduled task instructions (Darwin Trader)

Design: ws-setups/graph-engineering/docs/antigravity-scheduled-tasks.md
(alternate executor for docs/dev-test-node.md and docs/e2e-testing-recommendations.md).

First run `git checkout main && git fetch origin && git reset --hard origin/main` so this checkout is current, before anything below.

Check darwin-trader's open `type:user-story` issues. Never query subtasks or PRs directly — only reach one as a child of the story being processed.

## Step 1 — resolve approved-but-conflicting PRs (highest priority)

For each story: find its subtasks via `gh api repos/<repo>/issues/<story>/sub_issues`, and among those, any with an open PR labeled `review:approved` where `gh pr view --json mergeable -q .mergeable` returns `CONFLICTING`. If one exists anywhere, handle it and stop — do not fall through to Step 2 this poll:

1. Check out the PR's existing branch (not `main`).
2. `git fetch origin && git rebase origin/main`.
3. **Clean rebase:** re-run unit tests (Android: `cd android; .\gradlew.bat testSnapshotDebugUnitTest --no-daemon; cd ..` + Python: `pytest api_gateway/tests strategy_engine/tests`). If tests pass: `git fetch origin` again, read the confirmed current remote SHA for this branch, then push with a SHA-qualified lease — `git push --force-with-lease="<branch>:<sha>"`, **not** a bare `--force-with-lease`.
4. **Conflicting rebase:** only resolve a hunk when it's unambiguously additive on both sides (e.g. concurrent `CHANGELOG.md` additions under `## [Unreleased]`). For real code conflicts, abort rebase and add `status:needs-po-input` to the subtask.

## Step 2 — fix-up work takes priority over new implementation

Only reached if Step 1 found no approved-and-conflicting PR anywhere.

For each story: find its subtasks via `gh api repos/<repo>/issues/<story>/sub_issues`, and among those, any with an open PR labeled `review:changes-requested`. If one exists anywhere, handle it and stop:

1. Read the parent story for context, check out the PR's existing branch (not `main`), and read the blocking issues from the PR's most recent comment starting with `<!-- pr-review-verdict -->`.
2. Address every blocking item across Android and Backend. Never weaken or delete an existing test assertion to force a pass.
3. Re-run unit tests and targeted delta E2E tests (`.\scripts\run-e2e-tests.ps1 -Delta`), up to 3 attempts.
4. If tests pass: commit, push to the same branch, comment on the PR summarizing changes, and remove the `review:changes-requested` label.
5. If still failing after 3 attempts, comment on the PR explaining what's blocking it and request PO input.

## Step 3 — otherwise, is anything else already in flight?

Only reached if Steps 1 and 2 found nothing to do.

a. Is there already any open PR in darwin-trader (`gh pr list --state open`)? If yes, STOP HERE.
b. Is any open `type:user-story` issue currently labeled `status:in-development`? If yes, STOP HERE too.

If neither is true, continue to Step 4.

## Step 4 — new implementation work

Check darwin-trader for open issues labeled `type:user-story` AND `status:ready`.

For each matching story:
1. Read the story's full title, body, and acceptance criteria.
2. Find its subtasks via `gh api repos/<repo>/issues/<story>/sub_issues`, filtered to those labeled `status:awaiting-approval`. If none, skip this story.
3. Before touching any file: add the label `status:in-development` to the STORY.
4. For each such subtask:
   a. Create branch `feat/issue-<N>` from the latest `main`.
   b. Implement the change described in the subtask.
   c. Run unit tests (`cd android; .\gradlew.bat testSnapshotDebugUnitTest --no-daemon; cd ..` + `pytest api_gateway/tests strategy_engine/tests`).
   d. If modifying UI or user journeys, execute delta E2E tests (`.\scripts\run-e2e-tests.ps1 -Delta`) and capture visual artifacts.
   e. If tests pass: commit, push branch, open PR titled after the subtask, with test summaries, link back to parent story, and "Closes #<N>". Remove `status:awaiting-approval` and add `status:in-progress` on the subtask. Publish sticky PR evidence (`.\scripts\post-e2e-evidence.ps1`).
   f. If failing after 3 attempts: do not open PR. Relabel `status:needs-po-input` and comment with details.
5. Once every subtask in step 2 has been attempted, remove `status:in-development` from the STORY.
