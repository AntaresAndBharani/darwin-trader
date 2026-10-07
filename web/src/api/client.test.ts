import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { api, apiClient } from './client';

describe('API Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('getConnectionStatus calls GET /account/status and returns ConnectionStatus', async () => {
    const mockStatus = {
      status: 'CONNECTED',
      server: 'Darwinex-Demo',
      mock_mode: true,
      latency_ms: 12.5,
      connected_at: '2026-10-07T12:00:00Z',
      last_error: null,
      account_info: null,
    };

    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockStatus });

    const result = await api.getConnectionStatus();

    expect(getSpy).toHaveBeenCalledWith('/account/status');
    expect(result.status).toBe('CONNECTED');
    expect(result.latency_ms).toBe(12.5);
    expect(result.server).toBe('Darwinex-Demo');
  });

  it('getAccountInfo calls GET /account/info and returns AccountInfo', async () => {
    const mockAccount = {
      login: 123456,
      trade_mode: 'DEMO',
      server: 'Darwinex-Demo',
      balance: 100000.0,
      equity: 100000.0,
      margin: 0.0,
      free_margin: 100000.0,
      margin_level: 0.0,
      currency: 'USD',
      profit: 0.0,
      d_score: 75.4,
    };

    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockAccount });

    const result = await api.getAccountInfo();

    expect(getSpy).toHaveBeenCalledWith('/account/info');
    expect(result.login).toBe(123456);
    expect(result.balance).toBe(100000.0);
    expect(result.d_score).toBe(75.4);
  });

  it('getPositions calls GET /account/positions and returns Position list', async () => {
    const mockPositions = [
      {
        ticket: 101,
        symbol: 'EURUSD',
        order_type: 'BUY',
        volume: 0.1,
        open_price: 1.085,
        current_price: 1.087,
        sl: 1.08,
        tp: 1.09,
        pnl: 20.0,
        swap: 0.0,
        open_time: '2026-10-07T12:00:00Z',
        magic: 20260811,
      },
    ];

    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: mockPositions });

    const result = await api.getPositions();

    expect(getSpy).toHaveBeenCalledWith('/account/positions');
    expect(result).toHaveLength(1);
    expect(result[0].ticket).toBe(101);
    expect(result[0].symbol).toBe('EURUSD');
  });
});
