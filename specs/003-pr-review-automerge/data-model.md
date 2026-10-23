# Phase 1 Data Model: Automated PR Review & Auto-Merge Pipeline

## 1. Pre-Flight Metadata State (`steps.meta` Outputs)

Computed by querying `gh pr view "$PR_NUMBER" -R "$REPO" --json state,isDraft,headRefName,headRefOid,comments` and `gh api "repos/$REPO/commits/$HEAD_SHA"`:

| Output Field | Type | Allowed Values | Description |
| :--- | :--- | :--- | :--- |
| `head_ref` | `string` | Branch name (e.g., `feat/002-yahoo-finance-workspace`) | Head branch name of the target Pull Request. |
| `head_sha` | `string` | 40-char Git SHA | Initial `HEAD` commit SHA of the Pull Request at workflow start. |
| `skip` | `string` | `'true'` \| `'false'` | `'true'` when the PR is not `OPEN`, is a draft, has reached `ROUND_CAP` (`3`), or has a `[skip pr-review]` commit without an `APPROVED` verdict. |
| `merge_only` | `string` | `'true'` \| `'false'` | `'true'` when the PR is `OPEN`, its `HEAD` commit contains `[skip pr-review]`, and the latest `<!-- pr-review-verdict -->` comment contains `APPROVED`. |

### State Routing Table

| PR State / Draft | Latest Commit Has `[skip pr-review]`? | Latest Verdict Comment | `ROUNDS >= ROUND_CAP`? | Resulting Outputs (`skip`, `merge_only`) | Execution Path |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `state != OPEN` or `isDraft == true` | Any | Any | Any | `skip=true`, `merge_only=false` | Exit `0` (No-op) |
| `OPEN`, non-draft | Yes | `APPROVED` | Any | `skip=false`, `merge_only=true` | Fast-path: Ensure `review:approved` $\rightarrow$ Poll CI for `head_sha` $\rightarrow$ Merge $\rightarrow$ Close parent story |
| `OPEN`, non-draft | Yes | None or `CHANGES_REQUESTED` | Any | `skip=true`, `merge_only=false` | Exit `0` (No-op) |
| `OPEN`, non-draft | No | Any | Yes (`>= 3`) | `skip=true`, `merge_only=false` | Ensure & apply `status:needs-po-input` $\rightarrow$ Post escalation comment $\rightarrow$ Exit `0` |
| `OPEN`, non-draft | No | Any | No (`< 3`) | `skip=false`, `merge_only=false` | Full Review: Checkout $\rightarrow$ Setup $\rightarrow$ Claude Review & Auto-Fix $\rightarrow$ Verdict/Labels/Issues $\rightarrow$ Poll CI for `CURRENT_SHA` $\rightarrow$ Merge $\rightarrow$ Close parent story |

---

## 2. Review Output Schema (`pr_review_output.json`)

Produced by Claude Opus 5.5 High during full review runs:

| Field | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `verdict` | `string` | `"APPROVED"` \| `"CHANGES_REQUESTED"` | Final review decision after applying any in-place auto-fixes. |
| `fixes_applied` | `boolean` | `true` \| `false` | Whether files in the working tree were edited during the review. |
| `summary` | `string` | Non-empty string | Concise 1–2 sentence summary of the review and auto-fixes. |
| `pr_comment_markdown` | `string` | Non-empty Markdown | Full structured review report posted with `<!-- pr-review-verdict -->`. |
| `blocking_issues` | `array<object>` | Empty when `APPROVED` | Blocking findings (`file`, `issue`, `suggested_fix`) requiring human input. |
| `followup_backlog_issues` | `array<object>` | Optional array | Non-blocking follow-up issues (`title`, `body`, `labels`) created via `gh issue create`. |

---

## 3. Repository Pipeline Labels Catalog

Standard labels idempotently ensured via `gh label create <name> -R "$REPO" --color <color> --description <description> --force`:

| Label Name | Hex Color | Description | Applied When |
| :--- | :--- | :--- | :--- |
| `review:approved` | `0E8A16` | PR approved by automated Claude Opus review | Verdict is `APPROVED` (or during `merge_only` fast-path) |
| `review:changes-requested` | `D93F0B` | PR requires changes or CI remediation | Verdict is `CHANGES_REQUESTED` or CI fails/times out on `CURRENT_SHA` |
| `status:needs-po-input` | `B60205` | Escalated to Product Owner after max review rounds | Review round count reaches `ROUND_CAP` (`3`) |
| `status:ready` | `0E8A16` | Story or subtask ready for Dev & Test implementation | Removed from parent story when transitioning to `status:done` |
| `status:done` | `0E8A16` | All subtasks merged and parent story completed | Applied to parent story when `OPEN_SIBLINGS == 0` |
| `tech-debt` | `FBCA04` | Technical debt or non-blocking improvement | Default label for `followup_backlog_issues` |
