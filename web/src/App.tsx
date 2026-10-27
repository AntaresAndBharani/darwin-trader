import { FC, useState, useEffect, useRef } from 'react';
import { StatusRibbon } from './components/StatusRibbon';
import { PositionsGrid } from './components/PositionsGrid';
import {
  ConnectModal,
  DEFAULT_LOGIN,
  DEFAULT_SERVER,
  DEFAULT_TERMINAL_PATH,
} from './components/ConnectModal';
import { ChartWorkspace } from './components/ChartWorkspace';
import { YahooWorkspace } from './components/YahooWorkspace';
import { StrategyLifecycleWorkspace } from './components/StrategyLifecycleWorkspace';
import { ErrorBoundary } from './components/ErrorBoundary';
import { api } from './api/client';
import { accountApi } from './api/account';

export type WorkspaceTab = 'darwinex' | 'yahoo' | 'strategy';

export const App: FC = () => {
  const [isConnectOpen, setIsConnectOpen] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('darwinex');
  const autoConnectAttemptedRef = useRef<boolean>(false);

  // Automatically attach to Darwinex-Live (4000073238) on mount if Gateway is still in default state
  useEffect(() => {
    if (autoConnectAttemptedRef.current) return;
    autoConnectAttemptedRef.current = true;

    let isMounted = true;
    (async () => {
      try {
        const status = await api.getConnectionStatus();
        if (!isMounted) return;

        const isDefaultUnconfigured =
          status.status !== 'CONNECTED' ||
          (status.mock_mode === true && status.server === 'Darwinex-Demo');

        if (isDefaultUnconfigured) {
          await accountApi.connect({
            login: DEFAULT_LOGIN,
            server: DEFAULT_SERVER,
            path: DEFAULT_TERMINAL_PATH,
            mock_mode: false,
          });
        }
      } catch {
        // Silent background auto-connect attempt; StatusRibbon displays current state
      }
    })();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans">
      {/* Top Telemetry Status Ribbon */}
      <StatusRibbon />

      {/* Main Workspace Area */}
      <main className="flex-1 p-6 max-w-7xl mx-auto w-full flex flex-col gap-6">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-zinc-800 pb-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="text-emerald-400">Darwin Trader</span>
              <span className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono">
                v1.0.0
              </span>
            </h1>
            <p className="text-xs text-zinc-400 mt-1">
              Visual Algorithmic Trading Platform &middot; Hardware-accelerated TradingView &amp;
              MetaTrader 5 / Yahoo Finance Bridge
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* Top-Level Workspace Navigation Tabs */}
            <nav
              data-testid="workspace-tabs"
              className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg p-1 gap-1"
            >
              <button
                type="button"
                data-testid="tab-darwinex"
                onClick={() => setActiveTab('darwinex')}
                className={`px-3 py-1.5 text-xs font-semibold rounded transition-colors cursor-pointer ${
                  activeTab === 'darwinex'
                    ? 'bg-emerald-950/90 text-emerald-300 border border-emerald-700/70'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                Darwinex MT5
              </button>
              <button
                type="button"
                data-testid="tab-yahoo"
                onClick={() => setActiveTab('yahoo')}
                className={`px-3 py-1.5 text-xs font-semibold rounded transition-colors cursor-pointer ${
                  activeTab === 'yahoo'
                    ? 'bg-emerald-950/90 text-emerald-300 border border-emerald-700/70'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                Yahoo Finance
              </button>
              <button
                type="button"
                data-testid="tab-strategy"
                onClick={() => setActiveTab('strategy')}
                className={`px-3 py-1.5 text-xs font-semibold rounded transition-colors cursor-pointer ${
                  activeTab === 'strategy'
                    ? 'bg-emerald-950/90 text-emerald-300 border border-emerald-700/70'
                    : 'text-zinc-400 hover:text-zinc-200'
                }`}
              >
                Strategy Lifecycle
              </button>
            </nav>

            <button
              type="button"
              data-testid="header-connect-btn"
              onClick={() => setIsConnectOpen(true)}
              className="px-3.5 py-1.5 text-xs font-semibold rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors flex items-center gap-1.5 cursor-pointer"
            >
              <span>Connect MT5...</span>
            </button>
          </div>
        </header>

        {activeTab === 'darwinex' && (
          <ErrorBoundary fallbackTitle="Darwinex MT5 Workspace Error">
            {/* Dashboard overview container */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-5">
                <h2 className="text-sm font-semibold text-zinc-300">Live Gateway Telemetry</h2>
                <p className="text-xs text-zinc-400 mt-1">
                  Real-time WebSocket streaming at 1Hz from{' '}
                  <code className="text-emerald-400">/ws/live</code>.
                </p>
              </div>
              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-5">
                <h2 className="text-sm font-semibold text-zinc-300">Strategy Engine</h2>
                <p className="text-xs text-zinc-400 mt-1">
                  Connected via decoupled FastAPI bridge with zero MT5 core modifications.
                </p>
              </div>
              <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-5">
                <h2 className="text-sm font-semibold text-zinc-300">TradingView Canvas</h2>
                <p className="text-xs text-zinc-400 mt-1">
                  Institutional microstructure metrics &amp; client-side Heikin-Ashi transform
                  engine.
                </p>
              </div>
            </div>

            {/* TradingView Chart Workspace */}
            <section>
              <ChartWorkspace />
            </section>

            {/* Full-Width Positions Grid (Strategy Lifecycle promoted to dedicated top-level tab) */}
            <div className="w-full">
              <PositionsGrid />
            </div>
          </ErrorBoundary>
        )}

        {activeTab === 'yahoo' && (
          <ErrorBoundary fallbackTitle="Yahoo Finance Workspace Error">
            <YahooWorkspace />
          </ErrorBoundary>
        )}

        {activeTab === 'strategy' && (
          <ErrorBoundary fallbackTitle="Strategy Lifecycle Workspace Error">
            <StrategyLifecycleWorkspace />
          </ErrorBoundary>
        )}
      </main>

      {/* MetaTrader 5 Connect Modal */}
      <ConnectModal isOpen={isConnectOpen} onClose={() => setIsConnectOpen(false)} />
    </div>
  );
};

export default App;
