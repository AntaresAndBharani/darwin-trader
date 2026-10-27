import { FC, useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickSeries,
  AreaSeries,
  createSeriesMarkers,
  ColorType,
  UTCTimestamp,
  SeriesMarker,
  Time,
} from 'lightweight-charts';
import {
  yahooApi,
  YahooTicker,
  YahooFilterFacets,
  YahooStrategyDefinition,
  YahooPortfolioBacktestResponse,
  YahooAssetBacktestResult,
  YahooTradeRecord,
  YahooBacktestStatusResponse,
} from '../api/yahoo';
import { computeHeikinAshi, HeikinAshiBar } from '../utils/heikinAshi';

// Offline fallback mirroring `YAHOO_STRATEGY_CATALOG` in strategy_engine/yahoo_backtester.py
const DEFAULT_STRATEGIES_FALLBACK: YahooStrategyDefinition[] = [
  {
    id: 'darwin_trend',
    name: 'Darwin Trend ATR',
    description: 'EMA Trend Crossover + RSI Momentum + ATR Volatility Dynamic SL/TP.',
    parameters: [
      {
        key: 'fast_ema_period',
        label: 'Fast EMA Period',
        type: 'int',
        default: 12,
        min_value: 2,
        max_value: 200,
        step: 1,
        description: 'Short-term exponential moving average lookback period.',
      },
      {
        key: 'slow_ema_period',
        label: 'Slow EMA Period',
        type: 'int',
        default: 26,
        min_value: 5,
        max_value: 400,
        step: 1,
        description: 'Long-term exponential moving average lookback period.',
      },
      {
        key: 'rsi_period',
        label: 'RSI Period',
        type: 'int',
        default: 14,
        min_value: 2,
        max_value: 100,
        step: 1,
        description: 'Relative Strength Index lookback period.',
      },
      {
        key: 'rsi_overbought',
        label: 'RSI Overbought',
        type: 'float',
        default: 70.0,
        min_value: 51.0,
        max_value: 95.0,
        step: 1.0,
        description: 'Upper RSI threshold capping bullish entries.',
      },
      {
        key: 'rsi_oversold',
        label: 'RSI Oversold',
        type: 'float',
        default: 30.0,
        min_value: 5.0,
        max_value: 49.0,
        step: 1.0,
        description: 'Lower RSI threshold capping bearish entries.',
      },
      {
        key: 'atr_period',
        label: 'ATR Period',
        type: 'int',
        default: 14,
        min_value: 2,
        max_value: 100,
        step: 1,
        description: 'Average True Range volatility lookback period.',
      },
      {
        key: 'atr_multiplier',
        label: 'ATR Stop Multiplier',
        type: 'float',
        default: 2.0,
        min_value: 0.5,
        max_value: 10.0,
        step: 0.1,
        description: 'Stop-loss distance in multiples of ATR (TP = 1.8x SL).',
      },
    ],
  },
  {
    id: 'darwinx_zero_trader',
    name: 'DarwinX Zero Trader',
    description:
      'Multi-Timeframe 1W Heikin-Ashi Pullback-Reversal Filter with Quad-MA Trend Alignment and 3-Stage Position Lifecycle.',
    parameters: [
      {
        key: 'ema_period',
        label: 'Fast EMA Period',
        type: 'int',
        default: 21,
        min_value: 2,
        max_value: 150,
        step: 1,
        description: 'Fast EMA period in the Quad-MA stack.',
      },
      {
        key: 'sma_fast_period',
        label: 'Fast SMA Period',
        type: 'int',
        default: 50,
        min_value: 5,
        max_value: 250,
        step: 1,
        description: 'Fast SMA period in the Quad-MA stack.',
      },
      {
        key: 'sma_mid_period',
        label: 'Mid SMA Period',
        type: 'int',
        default: 100,
        min_value: 10,
        max_value: 350,
        step: 1,
        description: 'Medium SMA period in the Quad-MA stack.',
      },
      {
        key: 'sma_slow_period',
        label: 'Slow Baseline SMA Period',
        type: 'int',
        default: 200,
        min_value: 20,
        max_value: 500,
        step: 5,
        description: 'Anchor trend SMA period; price and all faster MAs must exceed this level.',
      },
      {
        key: 'stop_loss_pct',
        label: 'Stop Loss (%)',
        type: 'float',
        default: 10.0,
        min_value: 0.5,
        max_value: 50.0,
        step: 0.5,
        description: 'Initial protective stop-loss percentage below entry.',
      },
      {
        key: 'partial_tp_pct',
        label: 'Partial Take Profit TP1 (%)',
        type: 'float',
        default: 5.0,
        min_value: 0.5,
        max_value: 100.0,
        step: 0.5,
        description: 'First target gain percentage to scale out partial profit and ratchet stop to break-even.',
      },
      {
        key: 'partial_fraction',
        label: 'Partial Scale-Out Fraction',
        type: 'float',
        default: 0.5,
        min_value: 0.1,
        max_value: 0.9,
        step: 0.05,
        description: 'Fraction of position closed at TP1 (0.5 = 50%).',
      },
    ],
  },
];

function buildDefaultParamsMap(strategy: YahooStrategyDefinition): Record<string, number | string> {
  const map: Record<string, number | string> = {};
  for (const p of strategy.parameters) {
    map[p.key] = p.default;
  }
  return map;
}

function formatNumber(val: number | null | undefined, digits = 2, fallback = '0.00'): string {
  if (val == null || Number.isNaN(val) || !Number.isFinite(val)) return fallback;
  return val.toFixed(digits);
}

