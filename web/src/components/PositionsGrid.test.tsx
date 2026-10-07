import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PositionsGrid, formatPnL } from './PositionsGrid';
import { Position } from '../api/client';
import { strategyApi } from '../api/strategy';

describe('PositionsGrid Component', () => {
  const mockPositions: Position[] = [
    {
      ticket: 1001,
      symbol: 'EURUSD',
      order_type: 'BUY',
      volume: 0.10,
      open_price: 1.08500,
      current_price: 1.08750,
      sl: 1.08000,
      tp: 1.09500,
      pnl: 25.00,
      swap: 0.0,
      open_time: '2026-10-07T12:00:00Z',
      magic: 20260811,
    },
    {
      ticket: 1002,
      symbol: 'GBPUSD',
      order_type: 'SELL',
      volume: 0.20,
      open_price: 1.29500,
      current_price: 1.29200,
      sl: 1.30000,
      tp: 1.28500,
      pnl: 60.00,
      swap: -1.50,
      open_time: '2026-10-07T12:05:00Z',
      magic: 20260811,
    },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('formats floating P&L correctly with sign prefix', () => {
    expect(formatPnL(25.5)).toBe('+$25.50');
    expect(formatPnL(-12.4)).toBe('-$12.40');
    expect(formatPnL(0)).toBe('$0.00');
    expect(formatPnL(undefined)).toBe('$0.00');
  });

  it('renders tickets, volumes, prices, and floating P&L (Scenario 3)', () => {
    render(<PositionsGrid positions={mockPositions} />);

    // Count badge
    expect(screen.getByTestId('positions-count-badge')).toHaveTextContent('2');

    // Total PnL (25 + 60 = +$85.00)
    expect(screen.getByTestId('total-pnl')).toHaveTextContent('+$85.00');

    // Ticket #1001
    expect(screen.getByTestId('ticket-1001')).toHaveTextContent('#1001');
    expect(screen.getByTestId('symbol-1001')).toHaveTextContent('EURUSD');
    expect(screen.getByTestId('type-1001')).toHaveTextContent('BUY');
    expect(screen.getByTestId('volume-1001')).toHaveTextContent('0.10');
    expect(screen.getByTestId('open-price-1001')).toHaveTextContent('1.08500');
    expect(screen.getByTestId('current-price-1001')).toHaveTextContent('1.08750');
    expect(screen.getByTestId('pnl-1001')).toHaveTextContent('+$25.00');

    // Ticket #1002
    expect(screen.getByTestId('ticket-1002')).toHaveTextContent('#1002');
    expect(screen.getByTestId('symbol-1002')).toHaveTextContent('GBPUSD');
    expect(screen.getByTestId('type-1002')).toHaveTextContent('SELL');
    expect(screen.getByTestId('volume-1002')).toHaveTextContent('0.20');
    expect(screen.getByTestId('open-price-1002')).toHaveTextContent('1.29500');
    expect(screen.getByTestId('current-price-1002')).toHaveTextContent('1.29200');
    expect(screen.getByTestId('pnl-1002')).toHaveTextContent('+$60.00');
  });

  it('renders empty positions message when no positions exist', () => {
    render(<PositionsGrid positions={[]} />);

    expect(screen.getByTestId('positions-count-badge')).toHaveTextContent('0');
    expect(screen.getByTestId('empty-positions')).toHaveTextContent('No active positions');
  });

  it('executes full two-stage confirmed Kill Switch workflow (Scenario 3)', async () => {
    const killSpy = vi.spyOn(strategyApi, 'killSwitch').mockResolvedValueOnce({
      message: 'Emergency Kill Switch Activated',
      positions_closed: 2,
      detail: 'Closed 2 positions',
      status: 'PAUSED',
    });
    const onKillSwitchSuccess = vi.fn();

    render(<PositionsGrid positions={mockPositions} onKillSwitchSuccess={onKillSwitchSuccess} />);

    // Stage 1: User clicks "Emergency Kill Switch"
    const killBtn = screen.getByRole('button', { name: /emergency kill switch/i });
    fireEvent.click(killBtn);

    // Modal appears requiring explicit confirmation
    expect(screen.getByTestId('confirm-modal')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-modal-title')).toHaveTextContent('EMERGENCY KILL SWITCH');
    expect(screen.getByTestId('confirm-modal-prompt')).toHaveTextContent(
      'Are you sure you want to close ALL 2 active position(s)'
    );

    // Stage 2: User explicitly confirms
    const confirmBtn = screen.getByTestId('confirm-modal-confirm');
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(killSpy).toHaveBeenCalledTimes(1);
    });

    expect(onKillSwitchSuccess).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'Emergency Kill Switch Activated',
        positions_closed: 2,
      })
    );

    // Modal is dismissed and grid reflects 0 open positions
    expect(screen.queryByTestId('confirm-modal')).not.toBeInTheDocument();
    expect(screen.getByTestId('positions-count-badge')).toHaveTextContent('0');
    expect(screen.getByTestId('empty-positions')).toHaveTextContent('No active positions');
  });

  it('preserves open positions and sends NO network request when user cancels kill switch (Scenario 4)', async () => {
    const killSpy = vi.spyOn(strategyApi, 'killSwitch');

    render(<PositionsGrid positions={mockPositions} />);

    // User clicks Emergency Kill Switch
    fireEvent.click(screen.getByRole('button', { name: /emergency kill switch/i }));
    expect(screen.getByTestId('confirm-modal')).toBeInTheDocument();

    // User clicks Cancel
    fireEvent.click(screen.getByTestId('confirm-modal-cancel'));

    // Verify modal is closed
    expect(screen.queryByTestId('confirm-modal')).not.toBeInTheDocument();

    // Verify NO network request was dispatched
    expect(killSpy).not.toHaveBeenCalled();

    // All positions remain active and unaffected
    expect(screen.getByTestId('ticket-1001')).toBeInTheDocument();
    expect(screen.getByTestId('ticket-1002')).toBeInTheDocument();
    expect(screen.getByTestId('positions-count-badge')).toHaveTextContent('2');
  });

  it('preserves open positions and sends NO network request when backdrop is clicked (Scenario 4)', async () => {
    const killSpy = vi.spyOn(strategyApi, 'killSwitch');

    render(<PositionsGrid positions={mockPositions} />);

    fireEvent.click(screen.getByRole('button', { name: /emergency kill switch/i }));
    expect(screen.getByTestId('confirm-modal')).toBeInTheDocument();

    // Click backdrop
    fireEvent.click(screen.getByTestId('confirm-modal-backdrop'));

    expect(screen.queryByTestId('confirm-modal')).not.toBeInTheDocument();
    expect(killSpy).not.toHaveBeenCalled();
    expect(screen.getByTestId('positions-count-badge')).toHaveTextContent('2');
  });

  it('displays error alert if kill switch API call fails', async () => {
    vi.spyOn(strategyApi, 'killSwitch').mockRejectedValueOnce(new Error('Network gateway timeout'));

    render(<PositionsGrid positions={mockPositions} />);

    fireEvent.click(screen.getByRole('button', { name: /emergency kill switch/i }));
    fireEvent.click(screen.getByTestId('confirm-modal-confirm'));

    await waitFor(() => {
      expect(screen.getByTestId('positions-error')).toHaveTextContent('Network gateway timeout');
    });

    // Positions remain intact on failure
    expect(screen.getByTestId('positions-count-badge')).toHaveTextContent('2');
  });
});
