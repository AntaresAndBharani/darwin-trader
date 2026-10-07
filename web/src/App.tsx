import type { FC } from 'react';
import { StatusRibbon } from './components/StatusRibbon';

export const App: FC = () => {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans">
      {/* Top Telemetry Status Ribbon */}
      <StatusRibbon />

      {/* Main Workspace Area */}
      <main className="flex-1 p-6 max-w-7xl mx-auto w-full flex flex-col gap-6">
        <header className="flex items-center justify-between border-b border-zinc-800 pb-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="text-emerald-400">Darwin Trader</span>
              <span className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono">v1.0.0</span>
            </h1>
            <p className="text-xs text-zinc-400 mt-1">
              Visual Algorithmic Trading Platform &middot; Hardware-accelerated TradingView &amp; MetaTrader 5 Bridge
            </p>
          </div>
        </header>

        {/* Dashboard overview container */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-5">
            <h2 className="text-sm font-semibold text-zinc-300">Live Gateway Telemetry</h2>
            <p className="text-xs text-zinc-400 mt-1">
              Real-time WebSocket streaming at 1Hz from <code className="text-emerald-400">/ws/live</code>.
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
              Institutional microstructure metrics &amp; client-side Heikin-Ashi transform engine.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;
