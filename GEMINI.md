# Darwin Trader - Project Instructions & Context

## Project Overview
- **Application:** Darwin Trader — Algorithmic Trading Platform (Android Mobile Client + Python FastAPI Gateway + MetaTrader5 Strategy Engine).
- **Stack:**
  - **Android:** Android SDK 35, Kotlin (JVM 17), Jetpack Compose, Material 3, Retrofit, OkHttp.
  - **Backend:** Python 3.10+, FastAPI, MetaTrader5, Pandas, NumPy, pytest.
- **Build Tool:** Gradle Kotlin DSL (Use `.\gradlew.bat` in `android/` on Windows).

## Quick Commands
- **GitHub Token Setup:** `& C:\Users\rogal\workspaces\Set-GhToken-Antares.ps1` (Run before git push / gh commands)
- **Run Android Unit Tests:** `cd android; .\gradlew.bat testSnapshotDebugUnitTest --no-daemon; cd ..`
- **Run Backend Tests:** `pytest api_gateway/tests strategy_engine/tests`
- **Build Snapshot APK (CI Parity):** `cd android; .\gradlew.bat assembleSnapshot -PsnapshotLabel=localtest --no-daemon; cd ..`
- **Full Pre-PR Verification Suite:** `cd android; .\gradlew.bat testSnapshotDebugUnitTest assembleSnapshot -PsnapshotLabel=localtest --no-daemon; cd ..`
- **Run Targeted E2E Tests (Maestro):** `.\scripts\run-e2e-tests.ps1 -Delta`
- **Capture & Publish E2E Artifacts:** `.\scripts\run-e2e-tests.ps1 -CaptureArtifacts -Version "latest" -PushArtifacts`

## Core Development Guidelines
1. **Architecture:**
   - **Android:** MVVM with Unidirectional Data Flow (UDF). Composable -> ViewModel / ScreenState -> ApiService -> Retrofit.
   - **Backend:** Modular FastAPI routes (`routes_account.py`, `routes_strategy.py`) + Strategy Engine (`backtester.py`, `risk_manager.py`).
2. **Testing & CI Parity:** Prior to opening a PR, run the **Full Pre-PR Verification Suite** and ensure all local unit tests and delta E2E flows pass.
3. **E2E Visual Testing:** When modifying UI components in `android/app/src/main/java/**/ui/`, run targeted delta E2E flows (`.\scripts\run-e2e-tests.ps1 -Delta`) and capture visual artifacts to `docs/screenshots/`.
4. **Environment Isolation:** User-specific JVM paths belong in `~/.gradle/gradle.properties`. Never commit machine-specific paths into repository `gradle.properties`.
5. **Local APK Sync:** When building APKs, automatically copy the output APK to `local_test\latest.apk`.
6. **GitHub Permissions:** Always run `C:\Users\rogal\workspaces\Set-GhToken-Antares.ps1` for Git push and `gh` operations under the `AntaresAndBharani` organization.
7. **CI/CD Lifecycle & Definition of Done:**
   - **PR Workflow:** Opening/updating a PR builds the snapshot APK and updates the rolling `snapshot` pre-release on GitHub.
   - **Agent Completion Gate:** Development is only complete when local tests pass, delta E2E artifacts are captured, PR is opened, and remote CI checks pass (100% Green).

## Agentic SDLC Pipeline
The 5-node autonomous pipeline (Architect → Three Amigos → Dev & Test → PR Review → Merge & Backlog) runs across GitHub Actions and Antigravity Scheduled Tasks:

- **As PO, draft a User Story** with the `user-story.yml` issue template. Relabel `status:ready-for-architect` to hand off.
- **Label meanings:**
  - `status:definition` — PO drafting
  - `status:ready-for-architect` — PO says go; Architect decomposes into subtasks
  - `status:needs-po-input` — Architect / Dev escalation needing PO decision
  - `status:review` — Architect hands subtasks to Three Amigos for batch review
  - `status:needs-revision` / `status:needs-clarification` — Three Amigos feedback loop
  - `status:awaiting-approval` — Three Amigos internal clearance marker on subtasks
  - `status:ready` — Three Amigos auto-promotes story to ready; Dev & Test starts implementation
  - `status:done` — set automatically once all subtasks are closed; closes story
