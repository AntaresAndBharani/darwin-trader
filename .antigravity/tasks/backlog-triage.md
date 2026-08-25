# Backlog Triage — Antigravity scheduled task instructions (Darwin Trader)

Design: ws-setups/graph-engineering/docs/backlog-triage-node.md.

First run `git checkout main && git fetch origin && git reset --hard origin/main` so this checkout is current.

Process each backlog label independently (currently: `tech-debt`, `enhancement`):

For each label:
1. List open issues with that label (`gh issue list --state open --label <label>`).
2. Cluster issues by theme (shared component/file/module).
3. For each cluster: synthesize one `type:user-story` issue following the `user-story.yml` template, labeled `status:ready-for-architect` and `origin:backlog-triage`.
4. Close absorbed source issues with an explanatory comment: "Closed as absorbed and consolidated into parent story #<N>."
