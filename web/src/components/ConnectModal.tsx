import { FC, useState, useEffect, FormEvent, MouseEvent } from 'react';
import { accountApi, AccountConnectResponse } from '../api/account';

export interface ConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (response: AccountConnectResponse) => void;
  defaultServer?: string;
  defaultLogin?: number | string;
}

export const ConnectModal: FC<ConnectModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  defaultServer = 'Darwinex-Demo',
  defaultLogin = '',
}) => {
  const [server, setServer] = useState<string>(defaultServer);
  const [login, setLogin] = useState<string>(String(defaultLogin || ''));
  const [password, setPassword] = useState<string>('');
  const [mockMode, setMockMode] = useState<boolean>(true);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setError(null);
      setServer(defaultServer);
      setLogin(String(defaultLogin || ''));
      setPassword('');
    }
  }, [isOpen, defaultServer, defaultLogin]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isLoading) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isLoading, onClose]);

  if (!isOpen) return null;

  const handleBackdropClick = (e: MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget && !isLoading) {
      onClose();
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const loginNum = parseInt(login, 10);
    if (isNaN(loginNum) || loginNum <= 0) {
      setError('Please enter a valid numeric MT5 account login.');
      return;
    }

    try {
      setIsLoading(true);
      setError(null);
      const res = await accountApi.connect({
        login: loginNum,
        password,
        server: server.trim(),
        mock_mode: mockMode,
      });

      if (res.status === 'ERROR' || res.error) {
        setError(res.error || res.message || 'Connection failed.');
        return;
      }

      if (onSuccess) {
        onSuccess(res);
      }
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to connect to MetaTrader 5';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      data-testid="connect-modal-backdrop"
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="connect-modal-title"
        data-testid="connect-modal"
        className="bg-zinc-900 border border-zinc-700 rounded-lg max-w-md w-full p-6 shadow-2xl flex flex-col gap-4 text-zinc-100 animate-in fade-in zoom-in-95 duration-150"
      >
        <div className="flex items-start justify-between gap-3 border-b border-zinc-800 pb-3">
          <div>
            <h2 id="connect-modal-title" className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
              <span className="text-emerald-400">MetaTrader 5</span> Connection
            </h2>
            <p className="text-xs text-zinc-400 mt-0.5">
              Enter your broker credentials to establish a gateway bridge.
            </p>
          </div>
          <button
            type="button"
            data-testid="connect-modal-close"
            onClick={onClose}
            disabled={isLoading}
            aria-label="Close dialog"
            className="text-zinc-400 hover:text-zinc-200 transition-colors p-1 rounded hover:bg-zinc-800 disabled:opacity-50 cursor-pointer"
          >
            &times;
          </button>
        </div>

        {error && (
          <div
            data-testid="connect-error-alert"
            role="alert"
            className="text-xs text-rose-300 bg-rose-950/70 border border-rose-800 px-3 py-2 rounded flex items-start gap-2"
          >
            <span className="font-bold text-rose-400">Error:</span>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-3.5">
          <div className="flex flex-col gap-1">
            <label htmlFor="connect-server" className="text-xs font-semibold text-zinc-300">
              Server
            </label>
            <input
              id="connect-server"
              data-testid="connect-server-input"
              type="text"
              required
              value={server}
              onChange={(e) => setServer(e.target.value)}
              disabled={isLoading}
              placeholder="e.g. Darwinex-Demo or MetaQuotes-Demo"
              className="px-3 py-1.5 bg-zinc-950 border border-zinc-700 rounded text-sm text-zinc-100 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="connect-login" className="text-xs font-semibold text-zinc-300">
              MT5 Login Account
            </label>
            <input
              id="connect-login"
              data-testid="connect-login-input"
              type="number"
              required
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              disabled={isLoading}
              placeholder="e.g. 50123456"
              className="px-3 py-1.5 bg-zinc-950 border border-zinc-700 rounded text-sm text-zinc-100 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="connect-password" className="text-xs font-semibold text-zinc-300">
              Password
            </label>
            <input
              id="connect-password"
              data-testid="connect-password-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              placeholder="Master or Investor Password"
              className="px-3 py-1.5 bg-zinc-950 border border-zinc-700 rounded text-sm text-zinc-100 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
            />
          </div>

          <div className="flex items-center gap-2 pt-1">
            <input
              id="connect-mock-mode"
              data-testid="connect-mock-mode-input"
              type="checkbox"
              checked={mockMode}
              onChange={(e) => setMockMode(e.target.checked)}
              disabled={isLoading}
              className="rounded bg-zinc-950 border-zinc-700 text-emerald-500 focus:ring-emerald-500 h-4 w-4"
            />
            <label htmlFor="connect-mock-mode" className="text-xs text-zinc-400 select-none">
              Simulation / Mock Mode (Safe Sandbox)
            </label>
          </div>

          <div className="flex items-center justify-end gap-3 mt-3 pt-3 border-t border-zinc-800">
            <button
              type="button"
              data-testid="connect-cancel-btn"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2 text-xs font-medium rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors disabled:opacity-50 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              data-testid="connect-submit-btn"
              disabled={isLoading}
              className="px-4 py-2 text-xs font-semibold rounded bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white transition-colors disabled:opacity-50 shadow-lg shadow-emerald-950/40 cursor-pointer flex items-center gap-1.5"
            >
              {isLoading ? 'Connecting...' : 'Connect'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default ConnectModal;
