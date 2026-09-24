# 📋 Implementation Plan & Refinement Lifecycle: Complete Decommissioning of Android Mobile App, CI/CD Workflows, and Test Suites

## 📝 Initial Draft Proposal (Operator Requisite)

- **Source Requirement:** `docs/draft-requisites/archive/impl_mobile_removal.md`
> "I want to remove everything related to the mobile app, including workflows and CI checks.
> This is because I'm not longer using that app, I'm using the tui instead.
> Remember this is something that mustn't impact in the current TUI functionality at all, so some refactoring could be needed."

---

## 🔍 Review Iteration 1: 3-Amigos Critical Architectural Review
- **Date / Author:** 2026-09-24 | Author Agent & 3-Amigos Review Panel
- **Scope:** Technical decoupling, zero-regression on TUI and Backend, CI/CD pipeline integrity, and local pipeline script maintenance.

### 1. Ground Truth Codebase Inspection & Footprint Analysis
An exhaustive inventory of the mobile footprint in `darwin-trader` reveals:
1. **Target Directories for Complete Removal:**
   - `android/`: Entire Android project (Jetpack Compose UI, ViewModel, Gradle wrapper, Android SDK 35 build files, JUnit unit tests, resources).
   - `e2e/`: Maestro Android E2E flows (`e2e/flows/*.yaml`, `flow-mapping.json`).
   - `local_test/`: Android local test APK outputs (`latest.apk`, `summary.json`).
2. **CI/CD Workflow Modifications (`.github/workflows/`):**
   - `.github/workflows/build.yml`: Currently runs Python backend/TUI tests, then sets up JDK 17, Gradle, runs Android unit tests (`testSnapshotDebugUnitTest`), summarizes Android unit tests via `summarize-unit-tests.ps1`, builds snapshot APK (`assembleSnapshot`), uploads APK artifact, and publishes rolling `snapshot` pre-release with the APK.
     - *Transformation:* Must be streamlined into a pure Python CI workflow running `pytest api_gateway/tests strategy_engine/tests tui/tests` and lint checks. Remove all Java/Gradle/Android steps and APK artifact uploads.
   - `.github/workflows/release.yml`: Pure Android APK release workflow (`assembleProd`, publishes APK on tag `v*`).
     - *Transformation:* Remove or archive. Release workflow will no longer build or attach APK files.
3. **Scripts to Remove / Refactor (`scripts/`):**
   - `scripts/run-e2e-tests.ps1`: Maestro Android runner (checks ADB, launches emulator, builds APK, executes Maestro flows). Remove.
   - `scripts/post-e2e-evidence.ps1`: Posts Android Maestro screenshot evidence to PRs. Remove.
   - `scripts/summarize-unit-tests.ps1`: Parses Android JUnit XML test results from `android/app/build/test-results`. Remove.
   - `scripts/local-pipeline/run-three-amigos-and-dev-test.ps1`: Lines 413-427 explicitly execute `android\gradlew.bat testSnapshotDebugUnitTest`. If `android/` is deleted without refactoring this script, any rebase check in the local pipeline scheduler will fail with a fatal file-not-found error.
     - *Transformation:* Remove the Android test execution block; keep and enforce the Python backend and TUI test execution (`pytest`).
4. **Backend & TUI Decoupling Verification:**
   - `api_gateway/main.py`: Contains comments/descriptions mentioning "Android Mobile App" (lines 16, 20, 47). Purely cosmetic; no functional imports or hard dependencies on `android/`.
   - `tui/`: Standalone Textual application communicating over HTTP REST / WebSocket with `api_gateway`. Zero dependencies on Android code.
   - Current Python test baseline: 145/145 tests pass cleanly (`pytest api_gateway/tests strategy_engine/tests tui/tests`).
5. **Documentation & Config Alignment:**
   - `GEMINI.md`: Full of Android references (SDK 35, Jetpack Compose, `gradlew.bat`, snapshot APK builds, Maestro E2E, APK sync). Must be cleaned to document pure Python TUI, FastAPI Gateway, and MetaTrader 5 Strategy Engine.
   - `README.md`: Architecture diagram and testing instructions prominently feature the Android app. Must be updated to feature the Terminal User Interface (TUI).
   - `.gitignore`: Contains numerous Android/Gradle specific ignore lines (`.gradle/`, `android/`, `local.properties`, `captures/`, `.externalNativeBuild/`, `*.apk`, `*.aab`, etc.). Needs cleanup.

### 2. Point-by-Point Critical Verdict Matrix

