import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from './App';
import { strategyApi } from './api/strategy';
import { api } from './api/client';
import { accountApi } from './api/account';
import { assetsApi } from './api/assets';
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
    vi.spyOn(strategyApi, 'getStatus').mockResolvedValue({
      status: 'IDLE',
      strategy_name: 'DarwinX',
      symbol: 'EURUSD',
      mock_mode: false,
      open_positions_count: 0,
      account_balance: 100000,
      account_equity: 100000,
      d_score: 75.0,
    });
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
    vi.spyOn(assetsApi, 'getMetrics').mockResolvedValue(null as unknown as import('./api/assets').AssetMetricsResponse);
  });

  it('auto-connects to Darwinex-Live (4000073238) on mount while keeping ConnectModal closed', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('status-ribbon')).toBeInTheDocument();
      expect(screen.getByTestId('positions-grid')).toBeInTheDocument();
      expect(screen.getByTestId('strategy-sidebar')).toBeInTheDocument();
      expect(screen.getByTestId('chart-workspace')).toBeInTheDocument();
      expect(accountApi.connect).toHaveBeenCalledWith({
        login: DEFAULT_LOGIN,
        server: DEFAULT_SERVER,
        path: DEFAULT_TERMINAL_PATH,
        mock_mode: false,
      });
    });

    // Modal remains closed unless explicitly triggered
    expect(screen.queryByTestId('connect-modal')).not.toBeInTheDocument();

    // Click header Connect MT5 button
    fireEvent.click(screen.getByTestId('header-connect-btn'));
    expect(screen.getByTestId('connect-modal')).toBeInTheDocument();

    // Close modal
    fireEvent.click(screen.getByTestId('connect-modal-close'));
    expect(screen.queryByTestId('connect-modal')).not.toBeInTheDocument();
  });
});
