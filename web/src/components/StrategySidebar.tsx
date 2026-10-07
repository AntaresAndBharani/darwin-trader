import { FC, useState, useEffect, useCallback, useRef } from 'react';
import { strategyApi, StrategyStatusResponse } from '../api/strategy';

export interface StrategySidebarProps {
  status?: StrategyStatusResponse | null;
  onStatusChange?: (newStatus: string) => void;
  onOpenConnect?: () => void;
  pollIntervalMs?: number;
}

export const StrategySidebar: FC<StrategySidebarProps> = ({
  status: propStatus,
  onStatusChange,
  onOpenConnect,
  pollIntervalMs = 3000,
}) => {
  const [internalStatus, setInternalStatus] = useState<StrategyStatusResponse | null>(null);
  const [actionLoading, setActionLoading] = useState<'start' | 'pause' | 'stop' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isMountedRef = useRef<boolean>(true);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await strategyApi.getStatus();
      if (isMountedRef.current) {
        setInternalStatus(data);
      }
    } catch (err: unknown) {
      if (isMountedRef.current) {
        const msg = err instanceof Error ? err.message : 'Failed to fetch strategy status';
        // Only set error if not already set by an action
        setError((prev) => prev || msg);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    if (propStatus === undefined) {
      fetchStatus();
      if (pollIntervalMs > 0) {
        const intervalId = window.setInterval(fetchStatus, pollIntervalMs);
        return () => {
          isMountedRef.current = false;
          window.clearInterval(intervalId);
        };
      }
    }
    return () => {
      isMountedRef.current = false;
    };
  }, [propStatus, fetchStatus, pollIntervalMs]);

  const currentData = propStatus !== undefined ? propStatus : internalStatus;
  const currentStatus = currentData?.status || 'IDLE';

  const handleStart = async () => {
    try {
      setActionLoading('start');
      setError(null);
      const res = await strategyApi.start();
      const updatedStatus = res.status || 'RUNNING';
      setInternalStatus((prev) => (prev ? { ...prev, status: updatedStatus } : null));
      if (onStatusChange) onStatusChange(updatedStatus);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start strategy';
      setError(msg);
    } finally {
      setActionLoading(null);
    }
  };

  const handlePause = async () => {
    try {
      setActionLoading('pause');
      setError(null);
      const res = await strategyApi.pause();
      const updatedStatus = res.status || 'PAUSED';
      setInternalStatus((prev) => (prev ? { ...prev, status: updatedStatus } : null));
      if (onStatusChange) onStatusChange(updatedStatus);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to pause strategy';
      setError(msg);
    } finally {
      setActionLoading(null);
    }
  };

  const handleStop = async () => {
    try {
      setActionLoading('stop');
      setError(null);
      const res = await strategyApi.stop();
      const updatedStatus = res.status || 'STOPPED';
      setInternalStatus((prev) => (prev ? { ...prev, status: updatedStatus } : null));
      if (onStatusChange) onStatusChange(updatedStatus);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to stop strategy';
      setError(msg);
    } finally {
      setActionLoading(null);
    }
  };

  const isRunning = currentStatus === 'RUNNING';
  const isPaused = currentStatus === 'PAUSED';
  const canStart = currentStatus === 'IDLE' || currentStatus === 'STOPPED' || currentStatus === 'PAUSED';
  const canPause = isRunning;
  const canStop = isRunning || isPaused;

  const getStatusBadge = () => {
    switch (currentStatus) {
      case 'RUNNING':
        return (
          <span
            data-testid="strategy-status-badge"
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-700/60"
          >
            <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-emerald-400 animate-pulse" />
            RUNNING
          </span>
        );
      case 'PAUSED':
        return (
          <span
            data-testid="strategy-status-badge"
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-amber-950 text-amber-400 border border-amber-700/60"
          >
            <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-amber-400" />
            PAUSED
          </span>
        );
      case 'STOPPED':
        return (
          <span
            data-testid="strategy-status-badge"
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-rose-950 text-rose-400 border border-rose-700/60"
          >
            <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-rose-500" />
            STOPPED
          </span>
        );
      default:
        return (
          <span
            data-testid="strategy-status-badge"
            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-zinc-800 text-zinc-400 border border-zinc-700"
          >
            <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-zinc-500" />
            {currentStatus || 'IDLE'}
          </span>
        );
    }
  };

  return (
    <aside
      data-testid="strategy-sidebar"
      className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-5 flex flex-col gap-4 text-zinc-100"
    >
      <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
        <h2 className="text-sm font-semibold text-zinc-200">Strategy Lifecycle</h2>
        {getStatusBadge()}
      </div>

      {error && (
        <div
          data-testid="strategy-error-alert"
          role="alert"
          className="p-3 text-xs bg-rose-950/70 border border-rose-800 text-rose-300 rounded flex items-start justify-between gap-2"
        >
          <div>
            <span className="font-bold text-rose-400">Execution Error: </span>
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-rose-400 hover:text-rose-200 text-sm font-bold"
            aria-label="Dismiss error"
          >
            &times;
          </button>
        </div>
      )}

      {/* Control Buttons */}
      <div className="grid grid-cols-3 gap-2">
        <button
          type="button"
          data-testid="strategy-start-btn"
          onClick={handleStart}
          disabled={!canStart || actionLoading !== null}
          className="px-3 py-2 text-xs font-semibold rounded bg-emerald-700 hover:bg-emerald-600 active:bg-emerald-800 text-white transition-colors disabled:opacity-40 disabled:pointer-events-none cursor-pointer"
        >
          {actionLoading === 'start' ? 'Starting...' : 'Start'}
        </button>

        <button
          type="button"
          data-testid="strategy-pause-btn"
          onClick={handlePause}
          disabled={!canPause || actionLoading !== null}
          className="px-3 py-2 text-xs font-semibold rounded bg-amber-700 hover:bg-amber-600 active:bg-amber-800 text-white transition-colors disabled:opacity-40 disabled:pointer-events-none cursor-pointer"
        >
          {actionLoading === 'pause' ? 'Pausing...' : 'Pause'}
        </button>

        <button
          type="button"
          data-testid="strategy-stop-btn"
          onClick={handleStop}
          disabled={!canStop || actionLoading !== null}
          className="px-3 py-2 text-xs font-semibold rounded bg-rose-700 hover:bg-rose-600 active:bg-rose-800 text-white transition-colors disabled:opacity-40 disabled:pointer-events-none cursor-pointer"
        >
          {actionLoading === 'stop' ? 'Stopping...' : 'Stop'}
        </button>
      </div>

      {/* Metadata Info Panel */}
      <div className="flex flex-col gap-2 pt-2 border-t border-zinc-800 text-xs">
        <div className="flex justify-between items-center text-zinc-400">
          <span>Strategy:</span>
          <span data-testid="strategy-name-val" className="font-semibold text-zinc-200">
            {currentData?.strategy_name || 'DarwinX'}
          </span>
        </div>
        <div className="flex justify-between items-center text-zinc-400">
          <span>Symbol:</span>
          <span data-testid="strategy-symbol-val" className="font-mono text-zinc-200">
            {currentData?.symbol || 'EURUSD'}
          </span>
        </div>
        <div className="flex justify-between items-center text-zinc-400">
          <span>Mode:</span>
          <span data-testid="strategy-mode-val" className="font-mono text-zinc-300">
            {currentData?.mock_mode ? 'MOCK / SIM' : 'LIVE'}
          </span>
        </div>
        <div className="flex justify-between items-center text-zinc-400">
          <span>Open Positions:</span>
          <span data-testid="strategy-positions-count" className="font-mono text-zinc-200">
            {currentData?.open_positions_count ?? 0}
          </span>
        </div>
      </div>

      {onOpenConnect && (
        <button
          type="button"
          data-testid="open-connect-dialog-btn"
          onClick={onOpenConnect}
          className="mt-1 w-full px-3 py-2 text-xs font-medium rounded border border-zinc-700 hover:border-zinc-500 bg-zinc-800/80 hover:bg-zinc-800 text-zinc-300 hover:text-white transition-colors cursor-pointer"
        >
          Broker Connection Settings...
        </button>
      )}
    </aside>
  );
};

export default StrategySidebar;