| Proposal Item | Analysis & Risk Assessment | Verdict |
| :--- | :--- | :--- |
| **1. Deletion of `android/` directory** | Contains 100+ Kotlin/Gradle files. Completely isolated from Python runtime. Verified: No python module imports or references anything in `android/`. | **APPROVED** |
| **2. Deletion of `e2e/` & `local_test/`** | Contains Maestro Android UI flows and APK scratch files. Obsolete with no Android app. | **APPROVED** |
| **3. Deletion of obsolete mobile scripts** | `run-e2e-tests.ps1`, `post-e2e-evidence.ps1`, `summarize-unit-tests.ps1`. Removing them eliminates dead code and prevents accidental invocation. | **APPROVED** |
| **4. Refactoring `run-three-amigos-and-dev-test.ps1`** | **CRITICAL:** Lines 413-427 must be cleanly modified to eliminate the `android\gradlew.bat` call. Failure to do so would break the autonomous agent pipeline. | **APPROVED (MANDATORY)** |
| **5. Streamlining `.github/workflows/build.yml`** | Remove JDK 17, Gradle setup, keystore creation, Android test execution, APK compilation, and APK release attachment. CI must strictly validate Python tests (`api_gateway`, `strategy_engine`, `tui`) with 100% green gate. | **APPROVED** |
| **6. Deletion of `.github/workflows/release.yml`** | Workflow is dedicated exclusively to building `assembleProd` APK. Since no APK exists, workflow is removed. | **APPROVED** |
| **7. Updating `GEMINI.md` & `README.md`** | Aligns project documentation with the active architecture (TUI + FastAPI + Strategy Engine). Prevents future agents from attempting to run Android gradle commands. | **APPROVED** |
| **8. Cleaning `.gitignore` and `api_gateway/main.py`** | Cosmetic docstring updates and removing dead Android ignore entries. | **APPROVED** |

### 3. Edge Cases & Resilience Strategy
- **Autonomous Pipeline Task Execution:** The scheduled local pipeline script `run-three-amigos-and-dev-test.ps1` runs in the background. Ensuring it only invokes `pytest` guarantees uninterrupted local pipeline autonomy.
- **GitHub Actions Pre-PR / PR Checks:** The GitHub Actions workflow must complete with a green check status on pull requests so that the Definition of Done (DoD) is satisfied without waiting for nonexistent APK builds.
- **TUI Regression Invariant:** TUI test suite (`tui/tests/test_tui.py`) must continue to run in CI and locally with 100% pass rate.

---

## 🧪 Claude QA Review Iteration 1 (Requirements & UX/UI Guardian)

### 🎯 Requirements Fidelity & Scope Alignment Audit
- Operator's three core invariants — (1) remove everything mobile-related including workflows/CI, (2) motivated by TUI being the only client now, (3) zero impact on TUI functionality — are all traceable into the Final Decision Plan's Component Impact Table and Scenario 4. No dilution of the core deliverable detected.
- Verified against the live codebase:
  - `scripts/local-pipeline/run-three-amigos-and-dev-test.ps1` lines 413-416/421-422 invoke `android\gradlew.bat testSnapshotDebugUnitTest`.
  - `.github/workflows/build.yml` sets up JDK 17/Gradle, runs `testSnapshotDebugUnitTest`, builds `assembleSnapshot`, and uploads APK.
  - `.github/workflows/release.yml` exists and is APK-only.
  - `api_gateway/main.py` contains Android references at lines 16, 20, and 47.
- **Gap found:** `.antigravity/rules.md` and `.antigravity/agents/tester.md` (and `.antigravity/tasks/*.md`) hard-code Android/Gradle/Maestro tooling as authoritative instructions for the repo's own autonomous agent pipeline.

### 🚨 Objections
1. **[BLOCKING]** `.antigravity/rules.md` and `.antigravity/agents/tester.md` (and `.antigravity/tasks/*.md`) are not included in the Component Impact Table or INVEST slices. Must be added before implementation.
2. **[NON-BLOCKING]** Ground Truth Inspection understates `api_gateway/main.py`'s Android references (cites lines 16/20, actual is 16/20/47).
3. **[NON-BLOCKING]** Scenario 3 / Slice 2 should explicitly state that the streamlined `build.yml`'s pytest step must remain a hard gate (no `continue-on-error`, no soft-fail).

### 🏁 Verdict
VERDICT: DISAGREED

---

## 🔍 Review Iteration 2 (Author Response & Scope Expansion)
- **Date / Author:** 2026-09-24 | Author Agent (Antigravity)
- Added `.antigravity/rules.md`, `.antigravity/agents/*.md`, and `.antigravity/tasks/*.md` to Component Impact Table, Slice 2, and Scenario 6.
- Acknowledged `api_gateway/main.py` line 47 and mandated hard-gated CI in `build.yml`.

