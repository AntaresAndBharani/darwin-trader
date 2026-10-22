/// <reference types="vitest" />
import { defineConfig, Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { spawn, ChildProcess } from 'node:child_process';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const GATEWAY_HOST = '127.0.0.1';
const GATEWAY_PORT = 8000;
const GATEWAY_URL = `http://${GATEWAY_HOST}:${GATEWAY_PORT}`;

const DEFAULT_LOGIN = 4000073238;
const DEFAULT_SERVER = 'Darwinex-Live';
const DEFAULT_TERMINAL_PATH = 'C:\\Program Files\\Darwinex MetaTrader 5\\terminal64.exe';

function checkPortOpen(host: string, port: number, timeoutMs = 1000): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let settled = false;
    const finish = (open: boolean) => {
      if (!settled) {
        settled = true;
        socket.destroy();
        resolve(open);
      }
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
    socket.connect(port, host);
  });
}

async function waitForGatewayHealthy(timeoutMs = 10000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${GATEWAY_URL}/`);
      if (res.ok) {
        const data = (await res.json()) as { status?: string };
        if (data.status === 'ONLINE') {
          return true;
        }
      }
    } catch {
      // Gateway still booting
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

async function autoConnectDarwinexLive(): Promise<void> {
  if (process.env.VITE_MOCK_MODE === 'true') return;
  try {
    const res = await fetch(`${GATEWAY_URL}/api/v1/account/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        login: DEFAULT_LOGIN,
        server: DEFAULT_SERVER,
        path: DEFAULT_TERMINAL_PATH,
        mock_mode: false,
      }),
    });
    if (res.ok) {
      const data = (await res.json()) as { status?: string; balance?: number };
      if (data.status === 'CONNECTED') {
        console.log(
          `[DarwinGateway] Connected to ${DEFAULT_SERVER} (Login: ${DEFAULT_LOGIN}, Balance: $${data.balance ?? 0}).`
        );
      }
    }
  } catch {
    // Non-fatal; UI will retry or display current connection status
  }
}

function darwinGatewayPlugin(): Plugin {
  let gatewayProc: ChildProcess | null = null;
  let startedByVite = false;

  const stopGateway = () => {
    if (startedByVite && gatewayProc && !gatewayProc.killed) {
      console.log('\n[DarwinGateway] Stopping background API Gateway...');
      try {
        gatewayProc.kill();
      } catch {
        // Ignore cleanup errors
      }
      gatewayProc = null;
      startedByVite = false;
    }
  };

  return {
    name: 'darwin-gateway-launcher',
    apply: 'serve',
    async configureServer(server) {
      if (process.env.VITEST) return;

      const isOpen = await checkPortOpen(GATEWAY_HOST, GATEWAY_PORT);
      if (!isOpen) {
        console.log(`[DarwinGateway] Starting FastAPI Gateway on ${GATEWAY_URL}...`);
        gatewayProc = spawn(
          'python',
          ['-m', 'uvicorn', 'api_gateway.main:app', '--host', GATEWAY_HOST, '--port', String(GATEWAY_PORT)],
          {
            cwd: REPO_ROOT,
            stdio: 'ignore',
            windowsHide: true,
          }
        );
        startedByVite = true;

        const healthy = await waitForGatewayHealthy(10000);
        if (!healthy) {
          console.error('[DarwinGateway] ERROR: API Gateway failed to start within 10 seconds.');
          stopGateway();
        } else {
          console.log('[DarwinGateway] API Gateway is ONLINE.');
        }
      } else {
        console.log(`[DarwinGateway] API Gateway is already running on ${GATEWAY_URL}.`);
      }

      await autoConnectDarwinexLive();

      server.httpServer?.once('close', stopGateway);
      process.once('exit', stopGateway);
      process.once('SIGINT', () => {
        stopGateway();
        process.exit(0);
      });
      process.once('SIGTERM', () => {
        stopGateway();
        process.exit(0);
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), darwinGatewayPlugin()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
});
