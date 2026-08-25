# Changelog

All notable changes to the Darwin Trader project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- **E2E Testing Framework with Maestro**:
  - Declarative E2E flows in `e2e/flows/` covering Dashboard metrics (`01_dashboard_flow.yaml`), Strategy parameters (`02_strategy_control_flow.yaml`), Backtest analytics (`03_backtest_analytics_flow.yaml`), and Navigation (`04_navigation_flow.yaml`).
  - Delta execution mapping (`e2e/flow-mapping.json`) mapping modified file globs across Android and Backend to targeted E2E tags.
  - Automated PowerShell test runner (`scripts/run-e2e-tests.ps1`) supporting `-Delta`, `-Tags`, `-CaptureArtifacts`, `-PushArtifacts`, auto-booting emulator, building snapshot APK, and generating summary reports.
  - Sticky PR evidence publisher (`scripts/post-e2e-evidence.ps1`) posting `<!-- e2e-evidence -->` markdown tables with pass/fail icons and screenshot links.
  - Unit test summarizer (`scripts/summarize-unit-tests.ps1`) parsing JUnit XML test results into sticky PR comments.
- **Agentic SDLC Pipeline (5-Node Graph)**:
  - Antigravity scheduled tasks (`.antigravity/tasks/dev-test.md`, `three-amigos.md`, `backlog-triage.md`).
  - Scoped agent personas (`.antigravity/agents/developer.md`, `tester.md`) and workspace rules (`.antigravity/rules.md`).
  - SMART GitHub issue templates (`.github/ISSUE_TEMPLATE/user-story.yml`, `subtask.yml`, `config.yml`).
  - Automated GitHub Actions workflows (`architect.yml`, `three-amigos.yml`, `dev-test.yml`, `pr-review.yml`, `merge.yml`) and prompt files in `.github/workflows/prompts/`.
- **Project Documentation & Rules**:
  - Created `GEMINI.md` defining development guidelines, quick commands, and Definition of Done.
  - Updated `README.md` with complete architecture, test commands, and pipeline documentation.
