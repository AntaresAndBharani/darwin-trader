import { apiClient } from './client';

export interface YahooTicker {
  symbol: string;
  name: string;
  market: string;
  sector: string;
  industry: string;
  active: boolean;
  created_at?: string;
  price_bars_count?: number;
  min_date?: string | null;
  max_date?: string | null;
}

export interface YahooFilterFacets {
  markets: string[];
  sectors: string[];
  industries: string[];
}

export interface YahooTickersListResponse {
  total: number;
  tickers: YahooTicker[];
  facets: YahooFilterFacets;
}

export interface YahooPriceBar {
  time: number;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface YahooHistoryResponse {
  symbol: string;
  timeframe: string;
  total_bars: number;
  bars: YahooPriceBar[];
}

export interface YahooValuationRow {
  as_of_date: string;
  period_type: string;
  trailing_pe: number | null;
  forward_pe: number | null;
  pb: number | null;
  ps: number | null;
  peg: number | null;
  ev_ebitda: number | null;
  ev_revenue: number | null;
  market_cap: number | null;
  enterprise_value: number | null;
  dividend_yield: number | null;
  updated_at?: string;
}

export interface YahooQuarterlyEarningRow {
  date: string;
  quarterly_eps: number | null;
  quarterly_revenue: number | null;
}

export interface YahooFundamentalsResponse {
  symbol: string;
  ticker: YahooTicker | null;
  latest_valuation: YahooValuationRow | null;
  valuation_history: YahooValuationRow[];
  quarterly_earnings: YahooQuarterlyEarningRow[];
}

export interface YahooSyncStatusResponse {
  status: 'IDLE' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED';
  total_tickers: number;
  completed_tickers: number;
  failed_tickers: number;
  rows_upserted: number;
  valuations_upserted: number;
  message: string;
}

export interface YahooTickerFilterParams {
  market?: string;
  sector?: string;
  industry?: string;
  active_only?: boolean;
  active?: boolean;
  search?: string;
}

export interface YahooTickerCreatePayload {
  symbol: string;
  name?: string;
  market?: string;
  sector?: string;
  industry?: string;
  active?: boolean;
}

export interface YahooTickerUpdatePayload {
  active?: boolean;
  name?: string;
  market?: string;
  sector?: string;
  industry?: string;
}

export interface YahooSyncPayload {
  symbol?: string | null;
  symbols?: string[];
  include_fundamentals?: boolean;
  include_valuation?: boolean;
  include_metadata?: boolean;
  start_date?: string | null;
  end_date?: string | null;
  workers?: number;
}

export interface StrategyParameterSpec {
  key: string;
  label: string;
  type: 'int' | 'float' | 'select';
  default: number | string;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  options?: string[] | null;
  description: string;
}

export interface YahooStrategyDefinition {
  id: string;
  name: string;
  description: string;
  parameters: StrategyParameterSpec[];
}

export interface YahooStrategiesListResponse {
  strategies: YahooStrategyDefinition[];
  shared_parameters: StrategyParameterSpec[];
}

export interface YahooBacktestRequest {
  strategy_id: string;
  symbols?: string[];
  market?: string | null;
  sector?: string | null;
  timeframe?: 'D1' | 'W1' | 'MN1';
  from_date?: string | null;
  to_date?: string | null;
  initial_balance?: number;
  risk_per_trade_pct?: number;
  strategy_params?: Record<string, number | string>;
}

export interface YahooTradeRecord {
  symbol: string;
  entry_time: string;
  exit_time: string;
  type: 'BUY' | 'SELL';
  entry_price: number;
  exit_price: number;
  stop_loss: number;
  take_profit: number;
  volume: number;
  pnl: number;
  pnl_pct: number;
  exit_reason: string;
  balance_after: number;
}

export interface YahooEquityPoint {
  time: number;
  date: string;
  balance: number;
  equity: number;
  drawdown_pct: number;
}

export interface YahooBacktestSummaryMetrics {
  initial_balance: number;
  final_balance: number;
  final_equity: number;
  net_profit: number;
  net_profit_pct: number;
  realized_pnl: number;
  realized_pnl_pct: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  profit_factor: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
}

export interface YahooAssetBacktestResult {
  symbol: string;
  name: string;
  market: string;
  sector: string;
  timeframe: string;
  total_bars: number;
  status: 'OK' | 'NO_DATA';
  message?: string | null;
  latest_signal: 'BUY' | 'SELL' | 'HOLD';
  latest_signal_reason: string;
  open_position?: Record<string, unknown> | null;
  metrics: YahooBacktestSummaryMetrics;
  equity_curve: YahooEquityPoint[];
  bars: YahooPriceBar[];
  trades: YahooTradeRecord[];
}

export interface YahooPortfolioBacktestResponse {
  strategy_id: string;
  strategy_name: string;
  timeframe: string;
  applied_params: Record<string, number | string>;
  total_assets: number;
  valid_assets: number;
  portfolio_metrics: YahooBacktestSummaryMetrics;
  portfolio_equity_curve: YahooEquityPoint[];
  asset_results: YahooAssetBacktestResult[];
}

export const YAHOO_SYNC_TIMEOUT_MS = 120000;

export const yahooApi = {
  getTickers: async (params: YahooTickerFilterParams = {}): Promise<YahooTickersListResponse> => {
    const res = await apiClient.get<YahooTickersListResponse>('/yahoo/tickers', { params });
    return res.data;
  },

  createTicker: async (payload: YahooTickerCreatePayload): Promise<YahooTicker> => {
    const res = await apiClient.post<YahooTicker>('/yahoo/tickers', payload);
    return res.data;
  },

  updateTicker: async (symbol: string, payload: YahooTickerUpdatePayload): Promise<YahooTicker> => {
    const res = await apiClient.patch<YahooTicker>(
      `/yahoo/tickers/${encodeURIComponent(symbol)}`,
      payload,
    );
    return res.data;
  },

  deleteTicker: async (
    symbol: string,
  ): Promise<{ symbol: string; deleted: boolean; deleted_prices: number; deleted_valuations: number }> => {
    const res = await apiClient.delete<{
      symbol: string;
      deleted: boolean;
      deleted_prices: number;
      deleted_valuations: number;
    }>(`/yahoo/tickers/${encodeURIComponent(symbol)}`);
    return res.data;
  },

  getHistory: async (
    symbol: string,
    timeframe: string = 'D1',
    limit: number = 1500,
  ): Promise<YahooHistoryResponse> => {
    const res = await apiClient.get<YahooHistoryResponse>(
      `/yahoo/tickers/${encodeURIComponent(symbol)}/history`,
      { params: { timeframe, limit } },
    );
    return res.data;
  },

  getFundamentals: async (symbol: string): Promise<YahooFundamentalsResponse> => {
    const res = await apiClient.get<YahooFundamentalsResponse>(
      `/yahoo/tickers/${encodeURIComponent(symbol)}/fundamentals`,
    );
    return res.data;
  },

  triggerSync: async (payload: YahooSyncPayload = {}): Promise<YahooSyncStatusResponse> => {
    // Single-ticker syncs run synchronously on the gateway (full history download for new
    // tickers), so allow more than the default client timeout.
    const res = await apiClient.post<YahooSyncStatusResponse>('/yahoo/sync', payload, {
      timeout: YAHOO_SYNC_TIMEOUT_MS,
    });
    return res.data;
  },

  getSyncStatus: async (): Promise<YahooSyncStatusResponse> => {
    const res = await apiClient.get<YahooSyncStatusResponse>('/yahoo/sync/status');
    return res.data;
  },

  getStrategies: async (): Promise<YahooStrategiesListResponse> => {
    const res = await apiClient.get<YahooStrategiesListResponse>('/yahoo/strategies');
    return res.data;
  },

  runBacktest: async (payload: YahooBacktestRequest): Promise<YahooPortfolioBacktestResponse> => {
    const res = await apiClient.post<YahooPortfolioBacktestResponse>(
      '/yahoo/strategies/backtest',
      payload,
      { timeout: YAHOO_SYNC_TIMEOUT_MS },
    );
    return res.data;
  },
};
