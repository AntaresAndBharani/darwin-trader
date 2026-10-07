import { apiClient } from './client';

export interface HistoricalBar {
  symbol?: string;
  timeframe?: string;
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  tick_volume?: number;
  spread?: number;
}

export interface HistoricalRatesResponse {
  symbol: string;
  timeframe: string;
  bars: HistoricalBar[];
  total_bars: number;
  limit: number;
  offset: number;
  page: number;
  total_pages: number;
}

export interface HistoricalSyncResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface HistoricalSyncStatus {
  job_id: string | null;
  status: 'IDLE' | 'IN_PROGRESS' | 'COMPLETED' | 'FAILED';
  completed_assets: number;
  failed_assets: number;
  total_assets: number;
  total_bars: number;
  current_symbol: string | null;
  message: string;
}

export interface AssetMetricsResponse {
  symbol: string;
  insufficient_data: boolean;
  bars_found: number;
  bars_required: number;
  yang_zhang_vol_annualized?: number | null;
  amihud_sensitivity?: number | null;
  vwap?: number | null;
  vwap_upper?: number | null;
  vwap_lower?: number | null;
  vwap_deviation_sigmas?: number | null;
  roll_spread_pct?: number | null;
  roll_spread_absolute?: number | null;
  last_bar_time?: number | null;
  ols_beta?: number | null;
  relative_strength?: number | null;
  kalman_beta?: number | null;
  kalman_alpha?: number | null;
  kalman_trend?: string | null;
  common_overlap_bars?: number;
  beta_trajectory?: number[];
  data_flags?: string[];
}

export const assetsApi = {
  getHistory: async (
    symbol: string,
    timeframe = 'D1',
    limit = 500,
    offset = 0
  ): Promise<HistoricalRatesResponse> => {
    const res = await apiClient.get<HistoricalRatesResponse>(`/assets/${encodeURIComponent(symbol)}/history`, {
      params: { timeframe, limit, offset },
    });
    return res.data;
  },

  getMetrics: async (symbol: string, timeframe = 'D1'): Promise<AssetMetricsResponse> => {
    const res = await apiClient.get<AssetMetricsResponse>(`/assets/${encodeURIComponent(symbol)}/metrics`, {
      params: { timeframe },
    });
    return res.data;
  },

  triggerSync: async (params?: {
    symbol?: string;
    category?: string;
    timeframe?: string;
    fresh?: boolean;
  }): Promise<HistoricalSyncResponse> => {
    const res = await apiClient.post<HistoricalSyncResponse>('/assets/history/sync', null, {
      params,
    });
    return res.data;
  },

  getSyncStatus: async (): Promise<HistoricalSyncStatus> => {
    const res = await apiClient.get<HistoricalSyncStatus>('/assets/history/sync/status');
    return res.data;
  },
};
