---
description: "Task list for Yahoo Finance Strategy Lifecycle & Backtesting Control Panel"
---

# Tasks: Yahoo Finance Strategy Lifecycle & Backtesting Control Panel

**Input**: Design documents from `/specs/004-yahoo-strategy-lifecycle/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/yahoo-strategy-api.md

**Tests**: Automated Python (`pytest`) and Web (`vitest`) test tasks are included per Constitution Principle IV (`SC-004`).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Ensure the feature branch and Yahoo Finance baseline (`YahooFinanceDB`, `yahoo_fetcher.py`, `routes_yahoo.py`, `YahooWorkspace.tsx`) are synchronized on `feat/004-yahoo-strategy-lifecycle`.

- [X] T001 Create feature branch `feat/004-yahoo-strategy-lifecycle` and integrate the Yahoo Finance storage/API baseline (`strategy_engine/yahoo_db.py`, `strategy_engine/yahoo_fetcher.py`, `api_gateway/routes_yahoo.py`, `web/src/api/yahoo.ts`, `web/src/components/YahooWorkspace.tsx`)
- [X] T002 Extend `strategy_engine/config.py` and `strategy_engine/strategies/darwinx_zero_trader.py` to support configurable Quad-MA periods (`ema_period=21`, `sma_fast_period=50`, `sma_mid_period=100`, `sma_slow_period=200`) and 3-stage parameters (`stop_loss_pct=10.0`, `partial_tp_pct=5.0`, `partial_fraction=0.5`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core Yahoo Finance date-range queries and strategy catalog/backtest data models that block all user stories.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Add date-range and warm-up bar query support (`from_date`, `to_date`, `warmup_bars`) to `YahooFinanceDB.get_price_history_range` in `strategy_engine/yahoo_db.py`
- [X] T004 Create `strategy_engine/yahoo_backtester.py` with `StrategyParameterSpec`, `YahooStrategyDefinition`, `get_yahoo_strategies_catalog()`, and zero-lookahead Weekly (`W1`) Heikin-Ashi enrichment (`enrich_weekly_heikin_ashi`)

**Checkpoint**: Foundation ready - user story implementation can now proceed.

---

## Phase 3: User Story 1 - Single-Asset Strategy Backtesting & Parameter Tuning on Yahoo Finance Data (Priority: P1) 🎯 MVP

**Goal**: Enable single-asset historical backtesting for `darwin_trend` and `darwinx_zero_trader` with dynamic parameter overrides, mark-to-market accounting, and API endpoints exclusively on Yahoo Finance data.

**Independent Test**: Call `GET /api/v1/yahoo/strategies` and `POST /api/v1/yahoo/strategies/backtest` for a single ticker (`["AAPL"]`) with custom `strategy_params`, verifying MTM KPIs (`final_equity == initial_balance + realized_pnl + unrealized_pnl`), `equity_curve`, `trades`, and `latest_signal`.

### Tests for User Story 1

- [X] T005 [P] [US1] Write unit tests for single-asset `darwin_trend` and `darwinx_zero_trader` backtesting, parameter validation bounds (`fast_ema_period < slow_ema_period`, `rsi_oversold < rsi_overbought`, `initial_balance > 0`, `0.5 <= risk_per_trade_pct <= 100.0`), zero-lookahead W1 HA alignment, and MTM accounting invariants in `strategy_engine/tests/test_yahoo_backtester.py`
- [X] T006 [P] [US1] Write FastAPI contract tests for `GET /api/v1/yahoo/strategies` and single-asset `POST /api/v1/yahoo/strategies/backtest` (including 400 validation errors and Darwinex Zero MT5 isolation) in `api_gateway/tests/test_routes_yahoo.py`

### Implementation for User Story 1

- [X] T007 [US1] Implement `run_single_asset_yahoo_backtest` in `strategy_engine/yahoo_backtester.py` with capital-percentage sizing (`risk_per_trade_pct`), per-bar MTM equity (`balance + unrealized_pnl`), Sharpe/Sortino/Drawdown/Profit Factor calculation, and terminal open-position MTM accounting
- [X] T008 [US1] Implement `GET /api/v1/yahoo/strategies` and `POST /api/v1/yahoo/strategies/backtest` request/response Pydantic models (`YahooBacktestRequest` with `initial_balance > 0`, `risk_per_trade_pct` in `[0.5, 100.0]`, `timeframe` in `["D1", "W1", "MN1"]`) in `api_gateway/routes_yahoo.py`

**Checkpoint**: User Story 1 is functional and independently testable.

---

## Phase 4: User Story 2 - Multi-Asset & Sector Batch Backtesting with Drill-Down Comparison (Priority: P2)

**Goal**: Support running a strategy across multiple Yahoo Finance tickers or a whole Market/Sector filter, allocating `initial_balance / N` per valid asset, forward-filling MTM portfolio equity (`ffill().fillna(capital_k)`), and returning per-asset comparison summaries.

**Independent Test**: Execute `POST /api/v1/yahoo/strategies/backtest` with multiple symbols or a `sector` filter (including a symbol with `0` bars), verifying `NO_DATA` graceful handling, equal capital allocation across valid symbols, and aggregated `portfolio_metrics` + `portfolio_equity_curve`.

### Tests for User Story 2

- [X] T009 [P] [US2] Add multi-asset portfolio aggregation, `ffill().fillna(capital_k)` timeline alignment, and partial `NO_DATA` resilience tests in `strategy_engine/tests/test_yahoo_backtester.py`
- [X] T010 [P] [US2] Add multi-asset and sector-filter batch API tests in `api_gateway/tests/test_routes_yahoo.py`

### Implementation for User Story 2

- [X] T011 [US2] Implement `run_yahoo_portfolio_backtest` in `strategy_engine/yahoo_backtester.py` supporting explicit symbol lists and `market`/`sector` filter resolution, equal capital allocation (`initial_balance / N`), union date reindexing with `ffill().fillna(capital_k)`, and `YahooPortfolioBacktestResponse` assembly
- [X] T012 [US2] Add TypeScript types (`YahooStrategyDefinition`, `YahooBacktestRequest`, `YahooPortfolioBacktestResponse`) and client methods (`yahooApi.getStrategies()`, `yahooApi.runBacktest()`) in `web/src/api/yahoo.ts` and unit tests in `web/src/api/yahoo.test.ts`

**Checkpoint**: User Stories 1 and 2 are functional and independently testable.

---

## Phase 5: User Story 3 - Full-Screen Workspace Navigation & Interactive Chart Mode Switching (Priority: P3)

**Goal**: Deliver the full-screen `StrategyLifecycleWorkspace` component and promote it to a top-level **Strategy Lifecycle** tab in `web/src/App.tsx` (with the legacy `StrategySidebar` removed from the Darwinex MT5 tab).

**Independent Test**: Render `App` and `StrategyLifecycleWorkspace` in Vitest (`npm test`), verifying top-level tab navigation, single/multi-asset switching, dynamic parameter editing + Reset to Defaults, KPI cards, chart toggle (`Equity Curve` vs `Price & Trade Markers`), clickable Multi-Asset Comparison Table drill-down, and Trade Execution Log.

### Tests for User Story 3

- [X] T013 [P] [US3] Write comprehensive component tests for `StrategyLifecycleWorkspace` (asset mode switch, strategy switching, parameter editing, Reset to Defaults, Run Backtest, KPI cards, Equity/Price chart toggle, Multi-Asset Comparison row click drill-down, and Trade Log rendering) in `web/src/components/StrategyLifecycleWorkspace.test.tsx`
- [X] T014 [P] [US3] Update `web/src/App.test.tsx` to verify the 3 top-level workspace tabs (`Darwinex MT5`, `Yahoo Finance`, `Strategy Lifecycle`) and absence of the legacy `StrategySidebar` on the Darwinex MT5 tab

### Implementation for User Story 3

- [X] T015 [US3] Implement `web/src/components/StrategyLifecycleWorkspace.tsx` featuring the full Strategy Control Panel (Single/Batch Yahoo asset selector, Strategy selector, Dynamic Parameter Form with Reset to Defaults & Run Backtest), KPI Summary Cards, `lightweight-charts` canvas with Equity Curve / Price & Markers toggle, Multi-Asset Comparison Table with row drill-down, and Trade Execution Log table
- [X] T016 [US3] Update `web/src/App.tsx` to expose the three top-level workspace tabs (`darwinex`, `yahoo`, `strategy`) and render `StrategyLifecycleWorkspace` in full screen

**Checkpoint**: All user stories (US1, US2, US3) are complete and independently verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, architecture sync, changelog, and full-suite CI parity verification.

- [X] T017 [P] Update `CHANGELOG.md` under `## [Unreleased]`, `.graph/architecture.md`, and remove the temporary Sync Impact Report HTML comment from `.specify/memory/constitution.md`
- [X] T018 Run full backend and frontend verification (`pytest api_gateway/tests strategy_engine/tests tui/tests`, `npm test -- --run`, `npm run lint`, `npm run build`) per `specs/004-yahoo-strategy-lifecycle/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Starts immediately (`T001`–`T002`)
- **Foundational (Phase 2)**: Depends on Setup (`T003`–`T004`) — blocks all user stories
- **User Story 1 (Phase 3, P1 MVP)**: Depends on Phase 2 (`T005`–`T008`)
- **User Story 2 (Phase 4, P2)**: Depends on User Story 1 single-asset backtest core (`T009`–`T012`)
- **User Story 3 (Phase 5, P3)**: Depends on Phase 4 API client (`T013`–`T016`)
- **Polish (Phase 6)**: Depends on Phases 3–5 (`T017`–`T018`)

### Parallel Opportunities

- `T005` and `T006` (engine vs API tests for US1) can run in parallel.
- `T009` and `T010` (engine vs API tests for US2) can run in parallel.
- `T013` and `T014` (`StrategyLifecycleWorkspace.test.tsx` vs `App.test.tsx` for US3) can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Run US1 unit and API contract tests in parallel:
Task: "T005 [P] [US1] Write unit tests for single-asset darwin_trend and darwinx_zero_trader backtesting in strategy_engine/tests/test_yahoo_backtester.py"
Task: "T006 [P] [US1] Write FastAPI contract tests for GET /api/v1/yahoo/strategies and POST /api/v1/yahoo/strategies/backtest in api_gateway/tests/test_routes_yahoo.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (`T001`–`T002`)
2. Complete Phase 2: Foundational (`T003`–`T004`)
3. Complete Phase 3: User Story 1 (`T005`–`T008`)
4. **VALIDATE**: Verify single-asset Yahoo Finance backtesting via `pytest`

### Incremental Delivery

1. Setup + Foundational → Yahoo Finance price range & Weekly HA ready
2. Add User Story 1 → Single-asset parameterized backtesting + FastAPI routes ready
3. Add User Story 2 → Multi-asset & sector batch portfolio backtesting + frontend API client ready
4. Add User Story 3 → Full-screen `StrategyLifecycleWorkspace` & 3-tab `App.tsx` navigation ready
5. Complete Phase 6 → Full test suite, lint, build, changelog, and PR ready
