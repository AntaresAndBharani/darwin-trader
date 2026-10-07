import { describe, it, expect, vi, beforeEach } from 'vitest';
import { assetsApi } from './assets';
import { apiClient } from './client';

describe('assetsApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('getHistory calls /assets/{symbol}/history with query parameters', async () => {
    const mockData = {
      symbol: 'EURUSD',
      timeframe: 'D1',
      bars: [{ time: 1000, open: 1.1, high: 1.2, low: 1.05, close: 1.15 }],
      total_bars: 1,
      limit: 500,
      offset: 0,
      page: 1,
      total_pages: 1,
    };
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: mockData });

    const result = await assetsApi.getHistory('EURUSD', 'D1', 500, 0);

    expect(getSpy).toHaveBeenCalledWith('/assets/EURUSD/history', {
      params: { timeframe: 'D1', limit: 500, offset: 0 },
    });
    expect(result).toEqual(mockData);
  });

  it('getMetrics calls /assets/{symbol}/metrics with timeframe', async () => {
    const mockMetrics = {
      symbol: 'AAPL',
      insufficient_data: false,
      bars_found: 250,
      bars_required: 21,
      kalman_beta: 1.24,
      kalman_alpha: 0.05,
      kalman_trend: 'EXPANDING',
    };
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: mockMetrics });

    const result = await assetsApi.getMetrics('AAPL', 'D1');

    expect(getSpy).toHaveBeenCalledWith('/assets/AAPL/metrics', {
      params: { timeframe: 'D1' },
    });
    expect(result).toEqual(mockMetrics);
  });

  it('triggerSync posts to /assets/history/sync with parameters', async () => {
    const mockResp = {
      job_id: 'job-123',
      status: 'IN_PROGRESS',
      message: 'Sync started',
    };
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: mockResp });

    const result = await assetsApi.triggerSync({ symbol: 'MSFT', fresh: true });

    expect(postSpy).toHaveBeenCalledWith('/assets/history/sync', null, {
      params: { symbol: 'MSFT', fresh: true },
    });
    expect(result).toEqual(mockResp);
  });

  it('getSyncStatus queries /assets/history/sync/status', async () => {
    const mockStatus = {
      job_id: 'job-123',
      status: 'COMPLETED',
      completed_assets: 1,
      failed_assets: 0,
      total_assets: 1,
      total_bars: 500,
      current_symbol: null,
      message: 'Sync complete',
    };
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: mockStatus });

    const result = await assetsApi.getSyncStatus();

    expect(getSpy).toHaveBeenCalledWith('/assets/history/sync/status');
    expect(result.status).toBe('COMPLETED');
  });
});
