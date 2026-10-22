import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import {
  ConnectModal,
  DEFAULT_LOGIN,
  DEFAULT_SERVER,
  DEFAULT_TERMINAL_PATH,
} from './ConnectModal';
import { accountApi, AccountConnectResponse } from '../api/account';

describe('ConnectModal', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('does not render when isOpen is false', () => {
    render(<ConnectModal isOpen={false} onClose={vi.fn()} />);
    expect(screen.queryByTestId('connect-modal')).not.toBeInTheDocument();
  });

  it('renders TUI-parity defaults when isOpen is true with no custom props', () => {
    render(<ConnectModal isOpen={true} onClose={vi.fn()} />);

    expect(screen.getByTestId('connect-modal')).toBeInTheDocument();
    expect(screen.getByTestId('connect-server-input')).toHaveValue(DEFAULT_SERVER);
    expect(screen.getByTestId('connect-login-input')).toHaveValue(DEFAULT_LOGIN);
    expect(screen.getByTestId('connect-password-input')).toHaveValue('');
    expect(screen.getByTestId('connect-path-input')).toHaveValue(DEFAULT_TERMINAL_PATH);
    expect(screen.getByTestId('connect-mock-mode-input')).not.toBeChecked();
    expect(screen.getByTestId('connect-submit-btn')).toHaveTextContent('Connect');
  });

  it('submits passwordless IPC live connection with TUI defaults and triggers onSuccess and onClose', async () => {
    const mockSuccessResponse: AccountConnectResponse = {
      status: 'CONNECTED',
      message: 'Connected to MT5',
      login: DEFAULT_LOGIN,
      server: DEFAULT_SERVER,
      trade_mode: 'REAL',
      balance: 100000,
      currency: 'EUR',
      error: null,
    };

    const connectSpy = vi.spyOn(accountApi, 'connect').mockResolvedValue(mockSuccessResponse);
    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(<ConnectModal isOpen={true} onClose={onClose} onSuccess={onSuccess} />);

    fireEvent.click(screen.getByTestId('connect-submit-btn'));

    await waitFor(() => {
      expect(connectSpy).toHaveBeenCalledWith({
        login: DEFAULT_LOGIN,
        password: '',
        server: DEFAULT_SERVER,
        path: DEFAULT_TERMINAL_PATH,
        mock_mode: false,
      });
      expect(onSuccess).toHaveBeenCalledWith(mockSuccessResponse);
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('normalizes blank terminal path to null and respects custom props', async () => {
    const mockSuccessResponse: AccountConnectResponse = {
      status: 'CONNECTED',
      message: 'Connected to MT5',
      login: 555888,
      server: 'Darwinex-Demo',
      trade_mode: 'DEMO',
      balance: 100000,
      currency: 'USD',
      error: null,
    };

    const connectSpy = vi.spyOn(accountApi, 'connect').mockResolvedValue(mockSuccessResponse);
    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(
      <ConnectModal
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
        defaultServer="Darwinex-Demo"
        defaultLogin={555888}
        defaultPath=""
        defaultMockMode={true}
      />
    );

    fireEvent.change(screen.getByTestId('connect-password-input'), {
      target: { value: 'myPassword123' },
    });

    fireEvent.click(screen.getByTestId('connect-submit-btn'));

    await waitFor(() => {
      expect(connectSpy).toHaveBeenCalledWith({
        login: 555888,
        password: 'myPassword123',
        server: 'Darwinex-Demo',
        path: null,
        mock_mode: true,
      });
      expect(onSuccess).toHaveBeenCalledWith(mockSuccessResponse);
      expect(onClose).toHaveBeenCalled();
    });
  });

  it('displays error alert when API returns error status', async () => {
    const mockErrorResponse: AccountConnectResponse = {
      status: 'ERROR',
      message: 'Authorization failed: Invalid MT5 account login or password',
      login: 111111,
      server: 'Darwinex-Demo',
      trade_mode: 'DEMO',
      balance: 0,
      currency: 'USD',
      error: 'Authorization failed: Invalid MT5 account login or password',
    };

    vi.spyOn(accountApi, 'connect').mockResolvedValue(mockErrorResponse);
    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(
      <ConnectModal
        isOpen={true}
        onClose={onClose}
        onSuccess={onSuccess}
        defaultServer="Darwinex-Demo"
        defaultLogin={111111}
      />
    );

    fireEvent.click(screen.getByTestId('connect-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('connect-error-alert')).toBeInTheDocument();
      expect(screen.getByTestId('connect-error-alert')).toHaveTextContent(
        'Authorization failed: Invalid MT5 account login or password'
      );
      expect(onSuccess).not.toHaveBeenCalled();
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  it('displays error alert when network request throws', async () => {
    vi.spyOn(accountApi, 'connect').mockRejectedValue(new Error('Network error: Gateway offline'));
    const onClose = vi.fn();

    render(<ConnectModal isOpen={true} onClose={onClose} defaultLogin={12345} />);

    fireEvent.click(screen.getByTestId('connect-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('connect-error-alert')).toBeInTheDocument();
      expect(screen.getByTestId('connect-error-alert')).toHaveTextContent('Network error: Gateway offline');
    });
  });

  it('validates numeric login requirement before dispatching', async () => {
    const connectSpy = vi.spyOn(accountApi, 'connect');
    render(<ConnectModal isOpen={true} onClose={vi.fn()} defaultLogin="" />);

    fireEvent.change(screen.getByTestId('connect-login-input'), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByTestId('connect-submit-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('connect-error-alert')).toHaveTextContent(
        'Please enter a valid numeric MT5 account login.'
      );
      expect(connectSpy).not.toHaveBeenCalled();
    });
  });

  it('calls onClose when cancel or close button is clicked', () => {
    const onClose = vi.fn();
    render(<ConnectModal isOpen={true} onClose={onClose} />);

    fireEvent.click(screen.getByTestId('connect-cancel-btn'));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('connect-modal-close'));
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('closes on Escape key press and backdrop click', () => {
    const onClose = vi.fn();
    render(<ConnectModal isOpen={true} onClose={onClose} />);

    fireEvent.click(screen.getByTestId('connect-modal-backdrop'));
    expect(onClose).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
