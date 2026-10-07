import '@testing-library/jest-dom';
import { vi } from 'vitest';

if (typeof window !== 'undefined') {
  if (!window.ResizeObserver) {
    window.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
}

export const mockSeries = {
  setData: vi.fn(),
  applyOptions: vi.fn(),
};

export const mockTimeScale = {
  fitContent: vi.fn(),
  scrollToPosition: vi.fn(),
  resetTimeScale: vi.fn(),
};

export const mockChart = {
  addSeries: vi.fn(() => mockSeries),
  removeSeries: vi.fn(),
  applyOptions: vi.fn(),
  timeScale: vi.fn(() => mockTimeScale),
  remove: vi.fn(),
};

vi.mock('lightweight-charts', () => ({
  createChart: vi.fn(() => mockChart),
  CandlestickSeries: { type: 'Candlestick' },
  ColorType: { Solid: 'solid', VerticalGradient: 'gradient' },
}));
