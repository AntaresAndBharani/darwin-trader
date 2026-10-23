# Tasks: Automated PR Review Auto-Merge, Self-Cancellation Prevention & Self-Healing Label Governance

**Input**: Design documents from `/specs/003-pr-review-automerge/`

**Prerequisites**: `plan.md` (required), `spec.md` (required for user stories), `research.md`, `data-model.md`, `contracts/pr-review-workflow.md`

**Tests**: Included per Constitution Principle IV (Test-First & Platform-Independent Simulation) to deterministically validate the workflow contract offline.

**Organization**: Tasks are grouped by user story (`US1`, `US2`, `US3`) to enable independent implementation and verification of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (`[US1]`, `[US2]`, `[US3]`)
- Exact file paths are included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Provision repository labels and establish the offline workflow contract test harness.

- [X] T001 Provision standard pipeline labels (`review:approved` `#0E8A16`, `review:changes-requested` `#D93F0B`, `status:needs-po-input` `#B60205`, `status:ready` `#0E8A16`, `status:done` `#0E8A16`, `tech-debt` `#FBCA04`) in `AntaresAndBharani/darwin-trader` via `gh label create --force`
- [X] T002 [P] Create workflow contract test module scaffold in `strategy_engine/tests/test_pr_review_workflow.py` to load and inspect `.github/workflows/pr-review.yml`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Retire competing merge workflow and establish non-cancelling concurrency in `.github/workflows/pr-review.yml`.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Delete `.github/workflows/merge.yml` so `review:approved` label events never spawn a duplicate competing merge workflow (`FR-008`, `SC-004`)
- [X] T004 Update top-level concurrency block in `.github/workflows/pr-review.yml` to `group: pr-review-${{ github.event.pull_request.number || inputs.pr_number }}` with `cancel-in-progress: false` (`FR-001`)

**Checkpoint**: Competing workflow retired and self-cancellation disabled.

---

## Phase 3: User Story 1 - End-to-End Automated Review, Fix, and Merge Without Self-Cancellation (Priority: P1) 🎯 MVP

**Goal**: Ensure full review runs that apply auto-fixes idempotently create required labels (`review:approved`, `review:changes-requested`, `status:needs-po-input`, `status:done`, `tech-debt`), file all `followup_backlog_issues`, squash-merge the PR, and close completed parent stories without crashing (`FR-001`, `FR-003`, `FR-004`, `FR-007`, `SC-001`).

**Independent Test**: Run `pytest strategy_engine/tests/test_pr_review_workflow.py -k "us1"` to verify concurrency configuration, idempotent label creation before `gh pr edit` and `gh issue create`, follow-up backlog issue creation resilience, and post-merge parent-story closure logic.

### Tests for User Story 1

- [X] T005 [P] [US1] Add unit/contract tests in `strategy_engine/tests/test_pr_review_workflow.py` verifying `cancel-in-progress: false`, idempotent `gh label create ... --force` helper before `gh pr edit` and `gh issue create`, `followup_backlog_issues` creation, and post-merge parent story closure (`status:done`)

### Implementation for User Story 1

- [X] T006 [US1] Implement idempotent label creation (`gh label create "status:needs-po-input" -R "$REPO" --color "B60205" --description "Escalated to Product Owner after max review rounds" --force || true`) in `steps.meta` of `.github/workflows/pr-review.yml` (`FR-003`)
- [X] T007 [US1] Implement `Commit auto-fixes, apply verdict, and prepare merge` (`id: verdict_step`) in `.github/workflows/pr-review.yml` with an inline Python `ensure_label(repo, name, color, description)` helper that runs `gh label create <name> -R <repo> --color <color> --description <description> --force` before applying `review:approved` (`0E8A16`) or `review:changes-requested` (`D93F0B`) (`verdict` constrained to `"APPROVED"` | `"CHANGES_REQUESTED"`) and before creating each item in `followup_backlog_issues` (`FR-003`, `FR-004`)
- [X] T008 [US1] Migrate and harden the `Close the parent story once every subtask is done` step into `.github/workflows/pr-review.yml` after the merge step, ensuring `status:done` (`0E8A16`) exists via `gh label create --force` before closing the parent story when `OPEN_SIBLINGS == 0` (`FR-007`)

**Checkpoint**: User Story 1 is functional and covered by offline contract tests.

---

## Phase 4: User Story 2 - Zero-Cost Recovery Merge for Approved Auto-Fix Commits (Priority: P2)

**Goal**: Provide a zero-LLM-token `merge_only` fast-path in `.github/workflows/pr-review.yml` when an open PR's latest commit contains `[skip pr-review]` and its most recent `<!-- pr-review-verdict -->` comment contains `APPROVED` (`FR-002`, `SC-002`).

**Independent Test**: Run `pytest strategy_engine/tests/test_pr_review_workflow.py -k "us2"` to verify `steps.meta` routing (`skip` constrained to `'true'` | `'false'`, `merge_only` constrained to `'true'` | `'false'`), conditional skipping of checkout/Python/Node/Claude steps when `merge_only == 'true'`, and fast-path execution in `verdict_step`.

### Tests for User Story 2

- [X] T009 [P] [US2] Add unit/contract tests in `strategy_engine/tests/test_pr_review_workflow.py` verifying `steps.meta` sets `merge_only=true` and `skip=false` when `LAST_MSG` contains `[skip pr-review]` and latest `<!-- pr-review-verdict -->` comment contains `APPROVED`, sets `skip=true` when not `APPROVED`, and guards environment/Claude steps with `steps.meta.outputs.merge_only != 'true'`

