import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { YahooWorkspace } from './YahooWorkspace';
import { yahooApi } from '../api/yahoo';
import { mockSeries } from '../test/setup';

describe('YahooWorkspace', () => {
  const mockTickers = [
    {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      market: 'NASDAQ',
      sector: 'Technology',
      industry: 'Consumer Electronics',
      active: true,
      price_bars_count: 252,
      min_date: '2025-01-02',
      max_date: '2026-04-10',
    },
    {
      symbol: 'SAN',
      name: 'Banco Santander',
      market: 'BME',
      sector: 'Financial Services',
      industry: 'Banks - Diversified',
      active: false,
      price_bars_count: 100,
      min_date: '2025-06-01',
      max_date: '2026-04-10',
    },
  ];

  const mockBars = [
    { time: 1775433600, date: '2026-04-06', open: 200.0, high: 205.0, low: 199.0, close: 203.0, volume: 40000000 },
    { time: 1775520000, date: '2026-04-07', open: 203.0, high: 208.0, low: 201.0, close: 206.5, volume: 42000000 },
  ];

  const mockFundamentals = {
    symbol: 'AAPL',
    ticker: mockTickers[0],
    latest_valuation: {
      as_of_date: '2026-03-31',
      period_type: '3M',
      trailing_pe: 32.15,
      forward_pe: 28.4,
      pb: 45.0,
      ps: 9.1,
      peg: 2.05,
      ev_ebitda: 24.2,
      ev_revenue: 8.9,
      market_cap: 3400000000000,
      enterprise_value: 3450000000000,
      dividend_yield: 0.005,
    },
    valuation_history: [
      {
        as_of_date: '2026-03-31',
        period_type: '3M',
        trailing_pe: 32.15,
        forward_pe: 28.4,
        pb: 45.0,
        ps: 9.1,
        peg: 2.05,
        ev_ebitda: 24.2,
        ev_revenue: 8.9,
        market_cap: 3400000000000,
        enterprise_value: 3450000000000,
        dividend_yield: 0.005,
      },
    ],
    quarterly_earnings: [
      {
        date: '2026-04-06',
        quarterly_eps: 2.15,
        quarterly_revenue: 119575000000,
      },
    ],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    mockSeries.setData.mockClear();

    vi.spyOn(yahooApi, 'getTickers').mockResolvedValue({
      total: 2,
      tickers: mockTickers,
      facets: {
        markets: ['BME', 'NASDAQ'],
        sectors: ['Financial Services', 'Technology'],
        industries: ['Banks - Diversified', 'Consumer Electronics'],
      },
    });
    vi.spyOn(yahooApi, 'getHistory').mockResolvedValue({
      symbol: 'AAPL',
      timeframe: 'D1',
      total_bars: 2,
      bars: mockBars,
    });
    vi.spyOn(yahooApi, 'getFundamentals').mockResolvedValue(mockFundamentals);
  });

  it('loads tickers, selects first ticker, and renders chart and fundamentals', async () => {
    render(<YahooWorkspace />);

    await waitFor(() => {
      expect(yahooApi.getTickers).toHaveBeenCalled();
      expect(screen.getByTestId('yahoo-ticker-row-AAPL')).toBeInTheDocument();
      expect(screen.getByTestId('yahoo-ticker-row-SAN')).toBeInTheDocument();
      expect(screen.getByTestId('yahoo-selected-symbol-heading')).toHaveTextContent('NASDAQ:AAPL');
      expect(screen.getByTestId('yahoo-val-trailing-pe')).toHaveTextContent('32.15');
      expect(screen.getByTestId('yahoo-val-market-cap')).toHaveTextContent('$3.40T');
      expect(screen.getByTestId('yahoo-valuation-table')).toBeInTheDocument();
      expect(screen.getByTestId('yahoo-earnings-table')).toBeInTheDocument();
    });

    expect(mockSeries.setData).toHaveBeenCalled();
  });

  it('filters tickers by market, switches timeframe, and toggles Heikin-Ashi', async () => {
    render(<YahooWorkspace />);

    await waitFor(() => {
      expect(screen.getByTestId('yahoo-selected-symbol-heading')).toHaveTextContent('NASDAQ:AAPL');
    });

    // Switch timeframe to W1
    fireEvent.change(screen.getByTestId('yahoo-timeframe-select'), { target: { value: 'W1' } });
    await waitFor(() => {
      expect(yahooApi.getHistory).toHaveBeenCalledWith('AAPL', 'W1');
    });

    // Toggle Heikin-Ashi
    const haBtn = screen.getByTestId('yahoo-heikin-ashi-toggle');
    expect(haBtn).toHaveTextContent('Heikin-Ashi: OFF');
    fireEvent.click(haBtn);
    expect(haBtn).toHaveTextContent('Heikin-Ashi: ON');

    // Filter by Market
    fireEvent.change(screen.getByTestId('yahoo-filter-market'), { target: { value: 'BME' } });
    await waitFor(() => {
      expect(yahooApi.getTickers).toHaveBeenCalledWith(
        expect.objectContaining({ market: 'BME' }),
      );
    });
  });

  it('supports adding, toggling active, syncing, and deleting a ticker', async () => {
    const createSpy = vi.spyOn(yahooApi, 'createTicker').mockResolvedValue({
      symbol: 'SHEL',
      name: 'Shell plc',
      market: 'LSE',
      sector: 'Energy',
      industry: 'Oil & Gas Integrated',
      active: true,
    });
    const updateSpy = vi.spyOn(yahooApi, 'updateTicker').mockResolvedValue({
      ...mockTickers[0],
      active: false,
    });
    const deleteSpy = vi.spyOn(yahooApi, 'deleteTicker').mockResolvedValue({
      symbol: 'AAPL',
      deleted: true,
      deleted_prices: 252,
      deleted_valuations: 1,
    });
    const syncSpy = vi.spyOn(yahooApi, 'triggerSync').mockResolvedValue({
      status: 'COMPLETED',
      total_tickers: 1,
      completed_tickers: 1,
      failed_tickers: 0,
      rows_upserted: 5,
      valuations_upserted: 1,
      message: 'Synced 1/1 ticker(s)',
    });

    render(<YahooWorkspace />);

    await waitFor(() => {
      expect(screen.getByTestId('yahoo-selected-symbol-heading')).toHaveTextContent('NASDAQ:AAPL');
    });

    // Add ticker
    fireEvent.change(screen.getByTestId('yahoo-add-symbol-input'), {
      target: { value: 'LSE:SHEL' },
    });
    fireEvent.change(screen.getByTestId('yahoo-add-name-input'), {
      target: { value: 'Shell plc' },
    });
    fireEvent.click(screen.getByTestId('yahoo-add-ticker-btn'));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith({
        symbol: 'LSE:SHEL',
        name: 'Shell plc',
        active: true,
      });
    });

    // Sync ticker
    fireEvent.click(screen.getByTestId('yahoo-sync-ticker-btn'));
    await waitFor(() => {
      expect(syncSpy).toHaveBeenCalledWith({ symbol: 'AAPL' });
    });

    // Toggle active
    fireEvent.click(screen.getByTestId('yahoo-toggle-active-btn'));
    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalledWith('AAPL', { active: false });
    });

    // Delete ticker requires confirmation; cancelling must not delete
    fireEvent.click(screen.getByTestId('yahoo-delete-ticker-btn'));
    expect(screen.getByTestId('confirm-modal-prompt')).toHaveTextContent('Delete AAPL');
    fireEvent.click(screen.getByTestId('confirm-modal-cancel'));
    expect(screen.queryByTestId('confirm-modal')).not.toBeInTheDocument();
    expect(deleteSpy).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('yahoo-delete-ticker-btn'));
    fireEvent.click(screen.getByTestId('confirm-modal-confirm'));
    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith('AAPL');
    });
    await waitFor(() => {
      expect(screen.queryByTestId('confirm-modal')).not.toBeInTheDocument();
    });
  });

  it('surfaces a failed single-ticker sync immediately without polling', async () => {
    vi.spyOn(yahooApi, 'triggerSync').mockResolvedValue({
      status: 'FAILED',
      total_tickers: 1,
      completed_tickers: 0,
      failed_tickers: 1,
      rows_upserted: 0,
      valuations_upserted: 0,
      message: 'Synced 0/1 ticker(s)',
    });
    const statusSpy = vi.spyOn(yahooApi, 'getSyncStatus');

    render(<YahooWorkspace />);

    await waitFor(() => {
      expect(screen.getByTestId('yahoo-selected-symbol-heading')).toHaveTextContent('NASDAQ:AAPL');
    });

    fireEvent.click(screen.getByTestId('yahoo-sync-ticker-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('yahoo-error-banner')).toHaveTextContent('Synced 0/1 ticker(s)');
    });
    expect(screen.getByTestId('yahoo-sync-ticker-btn')).not.toBeDisabled();
    expect(statusSpy).not.toHaveBeenCalled();
  });
});
