import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { createSeriesMarkers } from 'lightweight-charts';
import { StrategyLifecycleWorkspace } from './StrategyLifecycleWorkspace';
import { yahooApi, YahooPortfolioBacktestResponse } from '../api/yahoo';
import { mockSeries, mockSeriesMarkers } from '../test/setup';

const mockTickersResponse = {
  total: 2,
  tickers: [
    {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      market: 'NASDAQ',
      sector: 'Technology',
      industry: 'Consumer Electronics',
      active: true,
      price_bars_count: 500,
    },
    {
      symbol: 'MSFT',
      name: 'Microsoft Corp.',
      market: 'NASDAQ',
      sector: 'Technology',
      industry: 'Software',
      active: true,
      price_bars_count: 500,
    },
  ],
  facets: {
    markets: ['NASDAQ', 'NYSE'],
    sectors: ['Technology', 'Healthcare'],
    industries: ['Consumer Electronics', 'Software'],
  },
};

const mockSingleBacktestResponse: YahooPortfolioBacktestResponse = {
  strategy_id: 'darwin_trend',
  strategy_name: 'Darwin Trend (EMA Crossover + RSI + ATR)',
  timeframe: 'D1',
  applied_params: {
    fast_ema_period: 12,
    slow_ema_period: 26,
    rsi_period: 14,
  },
  from_date: '2024-01-01',
  to_date: '2024-01-02',
  total_symbols_requested: 1,
  valid_symbols_count: 1,
  portfolio_metrics: {
    initial_balance: 10000,
    final_equity: 11400,
    net_profit: 1400,
    net_profit_pct: 14.0,
    realized_pnl: 1250,
    realized_pnl_pct: 12.5,
    unrealized_pnl: 150,
    unrealized_pnl_pct: 1.5,
    total_trades: 4,
    winning_trades: 3,
    losing_trades: 1,
    win_rate_pct: 75.0,
    profit_factor: 3.1,
    max_drawdown: 220,
    max_drawdown_pct: 2.1,
    sharpe_ratio: 1.85,
  },
  portfolio_equity_curve: [
    { time: 1704067200, date: '2024-01-01', balance: 10000, equity: 10000, drawdown_pct: 0 },
    { time: 1704153600, date: '2024-01-02', balance: 11250, equity: 11400, drawdown_pct: 0 },
  ],
  asset_results: [
    {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      market: 'NASDAQ',
      sector: 'Technology',
      status: 'READY',
      bars_count: 250,
      effective_from_date: '2024-01-01',
      effective_to_date: '2024-01-02',
      latest_signal: 'ENTER_LONG',
      latest_signal_reason: 'Bullish EMA Crossover (Fast=185.20 > Slow=182.10, RSI=58.4)',
      metrics: {
        initial_balance: 10000,
        final_equity: 11400,
        net_profit: 1400,
        net_profit_pct: 14.0,
        realized_pnl: 1250,
        realized_pnl_pct: 12.5,
        unrealized_pnl: 150,
        unrealized_pnl_pct: 1.5,
        total_trades: 4,
        winning_trades: 3,
        losing_trades: 1,
        win_rate_pct: 75.0,
        profit_factor: 3.1,
        max_drawdown: 220,
        max_drawdown_pct: 2.1,
        sharpe_ratio: 1.85,
      },
      equity_curve: [
        { time: 1704067200, date: '2024-01-01', balance: 10000, equity: 10000, drawdown_pct: 0 },
        { time: 1704153600, date: '2024-01-02', balance: 11250, equity: 11400, drawdown_pct: 0 },
      ],
      bars: [
        {
          time: 1704067200,
          date: '2024-01-01',
          open: 180,
          high: 185,
          low: 179,
          close: 184,
          volume: 1000000,
        },
        {
          time: 1704153600,
          date: '2024-01-02',
          open: 184,
          high: 192,
          low: 183,
          close: 190,
          volume: 1200000,
        },
      ],
      trades: [
        {
          symbol: 'AAPL',
          type: 'BUY',
          stage: 'CLOSED',
          entry_date: '2024-01-01',
          entry_time: 1704067200,
          entry_price: 180.0,
          exit_date: '2024-01-02',
          exit_time: 1704153600,
          exit_price: 190.0,
          units: 125.0,
          pnl: 1250.0,
          pnl_pct: 12.5,
          balance_after: 11250.0,
          reason: 'Take Profit Hit',
        },
        {
          symbol: 'AAPL',
          type: 'BUY',
          stage: 'FULL',
          entry_date: '2024-01-02',
          entry_time: 1704153600,
          entry_price: 188.5,
          exit_date: null,
          exit_time: null,
          exit_price: 190.0,
          units: 100.0,
          pnl: 150.0,
          pnl_pct: 0.8,
          balance_after: 11400.0,
          reason: 'Open Position (Marked to Market)',
        },
      ],
    },
  ],
};