---

## 🏛️ Architect Review Iteration 2

- **Date / Reviewer:** 2026-09-24 | Principal Architect (Claude Opus 5.5)
- **Critique:** The author's audit only covered `.antigravity/`. Live CI prompt files, local pipeline Claude task files, and issue templates also mandate Android/Gradle/Maestro and will break automated runs:
  - `.github/workflows/prompts/{dev-test-implement,dev-test-fixup,architect-decompose,pr-review,three-amigos}.md`
  - `.claude/tasks/{architect-decompose,architect-restructure,pr-review,three-amigos-judge}.md`
  - `.github/ISSUE_TEMPLATE/{subtask,user-story}.yml`
- **Objections:**
  1. **[BLOCKING]** Missing `.github/workflows/prompts/*.md`, `.claude/tasks/*.md`, and `.github/ISSUE_TEMPLATE/*.yml` in Impact Table and Slice 2.
  2. **[NON-BLOCKING]** Scenario 4 hard-codes 145 tests; should require full suite passes with 0 failures/errors and $\ge$ pre-change baseline.
  3. **[NON-BLOCKING]** Specific wording on `run-three-amigos-and-dev-test.ps1`: add `tui/tests`, drop `$androidTests` from failure checks (L421-422) and update `.SYNOPSIS`.
  4. **[NON-BLOCKING]** Update `.graph/architecture.md` (Android-centric diagrams and tree).
  5. **[NON-BLOCKING]** Operational check: check branch protection names before renaming `build.yml` job, and manually delete stale GitHub `snapshot` pre-release and tag.
- **Verdict:** VERDICT: DISAGREED

---

## 🧪 Claude QA Review Iteration 2 (Requirements & UX/UI Guardian)

- **Date / Reviewer:** 2026-09-24 | QA Lead & Requirements Guardian (Claude Sonnet)
- **Critique & Objections:**
  1. **[BLOCKING]** Concurs with Architect Objection 1: Component Impact Table and Slice 2 must cover `.github/workflows/prompts/*.md`, `.claude/tasks/*.md`, and `.github/ISSUE_TEMPLATE/{subtask,user-story}.yml`.
  2. **[NON-BLOCKING]** Concurs with re-wording Scenario 4 test count to avoid brittle fixed integer.
  3. **[NON-BLOCKING]** Add atomicity note: Slice 1 and Slice 2 land together in the same PR/commit.
  4. **[NON-BLOCKING]** Specifically name `$androidTests` removal in `run-three-amigos-and-dev-test.ps1`.
- **Verdict:** VERDICT: DISAGREED

---

## 🔍 Review Iteration 3 (Author Comprehensive Synthesis)
- **Date / Author:** 2026-09-24 | Author Agent (Antigravity)
- **Status:** Responding to Architect and Claude QA Round 2 Objections — Complete Scope Convergence

### 1. Full Resolution of Architect & QA Objection 1 (Complete Prompt & Template Surface)
The author conducted an exhaustive, repo-wide sweep and added the entire agent instruction, CI prompt, Claude task, issue template, and architecture graph surface to the plan:
1. **GitHub Actions Workflow Prompts:**
   - `.github/workflows/prompts/dev-test-implement.md`: Remove Android tech stack, Gradle test commands, `run-e2e-tests.ps1`, `post-e2e-evidence.ps1`; enforce pytest.
   - `.github/workflows/prompts/dev-test-fixup.md`: Remove Android unit tests and delta E2E test commands.
   - `.github/workflows/prompts/architect-decompose.md`: Remove Android conventions and `e2e/` structure guidance.
   - `.github/workflows/prompts/pr-review.md`: Remove `<!-- e2e-evidence -->` Maestro screenshot checklist requirement.
   - `.github/workflows/prompts/three-amigos.md`: Remove `e2e_tags` from subtask specification.
2. **Claude Pipeline Task Instructions (`.claude/tasks/`):**
   - `.claude/tasks/architect-decompose.md`: Remove Android and Maestro decomposition rules.
   - `.claude/tasks/architect-restructure.md`: Remove Android guidelines.
   - `.claude/tasks/pr-review.md`: Remove E2E screenshot checks.
   - `.claude/tasks/three-amigos-judge.md`: Remove E2E test tag requirements.
3. **GitHub Issue Templates (`.github/ISSUE_TEMPLATE/`):**
   - `.github/ISSUE_TEMPLATE/subtask.yml`: Remove Android file examples, Gradle commands, and `run-e2e-tests.ps1` from template prompts.
   - `.github/ISSUE_TEMPLATE/user-story.yml`: Remove Android architecture options and Maestro verification steps.
