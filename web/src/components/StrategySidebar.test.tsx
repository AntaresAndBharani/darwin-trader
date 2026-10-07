import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { StrategySidebar } from './StrategySidebar';
import { strategyApi, StrategyStatusResponse } from '../api/strategy';

describe('StrategySidebar', () => {
  const initialStatus: StrategyStatusResponse = {
    status: 'IDLE',
    strategy_name: 'DarwinX',
    symbol: 'EURUSD',
    mock_mode: true,
    open_positions_count: 0,
    account_balance: 100000,
    account_equity: 100000,
    d_score: 75.5,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches initial status on mount and displays metadata', async () => {
    vi.spyOn(strategyApi, 'getStatus').mockResolvedValue(initialStatus);

    render(<StrategySidebar pollIntervalMs={0} />);

    await waitFor(() => {
      expect(screen.getByTestId('strategy-status-badge')).toHaveTextContent('IDLE');
      expect(screen.getByTestId('strategy-name-val')).toHaveTextContent('DarwinX');
      expect(screen.getByTestId('strategy-symbol-val')).toHaveTextContent('EURUSD');
      expect(screen.getByTestId('strategy-mode-val')).toHaveTextContent('MOCK / SIM');
      expect(screen.getByTestId('strategy-positions-count')).toHaveTextContent('0');
    });
  });

  it('executes full lifecycle: IDLE -> Start (RUNNING) -> Pause (PAUSED) -> Stop (STOPPED)', async () => {
    vi.spyOn(strategyApi, 'getStatus').mockResolvedValue(initialStatus);
    const startSpy = vi.spyOn(strategyApi, 'start').mockResolvedValue({
      message: 'Strategy started successfully',
      status: 'RUNNING',
    });
    const pauseSpy = vi.spyOn(strategyApi, 'pause').mockResolvedValue({
      message: 'Strategy paused',
      status: 'PAUSED',
    });
    const stopSpy = vi.spyOn(strategyApi, 'stop').mockResolvedValue({
      message: 'Strategy stopped',
      status: 'STOPPED',
    });

    const onStatusChange = vi.fn();

    render(<StrategySidebar pollIntervalMs={0} onStatusChange={onStatusChange} />);

    // 1. Initial IDLE
    await waitFor(() => {
      expect(screen.getByTestId('strategy-status-badge')).toHaveTextContent('IDLE');
    });

    // Start button enabled, pause/stop disabled
    expect(screen.getByTestId('strategy-start-btn')).not.toBeDisabled();
    expect(screen.getByTestId('strategy-pause-btn')).toBeDisabled();
    expect(screen.getByTestId('strategy-stop-btn')).toBeDisabled();

    // 2. Click Start -> RUNNING
    fireEvent.click(screen.getByTestId('strategy-start-btn'));

    await waitFor(() => {
      expect(startSpy).toHaveBeenCalled();
      expect(screen.getByTestId('strategy-status-badge')).toHaveTextContent('RUNNING');
      expect(onStatusChange).toHaveBeenCalledWith('RUNNING');
    });

    expect(screen.getByTestId('strategy-start-btn')).toBeDisabled();
    expect(screen.getByTestId('strategy-pause-btn')).not.toBeDisabled();
    expect(screen.getByTestId('strategy-stop-btn')).not.toBeDisabled();

    // 3. Click Pause -> PAUSED
    fireEvent.click(screen.getByTestId('strategy-pause-btn'));

    await waitFor(() => {
      expect(pauseSpy).toHaveBeenCalled();
      expect(screen.getByTestId('strategy-status-badge')).toHaveTextContent('PAUSED');
      expect(onStatusChange).toHaveBeenCalledWith('PAUSED');
    });

    expect(screen.getByTestId('strategy-start-btn')).not.toBeDisabled();
    expect(screen.getByTestId('strategy-pause-btn')).toBeDisabled();
    expect(screen.getByTestId('strategy-stop-btn')).not.toBeDisabled();

    // 4. Click Stop -> STOPPED
    fireEvent.click(screen.getByTestId('strategy-stop-btn'));

    await waitFor(() => {
      expect(stopSpy).toHaveBeenCalled();
      expect(screen.getByTestId('strategy-status-badge')).toHaveTextContent('STOPPED');
      expect(onStatusChange).toHaveBeenCalledWith('STOPPED');
    });

    expect(screen.getByTestId('strategy-start-btn')).not.toBeDisabled();
    expect(screen.getByTestId('strategy-pause-btn')).toBeDisabled();
    expect(screen.getByTestId('strategy-stop-btn')).toBeDisabled();
  });

  it('displays UI error alert when start fails', async () => {
    vi.spyOn(strategyApi, 'getStatus').mockResolvedValue(initialStatus);
    vi.spyOn(strategyApi, 'start').mockRejectedValue(new Error('Gateway bridge timeout on MT5 start'));

    render(<StrategySidebar pollIntervalMs={0} />);

    await waitFor(() => {
      expect(screen.getByTestId('strategy-start-btn')).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId('strategy-start-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('strategy-error-alert')).toBeInTheDocument();
      expect(screen.getByTestId('strategy-error-alert')).toHaveTextContent(
        'Gateway bridge timeout on MT5 start'
      );
    });

    // Dismiss error alert
    fireEvent.click(screen.getByLabelText('Dismiss error'));
    expect(screen.queryByTestId('strategy-error-alert')).not.toBeInTheDocument();
  });

  it('triggers onOpenConnect callback when connection settings button is clicked', async () => {
    vi.spyOn(strategyApi, 'getStatus').mockResolvedValue(initialStatus);
    const onOpenConnect = vi.fn();

    render(<StrategySidebar pollIntervalMs={0} onOpenConnect={onOpenConnect} />);

    await waitFor(() => {
      expect(screen.getByTestId('open-connect-dialog-btn')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('open-connect-dialog-btn'));
    expect(onOpenConnect).toHaveBeenCalledTimes(1);
  });
});
