import { apiClient, AccountInfo, ConnectionState } from './client';

export interface AccountConnectRequest {
  login: number;
  password?: string;
  server?: string;
  path?: string | null;
  mock_mode?: boolean;
}

export interface AccountConnectResponse {
  status: ConnectionState;
  message: string;
  login: number;
  server: string;
  trade_mode: string;
  balance: number;
  currency: string;
  account_info?: AccountInfo | null;
  error?: string | null;
}

export const accountApi = {
  connect: async (data: AccountConnectRequest): Promise<AccountConnectResponse> => {
    const res = await apiClient.post<AccountConnectResponse>('/account/connect', data);
    return res.data;
  },
};
