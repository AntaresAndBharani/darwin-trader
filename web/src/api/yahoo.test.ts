import { describe, it, expect, vi, beforeEach } from 'vitest';
import { yahooApi, YAHOO_SYNC_TIMEOUT_MS } from './yahoo';
import { apiClient } from './client';

describe('Yahoo API Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('calls GET /yahoo/strategies on getStrategies()', async () => {
    const mockCatalog = {
      data: {
        strategies: [
          {
            id: 'darwin_trend',
            name: 'Darwin Trend (EMA + RSI + ATR)',
            description: 'EMA crossover with RSI confirmation',
            parameters: [
              {
                key: 'fast_ema_period',
                label: 'Fast EMA Period',
                type: 'int' as const,
                default: 9,
                min: 2,
                max: 200,
                step: 1,
                description: 'Fast EMA lookback',
              },
            ],
          },
        ],
        shared_parameters: [],
      },
    };
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValueOnce(mockCatalog);

    const res = await yahooApi.getStrategies();

    expect(getSpy).toHaveBeenCalledWith('/yahoo/strategies');
    expect(res.strategies).toHaveLength(1);
    expect(res.strategies[0].id).toBe('darwin_trend');
  });

  it('calls POST /yahoo/strategies/backtest on runBacktest()', async () => {
    const mockBacktest = {
      data: {
        strategy_id: 'darwin_trend',
        strategy_name: 'Darwin Trend (EMA + RSI + ATR)',
        timeframe: 'D1',
        applied_params: { fast_ema_period: 12, slow_ema_period: 26 },
        total_assets: 1,
        valid_assets: 1,
        portfolio_metrics: {
          initial_balance: 10000,
          final_balance: 10500,
          final_equity: 10500,
          net_profit: 500,
          net_profit_pct: 5.0,
          realized_pnl: 500,
          realized_pnl_pct: 5.0,
          unrealized_pnl: 0,
          unrealized_pnl_pct: 0,
          total_trades: 3,
          winning_trades: 2,
          losing_trades: 1,
          win_rate_pct: 66.67,
          profit_factor: 2.5,
          max_drawdown: 120,
          max_drawdown_pct: 1.2,
          sharpe_ratio: 1.45,
          sortino_ratio: 2.1,
        },
        portfolio_equity_curve: [],
        asset_results: [],
      },
    };
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValueOnce(mockBacktest);

    const payload = {
      strategy_id: 'darwin_trend',
      symbols: ['AAPL'],
      timeframe: 'D1' as const,
      initial_balance: 10000,
      risk_per_trade_pct: 20,
      strategy_params: { fast_ema_period: 12, slow_ema_period: 26 },
    };

    const res = await yahooApi.runBacktest(payload);

    expect(postSpy).toHaveBeenCalledWith('/yahoo/strategies/backtest', payload, {
      timeout: YAHOO_SYNC_TIMEOUT_MS,
    });
    expect(res.portfolio_metrics.net_profit).toBe(500);
  });
});