function formatCurrency(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val) || !Number.isFinite(val)) return '$0.00';
  const sign = val < 0 ? '-' : '';
  return `${sign}$${Math.abs(val).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatSignedPct(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val) || !Number.isFinite(val)) return '0.00%';
  const prefix = val > 0 ? '+' : '';
  return `${prefix}${val.toFixed(2)}%`;
}

export const StrategyLifecycleWorkspace: FC = () => {
  // Catalog & Tickers state
  const [strategies, setStrategies] = useState<YahooStrategyDefinition[]>(
    DEFAULT_STRATEGIES_FALLBACK,
  );
  const [tickers, setTickers] = useState<YahooTicker[]>([]);
  const [facets, setFacets] = useState<YahooFilterFacets>({
    markets: [],
    sectors: [],
    industries: [],
  });

  // Mode & Asset Selection state
  const [executionMode, setExecutionMode] = useState<'single' | 'batch'>('single');
  const [tickerSearch, setTickerSearch] = useState<string>('');
  const [singleSymbol, setSingleSymbol] = useState<string>('');
  const [batchMarket, setBatchMarket] = useState<string>('');
  const [batchSector, setBatchSector] = useState<string>('');
  const [batchSymbols, setBatchSymbols] = useState<string[]>([]);

  // Strategy & Parameters state
  const [selectedStrategyId, setSelectedStrategyId] = useState<string>('darwin_trend');
  const [timeframe, setTimeframe] = useState<'D1' | 'W1' | 'MN1'>('D1');
  const [initialBalance, setInitialBalance] = useState<number>(10000);
  const [riskPerTradePct, setRiskPerTradePct] = useState<number>(20);
  const [fromDate, setFromDate] = useState<string>('');
  const [toDate, setToDate] = useState<string>('');
  const [strategyParams, setStrategyParams] = useState<Record<string, number | string>>(() =>
    buildDefaultParamsMap(DEFAULT_STRATEGIES_FALLBACK[0]),
  );

  // Results & UI state
  const [backtestResult, setBacktestResult] = useState<YahooPortfolioBacktestResponse | null>(null);
  const [focusedSymbol, setFocusedSymbol] = useState<string | null>(null);
  const [chartMode, setChartMode] = useState<'equity' | 'price'>('equity');
  const [isHeikinAshi, setIsHeikinAshi] = useState<boolean>(false);
  const [tradeLogScope, setTradeLogScope] = useState<'focused' | 'all'>('all');

  const [isLoadingInit, setIsLoadingInit] = useState<boolean>(false);
  const [isRunningBacktest, setIsRunningBacktest] = useState<boolean>(false);
  const [backtestProgress, setBacktestProgress] = useState<YahooBacktestStatusResponse | null>(
    null,
  );
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);

  // Chart refs
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const activeSeriesRef = useRef<ISeriesApi<'Area'> | ISeriesApi<'Candlestick'> | null>(null);

  const activeStrategy = useMemo(
    () => strategies.find((s) => s.id === selectedStrategyId) || strategies[0],
    [strategies, selectedStrategyId],
  );

  // Load strategy catalog and Yahoo Finance tickers on mount
  const loadInitialData = useCallback(async () => {
    setIsLoadingInit(true);
    setError(null);
    try {
      const [stratRes, tickerRes] = await Promise.all([
        yahooApi.getStrategies().catch(() => ({
          strategies: DEFAULT_STRATEGIES_FALLBACK,
        })),
        yahooApi.getTickers({ active_only: true }).catch(() => ({
          total: 0,
          tickers: [],
          facets: { markets: [], sectors: [], industries: [] },
        })),
      ]);

      if (stratRes.strategies && stratRes.strategies.length > 0) {
        setStrategies(stratRes.strategies);
      }

      const loadedTickers = tickerRes.tickers || [];
      setTickers(loadedTickers);
      if (tickerRes.facets) {
        setFacets(tickerRes.facets);
      }
      if (loadedTickers.length > 0) {
        // Prioritize tickers with actual downloaded OHLCV bars over 0-bar stub tickers
        const tickersWithBars = loadedTickers.filter((t) => (t.price_bars_count ?? 0) > 0);
        const defaultPool = tickersWithBars.length > 0 ? tickersWithBars : loadedTickers;
        setSingleSymbol((prev) => prev || defaultPool[0].symbol);
        setBatchSymbols((prev) =>
          prev.length > 0 ? prev : defaultPool.slice(0, 3).map((t) => t.symbol),
        );
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to initialize Strategy Lifecycle');
    } finally {
      setIsLoadingInit(false);
    }
  }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Live elapsed timer and status polling while a backtest is running
  useEffect(() => {
    if (!isRunningBacktest) return;

    const startedAt = Date.now();
    let isCancelled = false;

    const elapsedInterval = window.setInterval(() => {
      if (!isCancelled) {
        setElapsedSeconds((Date.now() - startedAt) / 1000);
      }
    }, 100);

    let isPolling = false;
    const pollStatus = async () => {
      // Skip overlapping polls when a status request outlives the poll interval
      if (isPolling) return;
      isPolling = true;
      try {
        if (typeof yahooApi.getBacktestStatus !== 'function') return;
        const statusRes = await yahooApi.getBacktestStatus();
        // Only accept RUNNING snapshots: a COMPLETED/FAILED status is left over from the
        // previous run until the server picks up this request, and would flash a stale 100%.
        if (!isCancelled && statusRes && statusRes.status === 'RUNNING') {
          setBacktestProgress(statusRes);
        }
      } catch {
        // Ignore transient status polling failures while backtest is in flight
      } finally {
        isPolling = false;
      }
    };

    const pollInterval = window.setInterval(pollStatus, 200);

    return () => {
      isCancelled = true;
      window.clearInterval(elapsedInterval);
      window.clearInterval(pollInterval);
    };
  }, [isRunningBacktest]);

  // Handle strategy change -> reset strategy-specific params to that strategy's defaults
  const handleSelectStrategy = (newStrategyId: string) => {
    setSelectedStrategyId(newStrategyId);
    const found = strategies.find((s) => s.id === newStrategyId);
    if (found) {
      setStrategyParams(buildDefaultParamsMap(found));
    }
  };

  // Reset all parameters (shared + strategy-specific) to defaults
  const handleResetDefaults = () => {
    setTimeframe('D1');
    setInitialBalance(10000);
    setRiskPerTradePct(20);
    setFromDate('');
    setToDate('');
    if (activeStrategy) {
      setStrategyParams(buildDefaultParamsMap(activeStrategy));
    }
    setError(null);
  };

  const handleParamChange = (key: string, rawVal: string, type: 'int' | 'float' | 'select') => {
    if (type === 'select') {
      setStrategyParams((prev) => ({ ...prev, [key]: rawVal }));
      return;
    }
    const parsed = type === 'int' ? parseInt(rawVal, 10) : parseFloat(rawVal);
    setStrategyParams((prev) => ({
      ...prev,
      [key]: Number.isNaN(parsed) ? 0 : parsed,
    }));
  };

  // Filtered tickers for selector
  const filteredTickers = useMemo(() => {
    return tickers.filter((t) => {
      if (executionMode === 'batch') {
        if (batchMarket && t.market !== batchMarket) return false;
        if (batchSector && t.sector !== batchSector) return false;
      }
      if (tickerSearch.trim()) {
        const q = tickerSearch.trim().toLowerCase();
        const matchSym = t.symbol.toLowerCase().includes(q);
        const matchName = (t.name || '').toLowerCase().includes(q);
        const matchSector = (t.sector || '').toLowerCase().includes(q);
        return matchSym || matchName || matchSector;
      }
      return true;
    });
  }, [tickers, executionMode, batchMarket, batchSector, tickerSearch]);

  const handleToggleBatchSymbol = (sym: string) => {
    setBatchSymbols((prev) =>
      prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym],
    );
  };

  const handleSelectAllFiltered = () => {
    setBatchSymbols(filteredTickers.map((t) => t.symbol));
  };

  const handleClearBatchSelection = () => {
    setBatchSymbols([]);
  };

  // Run Backtest
  const handleRunBacktest = async () => {
    setError(null);

    if (executionMode === 'single' && !singleSymbol.trim()) {
      setError('Please select a Yahoo Finance ticker to backtest.');
      return;
    }
    if (
      executionMode === 'batch' &&
      batchSymbols.length === 0 &&
      !batchMarket &&
      !batchSector
    ) {
      setError('Please select at least one ticker or a Market/Sector filter for batch backtesting.');
      return;
    }

    const targetSymbols =
      executionMode === 'single'
        ? [singleSymbol]
        : batchSymbols.length > 0
          ? batchSymbols
          : filteredTickers.map((t) => t.symbol);
    const initialTotal = Math.max(1, targetSymbols.length);
    const firstSym = targetSymbols[0] || singleSymbol || 'Portfolio';

    setElapsedSeconds(0);
    setBacktestProgress({
      status: 'RUNNING',
      strategy_id: selectedStrategyId,
      strategy_name: activeStrategy?.name || selectedStrategyId,
      timeframe,
      total_symbols: initialTotal,
      completed_symbols: 0,
      current_symbol: firstSym,
      progress_pct: 0,
      elapsed_ms: 0,
      message: `Evaluating 1 / ${initialTotal} tickers — ${firstSym}...`,
    });
    setIsRunningBacktest(true);

    try {
      const payload =
        executionMode === 'single'
          ? {
              strategy_id: selectedStrategyId,
              symbols: [singleSymbol],
              timeframe,
              from_date: fromDate || null,
              to_date: toDate || null,
              initial_balance: initialBalance,
              risk_per_trade_pct: riskPerTradePct,
              strategy_params: strategyParams,
            }
          : {
              strategy_id: selectedStrategyId,
              symbols: batchSymbols.length > 0 ? batchSymbols : [],
              market: batchSymbols.length === 0 ? batchMarket || null : null,
              sector: batchSymbols.length === 0 ? batchSector || null : null,
              timeframe,
              from_date: fromDate || null,
              to_date: toDate || null,
              initial_balance: initialBalance,
              risk_per_trade_pct: riskPerTradePct,
              strategy_params: strategyParams,
            };

      const res = await yahooApi.runBacktest(payload);
      setBacktestResult(res);

      if (res.asset_results.length === 1) {
        setFocusedSymbol(res.asset_results[0].symbol);
      } else {
        // In multi-asset mode, start on Portfolio Aggregate view for KPIs/Equity curve
        setFocusedSymbol(null);
      }
    } catch (err: unknown) {
      const axiosDetail = (err as { response?: { data?: { detail?: string } } })?.response?.data
        ?.detail;
      setError(
        axiosDetail || (err instanceof Error ? err.message : 'Backtest execution failed'),
      );
    } finally {
      setIsRunningBacktest(false);
    }
  };

  // Determine the currently inspected asset (for Single Asset mode, drilled-down asset, or Price chart fallback)
  const focusedAssetResult: YahooAssetBacktestResult | null = useMemo(() => {
    if (!backtestResult || !backtestResult.asset_results || backtestResult.asset_results.length === 0)
      return null;
    if (focusedSymbol) {
      return (
        backtestResult.asset_results.find((a) => a.symbol === focusedSymbol) ||
        backtestResult.asset_results[0]
      );
    }
    if (backtestResult.asset_results.length === 1) {
      return backtestResult.asset_results[0];
    }
    return null;
  }, [backtestResult, focusedSymbol]);

  // For Price & Markers chart mode, we always need a concrete asset
  const priceChartAssetResult: YahooAssetBacktestResult | null = useMemo(() => {
    if (focusedAssetResult) return focusedAssetResult;
    if (!backtestResult || !backtestResult.asset_results || backtestResult.asset_results.length === 0)
      return null;
    return (
      backtestResult.asset_results.find((a) => a.status === 'READY') ||
      backtestResult.asset_results[0]
    );
  }, [focusedAssetResult, backtestResult]);

  // Active metrics shown in KPI cards (Focused Asset if selected, otherwise Portfolio Aggregate)
  const activeMetrics = useMemo(() => {
    if (!backtestResult) return null;
    if (focusedAssetResult) return focusedAssetResult.metrics;
    return backtestResult.portfolio_metrics;
  }, [backtestResult, focusedAssetResult]);

  // Active equity curve shown when chartMode === 'equity'
  const activeEquityCurve = useMemo(() => {
    if (!backtestResult) return [];
    if (focusedAssetResult) return focusedAssetResult.equity_curve || [];
    return backtestResult.portfolio_equity_curve || [];
  }, [backtestResult, focusedAssetResult]);

  // Contextual overlay message when the 360px chart has no plotted points
  const chartOverlayMessage: string | null = useMemo(() => {
    if (!backtestResult) {
      return isRunningBacktest
        ? backtestProgress?.message || 'Computing historical strategy backtest...'
        : 'Click "Run Backtest" to plot the Mark-to-Market equity curve and trade execution markers.';
    }
    if (chartMode === 'equity' && activeEquityCurve.length === 0) {
      const sym = focusedAssetResult?.symbol || priceChartAssetResult?.symbol;
      return sym
        ? `No historical price bars available for ${sym} (${focusedAssetResult?.status || 'NO_DATA'}) to compute an equity curve.`
        : 'No historical price bars available in the selected universe to compute an equity curve.';
    }
    if (chartMode === 'price' && (priceChartAssetResult?.bars?.length ?? 0) === 0) {
      const sym = priceChartAssetResult?.symbol || 'selected ticker';
      return `No historical price bars available for ${sym} (${priceChartAssetResult?.status || 'NO_DATA'}).`;
    }
    return null;
  }, [
    backtestResult,
    isRunningBacktest,
    backtestProgress,
    chartMode,
    activeEquityCurve.length,
    focusedAssetResult,
    priceChartAssetResult,
  ]);

  // Initialize Lightweight Charts instance
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#09090b' }, textColor: '#a1a1aa' },
      grid: { vertLines: { color: '#27272a' }, horzLines: { color: '#27272a' } },
      timeScale: { borderColor: '#3f3f46', timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: '#3f3f46' },
      width: chartContainerRef.current.clientWidth || 720,
      height: 360,
    });

    chartRef.current = chart;

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
      activeSeriesRef.current = null;
    };
  }, []);

  // Render chart data whenever backtestResult, chartMode, focusedAssetResult, or isHeikinAshi changes
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    if (activeSeriesRef.current) {
      try {
        chart.removeSeries(activeSeriesRef.current);
      } catch {
        // Ignore if already removed
      }
      activeSeriesRef.current = null;
    }

    if (!backtestResult) return;

    if (chartMode === 'equity') {
      const areaSeries = chart.addSeries(AreaSeries, {
        lineColor: '#10b981',
        topColor: 'rgba(16, 185, 129, 0.35)',
        bottomColor: 'rgba(16, 185, 129, 0.02)',
        lineWidth: 2,
      });
      activeSeriesRef.current = areaSeries;

      const points = activeEquityCurve
        .map((pt) => ({
          time: Number(pt.time) as UTCTimestamp,
          value: Number(pt.equity),
        }))
        .sort((a, b) => Number(a.time) - Number(b.time))
        .filter((item, idx, arr) => idx === 0 || item.time !== arr[idx - 1].time);

      areaSeries.setData(points);
      chart.timeScale().fitContent();
    } else {
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#10b981',
        downColor: '#ef4444',
        borderVisible: false,
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
      });
      activeSeriesRef.current = candleSeries;

      const rawBars = priceChartAssetResult?.bars || [];
      if (rawBars.length === 0) {
        candleSeries.setData([]);
        return;
      }

      const transformed = (isHeikinAshi ? computeHeikinAshi(rawBars) : rawBars)
        .map((b) => {
          const isHA = 'ha_open' in b;
          return {
            time: Number(b.time) as UTCTimestamp,
            open: isHA ? (b as HeikinAshiBar).ha_open : b.open,
            high: isHA ? (b as HeikinAshiBar).ha_high : b.high,
            low: isHA ? (b as HeikinAshiBar).ha_low : b.low,
            close: isHA ? (b as HeikinAshiBar).ha_close : b.close,
          };
        })
        .sort((a, b) => Number(a.time) - Number(b.time))
        .filter((item, idx, arr) => idx === 0 || item.time !== arr[idx - 1].time);

      candleSeries.setData(transformed);

      // Build Buy/Sell entry and exit markers from the asset's trades
      const dateToTime = new Map<string, UTCTimestamp>();
      for (const b of rawBars) {
        dateToTime.set(String(b.date || '').slice(0, 10), Number(b.time) as UTCTimestamp);
      }

      const markers: SeriesMarker<Time>[] = [];
      // Partial scale-outs share their entry with the final close; mark each entry once
      const markedEntries = new Set<string>();
      for (const tr of priceChartAssetResult?.trades || []) {
        const entryDateKey = String(tr.entry_date || '').slice(0, 10);
        const exitDateKey = tr.exit_date ? String(tr.exit_date).slice(0, 10) : '';
        const entryTs = dateToTime.get(entryDateKey);
        const exitTs = exitDateKey ? dateToTime.get(exitDateKey) : undefined;

        if (entryTs !== undefined && !markedEntries.has(entryDateKey)) {
          markedEntries.add(entryDateKey);
          markers.push({
            time: entryTs,
            position: tr.type === 'BUY' ? 'belowBar' : 'aboveBar',
            color: tr.type === 'BUY' ? '#10b981' : '#f59e0b',
            shape: tr.type === 'BUY' ? 'arrowUp' : 'arrowDown',
            text: `${tr.type} @ $${formatNumber(tr.entry_price, 2)}`,
          });
        }
        if (exitTs !== undefined) {
          const pnlVal = tr.pnl ?? 0;
          markers.push({
            time: exitTs,
            position: 'aboveBar',
            color: pnlVal >= 0 ? '#34d399' : '#f87171',
            shape: 'circle',
            text: `${tr.reason || 'Exit'} (${pnlVal >= 0 ? '+' : ''}$${formatNumber(tr.pnl, 0, '0')})`,
          });
        }
      }

      markers.sort((a, b) => Number(a.time) - Number(b.time));
      createSeriesMarkers(candleSeries, markers);
      chart.timeScale().fitContent();
    }
  }, [backtestResult, chartMode, activeEquityCurve, priceChartAssetResult, isHeikinAshi]);

  // Trades to display in the Trade Execution Log
  const displayedTrades: YahooTradeRecord[] = useMemo(() => {
    if (!backtestResult || !backtestResult.asset_results) return [];
    if (focusedAssetResult && tradeLogScope === 'focused') {
      return focusedAssetResult.trades || [];
    }
    return backtestResult.asset_results.flatMap((a) => a.trades || []);
  }, [backtestResult, focusedAssetResult, tradeLogScope]);

  const handleDrillDownAsset = (sym: string) => {
    setFocusedSymbol(sym);
    setTradeLogScope('focused');
  };

  return (
    <div data-testid="strategy-lifecycle-workspace" className="flex flex-col gap-6">
      {/* Top Banner */}
      <div className="bg-zinc-900/70 border border-zinc-800 rounded-lg p-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 className="text-lg font-bold text-white">
              Strategy Lifecycle &amp; Historical Backtest Control Panel
            </h2>
            <span
              data-testid="strategy-datasource-badge"
              className="text-[11px] font-mono px-2.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-700/80 text-emerald-300"
            >
              Data Source: Yahoo Finance SQLite
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-1">
            Configure shared capital &amp; strategy-specific parameters, execute on-demand backtests across single or multi-asset Yahoo Finance universes, and inspect Mark-to-Market equity curves &amp; trade logs.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="strategy-reset-defaults-btn"
            onClick={handleResetDefaults}
            className="px-3 py-1.5 rounded text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition-colors cursor-pointer"
          >
            Reset to Defaults
          </button>
          <button
            type="button"
            data-testid="strategy-run-backtest-btn"
            disabled={isRunningBacktest}
            onClick={handleRunBacktest}
            className="px-4 py-1.5 rounded text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-zinc-950 disabled:opacity-50 transition-colors cursor-pointer"
          >
            {isRunningBacktest ? 'Running Backtest...' : 'Run Backtest'}
          </button>
        </div>
      </div>

      {error && (
        <div
          data-testid="strategy-error-banner"
          className="px-3.5 py-2.5 text-xs rounded bg-rose-950/70 border border-rose-800 text-rose-200 font-medium"
        >
          {error}
        </div>
      )}

      {/* Main Split Grid: Left Control Panel (4 cols) + Right Results Dashboard (8 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Control Panel */}
        <aside
          data-testid="strategy-control-panel"
          className="lg:col-span-4 bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 flex flex-col gap-5"
        >
          {/* 1. Asset Universe Mode & Selection */}
          <div className="flex flex-col gap-3 border-b border-zinc-800 pb-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-zinc-300">
                1. Yahoo Asset Selection
              </span>
              <div className="flex rounded bg-zinc-950 p-0.5 border border-zinc-800">
                <button
                  type="button"
                  data-testid="mode-single-btn"
                  onClick={() => setExecutionMode('single')}
                  className={`px-2.5 py-1 text-[11px] font-semibold rounded transition-colors cursor-pointer ${
                    executionMode === 'single'
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/70'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  Single Asset
                </button>
                <button
                  type="button"
                  data-testid="mode-batch-btn"
                  onClick={() => setExecutionMode('batch')}
                  className={`px-2.5 py-1 text-[11px] font-semibold rounded transition-colors cursor-pointer ${
                    executionMode === 'batch'
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/70'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  Multi-Asset / Sector
                </button>
              </div>
            </div>

            <input
              type="text"
              data-testid="strategy-ticker-search"
              value={tickerSearch}
              onChange={(e) => setTickerSearch(e.target.value)}
              placeholder="Filter Yahoo tickers by symbol, name, or sector..."
              className="bg-zinc-950 border border-zinc-700 text-zinc-100 rounded px-2.5 py-1.5 text-xs focus:outline-none focus:border-emerald-500"
            />

            {executionMode === 'single' ? (
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="strategy-single-ticker-select"
                  className="text-[11px] text-zinc-400 font-medium"
                >
                  Target Yahoo Finance Ticker ({filteredTickers.length} available)
                </label>
                <select
                  id="strategy-single-ticker-select"
                  data-testid="strategy-single-ticker-select"
                  value={singleSymbol}
                  onChange={(e) => setSingleSymbol(e.target.value)}
                  className="bg-zinc-950 border border-zinc-700 text-zinc-100 rounded px-2.5 py-1.5 text-xs font-mono"
                >
                  {filteredTickers.length === 0 ? (
                    <option value="">No Yahoo tickers found</option>
                  ) : (
                    filteredTickers.map((t) => (
                      <option key={t.symbol} value={t.symbol}>
                        {t.market ? `${t.market}:${t.symbol}` : t.symbol} — {t.name || t.symbol}
                        {t.price_bars_count != null ? ` (${t.price_bars_count}d)` : ''}
                      </option>
                    ))
                  )}
                </select>
              </div>
            ) : (
              <div className="flex flex-col gap-2.5">
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label
                      htmlFor="strategy-batch-market-select"
                      className="text-[11px] text-zinc-400 block mb-1"
                    >
                      Market Filter
                    </label>
                    <select
                      id="strategy-batch-market-select"
                      data-testid="strategy-batch-market-select"
                      value={batchMarket}
                      onChange={(e) => setBatchMarket(e.target.value)}
                      className="w-full bg-zinc-950 border border-zinc-700 text-zinc-200 rounded px-2 py-1 text-xs"
                    >
                      <option value="">All Markets</option>
                      {facets.markets.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label
                      htmlFor="strategy-batch-sector-select"
                      className="text-[11px] text-zinc-400 block mb-1"
                    >
                      Sector Filter
                    </label>
                    <select
                      id="strategy-batch-sector-select"
                      data-testid="strategy-batch-sector-select"
                      value={batchSector}
                      onChange={(e) => setBatchSector(e.target.value)}
                      className="w-full bg-zinc-950 border border-zinc-700 text-zinc-200 rounded px-2 py-1 text-xs"
                    >
                      <option value="">All Sectors</option>
                      {facets.sectors.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex items-center justify-between text-[11px] text-zinc-400">
                  <span>Selected Tickers ({batchSymbols.length})</span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      data-testid="strategy-batch-select-all-btn"
                      onClick={handleSelectAllFiltered}
                      className="text-emerald-400 hover:underline cursor-pointer"
                    >
                      Select Filtered ({filteredTickers.length})
                    </button>
                    <button
                      type="button"
                      data-testid="strategy-batch-clear-btn"
                      onClick={handleClearBatchSelection}
                      className="text-zinc-400 hover:text-zinc-200 cursor-pointer"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                <div
                  data-testid="strategy-batch-ticker-list"
                  className="max-h-40 overflow-y-auto bg-zinc-950 border border-zinc-800 rounded p-2 flex flex-col gap-1"
                >
                  {filteredTickers.slice(0, 100).map((t) => {
                    const checked = batchSymbols.includes(t.symbol);
                    return (
                      <label
                        key={t.symbol}
                        className="flex items-center justify-between gap-2 text-xs text-zinc-300 px-1.5 py-1 rounded hover:bg-zinc-900 cursor-pointer"
                      >
                        <div className="flex items-center gap-2 truncate">
                          <input
                            type="checkbox"
                            data-testid={`batch-ticker-checkbox-${t.symbol}`}
                            checked={checked}
                            onChange={() => handleToggleBatchSymbol(t.symbol)}
                            className="rounded border-zinc-700 bg-zinc-900 text-emerald-500"
                          />
                          <span className="font-mono font-semibold text-emerald-400">
                            {t.symbol}
                          </span>
                          <span className="text-zinc-400 truncate text-[11px]">{t.name}</span>
                        </div>
                        <span className="text-[10px] text-zinc-500 font-mono">
                          {t.sector || t.market}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* 2. Strategy Selection */}
          <div className="flex flex-col gap-2 border-b border-zinc-800 pb-4">
            <label
              htmlFor="strategy-selector"
              className="text-xs font-bold uppercase tracking-wider text-zinc-300"
            >
              2. Trading Strategy
            </label>
            <select
              id="strategy-selector"
              data-testid="strategy-selector"
              value={selectedStrategyId}
              onChange={(e) => handleSelectStrategy(e.target.value)}
              className="bg-zinc-950 border border-zinc-700 text-emerald-300 font-semibold rounded px-2.5 py-2 text-xs"
            >
              {strategies.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
            {activeStrategy && (
              <p
                data-testid="strategy-description"
                className="text-[11px] text-zinc-400 leading-relaxed bg-zinc-950/60 border border-zinc-800/80 rounded p-2.5"
              >
                {activeStrategy.description}
              </p>
            )}
          </div>

          {/* 3. Shared Simulation Settings */}
          <div className="flex flex-col gap-3 border-b border-zinc-800 pb-4">
            <span className="text-xs font-bold uppercase tracking-wider text-zinc-300">
              3. Simulation &amp; Capital Settings
            </span>

            <div className="grid grid-cols-3 gap-2.5">
              <div>
                <label
                  htmlFor="param-timeframe"
                  className="text-[11px] text-zinc-400 block mb-1"
                >
                  Timeframe
                </label>
                <select
                  id="param-timeframe"
                  data-testid="param-timeframe"
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value as 'D1' | 'W1' | 'MN1')}
                  className="w-full bg-zinc-950 border border-zinc-700 text-zinc-100 rounded px-2 py-1.5 text-xs font-mono"
                >
                  <option value="D1">D1 (Daily)</option>
                  <option value="W1">W1 (Weekly)</option>
                  <option value="MN1">MN1 (Monthly)</option>
                </select>
              </div>

              <div>
                <label
                  htmlFor="param-initial_balance"
                  className="text-[11px] text-zinc-400 block mb-1"
                >
                  Initial Capital ($)
                </label>
                <input
                  id="param-initial_balance"
                  type="number"
                  data-testid="param-initial_balance"
                  min={100}
                  step={500}
                  value={initialBalance}
                  onChange={(e) => setInitialBalance(parseFloat(e.target.value) || 0)}
                  className="w-full bg-zinc-950 border border-zinc-700 text-zinc-100 rounded px-2 py-1.5 text-xs font-mono"
                />
              </div>

              <div>
                <label
                  htmlFor="param-risk_per_trade_pct"
                  className="text-[11px] text-zinc-400 block mb-1"
                >
                  Alloc / Trade (%)
                </label>
                <input
                  id="param-risk_per_trade_pct"
                  type="number"
                  data-testid="param-risk_per_trade_pct"
                  min={0.5}
                  max={100}
                  step={0.5}
                  value={riskPerTradePct}
                  onChange={(e) => setRiskPerTradePct(parseFloat(e.target.value) || 0)}
                  className="w-full bg-zinc-950 border border-zinc-700 text-zinc-100 rounded px-2 py-1.5 text-xs font-mono"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <label htmlFor="param-from_date" className="text-[11px] text-zinc-400 block mb-1">
                  From Date (optional)
                </label>
                <input
                  id="param-from_date"
                  type="date"
                  data-testid="param-from_date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 text-zinc-200 rounded px-2 py-1 text-xs font-mono"
                />
              </div>
              <div>
                <label htmlFor="param-to_date" className="text-[11px] text-zinc-400 block mb-1">
                  To Date (optional)
                </label>
                <input
                  id="param-to_date"
                  type="date"
                  data-testid="param-to_date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 text-zinc-200 rounded px-2 py-1 text-xs font-mono"
                />
              </div>
            </div>
          </div>

          {/* 4. Dynamic Strategy-Specific Parameters */}
          <div className="flex flex-col gap-3">
            <span className="text-xs font-bold uppercase tracking-wider text-zinc-300">
              4. Strategy Parameters ({activeStrategy?.name.split('(')[0].trim()})
            </span>

            <div
              data-testid="strategy-dynamic-params"
              className="grid grid-cols-2 gap-3"
            >
              {activeStrategy?.parameters.map((param) => (
                <div key={param.key} className="flex flex-col gap-1">
                  <label
                    htmlFor={`strategy-param-${param.key}`}
                    title={param.description}
                    className="text-[11px] text-zinc-300 font-medium truncate"
                  >
                    {param.label}
                  </label>
                  <input
                    id={`strategy-param-${param.key}`}
                    type="number"
                    data-testid={`strategy-param-${param.key}`}
                    min={param.min_value ?? undefined}
                    max={param.max_value ?? undefined}
                    step={param.step ?? 1}
                    value={strategyParams[param.key] ?? param.default}
                    onChange={(e) => handleParamChange(param.key, e.target.value, param.type)}
                    className="bg-zinc-950 border border-zinc-700 text-emerald-300 rounded px-2.5 py-1.5 text-xs font-mono focus:outline-none focus:border-emerald-500"
                  />
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* Right Results Dashboard */}
        <section
          data-testid="strategy-results-dashboard"
          className="lg:col-span-8 flex flex-col gap-5"
        >
          {/* Live Backtest Execution Progress Card */}
          {isRunningBacktest && (
            <div
              data-testid="strategy-backtest-progress"
              className="bg-zinc-900/90 border border-emerald-700/70 rounded-lg p-4 flex flex-col gap-3 shadow-lg"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <span
                    aria-hidden="true"
                    className="inline-block w-3.5 h-3.5 rounded-full border-2 border-emerald-400 border-t-transparent animate-spin"
                  />
                  <span className="text-sm font-bold text-emerald-300">
                    Running Strategy Backtest...
                  </span>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700 text-zinc-300">
                    {backtestProgress?.strategy_name || activeStrategy?.name || selectedStrategyId}{' '}
                    ({timeframe})
                  </span>
                </div>
                <div className="flex items-center gap-2 text-xs font-mono">
                  <span
                    data-testid="strategy-elapsed-time"
                    className="px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-800 text-emerald-300"
                  >
                    Elapsed: {elapsedSeconds.toFixed(1)}s
                  </span>
                  <span className="text-zinc-300 font-semibold">
                    {formatNumber(backtestProgress?.progress_pct ?? 0, 0, '0')}%
                  </span>
                </div>
              </div>

              <div className="w-full h-2 bg-zinc-950 border border-zinc-800 rounded-full overflow-hidden">
                <div
                  data-testid="strategy-progress-bar"
                  className="h-full bg-emerald-500 transition-all duration-200"
                  style={{
                    width: `${Math.min(100, Math.max(5, backtestProgress?.progress_pct ?? 5))}%`,
                  }}
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono text-zinc-400">
                <span data-testid="strategy-progress-message">
                  {backtestProgress?.message ||
                    'Evaluating strategy across selected Yahoo Finance universe...'}
                </span>
                <span>
                  {backtestProgress?.completed_symbols ?? 0} /{' '}
                  {backtestProgress?.total_symbols ?? 1} tickers
                </span>
              </div>
            </div>
          )}

          {!backtestResult && !isRunningBacktest && (
            <div
              data-testid="strategy-empty-state"
              className="bg-zinc-900/40 border border-zinc-800/80 rounded-lg p-6 text-center flex flex-col items-center gap-2"
            >
              <div className="text-sm font-semibold text-zinc-300">
                Ready to Run Historical Strategy Backtest on Yahoo Finance Data
              </div>
              <p className="text-xs text-zinc-500 max-w-lg">
                Select a single Yahoo Finance ticker or a multi-asset sector universe on the left, customize your strategy parameters, and click{' '}
                <strong className="text-emerald-400">Run Backtest</strong> to compute full Mark-to-Market equity curves, KPIs, and trade execution logs.
              </p>
              {isLoadingInit && (
                <span className="text-xs text-zinc-400 font-mono">
                  Loading Yahoo Finance strategy catalog...
                </span>
              )}
            </div>
          )}

          {/* Scope Bar when multi-asset results exist */}
          {backtestResult && backtestResult.asset_results.length > 1 && (
            <div
              data-testid="strategy-scope-bar"
              className="bg-zinc-900/80 border border-zinc-800 rounded-lg px-4 py-2.5 flex flex-wrap items-center justify-between gap-2"
            >
              <div className="flex items-center gap-2 text-xs">
                <span className="text-zinc-400">Viewing Metrics &amp; Equity For:</span>
                <span
                  data-testid="strategy-active-scope-label"
                  className="font-mono font-bold text-emerald-400"
                >
                  {focusedAssetResult
                    ? `${focusedAssetResult.symbol} (${focusedAssetResult.name})`
                    : `Portfolio Aggregate (${backtestResult.valid_symbols_count}/${backtestResult.total_symbols_requested} Active Tickers)`}
                </span>
              </div>
              {focusedAssetResult && (
                <button
                  type="button"
                  data-testid="strategy-view-portfolio-btn"
                  onClick={() => setFocusedSymbol(null)}
                  className="px-2.5 py-1 rounded text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-emerald-300 border border-zinc-700 cursor-pointer"
                >
                  &larr; View Portfolio Aggregate
                </button>
              )}
            </div>
          )}

          {/* KPI Summary Cards */}
          {activeMetrics && (
            <div
              data-testid="strategy-kpi-grid"
              className="grid grid-cols-2 sm:grid-cols-4 gap-3"
            >
              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 flex flex-col gap-1">
                <span className="text-[11px] text-zinc-400">Net Profit (MTM)</span>
                <div
                  data-testid="kpi-net-profit"
                  className={`text-base font-mono font-bold ${
                    (activeMetrics.net_profit ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {formatCurrency(activeMetrics.net_profit)}{' '}
                  <span className="text-xs">
                    ({formatSignedPct(activeMetrics.net_profit_pct)})
                  </span>
                </div>
              </div>

              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 flex flex-col gap-1">
                <span className="text-[11px] text-zinc-400">Final Equity (MTM)</span>
                <div
                  data-testid="kpi-final-equity"
                  className="text-base font-mono font-bold text-zinc-100"
                >
                  {formatCurrency(activeMetrics.final_equity)}
                </div>
                <span className="text-[10px] font-mono text-zinc-500">
                  Initial: {formatCurrency(activeMetrics.initial_balance)}
                </span>
              </div>

              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 flex flex-col gap-1">
                <span className="text-[11px] text-zinc-400">Realized / Unrealized PnL</span>
                <div
                  data-testid="kpi-pnl-breakdown"
                  className="text-xs font-mono text-zinc-200 flex flex-col gap-0.5"
                >
                  <span>
                    Realized:{' '}
                    <strong
                      className={
                        (activeMetrics.realized_pnl ?? 0) >= 0
                          ? 'text-emerald-400'
                          : 'text-rose-400'
                      }
                    >
                      {formatCurrency(activeMetrics.realized_pnl)}
                    </strong>
                  </span>
                  <span>
                    Unrealized:{' '}
                    <strong
                      className={
                        (activeMetrics.unrealized_pnl ?? 0) >= 0
                          ? 'text-emerald-400'
                          : 'text-rose-400'
                      }
                    >
                      {formatCurrency(activeMetrics.unrealized_pnl)}
                    </strong>
                  </span>
                </div>
              </div>

              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 flex flex-col gap-1">
                <span className="text-[11px] text-zinc-400">Win Rate &amp; Trades</span>
                <div
                  data-testid="kpi-win-rate"
                  className="text-base font-mono font-bold text-zinc-100"
                >
                  {formatNumber(activeMetrics.win_rate_pct, 1, '0.0')}%
                </div>
                <span className="text-[10px] font-mono text-zinc-400">
                  {activeMetrics.winning_trades ?? 0}W / {activeMetrics.losing_trades ?? 0}L (
                  {activeMetrics.total_trades ?? 0} total)
                </span>
              </div>

              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 flex flex-col gap-1">
                <span className="text-[11px] text-zinc-400">Profit Factor</span>
                <div
                  data-testid="kpi-profit-factor"
                  className="text-base font-mono font-bold text-zinc-100"
                >
                  {formatNumber(activeMetrics.profit_factor, 2)}
                </div>
              </div>

              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 flex flex-col gap-1">
                <span className="text-[11px] text-zinc-400">Max Drawdown</span>
                <div
                  data-testid="kpi-max-drawdown"
                  className="text-base font-mono font-bold text-rose-400"
                >
                  {formatCurrency(activeMetrics.max_drawdown)}{' '}
                  <span className="text-xs">
                    (-{formatNumber(activeMetrics.max_drawdown_pct, 2)}%)
                  </span>
                </div>
              </div>

              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 flex flex-col gap-1">
                <span className="text-[11px] text-zinc-400">Sharpe Ratio</span>
                <div
                  data-testid="kpi-sharpe-ratio"
                  className="text-base font-mono font-bold text-zinc-100"
                >
                  {formatNumber(activeMetrics.sharpe_ratio, 2)}
                </div>
              </div>

              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 flex flex-col gap-1">
                <span className="text-[11px] text-zinc-400">Latest Signal</span>
                {priceChartAssetResult ? (
                  <>
                    <div className="flex items-center gap-1.5">
                      <span
                        data-testid="kpi-latest-signal"
                        className={`text-xs font-mono font-bold px-2 py-0.5 rounded border ${
                          priceChartAssetResult.latest_signal === 'ENTER_LONG'
                            ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                            : priceChartAssetResult.latest_signal === 'ENTER_SHORT'
                              ? 'bg-rose-950 text-rose-300 border-rose-700'
                              : 'bg-zinc-800 text-zinc-300 border-zinc-700'
                        }`}
                      >
                        {priceChartAssetResult.latest_signal}
                      </span>
                      <span className="text-[10px] font-mono text-zinc-400">
                        {priceChartAssetResult.symbol}
                      </span>
                    </div>
                    <span
                      data-testid="kpi-latest-signal-reason"
                      title={priceChartAssetResult.latest_signal_reason}
                      className="text-[10px] text-zinc-400 truncate"
                    >
                      {priceChartAssetResult.latest_signal_reason}
                    </span>
                  </>
                ) : (
                  <span data-testid="kpi-latest-signal" className="text-xs font-mono text-zinc-500">
                    —
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Interactive Chart Card */}
          <div
            data-testid="strategy-chart-card"
            className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 flex flex-col gap-3"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-white">
                  {chartMode === 'equity'
                    ? `Mark-to-Market Equity Curve (${
                        focusedAssetResult ? focusedAssetResult.symbol : 'Portfolio'
                      })`
                    : `Price & Trade Executions (${priceChartAssetResult?.symbol || ''})`}
                </h3>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {chartMode === 'price' &&
                  backtestResult &&
                  backtestResult.asset_results.length > 1 && (
                    <select
                      data-testid="strategy-chart-asset-select"
                      aria-label="Chart Asset Selector"
                      value={priceChartAssetResult?.symbol || ''}
                      onChange={(e) => setFocusedSymbol(e.target.value)}
                      className="bg-zinc-950 border border-zinc-700 text-zinc-200 rounded px-2 py-1 text-xs font-mono"
                    >
                      {backtestResult.asset_results.map((ar) => (
                        <option key={ar.symbol} value={ar.symbol}>
                          {ar.symbol} ({(ar.trades || []).length} trades)
                        </option>
                      ))}
                    </select>
                  )}

                {chartMode === 'price' && (
                  <button
                    type="button"
                    data-testid="strategy-chart-ha-toggle"
                    onClick={() => setIsHeikinAshi((prev) => !prev)}
                    className={`px-2.5 py-1 rounded text-xs font-semibold border transition-colors cursor-pointer ${
                      isHeikinAshi
                        ? 'bg-emerald-950/80 border-emerald-500 text-emerald-300'
                        : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    {isHeikinAshi ? 'Heikin-Ashi: ON' : 'Heikin-Ashi: OFF'}
                  </button>
                )}

                <div className="flex rounded bg-zinc-950 p-0.5 border border-zinc-800">
                  <button
                    type="button"
                    data-testid="chart-mode-equity-btn"
                    onClick={() => setChartMode('equity')}
                    className={`px-3 py-1 text-xs font-semibold rounded transition-colors cursor-pointer ${
                      chartMode === 'equity'
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/70'
                        : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    Equity Curve
                  </button>
                  <button
                    type="button"
                    data-testid="chart-mode-price-btn"
                    onClick={() => setChartMode('price')}
                    className={`px-3 py-1 text-xs font-semibold rounded transition-colors cursor-pointer ${
                      chartMode === 'price'
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-700/70'
                        : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    Price &amp; Trade Markers
                  </button>
                </div>
              </div>
            </div>

            <div className="relative min-h-[360px] bg-zinc-950 border border-zinc-800 rounded">
              <div
                ref={chartContainerRef}
                data-testid="strategy-chart-canvas"
                className="w-full h-[360px]"
              />
              {chartOverlayMessage && (
                <div
                  data-testid="strategy-chart-empty-overlay"
                  className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-zinc-950/85 pointer-events-none"
                >
                  <span className="text-xs font-mono text-zinc-400 max-w-md">
                    {chartOverlayMessage}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Multi-Asset Comparison Table */}
          {backtestResult && backtestResult.asset_results.length > 0 && (
            <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                <div>
                  <h3 className="text-sm font-semibold text-white">
                    Asset Performance Comparison ({backtestResult.asset_results.length}{' '}
                    {backtestResult.asset_results.length === 1 ? 'Ticker' : 'Tickers'})
                  </h3>
                  <p className="text-[11px] text-zinc-400">
                    Click any ticker row to drill down into its individual equity curve, price markers, and trade execution log.
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table
                  data-testid="strategy-comparison-table"
                  className="w-full text-left border-collapse text-xs font-mono"
                >
                  <thead>
                    <tr className="border-b border-zinc-800 text-zinc-400 text-[11px]">
                      <th className="py-2 pr-2">Symbol</th>
                      <th className="py-2 px-2">Sector</th>
                      <th className="py-2 px-2">Status</th>
                      <th className="py-2 px-2">Bars</th>
                      <th className="py-2 px-2">Trades</th>
                      <th className="py-2 px-2">Win Rate</th>
                      <th className="py-2 px-2">Net Profit ($)</th>
                      <th className="py-2 px-2">Return (%)</th>
                      <th className="py-2 px-2">Unrealized</th>
                      <th className="py-2 px-2">Max DD</th>
                      <th className="py-2 px-2">Sharpe</th>
                      <th className="py-2 pl-2">Signal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtestResult.asset_results.map((ar) => {
                      const isFocused = focusedSymbol === ar.symbol;
                      return (
                        <tr
                          key={ar.symbol}
                          data-testid={`comparison-row-${ar.symbol}`}
                          onClick={() => handleDrillDownAsset(ar.symbol)}
                          className={`border-b border-zinc-900 transition-colors cursor-pointer ${
                            isFocused
                              ? 'bg-emerald-950/40 text-white'
                              : 'text-zinc-300 hover:bg-zinc-800/50'
                          }`}
                        >
                          <td className="py-2 pr-2 font-bold text-emerald-400">
                            {ar.symbol}
                          </td>
                          <td className="py-2 px-2 text-zinc-400 font-sans text-[11px]">
                            {ar.sector || '—'}
                          </td>
                          <td className="py-2 px-2">
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded ${
                                ar.status === 'READY'
                                  ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60'
                                  : 'bg-amber-950 text-amber-300 border border-amber-800/60'
                              }`}
                            >
                              {ar.status}
                            </span>
                          </td>
                          <td className="py-2 px-2">{ar.bars_count ?? 0}</td>
                          <td className="py-2 px-2">{ar.metrics?.total_trades ?? 0}</td>
                          <td className="py-2 px-2">
                            {formatNumber(ar.metrics?.win_rate_pct, 1, '0.0')}%
                          </td>
                          <td
                            className={`py-2 px-2 font-semibold ${
                              (ar.metrics?.net_profit ?? 0) >= 0
                                ? 'text-emerald-400'
                                : 'text-rose-400'
                            }`}
                          >
                            {formatCurrency(ar.metrics?.net_profit)}
                          </td>
                          <td
                            className={`py-2 px-2 ${
                              (ar.metrics?.net_profit_pct ?? 0) >= 0
                                ? 'text-emerald-400'
                                : 'text-rose-400'
                            }`}
                          >
                            {formatSignedPct(ar.metrics?.net_profit_pct)}
                          </td>
                          <td className="py-2 px-2">
                            {formatCurrency(ar.metrics?.unrealized_pnl)}
                          </td>
                          <td className="py-2 px-2 text-rose-400">
                            -{formatNumber(ar.metrics?.max_drawdown_pct, 2)}%
                          </td>
                          <td className="py-2 px-2">
                            {formatNumber(ar.metrics?.sharpe_ratio, 2)}
                          </td>
                          <td className="py-2 pl-2">
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                                ar.latest_signal === 'ENTER_LONG'
                                  ? 'bg-emerald-950 text-emerald-300'
                                  : ar.latest_signal === 'ENTER_SHORT'
                                    ? 'bg-rose-950 text-rose-300'
                                    : 'bg-zinc-800 text-zinc-400'
                              }`}
                            >
                              {ar.latest_signal || 'HOLD'}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Detailed Trade Execution Log */}
          {backtestResult && (
            <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 pb-2">
                <h3 className="text-sm font-semibold text-white">
                  Trade Execution Log ({displayedTrades.length} Executions)
                </h3>

                {focusedAssetResult && backtestResult.asset_results.length > 1 && (
                  <button
                    type="button"
                    data-testid="trade-log-scope-toggle"
                    onClick={() =>
                      setTradeLogScope((prev) => (prev === 'focused' ? 'all' : 'focused'))
                    }
                    className="px-2.5 py-1 rounded text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 cursor-pointer"
                  >
                    {tradeLogScope === 'focused'
                      ? `Showing ${focusedAssetResult.symbol} Only (Switch to All)`
                      : 'Showing All Assets (Switch to Focused)'}
                  </button>
                )}
              </div>

              {displayedTrades.length === 0 ? (
                <div
                  data-testid="strategy-trade-log-empty"
                  className="text-xs text-zinc-500 py-6 text-center"
                >
                  No trades triggered for the selected parameters and date range.
                </div>
              ) : (
                <div className="overflow-x-auto max-h-96 overflow-y-auto">
                  <table
                    data-testid="strategy-trade-log-table"
                    className="w-full text-left border-collapse text-xs font-mono"
                  >
                    <thead>
                      <tr className="border-b border-zinc-800 text-zinc-400 text-[11px]">
                        <th className="py-2 pr-2">Symbol</th>
                        <th className="py-2 px-2">Type</th>
                        <th className="py-2 px-2">Entry Date</th>
                        <th className="py-2 px-2">Exit Date</th>
                        <th className="py-2 px-2">Entry ($)</th>
                        <th className="py-2 px-2">Exit ($)</th>
                        <th className="py-2 px-2">Shares</th>
                        <th className="py-2 px-2">PnL ($)</th>
                        <th className="py-2 px-2">PnL (%)</th>
                        <th className="py-2 px-2">Exit Reason</th>
                        <th className="py-2 pl-2">Balance After</th>
                      </tr>
                    </thead>
                    <tbody>
                      {displayedTrades.map((tr, idx) => (
                        <tr
                          key={`${tr.symbol}-${tr.entry_time}-${tr.exit_time}-${idx}`}
                          className="border-b border-zinc-900 text-zinc-300"
                        >
                          <td className="py-1.5 pr-2 font-bold text-emerald-400">
                            {tr.symbol}
                          </td>
                          <td className="py-1.5 px-2">
                            <span
                              className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                                tr.type === 'BUY'
                                  ? 'bg-emerald-950 text-emerald-300'
                                  : 'bg-amber-950 text-amber-300'
                              }`}
                            >
                              {tr.type}
                            </span>
                          </td>
                          <td className="py-1.5 px-2">{tr.entry_date || '—'}</td>
                          <td className="py-1.5 px-2">{tr.exit_date ?? 'Open'}</td>
                          <td className="py-1.5 px-2">${formatNumber(tr.entry_price, 2)}</td>
                          <td className="py-1.5 px-2">${formatNumber(tr.exit_price, 2)}</td>
                          <td className="py-1.5 px-2">{formatNumber(tr.units, 2)}</td>
                          <td
                            className={`py-1.5 px-2 font-semibold ${
                              (tr.pnl ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                            }`}
                          >
                            {formatCurrency(tr.pnl)}
                          </td>
                          <td
                            className={`py-1.5 px-2 ${
                              (tr.pnl_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                            }`}
                          >
                            {formatSignedPct(tr.pnl_pct)}
                          </td>
                          <td className="py-1.5 px-2">
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                              {tr.reason || '—'}
                            </span>
                          </td>
                          <td className="py-1.5 pl-2">
                            {formatCurrency(tr.balance_after)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
};
