# Darwin Trader Workspace Rules

- **Tech Stack:** Android (Kotlin, Jetpack Compose, Material 3, Retrofit, OkHttp) + Python 3.10+ (FastAPI, MetaTrader5).
- **Android Test Command:** `.\gradlew.bat testSnapshotDebugUnitTest --no-daemon` (under `android/`)
- **Backend Test Command:** `pytest api_gateway/tests strategy_engine/tests`
- **Build Snapshot Command:** `.\gradlew.bat assembleSnapshot -PsnapshotLabel=localtest --no-daemon` (under `android/`)
- **E2E Test Command:** `.\scripts\run-e2e-tests.ps1 -Delta`
- **APK Target:** `local_test\latest.apk`
- For full details, see [GEMINI.md](file:///c:/Users/rogal/workspaces/ws-trading/darwin-trader/GEMINI.md) and [.antigravity/](file:///c:/Users/rogal/workspaces/ws-trading/darwin-trader/.antigravity).
