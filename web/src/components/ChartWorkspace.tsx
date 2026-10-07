import { FC, useEffect, useRef, useState, useCallback } from 'react';
import { createChart, IChartApi, ISeriesApi, CandlestickSeries, ColorType, UTCTimestamp } from 'lightweight-charts';
import { assetsApi, HistoricalBar, AssetMetricsResponse } from '../api/assets';
import { computeHeikinAshi, HeikinAshiBar } from '../utils/heikinAshi';

interface ChartWorkspaceProps {
  initialSymbol?: string;
  initialTimeframe?: string;
}

export const ChartWorkspace: FC<ChartWorkspaceProps> = ({
  initialSymbol = 'EURUSD',
  initialTimeframe = 'D1',
}) => {
  const [symbol, setSymbol] = useState<string>(initialSymbol);
  const [timeframe, setTimeframe] = useState<string>(initialTimeframe);
  const [bars, setBars] = useState<HistoricalBar[]>([]);
  const [metrics, setMetrics] = useState<AssetMetricsResponse | null>(null);
  const [isHeikinAshi, setIsHeikinAshi] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [syncStatus, setSyncStatus] = useState<string>('IDLE');
  const [error, setError] = useState<string | null>(null);

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const pollTimerRef = useRef<number | null>(null);

  const loadData = useCallback(async (sym: string, tf: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const [histData, metricData] = await Promise.all([
        assetsApi.getHistory(sym, tf).catch(() => ({ bars: [] })),
        assetsApi.getMetrics(sym, tf).catch(() => null),
      ]);
      setBars(histData.bars || []);
      setMetrics(metricData);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch asset data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initialize Lightweight Charts canvas
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#18181b' }, textColor: '#a1a1aa' },
      grid: { vertLines: { color: '#27272a' }, horzLines: { color: '#27272a' } },
      timeScale: { borderColor: '#3f3f46', timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: '#3f3f46' },
      width: chartContainerRef.current.clientWidth || 600,
      height: 380,
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981', downColor: '#ef4444', borderVisible: false,
      wickUpColor: '#10b981', wickDownColor: '#ef4444',
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    loadData(symbol, timeframe);
  }, [symbol, timeframe, loadData]);

  // Update chart series data when bars or Heikin-Ashi view toggles
  useEffect(() => {
    if (!seriesRef.current || bars.length === 0) return;

    const candleData = (isHeikinAshi ? computeHeikinAshi(bars) : bars).map((b) => {
      const isHA = 'ha_open' in b;
      return {
        time: Number(b.time) as UTCTimestamp,
        open: isHA ? (b as HeikinAshiBar).ha_open : b.open,
        high: isHA ? (b as HeikinAshiBar).ha_high : b.high,
        low: isHA ? (b as HeikinAshiBar).ha_low : b.low,
        close: isHA ? (b as HeikinAshiBar).ha_close : b.close,
      };
    });

    candleData.sort((a, b) => Number(a.time) - Number(b.time));
    const deduped = candleData.filter((item, idx, arr) => idx === 0 || item.time !== arr[idx - 1].time);

    seriesRef.current.setData(deduped);
    chartRef.current?.timeScale().fitContent();
  }, [bars, isHeikinAshi]);

  // Historical sync flow with status polling
  const handleSync = async () => {
    setIsSyncing(true);
    setSyncStatus('IN_PROGRESS');
    setError(null);
    try {
      await assetsApi.triggerSync({ symbol, timeframe });
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number }; message?: string };
      if (axiosErr.response?.status !== 409) {
        setError(axiosErr.message || 'Sync failed');
        setIsSyncing(false);
        setSyncStatus('FAILED');
        return;
      }
    }

    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = window.setInterval(async () => {
      try {
        const stat = await assetsApi.getSyncStatus();
        setSyncStatus(stat.status);
        if (stat.status === 'COMPLETED') {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          setIsSyncing(false);
          await loadData(symbol, timeframe);
        } else if (stat.status === 'FAILED') {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          setIsSyncing(false);
          setError(stat.message || 'Sync failed');
        }
      } catch (pollErr: unknown) {
        if (pollTimerRef.current) clearInterval(pollTimerRef.current);
        setIsSyncing(false);
        const pErr = pollErr as { message?: string };
        setError(pErr.message || 'Failed to poll sync status');
      }
    }, 600);
  };

  const metricRows = [
    { label: 'Kalman Dynamic Beta:', testId: 'kalman-beta-val', val: metrics?.kalman_beta != null ? metrics.kalman_beta.toFixed(4) : '—', color: 'text-emerald-400 font-bold' },
    { label: 'Kalman Alpha:', testId: 'kalman-alpha-val', val: metrics?.kalman_alpha != null ? metrics.kalman_alpha.toFixed(4) : '—', color: 'text-zinc-200' },
    { label: 'Yang-Zhang Vol (Ann):', testId: 'yang-zhang-vol-val', val: metrics?.yang_zhang_vol_annualized != null ? `${(metrics.yang_zhang_vol_annualized * 100).toFixed(2)}%` : '—', color: 'text-zinc-300' },
    { label: 'Amihud Sensitivity:', testId: 'amihud-val', val: metrics?.amihud_sensitivity != null ? metrics.amihud_sensitivity.toExponential(2) : '—', color: 'text-zinc-300' },
    { label: 'VWAP:', testId: 'vwap-val', val: metrics?.vwap != null ? metrics.vwap.toFixed(2) : '—', color: 'text-zinc-300' },
    { label: 'Roll Spread:', testId: 'roll-spread-val', val: metrics?.roll_spread_pct != null ? `${(metrics.roll_spread_pct * 100).toFixed(3)}%` : '—', color: 'text-zinc-300' },
    { label: 'OLS Beta:', testId: 'ols-beta-val', val: metrics?.ols_beta != null ? metrics.ols_beta.toFixed(3) : '—', color: 'text-zinc-300' },
    { label: 'Relative Strength:', testId: 'rel-strength-val', val: metrics?.relative_strength != null ? metrics.relative_strength.toFixed(3) : '—', color: 'text-zinc-300' },
  ];

  return (
    <div data-testid="chart-workspace" className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-5 flex flex-col gap-4">
      {/* Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-3">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <label htmlFor="symbol-select" className="text-xs font-semibold text-zinc-400">Symbol:</label>
            <select
              id="symbol-select"
              data-testid="asset-selector"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 text-zinc-100 rounded px-2.5 py-1 text-xs font-semibold"
            >
              {['EURUSD', 'AAPL', 'MSFT', 'NVDA', 'AMZN', 'SPY'].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <label htmlFor="tf-select" className="text-xs font-semibold text-zinc-400">TF:</label>
            <select
              id="tf-select"
              data-testid="timeframe-selector"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="bg-zinc-800 border border-zinc-700 text-zinc-100 rounded px-2 py-1 text-xs font-semibold"
            >
              {['M15', 'H1', 'H4', 'D1', 'W1'].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="heikin-ashi-toggle"
            onClick={() => setIsHeikinAshi((prev) => !prev)}
            className={`px-3 py-1 rounded text-xs font-semibold border transition-colors cursor-pointer ${
              isHeikinAshi ? 'bg-emerald-950/80 border-emerald-500 text-emerald-300' : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200'
            }`}
          >
            {isHeikinAshi ? 'Heikin-Ashi: ON' : 'Heikin-Ashi: OFF'}
          </button>

          <button
            type="button"
            data-testid="sync-rates-btn"
            disabled={isSyncing}
            onClick={handleSync}
            className="px-3 py-1 rounded text-xs font-semibold bg-zinc-800 border border-zinc-700 text-zinc-200 hover:bg-zinc-700 disabled:opacity-50 transition-colors cursor-pointer"
          >
            {isSyncing ? 'Syncing...' : 'Sync Rates'}
          </button>
          {syncStatus !== 'IDLE' && (
            <span data-testid="sync-status-badge" className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
              {syncStatus}
            </span>
          )}
        </div>
      </div>

      {error && (
        <div data-testid="chart-error" className="px-3 py-2 text-xs rounded bg-rose-950/60 border border-rose-800 text-rose-300">
          {error}
        </div>
      )}

      {/* Main Chart Body */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 items-stretch">
        <div className="lg:col-span-3 relative min-h-[380px] bg-zinc-950 border border-zinc-800 rounded flex flex-col justify-center">
          {isLoading && (
            <div data-testid="chart-loading" className="absolute inset-0 bg-zinc-950/70 z-10 flex items-center justify-center text-xs text-zinc-400">
              Loading OHLC rates...
            </div>
          )}
          {bars.length === 0 && !isLoading && (
            <div data-testid="chart-empty" className="text-center text-xs text-zinc-500 py-20">
              No historical rates loaded. Click &ldquo;Sync Rates&rdquo; to fetch bars from MetaTrader 5.
            </div>
          )}
          <div ref={chartContainerRef} data-testid="tradingview-canvas" className="w-full h-[380px]" />
        </div>

        {/* Metrics Panel */}
        <div data-testid="metrics-panel" className="lg:col-span-1 bg-zinc-950 border border-zinc-800 rounded p-3 flex flex-col gap-3 text-xs">
          <div className="border-b border-zinc-800 pb-1.5 flex items-center justify-between">
            <span className="font-semibold text-zinc-300">Institutional Metrics</span>
            <span
              data-testid="kalman-trend-badge"
              className={`text-[10px] px-1.5 py-0.5 rounded border uppercase font-mono ${
                metrics?.kalman_trend === 'EXPANDING' ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800' :
                metrics?.kalman_trend === 'DECAYING' ? 'bg-rose-950/60 text-rose-400 border-rose-800' :
                'bg-zinc-800 text-zinc-300 border-zinc-700'
              }`}
            >
              {metrics?.kalman_trend || 'NEUTRAL'}
            </span>
          </div>

          <div className="flex flex-col gap-2">
            {metricRows.map((row) => (
              <div key={row.testId} className="flex justify-between items-center py-1 border-b border-zinc-900">
                <span className="text-zinc-400">{row.label}</span>
                <span data-testid={row.testId} className={`font-mono ${row.color}`}>{row.val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
