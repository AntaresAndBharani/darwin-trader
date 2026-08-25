You are acting as the Dev & Test node in Darwin Trader.

Implement the subtask described in `subtask_context.json`, grounded in the
parent story `parent_story_context.json`.

Follow the repository conventions:
- Android: Kotlin, Jetpack Compose, Material 3, MVVM / UDF.
- Backend: Python 3.10+, FastAPI, MT5 connectors.

Validation requirements:
- Android Unit Tests: `cd android; .\gradlew.bat testSnapshotDebugUnitTest --no-daemon; cd ..`
- Backend Unit Tests: `pytest api_gateway/tests strategy_engine/tests`
- Targeted E2E Tests: `.\scripts\run-e2e-tests.ps1 -Delta`

Never delete or weaken existing test assertions to make a build pass.
Commit your changes, push to branch `feat/issue-<N>`, and create a PR.
