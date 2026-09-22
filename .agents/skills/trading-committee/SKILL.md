---
name: trading-committee
description: >-
  Workspace trading committee deliberation skill powered by Gemini 3.8 Flash (High) and backed by a pure deterministic technical calculation engine. Orchestrates a 4-persona panel (Regime Follower, Price Action Specialist, Wave Analyst, and Chief Risk Officer) across a 4-stage workflow with a 3-round dispute resolution cap to emit standardized Committee Trading Cards. Trigger with /trading-committee.
---

# Trading Committee Workspace Skill (/trading-committee)

The **Trading Committee** is an autonomous multi-perspective technical deliberation skill for `darwin-trader`. It synthesizes quantitative indicators from the deterministic engine into a cohesive trading thesis governed by strict risk management rules.

---

## 1. Invocation & Interface

- **Slash Command:**
  ```text
  /trading-committee <SYMBOL> [--mode entry|exit] [--direction long|short] [--entry-price PRICE]
  ```
- **Recommended Model:** `gemini-3.8-flash-high` (Gemini 3.8 Flash with High reasoning effort).
- **Execution Step 1 (Deterministic CLI Briefing):**
  The skill initiates by executing the backend CLI tool to fetch mathematically verified market metrics without LLM arithmetic drift:
  ```powershell
  python -m strategy_engine.cli committee <SYMBOL> [--mode <MODE>] [--direction <DIRECTION>] [--entry-price <PRICE>] --format json
  ```
- **Timeframe Boundary (Phase 1):** Deliberations strictly ingest and evaluate D1 (Macro/Daily) and H1 (Hourly structure) rates. Multi-timeframe H4 analysis is deferred to Phase 2; personas must never hallucinate 4H data.

---

## 2. Four-Persona Deliberation Council

| Persona | Core Responsibility & Methodological Framework |
| :--- | :--- |
| **1. Regime Follower** | **Macro & Trend Analysis**: Stan Weinstein Stage Analysis (Stages 1 through 4), moving average slope/stacking (EMA 20, 50, 200), and benchmark beta / relative strength vs. SPY. Detects degraded states (`[REGIME: SHORT_HISTORY_DEGRADED]`, `[DATA_STALE]`). |
| **2. Price Action Specialist** | **Structural & Orderflow Analysis**: Rolling swing pivots ($k=5$ bars left/right), swing ceiling and floor, horizontal support & resistance, Fair Value Gaps (FVG), and 50-bin Volume Profile (VPOC, HVN, LVN). Evaluates liquidity sweeps and rejection wicks. |
| **3. Wave Analyst** | **Cycle & Fibonacci Analysis**: Elliott Wave counts (5-wave impulse sequences, 3-wave ABC corrective cycles), 60-bar Dominant Fibonacci anchor grid, retracements (0.382, 0.500, 0.618 golden pocket, 0.786), and extension targets (1.272, 1.618). |
| **4. Chief Risk Officer (CRO)** | **Arbitration & Risk Gatekeeper**: Enforces mandatory risk invariants. Strictly requires a minimum Risk/Reward (R:R) ratio of **1:2.0** to TP1. Enforces structural stop loss placement (beyond swing floor/ceiling). Arbitrates disputes with a mandatory veto cap. |

---

## 3. Four-Stage Deliberation Protocol

### Stage 1: Macro & Regime Scan
- The **Regime Follower** assesses the macro trend, moving average alignment, and benchmark relative strength from the `CommitteeContext`.
- Identifies whether the asset is in Stage 1 (Accumulation), Stage 2 (Markup), Stage 3 (Distribution), Stage 4 (Decline), or Choppy regime.

### Stage 2: Technical Cross-Examination
- The **Price Action Specialist** and **Wave Analyst** cross-examine structural levels.
- S&R floors and VPOC are compared against Fibonacci retracements (e.g., confluence between 50 EMA, VPOC, and 0.618 golden pocket).

### Stage 3: Scenario Evaluation
- **Mode A (New Entry)**: Evaluates prospective LONG or SHORT setup. Pinpoints the high-probability entry zone, structural stop loss, and take-profit targets.
- **Mode B (Position Audit & Exit)**: Evaluates an open position given `--entry-price`. Assesses whether major Fibonacci extension targets (1.618) or structural floors have broken; recommends `SCALE_OUT` (50% profit taking), `EXIT`, or trailing invalidation adjustments.

### Stage 4: CRO Synthesis & Hard Risk Gate (Dispute Resolution Cap)
- **Consensus Scoring**: Tallied across the 3 analytical personas (Regime, Price Action, Wave):
  - `3/3 Bullish / Bearish Confluence`: High-conviction alignment.
  - `2/3 Conditional Confluence`: Actionable setup contingent on specific trigger.
  - `1/3 Discordant`: Conflicting signals; triggers internal debate or veto.
- **3-Round Dispute Resolution Protocol**:
  - When personas disagree on direction or cycle count, up to a maximum of 3 structured exchange rounds are conducted within the deliberation prompt.
  - If consensus is not reached by Round 3, the Chief Risk Officer issues an immediate mandatory **"WAIT"** or **"PASS"** verdict.
- **Hard Risk Gate**:
  - Minimum R:R ratio threshold: $\ge 1:2.0$. If $R:R < 1:2.0$, the CRO vetoes the setup (`WAIT` or `PASS`), overriding analytical enthusiasm.
  - Stop loss must be anchored to structural invalidation (e.g., below swing floor for LONG, above swing ceiling for SHORT).

---

## 4. Standardized Output Contract: Committee Trading Card

The final response must strictly adhere to the following markdown template:

```markdown
### Committee Verdict: [ENTER / WAIT / EXIT / SCALE OUT / PASS]
- **Direction:** [LONG / SHORT / NEUTRAL]
- **Market Regime Alignment:** [STAGE_2_MARKUP / STAGE_4_DECLINE / STAGE_1_ACCUMULATION / STAGE_3_DISTRIBUTION / CHOPPY]
- **Consensus Score:** [3/3 Bullish Confluence | 2/3 Conditional | 1/3 Discordant (VETOED)] (Across 3 analytical personas; CRO acts as arbiter)
- **Data Health:** [PRISTINE | DATA_STALE | SHORT_HISTORY_DEGRADED | BENCHMARK_INSUFFICIENT_OVERLAP | BENCHMARK_UNCACHED]

#### Technical Summary
- **Trend & MAs:** Price $XXX.XX vs EMA20 ($XXX.XX), EMA50 ($XXX.XX), EMA200 ($XXX.XX)
- **Momentum & Volatility:** RSI(14) = XX.X | ATR(14) = $X.XX
- **Key Structure:** Swing Ceiling @ $XXX.XX | Swing Floor @ $XXX.XX | VPOC @ $XXX.XX
- **Elliott Wave / Cycle:** [e.g., Wave 4 consolidation into 0.618 golden pocket]

#### Action Plan
- **Entry Zone:** $XXX.XX - $XXX.XX (or specific condition; N/A if WAIT/PASS)
- **Hard Invalidation (Stop Loss):** $XXX.XX (Structural invalidation below/above swing pivot)
- **Take-Profit Targets:** TP1: $XXX.XX (Scale 50%) | TP2: $XXX.XX (Runner to Fib 1.618)
- **Calculated R:R Ratio:** 1 : X.X (Minimum threshold: 1 : 2.0; N/A if WAIT/PASS)
```
