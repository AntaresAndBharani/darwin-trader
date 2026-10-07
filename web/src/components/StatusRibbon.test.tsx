import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusRibbon, formatCurrency } from './StatusRibbon';
import { ConnectionStatus, LiveTelemetry } from '../api/client';

describe('StatusRibbon Component', () => {
  const mockTelemetry: LiveTelemetry = {
    timestamp: '2026-10-07T12:00:00Z',
    balance: 100000.0,
    equity: 100500.5,
    profit: 500.5,
    free_margin: 95000.0,
    d_score: 78.4,
    positions_count: 2,
    open_positions: [],
  };

  const mockConnectionStatus: ConnectionStatus = {
    status: 'CONNECTED',
    server: 'Darwinex-Live',
    mock_mode: false,
    latency_ms: 14.8,
    connected_at: '2026-10-07T10:00:00Z',
    last_error: null,
    account_info: null,
  };

  it('formats currency correctly with fallback', () => {
    expect(formatCurrency(1000)).toBe('$1,000.00');
    expect(formatCurrency(undefined)).toBe('$0.00');
    expect(formatCurrency(NaN)).toBe('$0.00');
  });

  it('renders live balance, equity, and free margin from telemetry (Scenario 1)', () => {
    render(
      <StatusRibbon
        telemetry={mockTelemetry}
        connectionStatus={mockConnectionStatus}
        isWsConnected={true}
      />
    );

    expect(screen.getByTestId('balance-val')).toHaveTextContent('$100,000.00');
    expect(screen.getByTestId('equity-val')).toHaveTextContent('$100,500.50');
    expect(screen.getByTestId('free-margin-val')).toHaveTextContent('$95,000.00');
    expect(screen.getByTestId('profit-val')).toHaveTextContent('+$500.50');
    expect(screen.getByTestId('d-score-val')).toHaveTextContent('78.4');
  });

  it('renders reported MT5 latency matching ConnectionStatus.latency_ms (Scenario 1)', () => {
    render(
      <StatusRibbon
        telemetry={mockTelemetry}
        connectionStatus={mockConnectionStatus}
        isWsConnected={true}
      />
    );

    expect(screen.getByTestId('latency-ms')).toHaveTextContent('14.8 ms');
    expect(screen.getByTestId('server-name')).toHaveTextContent('Darwinex-Live');
  });

  it('renders CONNECTED status badge when connected', () => {
    render(
      <StatusRibbon
        telemetry={mockTelemetry}
        connectionStatus={mockConnectionStatus}
        isWsConnected={true}
      />
    );

    const badge = screen.getByTestId('connection-status');
    expect(badge).toHaveTextContent('CONNECTED');
    expect(badge).toHaveClass('text-emerald-400');
  });

  it('renders DISCONNECTED status badge when disconnected (Scenario 5)', () => {
    const disconnectedStatus: ConnectionStatus = {
      ...mockConnectionStatus,
      status: 'DISCONNECTED',
      server: 'Disconnected',
      latency_ms: 0.0,
    };

    render(
      <StatusRibbon
        telemetry={null}
        connectionStatus={disconnectedStatus}
        isWsConnected={false}
      />
    );

    const badge = screen.getByTestId('connection-status');
    expect(badge).toHaveTextContent('DISCONNECTED');
    expect(screen.getByTestId('ws-indicator')).toHaveClass('bg-zinc-600');
  });

  it('renders ERROR badge and alert when connection error occurs', () => {
    const errorStatus: ConnectionStatus = {
      ...mockConnectionStatus,
      status: 'ERROR',
    };

    render(
      <StatusRibbon
        telemetry={null}
        connectionStatus={errorStatus}
        isWsConnected={false}
        error="Invalid MT5 Credentials"
      />
    );

    const badge = screen.getByTestId('connection-status');
    expect(badge).toHaveTextContent('ERROR');
    expect(screen.getByTestId('error-alert')).toHaveTextContent('Invalid MT5 Credentials');
  });

  it('renders negative profit with rose color', () => {
    const lossTelemetry: LiveTelemetry = {
      ...mockTelemetry,
      profit: -245.5,
    };

    render(
      <StatusRibbon
        telemetry={lossTelemetry}
        connectionStatus={mockConnectionStatus}
        isWsConnected={true}
      />
    );

    const profitEl = screen.getByTestId('profit-val');
    expect(profitEl).toHaveTextContent('-$245.50');
    expect(profitEl).toHaveClass('text-rose-400');
  });
});
