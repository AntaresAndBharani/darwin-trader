import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from './client';
import { yahooApi } from './yahoo';

describe('yahooApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('calls GET /yahoo/tickers with filter params', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValue({
      data: {
        total: 1,
        tickers: [
          {
            symbol: 'AAPL',
            name: 'Apple Inc.',
            market: 'NASDAQ',
            sector: 'Technology',
            industry: 'Consumer Electronics',
            active: true,
          },
        ],
        facets: { markets: ['NASDAQ'], sectors: ['Technology'], industries: ['Consumer Electronics'] },
      },
    });

    const res = await yahooApi.getTickers({ market: 'NASDAQ', active_only: true });
    expect(getSpy).toHaveBeenCalledWith('/yahoo/tickers', {
      params: { market: 'NASDAQ', active_only: true },
    });
    expect(res.total).toBe(1);
    expect(res.tickers[0].symbol).toBe('AAPL');
  });

  it('calls POST, PATCH, and DELETE /yahoo/tickers', async () => {
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: {
        symbol: 'SHEL',
        name: 'Shell plc',
        market: 'LSE',
        sector: 'Energy',
        industry: 'Oil & Gas Integrated',
        active: true,
      },
    });
    const patchSpy = vi.spyOn(apiClient, 'patch').mockResolvedValue({
      data: {
        symbol: 'SHEL',
        name: 'Shell plc',
        market: 'LSE',
        sector: 'Energy',
        industry: 'Oil & Gas Integrated',
        active: false,
      },
    });
    const delSpy = vi.spyOn(apiClient, 'delete').mockResolvedValue({
      data: { symbol: 'SHEL', deleted: true, deleted_prices: 10, deleted_valuations: 2 },
    });

    const created = await yahooApi.createTicker({ symbol: 'LSE:SHEL', name: 'Shell plc' });
    expect(postSpy).toHaveBeenCalledWith('/yahoo/tickers', { symbol: 'LSE:SHEL', name: 'Shell plc' });
    expect(created.symbol).toBe('SHEL');

    const updated = await yahooApi.updateTicker('SHEL', { active: false });
    expect(patchSpy).toHaveBeenCalledWith('/yahoo/tickers/SHEL', { active: false });
    expect(updated.active).toBe(false);

    const deleted = await yahooApi.deleteTicker('SHEL');
    expect(delSpy).toHaveBeenCalledWith('/yahoo/tickers/SHEL');
    expect(deleted.deleted).toBe(true);
  });

  it('calls GET history, fundamentals, and sync endpoints', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
      if (url.endsWith('/history')) {
        return { data: { symbol: 'AAPL', timeframe: 'W1', total_bars: 1, bars: [] } };
      }
      if (url.endsWith('/fundamentals')) {
        return {
          data: {
            symbol: 'AAPL',
            ticker: null,
            latest_valuation: null,
            valuation_history: [],
            quarterly_earnings: [],
          },
        };
      }
      return {
        data: {
          status: 'COMPLETED',
          total_tickers: 1,
          completed_tickers: 1,
          failed_tickers: 0,
          rows_upserted: 5,
          valuations_upserted: 1,
          message: 'Done',
        },
      };
    });
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      data: {
        status: 'COMPLETED',
        total_tickers: 1,
        completed_tickers: 1,
        failed_tickers: 0,
        rows_upserted: 5,
        valuations_upserted: 1,
        message: 'Done',
      },
    });

    const hist = await yahooApi.getHistory('AAPL', 'W1', 500);
    expect(hist.timeframe).toBe('W1');
    expect(getSpy).toHaveBeenCalledWith('/yahoo/tickers/AAPL/history', {
      params: { timeframe: 'W1', limit: 500 },
    });

    const fund = await yahooApi.getFundamentals('AAPL');
    expect(fund.symbol).toBe('AAPL');

    const syncRes = await yahooApi.triggerSync({ symbol: 'AAPL' });
    expect(postSpy).toHaveBeenCalledWith('/yahoo/sync', { symbol: 'AAPL' });
    expect(syncRes.status).toBe('COMPLETED');

    const statusRes = await yahooApi.getSyncStatus();
    expect(statusRes.status).toBe('COMPLETED');
  });
});
