# Three Amigos — Antigravity scheduled task instructions (Darwin Trader)

Design: ws-setups/graph-engineering/docs/three-amigos-node.md.

First run `git checkout main && git fetch origin && git reset --hard origin/main` so this checkout is current.

Check darwin-trader for open issues labeled `type:user-story` AND `status:review`.

For each matching story:
1. Fetch all child subtasks via `gh api repos/<repo>/issues/<story>/sub_issues`.
2. Evaluate Product, Developer, and QA perspectives across the whole batch.
   - QA analysis: verify acceptance criteria testability, generate Given/When/Then BDD scenarios, and verify unit and integration test coverage across pytest test suites (`api_gateway/tests`, `strategy_engine/tests`, `tui/tests`).
3. If READY:
   - Post human-readable review summary comment on the parent story and child subtasks.
   - Label subtasks `status:awaiting-approval` and remove prior review labels.
   - Relabel parent story `status:ready` (removes `status:review`).
4. If NEEDS_REVISION / NEEDS_CLARIFICATION:
   - Relabel accordingly (`status:needs-revision` or `status:needs-clarification`) and comment with specific feedback for Architect.
