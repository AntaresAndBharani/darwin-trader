# Implementation Plan: Automated PR Review Auto-Merge, Self-Cancellation Prevention & Self-Healing Label Governance

**Branch**: `feat/003-pr-review-automerge` | **Date**: 2026-10-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-pr-review-automerge/spec.md`

## Summary

Resolve the four compounding CI/CD defects in `.github/workflows/pr-review.yml` and `.github/workflows/merge.yml` that prevented Pull Request #138 from auto-merging after Claude Opus 5.5 High review and auto-fix completion:
1. Consolidate the full review-to-merge and parent-story-closure lifecycle inside `.github/workflows/pr-review.yml` and delete `.github/workflows/merge.yml` so applying `review:approved` never triggers a competing workflow run.
2. Set `cancel-in-progress: false` on the `pr-review-<PR>` concurrency group so pushing an `[skip pr-review]` auto-fix commit with `ORCHESTRATION_PAT` queues behind the active run rather than self-cancelling it, and add a zero-token `merge_only=true` fast-path in `steps.meta` for open PRs whose `[skip pr-review]` commit already carries an `APPROVED` verdict comment.
3. Provision standard pipeline labels in the repository and idempotently ensure any required PR, story, or follow-up issue label exists via `gh label create <name> -R "$REPO" --force` before applying it.
4. Poll `CI` strictly by `--commit "$CURRENT_SHA"` (up to 60 attempts $\times$ 10s = 10 minutes), require an explicit `CI_PASSED="true"` gate before executing `gh pr merge`, and transition the PR to `review:changes-requested` with a diagnostic comment if CI fails or times out.

## Technical Context

**Language/Version**: YAML (GitHub Actions workflow syntax), Bash (`set -euo pipefail`), Python 3.11+ (inline workflow automation & `pytest` contract tests)

**Primary Dependencies**: GitHub Actions (`actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `anthropics/claude-code-action@v1`), GitHub CLI (`gh`), `jq`, `pytest`, `pyyaml`

**Storage**: N/A (stateless GitHub Actions workflow + GitHub PR comments/labels metadata)

**Testing**: `pytest` (`strategy_engine/tests/test_pr_review_workflow.py` + full backend/TUI/Web test suites)

**Target Platform**: GitHub Actions `ubuntu-latest` runners & local Windows/cross-platform test runners

**Project Type**: Full-stack algorithmic trading platform (`strategy_engine` + `api_gateway` + `tui` + `web` + `.github/workflows`)

**Performance Goals**: `merge_only` recovery path completes in `<30s` (when CI is already green) with `0` LLM tokens; pre-merge CI polling bounded to `<=10m` (`60 x 10s`)

**Constraints**: 100% deterministic offline unit/contract tests; idempotent GitHub label operations; zero duplicate merge runs

**Scale/Scope**: 1 unified PR review/merge workflow (`.github/workflows/pr-review.yml`), 1 retired workflow (`.github/workflows/merge.yml`), 1 new pytest contract test module (`strategy_engine/tests/test_pr_review_workflow.py`), and `CHANGELOG.md` update

## Constitution Check

*GATE: Checked before Phase 0 research and re-verified after Phase 1 design against Constitution v1.2.0.*

- **I. Clean Architecture & Pure Quantitative Core**: **PASS** — No domain, gateway, or client coupling is altered; changes are strictly scoped to `.github/workflows/` and offline test verification.
- **II. Darwinex Zero Risk & Capital Preservation**: **PASS** — Risk manager and kill-switch invariants are untouched.
- **III. Zero-Click Operational Readiness & Scoped Client Evolution**: **PASS** — TUI and Web startup and client workflows remain untouched.
- **IV. Test-First & Platform-Independent Simulation**: **PASS** — `strategy_engine/tests/test_pr_review_workflow.py` deterministically validates workflow structure, bash/python helper logic, `merge_only` routing, label self-healing, and exact-SHA CI gating completely offline.
- **V. Structured Concurrency, Lock Discipline & Observability**: **PASS** — Workflow concurrency is hardened with `cancel-in-progress: false` and explicit `CURRENT_SHA` commit isolation.
- **VI. Multi-Provider Data Isolation & Self-Contained Storage**: **PASS** — Database isolation is untouched.
- **Development Workflow & Quality Gates (Gate 4 — Remote CI, Automated PR Review & Auto-Merge Gate)**: **PASS** — Directly implements and enforces Gate 4 of Constitution v1.2.0.

## Project Structure

### Documentation (this feature)

```text
specs/003-pr-review-automerge/
├── plan.md                          # This file (/speckit-plan output)
├── research.md                      # Phase 0 output (/speckit-plan)
├── data-model.md                    # Phase 1 output (/speckit-plan)
├── quickstart.md                    # Phase 1 output (/speckit-plan)
├── contracts/
│   └── pr-review-workflow.md        # Phase 1 workflow contract (/speckit-plan)
├── checklists/
│   ├── requirements.md              # Spec quality checklist (/speckit-specify)
│   └── ci-workflow.md               # Domain requirements checklist (/speckit-checklist)
└── tasks.md                         # Phase 2 task list (/speckit-tasks)
```

### Source Code (repository root)

```text
.github/
└── workflows/
    ├── pr-review.yml                # MODIFIED: Unified review, auto-fix, label self-healing, merge_only fast-path, exact-SHA CI wait, squash-merge & story closure
    └── merge.yml                    # DELETED: Retired duplicate label-triggered merge workflow

strategy_engine/
└── tests/
    └── test_pr_review_workflow.py   # NEW: Deterministic unit & contract tests for pr-review.yml and helper logic

CHANGELOG.md                         # MODIFIED: Record fix under [Unreleased]
```

**Structure Decision**: Modifies `.github/workflows/pr-review.yml`, removes `.github/workflows/merge.yml`, and adds offline workflow contract tests under `strategy_engine/tests/test_pr_review_workflow.py` so the standard `pytest api_gateway/tests strategy_engine/tests tui/tests` CI gate automatically guards the workflow against regression.

## Complexity Tracking

No Constitution violations exist.
