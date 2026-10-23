import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from './App';
import { api } from './api/client';
import { accountApi } from './api/account';
import { assetsApi } from './api/assets';
import { yahooApi } from './api/yahoo';
import {
  DEFAULT_LOGIN,
  DEFAULT_SERVER,
  DEFAULT_TERMINAL_PATH,
} from './components/ConnectModal';

describe('App', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, 'getConnectionStatus').mockResolvedValue({
      status: 'DISCONNECTED',
      server: 'Darwinex-Demo',
      mock_mode: true,
      latency_ms: 0,
      account_info: null,
    });
    vi.spyOn(accountApi, 'connect').mockResolvedValue({
      status: 'CONNECTED',
      message: 'Connected to Darwinex-Live',
      login: DEFAULT_LOGIN,
      server: DEFAULT_SERVER,
      trade_mode: 'REAL',
      balance: 100000,
      currency: 'EUR',
      error: null,
    });
    vi.spyOn(api, 'getPositions').mockResolvedValue([]);
    vi.spyOn(assetsApi, 'getHistory').mockResolvedValue({
      symbol: 'EURUSD',
      timeframe: 'D1',
      bars: [],
      total_bars: 0,
      limit: 500,
      offset: 0,
      page: 1,
      total_pages: 1,
    });
    vi.spyOn(assetsApi, 'getMetrics').mockResolvedValue(
      null as unknown as import('./api/assets').AssetMetricsResponse,
    );
    vi.spyOn(yahooApi, 'getTickers').mockResolvedValue({
      total: 1,
      tickers: [
        {
          symbol: 'AAPL',
          name: 'Apple Inc.',
          market: 'NASDAQ',
          sector: 'Technology',
          industry: 'Consumer Electronics',
          active: true,
          price_bars_count: 100,
        },
      ],
      facets: { markets: ['NASDAQ'], sectors: ['Technology'], industries: ['Consumer Electronics'] },
    });
    vi.spyOn(yahooApi, 'getHistory').mockResolvedValue({
      symbol: 'AAPL',
      timeframe: 'D1',
      total_bars: 0,
      bars: [],
    });
    vi.spyOn(yahooApi, 'getFundamentals').mockResolvedValue({
      symbol: 'AAPL',
      ticker: null,
      latest_valuation: null,
      valuation_history: [],
      quarterly_earnings: [],
    });
    vi.spyOn(yahooApi, 'getStrategies').mockResolvedValue({
      strategies: [],
      shared_parameters: [],
    });
  });

  it('auto-connects to Darwinex-Live on mount, removes legacy StrategySidebar, and navigates across the 3 top-level tabs', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('status-ribbon')).toBeInTheDocument();
      expect(screen.getByTestId('positions-grid')).toBeInTheDocument();
      expect(screen.getByTestId('chart-workspace')).toBeInTheDocument();
      expect(accountApi.connect).toHaveBeenCalledWith({
        login: DEFAULT_LOGIN,
        server: DEFAULT_SERVER,
        path: DEFAULT_TERMINAL_PATH,
        mock_mode: false,
      });
    });

    // Legacy small StrategySidebar card is removed from Darwinex MT5 tab
    expect(screen.queryByTestId('strategy-sidebar')).not.toBeInTheDocument();

    // Modal remains closed unless explicitly triggered
    expect(screen.queryByTestId('connect-modal')).not.toBeInTheDocument();

    // Click header Connect MT5 button
    fireEvent.click(screen.getByTestId('header-connect-btn'));
    expect(screen.getByTestId('connect-modal')).toBeInTheDocument();

    // Close modal
    fireEvent.click(screen.getByTestId('connect-modal-close'));
    expect(screen.queryByTestId('connect-modal')).not.toBeInTheDocument();

    // Switch to Yahoo Finance tab
    fireEvent.click(screen.getByTestId('tab-yahoo'));
    await waitFor(() => {
      expect(screen.getByTestId('yahoo-workspace')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('chart-workspace')).not.toBeInTheDocument();

    // Switch to Strategy Lifecycle full-screen tab
    fireEvent.click(screen.getByTestId('tab-strategy'));
    await waitFor(() => {
      expect(screen.getByTestId('strategy-lifecycle-workspace')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('yahoo-workspace')).not.toBeInTheDocument();

    // Switch back to Darwinex MT5 tab
    fireEvent.click(screen.getByTestId('tab-darwinex'));
    expect(screen.getByTestId('chart-workspace')).toBeInTheDocument();
  });
});
