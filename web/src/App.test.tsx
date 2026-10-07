import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from './App';
import { strategyApi } from './api/strategy';
import { api } from './api/client';

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
    vi.spyOn(api, 'getPositions').mockResolvedValue([]);
    vi.spyOn(strategyApi, 'getStatus').mockResolvedValue({
      status: 'IDLE',
      strategy_name: 'DarwinX',
      symbol: 'EURUSD',
      mock_mode: true,
      open_positions_count: 0,
      account_balance: 100000,
      account_equity: 100000,
      d_score: 75.0,
    });
  });

  it('renders all core components and opens ConnectModal via header button', async () => {
    render(<App />);

    await waitFor(() => {
      expect(screen.getByTestId('status-ribbon')).toBeInTheDocument();
      expect(screen.getByTestId('positions-grid')).toBeInTheDocument();
      expect(screen.getByTestId('strategy-sidebar')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('connect-modal')).not.toBeInTheDocument();

    // Click header Connect MT5 button
    fireEvent.click(screen.getByTestId('header-connect-btn'));
    expect(screen.getByTestId('connect-modal')).toBeInTheDocument();

    // Close modal
    fireEvent.click(screen.getByTestId('connect-modal-close'));
    expect(screen.queryByTestId('connect-modal')).not.toBeInTheDocument();
  });
});
