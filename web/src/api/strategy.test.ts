import { describe, it, expect, vi, beforeEach } from 'vitest';
import { strategyApi } from './strategy';
import { apiClient } from './client';

describe('Strategy API Client', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('calls POST /strategy/kill-switch on killSwitch()', async () => {
    const mockResponse = {
      data: {
        message: 'Emergency Kill Switch Activated',
        positions_closed: 2,
        detail: 'Liquidated 2 positions',
        status: 'PAUSED',
      },
    };
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValueOnce(mockResponse);

    const result = await strategyApi.killSwitch();

    expect(postSpy).toHaveBeenCalledWith('/strategy/kill-switch');
    expect(result).toEqual(mockResponse.data);
    expect(result.positions_closed).toBe(2);
  });

  it('calls GET /strategy/status on getStatus()', async () => {
    const mockStatus = {
      data: {
        status: 'RUNNING',
        strategy_name: 'DarwinX',
        symbol: 'EURUSD',
        mock_mode: true,
        open_positions_count: 1,
        account_balance: 100000.0,
        account_equity: 100250.0,
        d_score: 75.4,
      },
    };
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValueOnce(mockStatus);

    const result = await strategyApi.getStatus();

    expect(getSpy).toHaveBeenCalledWith('/strategy/status');
    expect(result.status).toBe('RUNNING');
  });

  it('calls start, pause, and stop endpoints correctly', async () => {
    const postSpy = vi.spyOn(apiClient, 'post').mockImplementation(async (url) => ({
      data: { message: `Ok for ${url}`, status: 'OK' },
    }));

    await strategyApi.start();
    expect(postSpy).toHaveBeenCalledWith('/strategy/start');

    await strategyApi.pause();
    expect(postSpy).toHaveBeenCalledWith('/strategy/pause');

    await strategyApi.stop();
    expect(postSpy).toHaveBeenCalledWith('/strategy/stop');
  });
});
