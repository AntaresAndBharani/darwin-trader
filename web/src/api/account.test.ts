import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiClient } from './client';
import { accountApi } from './account';

describe('accountApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('posts credentials to /account/connect and returns response', async () => {
    const mockResponse = {
      data: {
        status: 'CONNECTED',
        message: 'Connected successfully',
        login: 123456,
        server: 'Darwinex-Live',
        trade_mode: 'REAL',
        balance: 50000,
        currency: 'EUR',
        account_info: {
          login: 123456,
          trade_mode: 'REAL',
          server: 'Darwinex-Live',
          balance: 50000,
          equity: 50200,
          margin: 1000,
          free_margin: 49200,
          margin_level: 5020,
          currency: 'EUR',
          profit: 200,
        },
        error: null,
      },
    };

    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue(mockResponse);

    const payload = {
      login: 123456,
      password: 'secretPassword',
      server: 'Darwinex-Live',
    };

    const res = await accountApi.connect(payload);

    expect(postSpy).toHaveBeenCalledWith('/account/connect', payload);
    expect(res.status).toBe('CONNECTED');
    expect(res.login).toBe(123456);
    expect(res.balance).toBe(50000);
  });

  it('handles connection failure response from API', async () => {
    const mockErrorResponse = {
      data: {
        status: 'ERROR',
        message: 'Invalid credentials or timeout',
        login: 999999,
        server: 'Darwinex-Demo',
        trade_mode: 'DEMO',
        balance: 0,
        currency: 'USD',
        account_info: null,
        error: 'Invalid credentials or timeout',
      },
    };

    vi.spyOn(apiClient, 'post').mockResolvedValue(mockErrorResponse);

    const res = await accountApi.connect({ login: 999999, password: 'bad', server: 'Darwinex-Demo' });
    expect(res.status).toBe('ERROR');
    expect(res.error).toBe('Invalid credentials or timeout');
  });
});
