import { FC, useState, useEffect, FormEvent, MouseEvent } from 'react';
import { accountApi, AccountConnectResponse } from '../api/account';

export const DEFAULT_TERMINAL_PATH = 'C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe';
export const DEFAULT_LOGIN = 4000073238;
export const DEFAULT_SERVER = 'Darwinex-Live';
export const SERVER_CHOICES = ['Darwinex-Demo', 'Darwinex-Live', 'MetaQuotes-Demo'] as const;

export interface ConnectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (response: AccountConnectResponse) => void;
  defaultServer?: string;
  defaultLogin?: number | string;
  defaultPath?: string;
  defaultMockMode?: boolean;
}

export const ConnectModal: FC<ConnectModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  defaultServer = DEFAULT_SERVER,
  defaultLogin = DEFAULT_LOGIN,
  defaultPath = DEFAULT_TERMINAL_PATH,
  defaultMockMode = false,
}) => {
  const [server, setServer] = useState<string>(defaultServer);
  const [login, setLogin] = useState<string>(
    defaultLogin !== undefined && defaultLogin !== null && defaultLogin !== ''
      ? String(defaultLogin)
      : ''
  );
  const [password, setPassword] = useState<string>('');
  const [path, setPath] = useState<string>(defaultPath);
  const [mockMode, setMockMode] = useState<boolean>(defaultMockMode);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setError(null);
      setServer(defaultServer);
      setLogin(
        defaultLogin !== undefined && defaultLogin !== null && defaultLogin !== ''
          ? String(defaultLogin)
          : ''
      );
      setPassword('');
      setPath(defaultPath);
      setMockMode(defaultMockMode);
    }
  }, [isOpen, defaultServer, defaultLogin, defaultPath, defaultMockMode]);

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

    const trimmedPath = path.trim();

    try {
      setIsLoading(true);
      setError(null);
      const res = await accountApi.connect({
        login: loginNum,
        password,
        server: server.trim() || DEFAULT_SERVER,
        path: trimmedPath ? trimmedPath : null,
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

  const serverOptions = SERVER_CHOICES.includes(server as (typeof SERVER_CHOICES)[number])
    ? [...SERVER_CHOICES]
    : [server, ...SERVER_CHOICES];

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
              Attach to running Darwinex MT5 terminal or enter broker credentials.
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
            <label htmlFor="connect-login" className="text-xs font-semibold text-zinc-300">
              Login ID
            </label>
            <input
              id="connect-login"
              data-testid="connect-login-input"
              type="number"
              required
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              disabled={isLoading}
              placeholder="e.g. 4000073238"
              className="px-3 py-1.5 bg-zinc-950 border border-zinc-700 rounded text-sm text-zinc-100 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="connect-password" className="text-xs font-semibold text-zinc-300">
              Password (Optional for running terminal)
            </label>
            <input
              id="connect-password"
              data-testid="connect-password-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              placeholder="Leave empty to attach to running MT5"
              className="px-3 py-1.5 bg-zinc-950 border border-zinc-700 rounded text-sm text-zinc-100 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="connect-server" className="text-xs font-semibold text-zinc-300">
              Server
            </label>
            <select
              id="connect-server"
              data-testid="connect-server-input"
              required
              value={server}
              onChange={(e) => setServer(e.target.value)}
              disabled={isLoading}
              className="px-3 py-1.5 bg-zinc-950 border border-zinc-700 rounded text-sm text-zinc-100 focus:outline-none focus:border-emerald-500 disabled:opacity-50"
            >
              {serverOptions.map((srv) => (
                <option key={srv} value={srv}>
                  {srv}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="connect-path" className="text-xs font-semibold text-zinc-300">
              Terminal Path (Optional)
            </label>
            <input
              id="connect-path"
              data-testid="connect-path-input"
              type="text"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              disabled={isLoading}
              placeholder="Optional path to terminal64.exe"
              className="px-3 py-1.5 bg-zinc-950 border border-zinc-700 rounded text-sm text-zinc-100 focus:outline-none focus:border-emerald-500 disabled:opacity-50 font-mono"
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
              Mock Mode (Simulation Sandbox)
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
