import { apiClient } from './client';

export interface KillSwitchResponse {
  message: string;
  positions_closed: number;
  detail: string;
  status: string;
}

export interface StrategyStatusResponse {
  status: string;
  strategy_name: string;
  symbol: string;
  mock_mode: boolean;
  open_positions_count: number;
  account_balance: number;
  account_equity: number;
  d_score: number | null;
}

export const strategyApi = {
  killSwitch: async (): Promise<KillSwitchResponse> => {
    const res = await apiClient.post<KillSwitchResponse>('/strategy/kill-switch');
    return res.data;
  },
  getStatus: async (): Promise<StrategyStatusResponse> => {
    const res = await apiClient.get<StrategyStatusResponse>('/strategy/status');
    return res.data;
  },
  start: async (): Promise<{ message: string; status: string }> => {
    const res = await apiClient.post<{ message: string; status: string }>('/strategy/start');
    return res.data;
  },
  pause: async (): Promise<{ message: string; status: string }> => {
    const res = await apiClient.post<{ message: string; status: string }>('/strategy/pause');
    return res.data;
  },
  stop: async (): Promise<{ message: string; status: string }> => {
    const res = await apiClient.post<{ message: string; status: string }>('/strategy/stop');
    return res.data;
  },
};