const mockBatchBacktestResponse: YahooPortfolioBacktestResponse = {
  ...mockSingleBacktestResponse,
  total_symbols_requested: 2,
  valid_symbols_count: 2,
  portfolio_metrics: {
    ...mockSingleBacktestResponse.portfolio_metrics,
    net_profit: 2200,
    net_profit_pct: 22.0,
    final_equity: 12200,
  },
  asset_results: [
    mockSingleBacktestResponse.asset_results[0],
    {
      ...mockSingleBacktestResponse.asset_results[0],
      symbol: 'MSFT',
      name: 'Microsoft Corp.',
      latest_signal: 'HOLD',
      latest_signal_reason: 'No trend crossover',
      metrics: {
        ...mockSingleBacktestResponse.asset_results[0].metrics,
        initial_balance: 5000,
        final_equity: 5800,
        net_profit: 800,
        net_profit_pct: 16.0,
      },
      trades: [
        {
          symbol: 'MSFT',
          type: 'BUY',
          stage: 'CLOSED',
          entry_date: '2024-01-01',
          entry_time: 1704067200,
          entry_price: 370.0,
          exit_date: '2024-01-02',
          exit_time: 1704153600,
          exit_price: 386.0,
          units: 50.0,
          pnl: 800.0,
          pnl_pct: 16.0,
          balance_after: 5800.0,
          reason: 'Take Profit Hit',
        },
      ],
    },
  ],
};

