import { FC, useState, useEffect, useRef, useCallback } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickSeries,
  ColorType,
  UTCTimestamp,
} from 'lightweight-charts';
import {
  yahooApi,
  YahooTicker,
  YahooFilterFacets,
  YahooPriceBar,
  YahooFundamentalsResponse,
} from '../api/yahoo';
import { computeHeikinAshi, HeikinAshiBar } from '../utils/heikinAshi';

function formatCompactCurrency(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val)) return '—';
  const abs = Math.abs(val);
  if (abs >= 1e12) return `$${(val / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(val / 1e6).toFixed(2)}M`;
  return `$${val.toFixed(2)}`;
}

function formatRatio(val: number | null | undefined, decimals: number = 2): string {
  if (val == null || Number.isNaN(val)) return '—';
  return val.toFixed(decimals);
}

export const YahooWorkspace: FC = () => {
  const [tickers, setTickers] = useState<YahooTicker[]>([]);
  const [totalTickers, setTotalTickers] = useState<number>(0);
  const [facets, setFacets] = useState<YahooFilterFacets>({
    markets: [],
    sectors: [],
    industries: [],
  });

  // Filters
  const [marketFilter, setMarketFilter] = useState<string>('');
  const [sectorFilter, setSectorFilter] = useState<string>('');
  const [industryFilter, setIndustryFilter] = useState<string>('');
  const [activeOnly, setActiveOnly] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Add ticker inputs
  const [newSymbol, setNewSymbol] = useState<string>('');
  const [newName, setNewName] = useState<string>('');

  // Selected ticker & chart state
  const [selectedSymbol, setSelectedSymbol] = useState<string>('');
  const [timeframe, setTimeframe] = useState<string>('D1');
  const [isHeikinAshi, setIsHeikinAshi] = useState<boolean>(false);
  const [bars, setBars] = useState<YahooPriceBar[]>([]);
  const [fundamentals, setFundamentals] = useState<YahooFundamentalsResponse | null>(null);

  // Loading & sync states
  const [isLoadingTickers, setIsLoadingTickers] = useState<boolean>(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const pollTimerRef = useRef<number | null>(null);

  const loadTickers = useCallback(
    async (preserveSelection?: string) => {
      setIsLoadingTickers(true);
      setError(null);
      try {
        const res = await yahooApi.getTickers({
          market: marketFilter || undefined,
          sector: sectorFilter || undefined,
          industry: industryFilter || undefined,
          active_only: activeOnly || undefined,
          search: searchQuery || undefined,
        });
        setTickers(res.tickers || []);
        setTotalTickers(res.total || 0);
        if (res.facets) {
          setFacets(res.facets);
        }
        const target = preserveSelection || selectedSymbol;
        if (res.tickers && res.tickers.length > 0) {
          const exists = res.tickers.some((t) => t.symbol === target);
          if (!target || !exists) {
            setSelectedSymbol(res.tickers[0].symbol);
          }
        } else {
          setSelectedSymbol('');
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load Yahoo Finance tickers');
      } finally {
        setIsLoadingTickers(false);
      }
    },
    [marketFilter, sectorFilter, industryFilter, activeOnly, searchQuery, selectedSymbol],
  );

  const loadSymbolDetail = useCallback(async (sym: string, tf: string) => {
    if (!sym) {
      setBars([]);
      setFundamentals(null);
      return;
    }
    setIsLoadingDetail(true);
    setError(null);
    try {
      const [histRes, fundRes] = await Promise.all([
        yahooApi.getHistory(sym, tf),
        yahooApi.getFundamentals(sym),
      ]);
      setBars(histRes.bars || []);
      setFundamentals(fundRes);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : `Failed to load data for ${sym}`);
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  // Initialize Lightweight Charts canvas
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: '#09090b' }, textColor: '#a1a1aa' },
      grid: { vertLines: { color: '#27272a' }, horzLines: { color: '#27272a' } },
      timeScale: { borderColor: '#3f3f46', timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: '#3f3f46' },
      width: chartContainerRef.current.clientWidth || 640,
      height: 360,
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
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
    loadTickers();
  }, [marketFilter, sectorFilter, industryFilter, activeOnly, searchQuery]);

  useEffect(() => {
    if (selectedSymbol) {
      loadSymbolDetail(selectedSymbol, timeframe);
    }
  }, [selectedSymbol, timeframe, loadSymbolDetail]);

  // Update chart series when bars or Heikin-Ashi toggle changes
  useEffect(() => {
    if (!seriesRef.current) return;
    if (bars.length === 0) {
      seriesRef.current.setData([]);
      return;
    }

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
    const deduped = candleData.filter(
      (item, idx, arr) => idx === 0 || item.time !== arr[idx - 1].time,
    );

    seriesRef.current.setData(deduped);
    chartRef.current?.timeScale().fitContent();
  }, [bars, isHeikinAshi]);

  const handleAddTicker = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = newSymbol.trim();
    if (!trimmed) return;
    setError(null);
    try {
      const created = await yahooApi.createTicker({
        symbol: trimmed,
        name: newName.trim() || undefined,
        active: true,
      });
      setNewSymbol('');
      setNewName('');
      await loadTickers(created.symbol);
      setSelectedSymbol(created.symbol);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add ticker');
    }
  };

  const handleToggleActive = async (ticker: YahooTicker) => {
    setError(null);
    try {
      await yahooApi.updateTicker(ticker.symbol, { active: !ticker.active });
      await loadTickers(ticker.symbol);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update ticker');
    }
  };

  const handleDeleteTicker = async (symbolToDelete: string) => {
    if (!symbolToDelete) return;
    setError(null);
    try {
      await yahooApi.deleteTicker(symbolToDelete);
      await loadTickers();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete ticker');
    }
  };

  const handleSyncSymbol = async (sym?: string) => {
    setIsSyncing(true);
    setError(null);
    setSyncMessage(sym ? `Syncing ${sym}...` : 'Starting batch catch-up sync...');
    try {
      const res = await yahooApi.triggerSync(sym ? { symbol: sym } : {});
      setSyncMessage(res.message);
      if (res.status === 'COMPLETED') {
        setIsSyncing(false);
        await loadTickers(sym || selectedSymbol);
        if (sym || selectedSymbol) {
          await loadSymbolDetail(sym || selectedSymbol, timeframe);
        }
        return;
      }

      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      pollTimerRef.current = window.setInterval(async () => {
        try {
          const stat = await yahooApi.getSyncStatus();
          setSyncMessage(stat.message);
          if (stat.status === 'COMPLETED' || stat.status === 'FAILED') {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            setIsSyncing(false);
            if (stat.status === 'FAILED') {
              setError(stat.message || 'Yahoo Finance sync failed');
            } else {
              await loadTickers(selectedSymbol);
              if (selectedSymbol) {
                await loadSymbolDetail(selectedSymbol, timeframe);
              }
            }
          }
        } catch {
          if (pollTimerRef.current) clearInterval(pollTimerRef.current);
          setIsSyncing(false);
        }
      }, 800);
    } catch (err: unknown) {
      setIsSyncing(false);
      setError(err instanceof Error ? err.message : 'Failed to trigger Yahoo Finance sync');
    }
  };

  const activeTickerObj =
    tickers.find((t) => t.symbol === selectedSymbol) || fundamentals?.ticker || null;
  const latestVal = fundamentals?.latest_valuation || null;
  const valHistory = fundamentals?.valuation_history || [];
  const earningsHistory = fundamentals?.quarterly_earnings || [];

  return (
    <div data-testid="yahoo-workspace" className="flex flex-col gap-5">
      {/* Filter & Ticker Creation Bar */}
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2.5">
            <input
              type="text"
              data-testid="yahoo-search-input"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search symbol or company..."
              className="bg-zinc-950 border border-zinc-700 text-zinc-100 rounded px-3 py-1.5 text-xs w-52 focus:outline-none focus:border-emerald-500"
            />

            <select
              data-testid="yahoo-filter-market"
              aria-label="Market Filter"
              value={marketFilter}
              onChange={(e) => setMarketFilter(e.target.value)}
              className="bg-zinc-950 border border-zinc-700 text-zinc-200 rounded px-2.5 py-1.5 text-xs"
            >
              <option value="">All Markets</option>
              {facets.markets.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>

            <select
              data-testid="yahoo-filter-sector"
              aria-label="Sector Filter"
              value={sectorFilter}
              onChange={(e) => setSectorFilter(e.target.value)}
              className="bg-zinc-950 border border-zinc-700 text-zinc-200 rounded px-2.5 py-1.5 text-xs"
            >
              <option value="">All Sectors</option>
              {facets.sectors.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>

            <select
              data-testid="yahoo-filter-industry"
              aria-label="Industry Filter"
              value={industryFilter}
              onChange={(e) => setIndustryFilter(e.target.value)}
              className="bg-zinc-950 border border-zinc-700 text-zinc-200 rounded px-2.5 py-1.5 text-xs max-w-[200px]"
            >
              <option value="">All Industries</option>
              {facets.industries.map((ind) => (
                <option key={ind} value={ind}>
                  {ind}
                </option>
              ))}
            </select>

            <label className="flex items-center gap-1.5 text-xs text-zinc-300 cursor-pointer select-none">
              <input
                type="checkbox"
                data-testid="yahoo-filter-active"
                checked={activeOnly}
                onChange={(e) => setActiveOnly(e.target.checked)}
                className="rounded border-zinc-700 bg-zinc-950 text-emerald-500"
              />
              <span>Active Only</span>
            </label>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="yahoo-catchup-all-btn"
              disabled={isSyncing}
              onClick={() => handleSyncSymbol(undefined)}
              className="px-3 py-1.5 rounded text-xs font-semibold bg-emerald-950/80 border border-emerald-600 text-emerald-300 hover:bg-emerald-900/80 disabled:opacity-50 transition-colors cursor-pointer"
            >
              {isSyncing ? 'Syncing...' : 'Catch-Up All Active'}
            </button>
          </div>
        </div>

        {/* Add Ticker Form */}
        <form
          onSubmit={handleAddTicker}
          className="flex flex-wrap items-center justify-between gap-2 border-t border-zinc-800/80 pt-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-zinc-400">Add Ticker:</span>
            <input
              type="text"
              data-testid="yahoo-add-symbol-input"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              placeholder="MARKET:SYMBOL (e.g. NASDAQ:AAPL, LSE:SHEL)"
              className="bg-zinc-950 border border-zinc-700 text-zinc-100 rounded px-2.5 py-1 text-xs w-64"
            />
            <input
              type="text"
              data-testid="yahoo-add-name-input"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Company Name (optional)"
              className="bg-zinc-950 border border-zinc-700 text-zinc-100 rounded px-2.5 py-1 text-xs w-48"
            />
            <button
              type="submit"
              data-testid="yahoo-add-ticker-btn"
              className="px-3 py-1 rounded text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors cursor-pointer"
            >
              + Add Ticker
            </button>
          </div>

          {syncMessage && (
            <span
              data-testid="yahoo-sync-status-msg"
              className="text-xs font-mono text-emerald-400 bg-zinc-950 px-2.5 py-1 rounded border border-zinc-800"
            >
              {syncMessage}
            </span>
          )}
        </form>
      </div>

      {error && (
        <div
          data-testid="yahoo-error-banner"
          className="px-3 py-2 text-xs rounded bg-rose-950/60 border border-rose-800 text-rose-300"
        >
          {error}
        </div>
      )}

      {/* Master-Detail Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-5 items-start">
        {/* Left Master Explorer List */}
        <aside
          data-testid="yahoo-ticker-list"
          className="lg:col-span-1 bg-zinc-900/60 border border-zinc-800 rounded-lg p-3 flex flex-col gap-2 max-h-[780px]"
        >
          <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
            <span className="text-xs font-semibold text-zinc-300">Ticker Universe</span>
            <span
              data-testid="yahoo-ticker-count"
              className="text-[11px] font-mono text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded"
            >
              {totalTickers} tickers
            </span>
          </div>

          {isLoadingTickers ? (
            <div className="py-10 text-center text-xs text-zinc-500">Loading tickers...</div>
          ) : tickers.length === 0 ? (
            <div className="py-10 text-center text-xs text-zinc-500">
              No tickers match the active filters.
            </div>
          ) : (
            <div className="overflow-y-auto flex flex-col gap-1 pr-1 max-h-[710px]">
              {tickers.slice(0, 250).map((t) => {
                const isSelected = t.symbol === selectedSymbol;
                return (
                  <button
                    key={t.symbol}
                    type="button"
                    data-testid={`yahoo-ticker-row-${t.symbol}`}
                    onClick={() => setSelectedSymbol(t.symbol)}
                    className={`w-full text-left px-2.5 py-2 rounded border transition-colors flex flex-col gap-0.5 cursor-pointer ${
                      isSelected
                        ? 'bg-emerald-950/50 border-emerald-600/80 text-white'
                        : 'bg-zinc-950/60 border-zinc-800/80 text-zinc-300 hover:bg-zinc-800/60'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-mono font-bold text-xs text-emerald-400">
                        {t.market ? `${t.market}:${t.symbol}` : t.symbol}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.2 rounded font-mono ${
                          t.active
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/60'
                            : 'bg-zinc-800 text-zinc-500'
                        }`}
                      >
                        {t.active ? 'ACTIVE' : 'INACTIVE'}
                      </span>
                    </div>
                    <div className="text-[11px] text-zinc-300 truncate">{t.name || t.symbol}</div>
                    <div className="flex items-center justify-between text-[10px] text-zinc-500">
                      <span className="truncate">{t.sector || 'Unclassified'}</span>
                      {t.price_bars_count != null && t.price_bars_count > 0 && (
                        <span className="font-mono">{t.price_bars_count}d</span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        {/* Right Detail Panel */}
        <div className="lg:col-span-3 flex flex-col gap-5">
          {/* Chart & Ticker Controls Card */}
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 flex flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-3">
              <div>
                <div className="flex items-center gap-2">
                  <h2
                    data-testid="yahoo-selected-symbol-heading"
                    className="text-lg font-bold text-white font-mono"
                  >
                    {activeTickerObj
                      ? activeTickerObj.market
                        ? `${activeTickerObj.market}:${activeTickerObj.symbol}`
                        : activeTickerObj.symbol
                      : selectedSymbol || 'No Ticker Selected'}
                  </h2>
                  {activeTickerObj?.sector && (
                    <span className="text-[11px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                      {activeTickerObj.sector}
                    </span>
                  )}
                  {activeTickerObj?.industry && (
                    <span className="text-[11px] px-2 py-0.5 rounded bg-zinc-950 text-zinc-400 border border-zinc-800">
                      {activeTickerObj.industry}
                    </span>
                  )}
                </div>
                <p className="text-xs text-zinc-400 mt-0.5">
                  {activeTickerObj?.name || 'Select a ticker from the universe explorer'}
                  {activeTickerObj?.min_date && activeTickerObj?.max_date && (
                    <span className="ml-2 font-mono text-zinc-500">
                      ({activeTickerObj.min_date} &rarr; {activeTickerObj.max_date})
                    </span>
                  )}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <select
                  data-testid="yahoo-timeframe-select"
                  aria-label="Yahoo Timeframe"
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="bg-zinc-800 border border-zinc-700 text-zinc-100 rounded px-2.5 py-1 text-xs font-semibold"
                >
                  <option value="D1">D1 (Daily)</option>
                  <option value="W1">W1 (Weekly)</option>
                  <option value="MN1">MN1 (Monthly)</option>
                </select>

                <button
                  type="button"
                  data-testid="yahoo-heikin-ashi-toggle"
                  onClick={() => setIsHeikinAshi((prev) => !prev)}
                  className={`px-3 py-1 rounded text-xs font-semibold border transition-colors cursor-pointer ${
                    isHeikinAshi
                      ? 'bg-emerald-950/80 border-emerald-500 text-emerald-300'
                      : 'bg-zinc-800 border-zinc-700 text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {isHeikinAshi ? 'Heikin-Ashi: ON' : 'Heikin-Ashi: OFF'}
                </button>

                {activeTickerObj && (
                  <>
                    <button
                      type="button"
                      data-testid="yahoo-sync-ticker-btn"
                      disabled={isSyncing}
                      onClick={() => handleSyncSymbol(activeTickerObj.symbol)}
                      className="px-3 py-1 rounded text-xs font-semibold bg-zinc-800 border border-zinc-700 text-emerald-400 hover:bg-zinc-700 disabled:opacity-50 transition-colors cursor-pointer"
                    >
                      {isSyncing ? 'Syncing...' : `Sync ${activeTickerObj.symbol}`}
                    </button>

                    <button
                      type="button"
                      data-testid="yahoo-toggle-active-btn"
                      onClick={() => handleToggleActive(activeTickerObj)}
                      className="px-2.5 py-1 rounded text-xs font-semibold bg-zinc-800 border border-zinc-700 text-zinc-300 hover:bg-zinc-700 transition-colors cursor-pointer"
                    >
                      {activeTickerObj.active ? 'Deactivate' : 'Activate'}
                    </button>

                    <button
                      type="button"
                      data-testid="yahoo-delete-ticker-btn"
                      onClick={() => handleDeleteTicker(activeTickerObj.symbol)}
                      className="px-2.5 py-1 rounded text-xs font-semibold bg-rose-950/60 border border-rose-800 text-rose-300 hover:bg-rose-900/60 transition-colors cursor-pointer"
                    >
                      Delete
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Chart Canvas */}
            <div className="relative min-h-[360px] bg-zinc-950 border border-zinc-800 rounded flex flex-col justify-center">
              {isLoadingDetail && (
                <div className="absolute inset-0 bg-zinc-950/70 z-10 flex items-center justify-center text-xs text-zinc-400">
                  Loading Yahoo Finance OHLCV &amp; fundamentals...
                </div>
              )}
              {bars.length === 0 && !isLoadingDetail && (
                <div
                  data-testid="yahoo-chart-empty"
                  className="text-center text-xs text-zinc-500 py-16"
                >
                  No OHLCV bars stored for {selectedSymbol || 'this ticker'}. Click &ldquo;Sync&rdquo; to download from Yahoo Finance.
                </div>
              )}
              <div
                ref={chartContainerRef}
                data-testid="yahoo-tradingview-canvas"
                className="w-full h-[360px]"
              />
            </div>
          </div>

          {/* Fundamentals & Quarterly Valuation Multiples Panel */}
          <div
            data-testid="yahoo-fundamentals-panel"
            className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 flex flex-col gap-4"
          >
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
              <h3 className="text-sm font-semibold text-zinc-200">
                Fundamentals &amp; Quarterly Valuation Multiples
              </h3>
              {latestVal && (
                <span className="text-xs font-mono text-zinc-400">
                  As of {latestVal.as_of_date} ({latestVal.period_type || 'Q'})
                </span>
              )}
            </div>

            {/* Latest Valuation Summary Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
              {[
                { label: 'Trailing P/E', val: formatRatio(latestVal?.trailing_pe), testId: 'yahoo-val-trailing-pe' },
                { label: 'Forward P/E', val: formatRatio(latestVal?.forward_pe), testId: 'yahoo-val-forward-pe' },
                { label: 'Price / Book', val: formatRatio(latestVal?.pb), testId: 'yahoo-val-pb' },
                { label: 'Price / Sales', val: formatRatio(latestVal?.ps), testId: 'yahoo-val-ps' },
                { label: 'PEG Ratio', val: formatRatio(latestVal?.peg), testId: 'yahoo-val-peg' },
                { label: 'EV / EBITDA', val: formatRatio(latestVal?.ev_ebitda), testId: 'yahoo-val-ev-ebitda' },
                { label: 'EV / Revenue', val: formatRatio(latestVal?.ev_revenue), testId: 'yahoo-val-ev-revenue' },
                { label: 'Market Cap', val: formatCompactCurrency(latestVal?.market_cap), testId: 'yahoo-val-market-cap' },
                { label: 'Enterprise Value', val: formatCompactCurrency(latestVal?.enterprise_value), testId: 'yahoo-val-ev' },
                {
                  label: 'Dividend Yield',
                  val:
                    latestVal?.dividend_yield != null
                      ? `${(latestVal.dividend_yield * 100).toFixed(2)}%`
                      : '—',
                  testId: 'yahoo-val-div-yield',
                },
              ].map((item) => (
                <div
                  key={item.testId}
                  className="bg-zinc-950 border border-zinc-800/80 rounded p-2.5 flex flex-col gap-1"
                >
                  <span className="text-[11px] text-zinc-400">{item.label}</span>
                  <span
                    data-testid={item.testId}
                    className="text-sm font-mono font-semibold text-zinc-100"
                  >
                    {item.val}
                  </span>
                </div>
              ))}
            </div>

            {/* Historical Quarterly Valuation & Earnings Tables */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
              <div className="xl:col-span-2 overflow-x-auto">
                <h4 className="text-xs font-semibold text-zinc-400 mb-2">
                  Historical Valuation History ({valHistory.length} quarters)
                </h4>
                {valHistory.length === 0 ? (
                  <p className="text-xs text-zinc-500 py-4">No quarterly valuation records available.</p>
                ) : (
                  <table
                    data-testid="yahoo-valuation-table"
                    className="w-full text-left border-collapse text-xs font-mono"
                  >
                    <thead>
                      <tr className="border-b border-zinc-800 text-zinc-400 text-[11px]">
                        <th className="py-1.5 pr-2">Date</th>
                        <th className="py-1.5 px-2">Period</th>
                        <th className="py-1.5 px-2">P/E</th>
                        <th className="py-1.5 px-2">Fwd P/E</th>
                        <th className="py-1.5 px-2">P/B</th>
                        <th className="py-1.5 px-2">P/S</th>
                        <th className="py-1.5 px-2">EV/EBITDA</th>
                        <th className="py-1.5 pl-2">Mkt Cap</th>
                      </tr>
                    </thead>
                    <tbody>
                      {valHistory.slice(0, 12).map((row) => (
                        <tr
                          key={`${row.as_of_date}-${row.period_type}`}
                          className="border-b border-zinc-900 text-zinc-300"
                        >
                          <td className="py-1.5 pr-2 text-emerald-400">{row.as_of_date}</td>
                          <td className="py-1.5 px-2">{row.period_type || '—'}</td>
                          <td className="py-1.5 px-2">{formatRatio(row.trailing_pe)}</td>
                          <td className="py-1.5 px-2">{formatRatio(row.forward_pe)}</td>
                          <td className="py-1.5 px-2">{formatRatio(row.pb)}</td>
                          <td className="py-1.5 px-2">{formatRatio(row.ps)}</td>
                          <td className="py-1.5 px-2">{formatRatio(row.ev_ebitda)}</td>
                          <td className="py-1.5 pl-2">{formatCompactCurrency(row.market_cap)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              <div className="xl:col-span-1 overflow-x-auto">
                <h4 className="text-xs font-semibold text-zinc-400 mb-2">
                  Quarterly EPS &amp; Revenue ({earningsHistory.length})
                </h4>
                {earningsHistory.length === 0 ? (
                  <p className="text-xs text-zinc-500 py-4">No quarterly earnings records available.</p>
                ) : (
                  <table
                    data-testid="yahoo-earnings-table"
                    className="w-full text-left border-collapse text-xs font-mono"
                  >
                    <thead>
                      <tr className="border-b border-zinc-800 text-zinc-400 text-[11px]">
                        <th className="py-1.5 pr-2">Date</th>
                        <th className="py-1.5 px-2">EPS</th>
                        <th className="py-1.5 pl-2">Revenue</th>
                      </tr>
                    </thead>
                    <tbody>
                      {earningsHistory.slice(0, 12).map((er) => (
                        <tr key={er.date} className="border-b border-zinc-900 text-zinc-300">
                          <td className="py-1.5 pr-2 text-emerald-400">{er.date}</td>
                          <td className="py-1.5 px-2">
                            {er.quarterly_eps != null ? `$${er.quarterly_eps.toFixed(2)}` : '—'}
                          </td>
                          <td className="py-1.5 pl-2">
                            {formatCompactCurrency(er.quarterly_revenue)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