### Implementation for User Story 2

- [X] T010 [US2] Update `Check PR state, loop cap, and skip markers` (`id: meta`) in `.github/workflows/pr-review.yml` to inspect the latest `<!-- pr-review-verdict -->` comment when `LAST_MSG` contains `[skip pr-review]` and emit `skip` (`'true'` | `'false'`) and `merge_only` (`'true'` | `'false'`) to `$GITHUB_OUTPUT` (`FR-002`)
- [X] T011 [US2] Guard `Checkout PR branch`, `Set up Python 3.11`, `Install Python dependencies`, `Set up Node.js 20`, `Install Frontend dependencies`, `Fetch PR context`, and `Run PR Review & Auto-Fix (Claude Opus 5.5 High)` in `.github/workflows/pr-review.yml` with `steps.meta.outputs.skip != 'true' && steps.meta.outputs.merge_only != 'true'`, and add the `merge_only == 'true'` branch in `steps.verdict_step` (`FR-002`, `SC-002`)

**Checkpoint**: User Stories 1 and 2 are functional and covered by offline contract tests.

---

## Phase 5: User Story 3 - Exact-Commit Verification Gating & Single-Workflow Ownership (Priority: P3)

**Goal**: Poll `CI` strictly for `--commit "$CURRENT_SHA"` up to 60 attempts (10s interval), require an explicit `CI_PASSED="true"` gate before `gh pr merge`, and transition the PR to `review:changes-requested` with a diagnostic comment if `CI` fails or times out (`FR-005`, `FR-006`, `FR-008`, `SC-003`, `SC-004`).

**Independent Test**: Run `pytest strategy_engine/tests/test_pr_review_workflow.py -k "us3"` to verify `--commit "$CURRENT_SHA"` filtering, `CI_PASSED="true"` gating, `review:changes-requested` fallback on CI failure/timeout, and absence of `.github/workflows/merge.yml`.

### Tests for User Story 3

- [X] T012 [P] [US3] Add unit/contract tests in `strategy_engine/tests/test_pr_review_workflow.py` verifying `--commit "$CURRENT_SHA"` CI polling (60 iterations), explicit `CI_PASSED="true"` gate, `review:changes-requested` transition + diagnostic PR comment on CI failure/timeout, and deletion of `.github/workflows/merge.yml`

### Implementation for User Story 3

- [X] T013 [US3] Implement `Wait for CI on target commit and auto-merge` (`id: merge_step`) in `.github/workflows/pr-review.yml` polling `gh run list -R "$REPO" --commit "$CURRENT_SHA" -w "CI" -L 1 --json status,conclusion` for up to 60 attempts (10s sleep), gating `gh pr merge "$PR_NUMBER" -R "$REPO" --squash --delete-branch` on `CI_PASSED="true"`, and transitioning to `review:changes-requested` with a diagnostic comment when `CI_PASSED != "true"` (`FR-005`, `FR-006`)

**Checkpoint**: All user stories (`US1`, `US2`, `US3`) are complete and independently tested.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final documentation, constitution cleanup, and full-suite regression verification.

- [X] T014 Remove the temporary `Sync Impact Report` HTML comment from `.specify/memory/constitution.md` prior to commit per `/speckit-constitution` rules
- [X] T015 [P] Update `CHANGELOG.md` under `## [Unreleased]` with the automated PR review auto-merge, self-cancellation prevention, `merge_only` fast-path, and self-healing label fix
- [X] T016 Run full backend, TUI, workflow contract, and Web verification suites (`pytest api_gateway/tests strategy_engine/tests tui/tests` and `npm test`, `npm run lint`, `npm run build` in `web/`) per `specs/003-pr-review-automerge/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup — blocks all User Stories.
- **User Stories (Phase 3–5)**:
  - **User Story 1 (P1)**: Starts immediately after Phase 2.
  - **User Story 2 (P2)**: Builds on `steps.meta` and `steps.verdict_step` in `.github/workflows/pr-review.yml`.
  - **User Story 3 (P3)**: Builds on `steps.verdict_step` outputs (`verdict`, `current_sha`) in `.github/workflows/pr-review.yml`.
- **Polish (Phase 6)**: Depends on Phases 3–5 completion.

### Parallel Opportunities

- `T001` (GitHub label provisioning) and `T002` (test scaffold creation) can run in parallel.
- Test authoring tasks `T005`, `T009`, and `T012` in `strategy_engine/tests/test_pr_review_workflow.py` can be developed together before validating against `.github/workflows/pr-review.yml`.
- `T014` (`.specify/memory/constitution.md`) and `T015` (`CHANGELOG.md`) touch independent files and can run in parallel.

---

## Parallel Example: User Story 1–3 Contract Tests

```bash
# Run all PR review workflow contract tests together:
python -m pytest strategy_engine/tests/test_pr_review_workflow.py -v
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1: self-cancellation disabled, self-healing labels, follow-up issues, and story closure).
3. Validate with `pytest strategy_engine/tests/test_pr_review_workflow.py`.

### Incremental Delivery

1. Add User Story 2 (`merge_only` zero-token recovery fast-path for `[skip pr-review]` PRs).
2. Add User Story 3 (strict `--commit "$CURRENT_SHA"` CI verification gate and failure fallback).
3. Complete Phase 6 (constitution cleanup, `CHANGELOG.md`, and full Python + Web test suite).
