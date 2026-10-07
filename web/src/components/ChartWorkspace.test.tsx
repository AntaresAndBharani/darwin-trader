import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { ChartWorkspace } from './ChartWorkspace';
import { assetsApi } from '../api/assets';
import { mockSeries } from '../test/setup';

describe('ChartWorkspace', () => {
  const mockBars = [
    { time: 1709510400, open: 102.0, high: 103.0, low: 98.0, close: 99.0 },
    { time: 1710115200, open: 99.0, high: 106.0, low: 98.5, close: 105.0 },
  ];

  const mockMetrics = {
    symbol: 'EURUSD',
    insufficient_data: false,
    bars_found: 250,
    bars_required: 21,
    kalman_beta: 1.2345,
    kalman_alpha: 0.0456,
    kalman_trend: 'EXPANDING',
    yang_zhang_vol_annualized: 0.1542,
    amihud_sensitivity: 0.00012,
    vwap: 1.085,
    roll_spread_pct: 0.00025,
    ols_beta: 1.15,
    relative_strength: 0.082,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    mockSeries.setData.mockClear();
    vi.spyOn(assetsApi, 'getHistory').mockResolvedValue({
      symbol: 'EURUSD',
      timeframe: 'D1',
      bars: mockBars,
      total_bars: 2,
      limit: 500,
      offset: 0,
      page: 1,
      total_pages: 1,
    });
    vi.spyOn(assetsApi, 'getMetrics').mockResolvedValue(mockMetrics);
  });

  it('renders canvas and fetches OHLC bars and metrics on load (Scenario 7 & 9)', async () => {
    render(<ChartWorkspace initialSymbol="EURUSD" initialTimeframe="D1" />);

    expect(screen.getByTestId('chart-workspace')).toBeInTheDocument();
    expect(screen.getByTestId('tradingview-canvas')).toBeInTheDocument();

    await waitFor(() => {
      expect(assetsApi.getHistory).toHaveBeenCalledWith('EURUSD', 'D1');
      expect(assetsApi.getMetrics).toHaveBeenCalledWith('EURUSD', 'D1');
      expect(screen.getByTestId('kalman-beta-val')).toHaveTextContent('1.2345');
      expect(screen.getByTestId('kalman-alpha-val')).toHaveTextContent('0.0456');
      expect(screen.getByTestId('kalman-trend-badge')).toHaveTextContent('EXPANDING');
      expect(screen.getByTestId('yang-zhang-vol-val')).toHaveTextContent('15.42%');
      expect(screen.getByTestId('vwap-val')).toHaveTextContent('1.08');
      expect(screen.getByTestId('ols-beta-val')).toHaveTextContent('1.150');
    });

    expect(mockSeries.setData).toHaveBeenCalledWith([
      { time: 1709510400, open: 102.0, high: 103.0, low: 98.0, close: 99.0 },
      { time: 1710115200, open: 99.0, high: 106.0, low: 98.5, close: 105.0 },
    ]);
  });

  it('toggles Heikin-Ashi client-side without backend requests (Scenario 8)', async () => {
    render(<ChartWorkspace initialSymbol="EURUSD" />);

    await waitFor(() => {
      expect(mockSeries.setData).toHaveBeenCalled();
    });

    const toggleBtn = screen.getByTestId('heikin-ashi-toggle');
    expect(toggleBtn).toHaveTextContent('Heikin-Ashi: OFF');

    const getHistoryCallsBefore = vi.mocked(assetsApi.getHistory).mock.calls.length;
    const getMetricsCallsBefore = vi.mocked(assetsApi.getMetrics).mock.calls.length;

    mockSeries.setData.mockClear();

    // Toggle Heikin-Ashi ON
    fireEvent.click(toggleBtn);
    expect(toggleBtn).toHaveTextContent('Heikin-Ashi: ON');

    // Confirm no additional backend calls were dispatched
    expect(vi.mocked(assetsApi.getHistory).mock.calls.length).toBe(getHistoryCallsBefore);
    expect(vi.mocked(assetsApi.getMetrics).mock.calls.length).toBe(getMetricsCallsBefore);

    // Confirm transformed Heikin-Ashi candles were set
    expect(mockSeries.setData).toHaveBeenCalledWith([
      { time: 1709510400, open: 100.5, high: 103.0, low: 98.0, close: 100.5 },
      { time: 1710115200, open: 100.5, high: 106.0, low: 98.5, close: 102.125 },
    ]);

    // Toggle Heikin-Ashi back OFF
    mockSeries.setData.mockClear();
    fireEvent.click(toggleBtn);
    expect(toggleBtn).toHaveTextContent('Heikin-Ashi: OFF');
    expect(mockSeries.setData).toHaveBeenCalledWith([
      { time: 1709510400, open: 102.0, high: 103.0, low: 98.0, close: 99.0 },
      { time: 1710115200, open: 99.0, high: 106.0, low: 98.5, close: 105.0 },
    ]);
  });

  it('changes symbol and re-fetches data', async () => {
    render(<ChartWorkspace initialSymbol="EURUSD" />);

    await waitFor(() => {
      expect(assetsApi.getHistory).toHaveBeenCalledWith('EURUSD', 'D1');
    });

    const selector = screen.getByTestId('asset-selector');
    fireEvent.change(selector, { target: { value: 'AAPL' } });

    await waitFor(() => {
      expect(assetsApi.getHistory).toHaveBeenCalledWith('AAPL', 'D1');
      expect(assetsApi.getMetrics).toHaveBeenCalledWith('AAPL', 'D1');
    });
  });

  it('executes manual historical sync flow and refreshes chart on completion (Scenario 10)', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });

    const triggerSyncSpy = vi.spyOn(assetsApi, 'triggerSync').mockResolvedValue({
      job_id: 'sync-1',
      status: 'IN_PROGRESS',
      message: 'Sync started',
    });

    let pollCount = 0;
    const getSyncStatusSpy = vi.spyOn(assetsApi, 'getSyncStatus').mockImplementation(async () => {
      pollCount++;
      if (pollCount === 1) {
        return {
          job_id: 'sync-1',
          status: 'IN_PROGRESS',
          completed_assets: 0,
          failed_assets: 0,
          total_assets: 1,
          total_bars: 0,
          current_symbol: 'EURUSD',
          message: 'Syncing',
        };
      }
      return {
        job_id: 'sync-1',
        status: 'COMPLETED',
        completed_assets: 1,
        failed_assets: 0,
        total_assets: 1,
        total_bars: 100,
        current_symbol: null,
        message: 'Sync complete',
      };
    });

    render(<ChartWorkspace initialSymbol="EURUSD" />);

    await waitFor(() => {
      expect(assetsApi.getHistory).toHaveBeenCalledTimes(1);
    });

    const syncBtn = screen.getByTestId('sync-rates-btn');
    await act(async () => {
      fireEvent.click(syncBtn);
    });

    expect(triggerSyncSpy).toHaveBeenCalledWith({ symbol: 'EURUSD', timeframe: 'D1' });

    // Advance timer for first poll (IN_PROGRESS)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(650);
    });
    expect(getSyncStatusSpy).toHaveBeenCalledTimes(1);

    // Advance timer for second poll (COMPLETED)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(650);
    });
    expect(getSyncStatusSpy).toHaveBeenCalledTimes(2);

    // Upon completion, chart re-fetches history
    await waitFor(() => {
      expect(assetsApi.getHistory).toHaveBeenCalledTimes(2);
      expect(assetsApi.getMetrics).toHaveBeenCalledTimes(2);
    });

    vi.useRealTimers();
  });
});
