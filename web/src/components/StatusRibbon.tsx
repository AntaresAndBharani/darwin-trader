import type { FC } from 'react';
import { useLiveTelemetry, LiveTelemetry, ConnectionStatus } from '../api/client';

export interface StatusRibbonProps {
  telemetry?: LiveTelemetry | null;
  connectionStatus?: ConnectionStatus | null;
  isWsConnected?: boolean;
  error?: string | null;
}

export const formatCurrency = (val: number | undefined | null, currency = 'USD'): string => {
  if (val === undefined || val === null || isNaN(val)) return '$0.00';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
};

export const StatusRibbon: FC<StatusRibbonProps> = (props) => {
  // If props are passed, use them; otherwise hook into live telemetry
  const live = useLiveTelemetry({ enabled: props.telemetry === undefined && props.connectionStatus === undefined });

  const telemetry = props.telemetry !== undefined ? props.telemetry : live.telemetry;
  const connectionStatus = props.connectionStatus !== undefined ? props.connectionStatus : live.connectionStatus;
  const isWsConnected = props.isWsConnected !== undefined ? props.isWsConnected : live.isWsConnected;
  const error = props.error !== undefined ? props.error : live.error;

  const status = connectionStatus?.status || 'DISCONNECTED';
  const server = connectionStatus?.server || 'Disconnected';
  const latency = connectionStatus?.latency_ms !== undefined ? `${connectionStatus.latency_ms.toFixed(1)} ms` : '-- ms';
  
  // Balance, equity, free margin from telemetry, fallback to account_info if telemetry not yet received
  const balance = telemetry?.balance ?? connectionStatus?.account_info?.balance ?? 0;
  const equity = telemetry?.equity ?? connectionStatus?.account_info?.equity ?? 0;
  const freeMargin = telemetry?.free_margin ?? connectionStatus?.account_info?.free_margin ?? 0;
  const profit = telemetry?.profit ?? connectionStatus?.account_info?.profit ?? 0;
  const dScore = telemetry?.d_score ?? connectionStatus?.account_info?.d_score;
  const currency = connectionStatus?.account_info?.currency || 'USD';

  const getStatusBadge = () => {
    switch (status) {
      case 'CONNECTED':
        return (
          <span
            data-testid="connection-status"
            className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-700/60"
          >
            <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            CONNECTED
          </span>
        );
      case 'ERROR':
        return (
          <span
            data-testid="connection-status"
            className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-950 text-rose-400 border border-rose-700/60"
          >
            <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-rose-400"></span>
            ERROR
          </span>
        );
      default:
        return (
          <span
            data-testid="connection-status"
            className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-zinc-800 text-zinc-400 border border-zinc-700"
          >
            <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-zinc-500"></span>
            DISCONNECTED
          </span>
        );
    }
  };

  return (
    <div
      data-testid="status-ribbon"
      className="w-full bg-zinc-900/90 border-b border-zinc-800 backdrop-blur px-4 py-2.5 flex flex-wrap items-center justify-between gap-3 text-sm select-none"
    >
      {/* Left side: Gateway / Broker connection & Latency */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-zinc-400 font-medium">Gateway:</span>
          {getStatusBadge()}
        </div>

        <div className="flex items-center gap-1.5 text-xs text-zinc-400 border-l border-zinc-800 pl-3">
          <span>Server:</span>
          <span data-testid="server-name" className="text-zinc-200 font-mono font-medium">
            {server}
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-zinc-400 border-l border-zinc-800 pl-3">
          <span>Latency:</span>
          <span data-testid="latency-ms" className="text-emerald-400 font-mono font-medium">
            {latency}
          </span>
        </div>

        <div className="flex items-center gap-1.5 text-xs border-l border-zinc-800 pl-3">
          <span
            data-testid="ws-indicator"
            className={`w-2 h-2 rounded-full ${isWsConnected ? 'bg-emerald-500' : 'bg-zinc-600'}`}
            title={isWsConnected ? 'WebSocket live telemetry active' : 'WebSocket disconnected'}
          />
          <span className="text-zinc-400 text-[11px]">
            {isWsConnected ? 'LIVE' : 'WS OFF'}
          </span>
        </div>
      </div>

      {/* Error alert banner if any */}
      {error && (
        <div
          data-testid="error-alert"
          className="text-xs text-rose-400 bg-rose-950/60 border border-rose-800/60 px-2.5 py-1 rounded"
        >
          {error}
        </div>
      )}

      {/* Right side: Financial Metrics from Telemetry */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex flex-col items-end">
          <span className="text-[11px] uppercase tracking-wider text-zinc-400">Balance</span>
          <span data-testid="balance-val" className="font-mono font-semibold text-zinc-100">
            {formatCurrency(balance, currency)}
          </span>
        </div>

        <div className="flex flex-col items-end border-l border-zinc-800 pl-4">
          <span className="text-[11px] uppercase tracking-wider text-zinc-400">Equity</span>
          <span data-testid="equity-val" className="font-mono font-semibold text-zinc-100">
            {formatCurrency(equity, currency)}
          </span>
        </div>

        <div className="flex flex-col items-end border-l border-zinc-800 pl-4">
          <span className="text-[11px] uppercase tracking-wider text-zinc-400">Free Margin</span>
          <span data-testid="free-margin-val" className="font-mono font-semibold text-cyan-400">
            {formatCurrency(freeMargin, currency)}
          </span>
        </div>

        <div className="flex flex-col items-end border-l border-zinc-800 pl-4">
          <span className="text-[11px] uppercase tracking-wider text-zinc-400">Floating P&amp;L</span>
          <span
            data-testid="profit-val"
            className={`font-mono font-semibold ${
              profit > 0 ? 'text-emerald-400' : profit < 0 ? 'text-rose-400' : 'text-zinc-300'
            }`}
          >
            {profit >= 0 ? '+' : ''}
            {formatCurrency(profit, currency)}
          </span>
        </div>

        {dScore !== undefined && dScore !== null && (
          <div className="flex flex-col items-end border-l border-zinc-800 pl-4">
            <span className="text-[11px] uppercase tracking-wider text-zinc-400">D-Score</span>
            <span data-testid="d-score-val" className="font-mono font-semibold text-amber-400">
              {dScore.toFixed(1)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default StatusRibbon;