describe('StrategyLifecycleWorkspace', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockSeries.setData.mockClear();
    mockSeriesMarkers.setMarkers.mockClear();

    vi.spyOn(yahooApi, 'getTickers').mockResolvedValue(mockTickersResponse);
    vi.spyOn(yahooApi, 'getStrategies').mockResolvedValue({
      strategies: [],
    });
  });

  it('loads Yahoo tickers, switches strategies, edits parameters, and resets to defaults', async () => {
    render(<StrategyLifecycleWorkspace />);

    await waitFor(() => {
      expect(yahooApi.getTickers).toHaveBeenCalledWith({ active_only: true });
      expect(screen.getByTestId('strategy-single-ticker-select')).toHaveValue('AAPL');
    });

    // Verify Darwin Trend parameters are rendered by default
    const fastEmaInput = screen.getByTestId('strategy-param-fast_ema_period') as HTMLInputElement;
    expect(fastEmaInput.value).toBe('12');

    // Edit Fast EMA and Initial Balance
    fireEvent.change(fastEmaInput, { target: { value: '15' } });
    expect(fastEmaInput.value).toBe('15');

    const balanceInput = screen.getByTestId('param-initial_balance') as HTMLInputElement;
    fireEvent.change(balanceInput, { target: { value: '25000' } });
    expect(balanceInput.value).toBe('25000');

    // Switch strategy to DarwinX Zero Trader
    const strategySelect = screen.getByTestId('strategy-selector');
    fireEvent.change(strategySelect, { target: { value: 'darwinx_zero_trader' } });

    const stopLossInput = screen.getByTestId('strategy-param-stop_loss_pct') as HTMLInputElement;
    expect(stopLossInput.value).toBe('10');

    fireEvent.change(stopLossInput, { target: { value: '14' } });
    expect(stopLossInput.value).toBe('14');

    // Click Reset to Defaults
    fireEvent.click(screen.getByTestId('strategy-reset-defaults-btn'));
    expect(stopLossInput.value).toBe('10');
    expect(balanceInput.value).toBe('10000');
  });

  it('executes a single-asset backtest, renders KPIs & trade log, and toggles Equity Curve vs Price & Markers chart', async () => {
    const runBacktestSpy = vi
      .spyOn(yahooApi, 'runBacktest')
      .mockResolvedValue(mockSingleBacktestResponse);

    render(<StrategyLifecycleWorkspace />);

    await waitFor(() => {
      expect(screen.getByTestId('strategy-single-ticker-select')).toHaveValue('AAPL');
    });

    // Customize Fast EMA period before running
    const fastEmaInput = screen.getByTestId('strategy-param-fast_ema_period');
    fireEvent.change(fastEmaInput, { target: { value: '12' } });

    fireEvent.click(screen.getByTestId('strategy-run-backtest-btn'));

    await waitFor(() => {
      expect(runBacktestSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          strategy_id: 'darwin_trend',
          symbols: ['AAPL'],
          timeframe: 'D1',
          initial_balance: 10000,
          risk_per_trade_pct: 20,
          strategy_params: expect.objectContaining({
            fast_ema_period: 12,
          }),
        }),
      );
    });

    // Verify KPI Cards
    expect(screen.getByTestId('kpi-net-profit')).toHaveTextContent('$1,400.00');
    expect(screen.getByTestId('kpi-net-profit')).toHaveTextContent('+14.00%');
    expect(screen.getByTestId('kpi-final-equity')).toHaveTextContent('$11,400.00');
    expect(screen.getByTestId('kpi-win-rate')).toHaveTextContent('75.0%');
    expect(screen.getByTestId('kpi-profit-factor')).toHaveTextContent('3.10');
    expect(screen.getByTestId('kpi-latest-signal')).toHaveTextContent('ENTER_LONG');
    expect(screen.getByTestId('kpi-sharpe-ratio')).toHaveTextContent('1.85');

    // Verify Equity Curve was plotted on chart
    expect(mockSeries.setData).toHaveBeenCalledWith([
      { time: 1704067200, value: 10000 },
      { time: 1704153600, value: 11400 },
    ]);

    // Switch chart mode to Price & Trade Markers
    mockSeries.setData.mockClear();
    fireEvent.click(screen.getByTestId('chart-mode-price-btn'));

    await waitFor(() => {
      expect(mockSeries.setData).toHaveBeenCalledWith([
        { time: 1704067200, open: 180, high: 185, low: 179, close: 184 },
        { time: 1704153600, open: 184, high: 192, low: 183, close: 190 },
      ]);
    });

    // Toggle Heikin-Ashi in Price mode
    fireEvent.click(screen.getByTestId('strategy-chart-ha-toggle'));
    expect(screen.getByTestId('strategy-chart-ha-toggle')).toHaveTextContent('Heikin-Ashi: ON');

    // Entry markers for both trades plus an exit marker only for the closed one
    const markerCalls = vi.mocked(createSeriesMarkers).mock.calls;
    const latestMarkers = markerCalls[markerCalls.length - 1][1] as Array<{ shape: string }>;
    expect(latestMarkers.filter((m) => m.shape === 'arrowUp')).toHaveLength(2);
    expect(latestMarkers.filter((m) => m.shape === 'circle')).toHaveLength(1);

    // Verify Trade Execution Log renders the closed AAPL trade and the still-open position
    const tradeLog = screen.getByTestId('strategy-trade-log-table');
    expect(tradeLog).toHaveTextContent('Take Profit Hit');
    expect(tradeLog).toHaveTextContent('Open Position (Marked to Market)');
    expect(tradeLog).toHaveTextContent('Open');
  });

  it('supports Multi-Asset batch backtesting and drills down into a clicked ticker row in the comparison table', async () => {
    const runBacktestSpy = vi
      .spyOn(yahooApi, 'runBacktest')
      .mockResolvedValue(mockBatchBacktestResponse);

    render(<StrategyLifecycleWorkspace />);

    await waitFor(() => {
      expect(screen.getByTestId('mode-batch-btn')).toBeInTheDocument();
    });

    // Switch to Multi-Asset / Sector mode
    fireEvent.click(screen.getByTestId('mode-batch-btn'));
    fireEvent.click(screen.getByTestId('strategy-run-backtest-btn'));

    await waitFor(() => {
      expect(runBacktestSpy).toHaveBeenCalled();
      expect(screen.getByTestId('strategy-active-scope-label')).toHaveTextContent(
        'Portfolio Aggregate (2/2 Active Tickers)',
      );
      expect(screen.getByTestId('kpi-net-profit')).toHaveTextContent('$2,200.00');
    });

    // Click MSFT row in the Multi-Asset Comparison Table to drill down
    fireEvent.click(screen.getByTestId('comparison-row-MSFT'));

    await waitFor(() => {
      expect(screen.getByTestId('strategy-active-scope-label')).toHaveTextContent(
        'MSFT (Microsoft Corp.)',
      );
      expect(screen.getByTestId('kpi-net-profit')).toHaveTextContent('$800.00');
    });

    // Return to Portfolio Aggregate view
    fireEvent.click(screen.getByTestId('strategy-view-portfolio-btn'));
    expect(screen.getByTestId('strategy-active-scope-label')).toHaveTextContent(
      'Portfolio Aggregate',
    );
  });
});
