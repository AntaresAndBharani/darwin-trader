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
};
