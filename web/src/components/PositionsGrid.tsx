import { FC, useState, useEffect } from 'react';
import { Position, useLiveTelemetry, api } from '../api/client';
import { strategyApi, KillSwitchResponse } from '../api/strategy';
import { ConfirmModal } from './ConfirmModal';

export interface PositionsGridProps {
  positions?: Position[];
  onKillSwitchSuccess?: (response: KillSwitchResponse) => void;
}

export const formatPnL = (val: number | undefined | null): string => {
  if (val === undefined || val === null || isNaN(val)) return '$0.00';
  const prefix = val > 0 ? '+' : '';
  return `${prefix}${new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val)}`;
};

export const PositionsGrid: FC<PositionsGridProps> = ({
  positions: propPositions,
  onKillSwitchSuccess,
}) => {
  const live = useLiveTelemetry({ enabled: propPositions === undefined });
  const [localPositions, setLocalPositions] = useState<Position[] | null>(null);
  const [isModalOpen, setIsModalOpen] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Sync with propPositions if passed
  useEffect(() => {
    if (propPositions !== undefined) {
      setLocalPositions(propPositions);
    }
  }, [propPositions]);

  // Initial fetch from REST API if uncontrolled
  useEffect(() => {
    if (propPositions !== undefined) return;
    let isMounted = true;
    api.getPositions()
      .then((data) => {
        if (isMounted) setLocalPositions(data);
      })
      .catch((err) => {
        if (isMounted) {
          console.warn('Failed to fetch initial positions:', err);
        }
      });
    return () => {
      isMounted = false;
    };
  }, [propPositions]);

  // Sync with live WebSocket telemetry stream if uncontrolled
  useEffect(() => {
    if (propPositions !== undefined) return;
    if (live.telemetry?.open_positions) {
      setLocalPositions(live.telemetry.open_positions);
    }
  }, [propPositions, live.telemetry]);

  const positions = localPositions ?? propPositions ?? [];
  const totalPnL = positions.reduce((sum, p) => sum + (p.pnl || 0), 0);

  const handleOpenKillSwitchModal = () => {
    setError(null);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    if (!isProcessing) {
      setIsModalOpen(false);
    }
  };

  const handleConfirmKillSwitch = async () => {
    try {
      setIsProcessing(true);
      setError(null);
      const res = await strategyApi.killSwitch();
      setLocalPositions([]);
      setIsModalOpen(false);
      if (onKillSwitchSuccess) {
        onKillSwitchSuccess(res);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to execute Kill Switch';
      setError(msg);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div data-testid="positions-grid" className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-5 flex flex-col gap-4">
      {/* Header bar with title, count, total PnL, and Kill Switch */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-3">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-semibold text-zinc-100 flex items-center gap-2">
            <span>Open Positions</span>
            <span
              data-testid="positions-count-badge"
              className="px-2 py-0.5 text-xs font-mono rounded bg-zinc-800 text-zinc-300"
            >
              {positions.length}
            </span>
          </h2>
          <div className="text-xs text-zinc-400 border-l border-zinc-800 pl-3 flex items-center gap-1.5">
            <span>Total Floating P&amp;L:</span>
            <span
              data-testid="total-pnl"
              className={`font-mono font-medium ${
                totalPnL > 0 ? 'text-emerald-400' : totalPnL < 0 ? 'text-rose-400' : 'text-zinc-300'
              }`}
            >
              {formatPnL(totalPnL)}
            </span>
          </div>
        </div>

        <button
          type="button"
          data-testid="kill-switch-btn"
          onClick={handleOpenKillSwitchModal}
          className="px-3.5 py-1.5 text-xs font-bold uppercase tracking-wider rounded bg-rose-600 hover:bg-rose-500 active:bg-rose-700 text-white transition-colors shadow-lg shadow-rose-950/40 flex items-center gap-1.5 cursor-pointer"
        >
          <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
          Emergency Kill Switch
        </button>
      </div>

      {error && (
        <div data-testid="positions-error" className="p-3 text-xs bg-rose-950/70 border border-rose-800 text-rose-300 rounded">
          {error}
        </div>
      )}

      {/* Positions Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-zinc-800 text-zinc-400 font-medium select-none">
              <th className="py-2.5 px-3">Ticket</th>
              <th className="py-2.5 px-3">Symbol</th>
              <th className="py-2.5 px-3">Type</th>
              <th className="py-2.5 px-3 text-right">Volume</th>
              <th className="py-2.5 px-3 text-right">Open Price</th>
              <th className="py-2.5 px-3 text-right">Current Price</th>
              <th className="py-2.5 px-3 text-right">S/L &middot; T/P</th>
              <th className="py-2.5 px-3 text-right">Profit / Loss</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60 font-mono">
            {positions.length === 0 ? (
              <tr>
                <td
                  colSpan={8}
                  data-testid="empty-positions"
                  className="py-8 text-center text-zinc-500 text-xs font-sans"
                >
                  No active positions
                </td>
              </tr>
            ) : (
              positions.map((pos) => {
                const isBuy = pos.order_type === 'BUY';
                const isProfit = pos.pnl > 0;
                const isLoss = pos.pnl < 0;

                return (
                  <tr
                    key={pos.ticket}
                    data-testid={`position-row-${pos.ticket}`}
                    className="hover:bg-zinc-800/40 transition-colors"
                  >
                    <td data-testid={`ticket-${pos.ticket}`} className="py-2.5 px-3 font-semibold text-zinc-200">
                      #{pos.ticket}
                    </td>
                    <td data-testid={`symbol-${pos.ticket}`} className="py-2.5 px-3 font-bold text-white font-sans">
                      {pos.symbol}
                    </td>
                    <td data-testid={`type-${pos.ticket}`} className="py-2.5 px-3 font-sans">
                      <span
                        className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          isBuy ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60' : 'bg-rose-950 text-rose-400 border border-rose-800/60'
                        }`}
                      >
                        {pos.order_type}
                      </span>
                    </td>
                    <td data-testid={`volume-${pos.ticket}`} className="py-2.5 px-3 text-right text-zinc-300">
                      {pos.volume.toFixed(2)}
                    </td>
                    <td data-testid={`open-price-${pos.ticket}`} className="py-2.5 px-3 text-right text-zinc-300">
                      {pos.open_price.toFixed(5)}
                    </td>
                    <td data-testid={`current-price-${pos.ticket}`} className="py-2.5 px-3 text-right text-zinc-100">
                      {pos.current_price.toFixed(5)}
                    </td>
                    <td data-testid={`sltp-${pos.ticket}`} className="py-2.5 px-3 text-right text-zinc-400 text-[11px]">
                      {pos.sl ? pos.sl.toFixed(5) : '-'} / {pos.tp ? pos.tp.toFixed(5) : '-'}
                    </td>
                    <td
                      data-testid={`pnl-${pos.ticket}`}
                      className={`py-2.5 px-3 text-right font-semibold ${
                        isProfit ? 'text-emerald-400' : isLoss ? 'text-rose-400' : 'text-zinc-300'
                      }`}
                    >
                      {formatPnL(pos.pnl)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Two-Stage Confirmed Kill Switch Modal */}
      <ConfirmModal
        isOpen={isModalOpen}
        title="EMERGENCY KILL SWITCH"
        prompt={
          positions.length > 0
            ? `Are you sure you want to close ALL ${positions.length} active position(s) and pause strategy execution? This action will immediately liquidate tickets in MetaTrader 5.`
            : 'No active open positions to liquidate. Are you sure you want to pause strategy execution?'
        }
        confirmText="Confirm Kill Switch"
        cancelText="Cancel"
        isDanger={true}
        isLoading={isProcessing}
        onConfirm={handleConfirmKillSwitch}
        onCancel={handleCloseModal}
      />
    </div>
  );
};
