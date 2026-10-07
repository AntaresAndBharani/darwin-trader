import axios from 'axios';
import { useState, useEffect, useCallback, useRef } from 'react';

export type ConnectionState = 'CONNECTED' | 'DISCONNECTED' | 'ERROR';

export interface AccountInfo {
  login: number;
  trade_mode: string;
  server: string;
  balance: number;
  equity: number;
  margin: number;
  free_margin: number;
  margin_level: number;
  currency: string;
  profit: number;
  d_score?: number | null;
}

export interface ConnectionStatus {
  status: ConnectionState;
  server: string;
  mock_mode: boolean;
  latency_ms: number;
  connected_at?: string | null;
  last_error?: string | null;
  account_info?: AccountInfo | null;
}

export interface Position {
  ticket: number;
  symbol: string;
  order_type: 'BUY' | 'SELL' | 'NONE';
  volume: number;
  open_price: number;
  current_price: number;
  sl: number;
  tp: number;
  pnl: number;
  swap: number;
  open_time: string;
  magic: number;
}

export interface LiveTelemetry {
  timestamp: string;
  balance: number;
  equity: number;
  profit: number;
  free_margin: number;
  d_score?: number | null;
  positions_count: number;
  open_positions: Position[];
}

export const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

export const api = {
  getConnectionStatus: async (): Promise<ConnectionStatus> => {
    const res = await apiClient.get<ConnectionStatus>('/account/status');
    return res.data;
  },
  getAccountInfo: async (): Promise<AccountInfo> => {
    const res = await apiClient.get<AccountInfo>('/account/info');
    return res.data;
  },
  getPositions: async (): Promise<Position[]> => {
    const res = await apiClient.get<Position[]>('/account/positions');
    return res.data;
  },
};

export interface UseLiveTelemetryOptions {
  wsUrl?: string;
  pollStatusIntervalMs?: number;
  enabled?: boolean;
}

export function useLiveTelemetry(options: UseLiveTelemetryOptions = {}) {
  const {
    wsUrl,
    pollStatusIntervalMs = 3000,
    enabled = true,
  } = options;

  const [telemetry, setTelemetry] = useState<LiveTelemetry | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus | null>(null);
  const [isWsConnected, setIsWsConnected] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const isMountedRef = useRef<boolean>(true);

  const fetchStatus = useCallback(async () => {
    try {
      const status = await api.getConnectionStatus();
      if (isMountedRef.current) {
        setConnectionStatus(status);
        setError(null);
      }
    } catch (err: unknown) {
      if (isMountedRef.current) {
        const message = err instanceof Error ? err.message : 'Failed to fetch status';
        setError(message);
      }
    }
  }, []);

  const connectWs = useCallback(() => {
    if (!enabled || typeof window === 'undefined') return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const targetWsUrl = wsUrl || `${protocol}//${window.location.host}/ws/live`;

    try {
      const socket = new WebSocket(targetWsUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        if (isMountedRef.current) {
          setIsWsConnected(true);
          setError(null);
        }
      };

      socket.onmessage = (event) => {
        try {
          const data: LiveTelemetry = JSON.parse(event.data);
          if (isMountedRef.current) {
            setTelemetry(data);
          }
        } catch (parseErr) {
          console.error('Failed to parse telemetry message:', parseErr);
        }
      };

      socket.onclose = () => {
        if (isMountedRef.current) {
          setIsWsConnected(false);
          // Auto reconnect after 2 seconds
          reconnectTimeoutRef.current = window.setTimeout(() => {
            if (isMountedRef.current && enabled) {
              connectWs();
            }
          }, 2000);
        }
      };

      socket.onerror = () => {
        if (isMountedRef.current) {
          setIsWsConnected(false);
        }
      };
    } catch (err) {
      if (isMountedRef.current) {
        setIsWsConnected(false);
        const msg = err instanceof Error ? err.message : 'WebSocket initialization failed';
        setError(msg);
      }
    }
  }, [enabled, wsUrl]);

  useEffect(() => {
    isMountedRef.current = true;
    if (!enabled) return;

    fetchStatus();
    connectWs();

    const intervalId = window.setInterval(fetchStatus, pollStatusIntervalMs);

    return () => {
      isMountedRef.current = false;
      window.clearInterval(intervalId);
      if (reconnectTimeoutRef.current !== null) {
        window.clearTimeout(reconnectTimeoutRef.current);
      }
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [enabled, fetchStatus, connectWs, pollStatusIntervalMs]);

  return {
    telemetry,
    connectionStatus,
    isWsConnected,
    error,
    refreshStatus: fetchStatus,
  };
}
