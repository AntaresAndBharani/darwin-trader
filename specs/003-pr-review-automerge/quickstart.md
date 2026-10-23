# Quickstart & Validation Guide: Automated PR Review Auto-Merge

## Prerequisites

- Python 3.11+ with `pytest` and `pyyaml` installed.
- Node.js 20+ (`npm` in `web/`).
- GitHub CLI (`gh`) authenticated via `C:\Users\rogal\workspaces\Set-GhToken-Antares.ps1`.

## 1. Run Deterministic Offline Workflow Contract & Unit Tests

Verify the workflow structure, concurrency settings, `merge_only` fast-path logic, idempotent label creation, exact-SHA CI polling, and retirement of `merge.yml`:

```powershell
$env:PYTHONPATH = "."
python -m pytest api_gateway/tests strategy_engine/tests tui/tests
```

Expected outcome: All backend, TUI, and PR-review workflow contract tests pass (`100% green`).

## 2. Run Web Frontend Test, Lint & Build Suite

```powershell
Push-Location web
npm test
npm run lint
npm run build
Pop-Location
```

Expected outcome: All Vitest suites, ESLint checks, and TypeScript/Vite production builds succeed.

## 3. Verify Repository Labels Provisioned

```powershell
& C:\Users\rogal\workspaces\Set-GhToken-Antares.ps1
gh label list -R AntaresAndBharani/darwin-trader
```

Expected outcome: `review:approved`, `review:changes-requested`, `status:needs-po-input`, `status:ready`, `status:done`, and `tech-debt` are present in the repository label list.

## 4. End-to-End PR Auto-Merge Verification

1. Push `feat/003-pr-review-automerge` and open the Pull Request against `main`.
2. Observe `.github/workflows/pr-review.yml` execute on the Pull Request, apply `review:approved`, wait for `CI` (`build.yml`) on the exact head commit SHA, and squash-merge automatically.
3. For any stranded already-approved `[skip pr-review]` PR (such as PR #138), trigger:
   ```powershell
   gh workflow run pr-review.yml -R AntaresAndBharani/darwin-trader -f pr_number=138
   ```
   and verify it enters `merge_only=true` (0 LLM tokens) and squash-merges.
