# Phase 0 Research: Automated PR Review Auto-Merge, Self-Cancellation Prevention & Self-Healing Label Governance

## 1. Self-Cancellation Prevention in GitHub Actions When Pushing with a PAT

- **Decision**: Configure `concurrency: { group: pr-review-${{ github.event.pull_request.number || inputs.pr_number }}, cancel-in-progress: false }` in `.github/workflows/pr-review.yml`.
- **Rationale**: Because `pr-review.yml` pushes automated fixes (`fix(pr-review): apply Claude Opus 5.5 auto-fixes [skip pr-review]`) using `secrets.ORCHESTRATION_PAT` (required so the `CI` workflow triggers on the auto-fix commit), GitHub immediately fires a `pull_request: [synchronize]` webhook event ~4 seconds after `git push`. With `cancel-in-progress: true`, the newly triggered `synchronize` run cancels the active run before it can finish applying labels, filing follow-up issues, waiting for `CI`, and squash-merging. Setting `cancel-in-progress: false` queues the `synchronize` run behind the active run; once the active run merges the PR, the queued run starts, detects `state == "MERGED"` in `steps.meta`, and exits in `<2s`.
- **Alternatives Considered**:
  - *Pushing with `GITHUB_TOKEN`*: Rejected because pushes made with `GITHUB_TOKEN` do not trigger the `CI` (`build.yml`) workflow on the auto-fix commit, violating Constitution Principle IV and Gate 4.
  - *Making Run 1 exit after `git push` and relying solely on Run 2 to merge*: Rejected because it splits a single logical review/merge transaction across two workflow runs and leaves Run 1's label/issue mutations vulnerable if `git push` triggers cancellation before they complete.

## 2. Zero-Token `merge_only` Fast-Path for `[skip pr-review]` Commits

- **Decision**: In `steps.meta`, when the head commit message contains `[skip pr-review]` and the PR is still `OPEN`, inspect the latest PR comment containing `<!-- pr-review-verdict -->`. If that comment contains `APPROVED`, set `skip=false` and `merge_only=true` (skipping checkout, Python/Node setup, and Claude Code execution) and proceed directly to ensuring `review:approved`, polling `CI` for `head_sha`, squash-merging, and checking parent-story closure.
- **Rationale**: Provides zero-LLM-token recovery for already-reviewed PRs (such as PR #138) or manual `workflow_dispatch` retries without re-running a 6-minute Claude Opus 5.5 review on code that Claude itself just fixed and approved.
- **Alternatives Considered**:
  - *Removing `[skip pr-review]` marker and re-running Claude*: Rejected because it wastes 6+ minutes and significant Claude Opus 5.5 token budget on already-verified auto-fixes.

## 3. Idempotent Self-Healing Repository Labels

- **Decision**: Pre-provision standard pipeline labels (`review:approved`, `review:changes-requested`, `status:needs-po-input`, `status:ready`, `status:done`, `tech-debt`) in `AntaresAndBharani/darwin-trader` and wrap every label application in `pr-review.yml` with `gh label create <label> -R "$REPO" --color <hex> --description <desc> --force` before calling `gh pr edit --add-label` or `gh issue create --label`.
- **Rationale**: In PR #138, `gh pr edit 138 --add-label review:approved` with `check=True` threw `CalledProcessError` (`'review:approved' not found`) because the label had not been created in the repository. `gh label create --force` is idempotent (creates the label if missing or updates its metadata if present) and guarantees label operations never crash the workflow.
- **Alternatives Considered**:
  - *Ignoring `gh pr edit` errors (`check=False`) without creating labels*: Rejected because downstream workflows (`dev-test.yml`) and human operators rely on `review:changes-requested`, `review:approved`, and `status:needs-po-input` labels being visibly applied to PRs.

## 4. Commit-Scoped CI Verification & Failure Fallback

- **Decision**: Query `gh run list -R "$REPO" --commit "$CURRENT_SHA" -w "CI" -L 1 --json status,conclusion` inside a 60-iteration loop (10s sleep, 10 minutes max), require an explicit `CI_PASSED="true"` gate before running `gh pr merge`, and if `CI_PASSED != "true"` (due to failure, cancellation, or timeout), transition the PR label from `review:approved` to `review:changes-requested`, post a diagnostic comment referencing `CURRENT_SHA`, and exit `1`.
- **Rationale**: Filtering by `--branch "$HEAD_REF"` alone can return the *previous* commit's `completed:success` CI run in the first few seconds after `git push` before the new CI run registers. Requiring `CI_PASSED="true"` also prevents the bash `for` loop from falling through to `gh pr merge` if all iterations complete while CI is still `in_progress`.
- **Alternatives Considered**:
  - *GitHub native `gh pr merge --auto`*: Rejected because repository branch protection rules with required status checks may not be enabled on all branches, in which case `gh pr merge --auto` fails or merges immediately without waiting for `CI`.

## 5. Consolidating `merge.yml` into `pr-review.yml`

- **Decision**: Delete `.github/workflows/merge.yml` and embed its post-merge parent-story closure step directly at the end of `.github/workflows/pr-review.yml`.
- **Rationale**: Because `pr-review.yml` uses `ORCHESTRATION_PAT` to apply `review:approved`, keeping `merge.yml` (`on: pull_request: [labeled]`) causes a duplicate workflow run that races `pr-review.yml` to poll CI and merge the PR.
- **Alternatives Considered**:
  - *Keeping both workflows*: Rejected due to redundant runner consumption and race conditions during `gh pr merge`.