4. **Architectural Graph Context (`.graph/`):**
   - `.graph/architecture.md`: Replace Android Jetpack Compose diagrams, directory trees, and tech-stack tables with the TUI + FastAPI + MT5 architecture.

### 2. Resolution of Non-Blocking Recommendations
1. **Local Pipeline Script Precision (`run-three-amigos-and-dev-test.ps1`):**
   - Explicitly update L22 `.SYNOPSIS` to state "Runs Python test suite across api_gateway, strategy_engine, and tui."
   - Explicitly expand L419 to include `tui/tests`: `python.exe -m pytest api_gateway/tests strategy_engine/tests tui/tests`.
   - Explicitly remove `$androidTests` invocation (L413-416), remove `$androidTests.ExitCode -ne 0` condition from L421, and remove Android references from L422 log output.
2. **Brittle Test Count Generalization (Scenario 4):**
   - Reworded Scenario 4 to require that the full test suite (`api_gateway`, `strategy_engine`, `tui`) passes with **0 failures and 0 errors**, and the total collected test count is $\ge$ the pre-change baseline ($\ge 145$ tests).
3. **Single Atomic Commit / PR Invariant:**
   - Mandated that Slice 1 (deletions) and Slice 2 (workflow, prompt, script, and documentation updates) must land **together in a single atomic commit and PR**, guaranteeing the automated CI and local pipelines never enter a broken intermediate state.
4. **CI Workflow & Job Name Protection:**
   - Preserved `name: Build APK & CI` and `jobs: build:` in `.github/workflows/build.yml` (or verified against branch protection) to prevent PR check starvation, while internally purging all Android/Gradle/APK steps.
5. **Repo-Wide Cleanliness Gate (New Scenario 7):**
   - Formulated an automated, machine-checkable `git grep` acceptance scenario asserting 0 occurrences of mobile tooling outside of `CHANGELOG.md` and `docs/draft-requisites/archive/`.

---

## 🎯 Final Decision Plan & User Story Specification
- **Status:** ✅ **APPROVED BY ARCHITECT & QA CONSENSUS** (Dual Consensus Reached)

### User Story: Decommission Android Mobile App & Workflows
**As a** algorithmic trader and maintainer of Darwin Trader,  
**I want** to completely decommission and remove the legacy Android mobile app, its build systems, Maestro E2E test suites, Android CI/CD workflows, CI/local agent prompts, and issue templates,  
**So that** the entire repository, automated SDLC pipeline, and agent governance are lightweight, dedicated purely to the Python TUI, FastAPI Gateway, and Strategy Engine, with zero dangling mobile references and zero risk of pipeline failure.

---

### BDD Acceptance Criteria (Gherkin)

#### Scenario 1: Clean Removal of Android and Mobile Test Directories
```gherkin
Given the Darwin Trader repository
When the mobile removal is executed
Then the directories `android/`, `e2e/`, and `local_test/` no longer exist on disk or in git tracking
And the scripts `scripts/run-e2e-tests.ps1`, `scripts/post-e2e-evidence.ps1`, and `scripts/summarize-unit-tests.ps1` are removed
And `.github/workflows/release.yml` is deleted.
```

#### Scenario 2: Local Pipeline Script Refactoring & Comprehensive Pytest Execution
```gherkin
Given the local pipeline script `scripts/local-pipeline/run-three-amigos-and-dev-test.ps1`
When an automated rebase and test check is performed
Then it executes `python.exe -m pytest api_gateway/tests strategy_engine/tests tui/tests`
And it contains no references to `$androidTests`, `$androidGradle`, or `gradlew.bat`
And the script successfully completes without file-not-found or undefined variable errors.
```

#### Scenario 3: Hard-Gated Python CI Workflow Verification
```gherkin
Given a push or pull request to the repository
When the GitHub Actions `build.yml` workflow triggers
Then it sets up Python 3.11, installs dependencies, and runs `pytest api_gateway/tests strategy_engine/tests tui/tests` as a hard gate (no continue-on-error)
And it completes with a passing green check without configuring JDK, Gradle, or building APK files
And the workflow and job names preserve branch protection compatibility.
```

#### Scenario 4: Preserved TUI and Backend Health (Zero Regression)
```gherkin
Given the complete removal of mobile artifacts
When running `pytest api_gateway/tests strategy_engine/tests tui/tests` locally
Then the full test suite passes with 0 failures and 0 errors, with total collected tests >= the 145 baseline
And the TUI launcher `run-tui.ps1` launches the Textual interface without errors.
```

#### Scenario 5: Documentation & Guideline Modernization
```gherkin
Given the updated repository
When reviewing `README.md`, `GEMINI.md`, `.graph/architecture.md`, and `.gitignore`
Then the documentation and architecture diagrams accurately describe the Python TUI + FastAPI + MT5 Strategy Engine architecture
And all references to Android SDK, Gradle, APK releases, and Maestro are removed.
```

#### Scenario 6: CI Prompts, Claude Tasks, Issue Templates & Agent Rules Alignment
```gherkin
Given the repository agent governance and CI prompt files
When inspecting `.antigravity/rules.md`, `.antigravity/agents/*.md`, `.antigravity/tasks/*.md`, `.github/workflows/prompts/*.md`, `.claude/tasks/*.md`, and `.github/ISSUE_TEMPLATE/*.yml`
Then all instructions to author or run Android unit tests, Gradle commands, Maestro E2E test flows, and APK targets are removed
And all agent instructions reflect development and verification strictly via Python pytest across `api_gateway`, `strategy_engine`, and `tui`.
```

#### Scenario 7: Objective Repo-Wide Zero-Dangling-Mobile Cleanliness Gate
```gherkin
Given the completed changes in git working tree
When running `git grep -i -E "gradlew|maestro|run-e2e-tests|post-e2e-evidence|summarize-unit-tests|android/app|local_test" -- :^CHANGELOG.md :^docs/draft-requisites/archive :^docs/draft-requisites/implementation-plan.md`
Then the command exits with code 1 (0 matches found outside CHANGELOG, plan, and archive).
```

---

### Component Impact Table

| Component / Path | Action | Description |
| :--- | :--- | :--- |
| `android/` | **DELETE** | Entire Android application source code, gradle wrappers, build scripts, tests. |
| `e2e/` | **DELETE** | Maestro flows, flow mappings, and Android E2E artifacts. |
| `local_test/` | **DELETE** | Local APK builds and test summary artifacts. |
| `scripts/run-e2e-tests.ps1` | **DELETE** | Maestro Android test runner script. |
| `scripts/post-e2e-evidence.ps1` | **DELETE** | Maestro screenshot PR commenting script. |
| `scripts/summarize-unit-tests.ps1` | **DELETE** | Android JUnit XML summarizer script. |
| `.github/workflows/release.yml` | **DELETE** | Prod APK release workflow. |
| `.github/workflows/build.yml` | **MODIFY** | Streamline to pure Python CI (hard-gated pytest backend & TUI); drop JDK, Gradle, APK packaging/release; preserve job/workflow names for branch protection. |
| `.github/workflows/dev-test.yml` | **MODIFY** | Purge obsolete `Set up JDK 17` step (L27-31). |
| `scripts/local-pipeline/run-three-amigos-and-dev-test.ps1` | **MODIFY** | Update synopsis, add `tui/tests` to pytest command, remove `$androidTests` and Android log statements. |
| `api_gateway/main.py` | **MODIFY** | Update docstrings/comments at lines 16, 20, and 47 to reflect TUI / Web client connectivity. |
| `README.md` | **MODIFY** | Replace Android architecture diagram and build steps with TUI dashboard guide and pytest instructions. |
| `GEMINI.md` | **MODIFY** | Replace Android SDK, Gradle, and Maestro guidelines with TUI & Python standards. |
| `.gitignore` | **MODIFY** | Remove obsolete Android, Gradle, and keystore ignore rules. |
| `.graph/architecture.md` | **MODIFY** | Update architecture diagrams, directory tree, and tech stack tables to remove Android. |
| `.antigravity/rules.md` | **MODIFY** | Remove Android tech stack, Gradle test/build commands, Maestro runner, and APK target. |
| `.antigravity/agents/developer.md` | **MODIFY** | Remove Android Compose, MVVM/UDF, and delta E2E instructions; focus on Python TUI & backend. |
| `.antigravity/agents/tester.md` | **MODIFY** | Remove Android unit test and Maestro flow authoring responsibilities; focus on pytest & TUI tests. |
| `.antigravity/tasks/*.md` | **MODIFY** | Refactor `backlog-triage.md`, `dev-test-fixup.md`, `dev-test-implement.md`, `dev-test.md`, and `three-amigos.md` to remove Gradle/Maestro/E2E steps. |
| `.github/workflows/prompts/*.md` | **MODIFY** | Refactor `dev-test-implement.md`, `dev-test-fixup.md`, `architect-decompose.md`, `pr-review.md`, and `three-amigos.md` to remove Android/Maestro/E2E requirements. |
| `.claude/tasks/*.md` | **MODIFY** | Refactor `architect-decompose.md`, `architect-restructure.md`, `pr-review.md`, and `three-amigos-judge.md` to remove Android/E2E instructions. |
| `.github/ISSUE_TEMPLATE/*.yml` | **MODIFY** | Refactor `subtask.yml` and `user-story.yml` to remove Android path examples and Gradle/Maestro verification commands. |

---

### INVEST Subtask Breakdown

- **Slice 1 (Codebase & Script Deletion):**
  - Delete directory `android/`
  - Delete directory `e2e/`
  - Delete directory `local_test/`
  - Delete `scripts/run-e2e-tests.ps1`
  - Delete `scripts/post-e2e-evidence.ps1`
  - Delete `scripts/summarize-unit-tests.ps1`
  - Delete `.github/workflows/release.yml`

- **Slice 2 (Pipeline, Workflow, Agent Governance, Prompts & Documentation Alignment):**
  - Refactor `scripts/local-pipeline/run-three-amigos-and-dev-test.ps1`:
    - Update synopsis on L22 to reference Python test suites.
    - Add `tui/tests` to pytest execution on L419.
    - Remove `$androidGradle`, `$androidDir`, and `$androidTests` invocation (L413-416).
    - Update L421 to check only `$pythonTests.ExitCode -ne 0` and remove Android from L422 log.
  - Refactor `.github/workflows/build.yml` into a lightweight, hard-gated Python CI workflow (Python 3.11, pytest across `api_gateway`, `strategy_engine`, `tui`; drop JDK, Gradle, APK steps; retain workflow/job names).
  - Refactor `.github/workflows/dev-test.yml` to remove the obsolete `Set up JDK 17` step (L27-31).
  - Clean `api_gateway/main.py` docstrings/comments at lines 16, 20, 47.
  - Update `README.md`, `GEMINI.md`, `.graph/architecture.md`, and `.gitignore` to reflect the pure Python TUI & Gateway architecture.
  - Refactor agent rules and task prompts in `.antigravity/`:
    - `.antigravity/rules.md`
    - `.antigravity/agents/{developer,tester}.md`
    - `.antigravity/tasks/{backlog-triage,dev-test-fixup,dev-test-implement,dev-test,three-amigos}.md`
  - Refactor CI workflow prompts in `.github/workflows/prompts/`:
    - `dev-test-implement.md`, `dev-test-fixup.md`, `architect-decompose.md`, `pr-review.md`, `three-amigos.md`
  - Refactor Claude task prompts in `.claude/tasks/`:
    - `architect-decompose.md`, `architect-restructure.md`, `pr-review.md`, `three-amigos-judge.md`
  - Refactor issue templates in `.github/ISSUE_TEMPLATE/`:
    - `subtask.yml`, `user-story.yml`
  - Run local test suite (`pytest`) to confirm 100% green pass ($\ge 145$ tests, 0 failures, 0 errors).
  - Run repo-wide grep verification (`git grep -i -E "gradlew|maestro|run-e2e-tests|post-e2e-evidence|summarize-unit-tests|android/app|local_test" -- :^CHANGELOG.md :^docs/draft-requisites/archive :^docs/draft-requisites/implementation-plan.md`) to verify 0 remaining matches outside `CHANGELOG.md`, `docs/draft-requisites/archive`, and the plan itself.

*(Note: Slices 1 and 2 must land atomically in the same commit/PR to avoid transient pipeline breakage).*

---

## 🏛️ Architect Review Iteration 3

- **Date / Reviewer:** 2026-09-24 | Principal Architect (Claude Opus 5.5)
- **Scope verified against codebase:** I ran Scenario 7's `git grep` against the current tree, grepped every `.github/workflows/*.yml` for JDK/Gradle/APK/E2E usage, and checked the line-number claims in `api_gateway/main.py` and `scripts/local-pipeline/run-three-amigos-and-dev-test.ps1`.

### ⚖️ Architecture & Drawbacks Critique

- **Round 2 BLOCKING objection is resolved.** The Impact Table, Slice 2 and Scenario 6 now name every file that the round 2 review flagged: `.github/workflows/prompts/{dev-test-implement,dev-test-fixup,architect-decompose,pr-review,three-amigos}.md`, `.claude/tasks/{architect-decompose,architect-restructure,pr-review,three-amigos-judge}.md`, and `.github/ISSUE_TEMPLATE/{subtask,user-story}.yml`. `.graph/architecture.md` has been added too. Apart from the two items below, every file that the current mobile grep matches is either planned for deletion or listed for modification.
- **Line-number claims are accurate.** `main.py` L16/L20/L47 contain the three Android references. In `run-three-amigos-and-dev-test.ps1`, L22 is the synopsis, L413–416 invoke `$androidTests`, L419 runs pytest without `tui/tests`, and L421–422 hold the combined exit check and the log line. `tui/tests/test_tui.py` exists, so adding `tui/tests` to the pytest command is valid.
- **Race conditions / intermediate states:** Landing Slice 1 and Slice 2 in a single commit/PR removes the window where CI or the local pipeline would call a deleted `gradlew.bat` or `run-e2e-tests.ps1`. No runtime concurrency is involved, since this is a deletion and config change.
- **Backward compatibility:** `build.yml` keeps its workflow and job names, so required status checks are preserved. The TUI, gateway and engine have no import or runtime dependency on `android/`, `e2e/` or `local_test/`. Scenario 4, a full-suite hard gate at or above the baseline, adequately protects the operator's "mustn't impact TUI" constraint.
- **Performance:** CI gets faster because the JDK, Gradle and APK steps are removed.
- **Residual gaps (both minor, neither breaks anything):**
  1. `.github/workflows/dev-test.yml` L27–31 still sets up JDK 17 (`actions/setup-java@v4`). This step exists only for Gradle. The plan never mentions it, and Scenario 7's regex can't catch it. It's dead weight rather than a failure, but it's left-over "mobile CI" that the operator asked to remove.
  2. As written, Scenario 7 can't pass. `docs/draft-requisites/implementation-plan.md` (tracked, and currently modified in the working tree) matches the regex on lines 20, 21, 23, 28 and 29 because it describes the removal itself. The pathspec only excludes `CHANGELOG.md` and `docs/draft-requisites/archive`, so the gate would exit 0 (matches found) instead of 1.

### 🚨 Objections

1. **[NON-BLOCKING]** Scenario 7 always fails as written: `docs/draft-requisites/implementation-plan.md` matches the regex. Either archive that doc into `docs/draft-requisites/archive/` before running the gate, or add `:^docs/draft-requisites/implementation-plan.md` to the pathspec in both Scenario 7 and the Slice 2 verification step. The criterion can still be tested and the fix is mechanical, so this isn't blocking. Still, fix it before implementation so the dev agent doesn't loosen the gate on its own judgement.
2. **[NON-BLOCKING]** Add `.github/workflows/dev-test.yml` to the Impact Table and Slice 2 so the "Set up JDK 17" step (L27–31) gets removed. Optionally, add `setup-java` to the Scenario 7 regex so the gate catches it.
3. **[NON-BLOCKING]** Scenario 7's regex misses `e2e-evidence`, `e2e_tags` and bare `android` / `apk` terms, which appear in `prompts/pr-review.md`, `prompts/three-amigos.md` and `prompts/dev-test-fixup.md`. Scenario 6 still covers those files, but adding `e2e-evidence|e2e_tags|setup-java|assembleSnapshot` would make the gate cover the whole surface.
4. **[NON-BLOCKING]** Scenario 4 says "≥ the 145 baseline". Record the actual pre-change `pytest --collect-only -q` count at implementation time instead of trusting the hard-coded number. This carries over from round 2 and is mostly addressed.
5. **[NON-BLOCKING]** Carried over from round 2 (operational, not code): after merge, manually delete the stale GitHub `snapshot` pre-release and tag.

### 🛠️ Required Changes

None. There are no BLOCKING objections. I strongly recommend applying objections 1 and 2 during implementation, since each is a one-line plan edit.

### 🏁 Verdict

The round 2 blocking scope gap is closed, the plan's code-location claims are accurate, the atomic-landing rule removes the risk of a broken intermediate pipeline state, and the TUI zero-regression requirement is covered by a hard-gated full test suite. The remaining items are gate hygiene and one omitted JDK setup step. Neither would ship a wrong or unsafe result.

VERDICT: AGREED


## 🏛️ Architect Review Iteration 3` to the end of the plan.

- **VERDICT: AGREED.** There are no blocking objections.
- **Round 2's blocking gap is fixed.** The plan now covers all the CI prompt files, Claude task files and issue templates it was missing, plus `.graph/architecture.md`. The line numbers it gives for `api_gateway/main.py` and `run-three-amigos-and-dev-test.ps1` all match the actual code.
- **Scenario 7 will fail as written (non-blocking).** `docs/draft-requisites/implementation-plan.md` matches the search pattern, so the check finds hits and fails. The plan should either archive that file first or exclude it from the check, so the implementing agent doesn't loosen the check on its own.
- **One mobile CI step is missing from the plan (non-blocking).** `.github/workflows/dev-test.yml` (lines 27–31) still sets up JDK 17 only for Gradle. It breaks nothing, but it's leftover mobile CI the operator asked to remove. It should be added to the Impact Table and Slice 2.
- **Other non-blocking notes:**
  - Widen the Scenario 7 search pattern to include `e2e-evidence`, `e2e_tags`, `setup-java` and `assembleSnapshot`.
  - Record the real test count before the change rather than relying on the hard-coded 145.
  - After merging, manually delete the stale GitHub `snapshot` pre-release and its tag.

---

## 🧪 QA Review Iteration 3 (Requirements & UX/UI Guardian)

- **Date / Reviewer:** 2026-09-24 | QA Lead & Requirements Guardian (Claude Sonnet / Gemini QA Lead)
- **Scope Verified:** Requirements fidelity against Operator Requisite, TUI experience & zero-regression invariants, functional pipeline rigor, and BDD testability.

### 🎯 Requirements Fidelity & Scope Alignment Audit
- **Operator Requisite Alignment:** The operator's core requirement is unambiguous: complete removal of everything related to the mobile app (including workflows and CI checks) while guaranteeing zero impact on current TUI functionality.
- **Round 2 Scope Resolution:** The author has fully incorporated the previously missing governance surfaces:
  - All CI workflow prompts (`.github/workflows/prompts/*.md`) and Claude pipeline task instructions (`.claude/tasks/*.md`).
  - GitHub issue templates (`.github/ISSUE_TEMPLATE/{subtask,user-story}.yml`).
  - System architecture graph (`.graph/architecture.md`).
- **Residual Workflow Finding:** `.github/workflows/dev-test.yml` still contains a 5-line `Set up JDK 17` step (L27-31) that was originally introduced for mobile Gradle tasks. While leaving it does not break python-only dev-test jobs, purging it aligns with the operator's directive to remove all mobile CI leftovers.

### 🖥️ UX/UI & Functional Rigor Review
- **TUI Zero-Regression Assurance:**
  - The TUI has zero code or package dependencies on `android/`, `e2e/`, or `local_test/`.
  - Expanding the local pipeline runner (`scripts/local-pipeline/run-three-amigos-and-dev-test.ps1` L419) to explicitly include `tui/tests` alongside backend tests materially improves TUI regression protection.
  - Scenario 4 enforces a non-negotiable pass on the complete suite with $\ge 145$ tests and 0 failures/errors, plus execution of the `run-tui.ps1` launcher.
- **Developer Experience & Templates:**
  - Replacing Android-centric placeholders in `.github/ISSUE_TEMPLATE/subtask.yml` and `user-story.yml` eliminates cognitive friction and stops the inadvertent generation of mobile subtasks.
- **Failure Modes & Pipeline Atomicity:**
  - The atomic landing constraint (Slices 1 and 2 merged concurrently in a single PR/commit) prevents intermediate broken builds where scripts call nonexistent gradle wrappers or test runners.
  - Retaining GitHub workflow and job names (`name: Build APK & CI`, `jobs: build:`) in `.github/workflows/build.yml` protects branch protection status checks from failing closed.

### 🚨 Objections (each tagged [BLOCKING] or [NON-BLOCKING])
1. **[NON-BLOCKING] Scenario 7 Cleanliness Gate Pathspec Exclusion:**
   - As flagged by the Architect, `docs/draft-requisites/implementation-plan.md` matches the grep regex (mentioning `gradlew`, `android/app`, etc.) and will cause Scenario 7 to exit with code 0 instead of 1.
   - *Remediation:* During execution of Slice 2, either archive `docs/draft-requisites/implementation-plan.md` into `docs/draft-requisites/archive/` or add `:^docs/draft-requisites/implementation-plan.md` to the pathspec in Scenario 7.
2. **[NON-BLOCKING] Purge JDK 17 Step in `.github/workflows/dev-test.yml`:**
   - Remove lines 27-31 (`Set up JDK 17`) in `.github/workflows/dev-test.yml` during Slice 2, ensuring no dead-weight mobile build tooling remains in CI.
3. **[NON-BLOCKING] Pre-change Dynamic Test Count Baseline:**
   - Run `pytest --collect-only -q` immediately before refactoring to establish the authoritative minimum baseline rather than relying on a static integer.

### 🧪 Acceptance Criteria & Testability Assessment
- **BDD Coverage:** Scenarios 1 through 7 comprehensively cover happy paths, file cleanup, script refactoring, CI hard gating, zero-regression on TUI, and repo cleanliness.
- **Clarity & Determinism:** All acceptance criteria are machine-verifiable via exit codes (`git grep`, `pytest`, PowerShell script exit codes) without ambiguous human-interpretation loopholes.

### 🏁 Verdict

The Final Decision Plan completely satisfies the operator's requirements and resolves all Round 2 blocking issues. The TUI experience and SDLC pipeline are rigorously protected against regressions. The remaining minor findings are non-blocking hygiene items that can be trivially applied during implementation.

VERDICT: AGREED
