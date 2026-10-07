export interface OHLCBar {
  time: number | string;
  open: number;
  high: number;
  low: number;
  close: number;
  tick_volume?: number;
  spread?: number;
  symbol?: string;
  timeframe?: string;
}

export interface HeikinAshiBar extends OHLCBar {
  ha_open: number;
  ha_high: number;
  ha_low: number;
  ha_close: number;
  ha_color: 'GREEN' | 'RED';
}

/**
 * Computes client-side Heikin-Ashi candlesticks without backend round-trips.
 *
 * Mathematical formulas strictly conforming to Scenario 8:
 * - HA_Close = (Open + High + Low + Close) / 4
 * - HA_Open  = (prev_HA_Open + prev_HA_Close) / 2 [seeded with (Open_0 + Close_0) / 2 on first bar]
 * - HA_High  = max(High, HA_Open, HA_Close)
 * - HA_Low   = min(Low, HA_Open, HA_Close)
 * - HA_Color = HA_Close > HA_Open ? 'GREEN' : 'RED'
 */
export function computeHeikinAshi(bars: readonly OHLCBar[]): HeikinAshiBar[] {
  if (!bars || bars.length === 0) {
    return [];
  }

  const result: HeikinAshiBar[] = [];

  for (let i = 0; i < bars.length; i++) {
    const bar = bars[i];
    const open = Number(bar.open);
    const high = Number(bar.high);
    const low = Number(bar.low);
    const close = Number(bar.close);

    const haClose = (open + high + low + close) / 4;
    const haOpen =
      i === 0
        ? (open + close) / 2
        : (result[i - 1].ha_open + result[i - 1].ha_close) / 2;
    const haHigh = Math.max(high, haOpen, haClose);
    const haLow = Math.min(low, haOpen, haClose);
    const haColor: 'GREEN' | 'RED' = haClose > haOpen ? 'GREEN' : 'RED';

    result.push({
      ...bar,
      open,
      high,
      low,
      close,
      ha_open: haOpen,
      ha_high: haHigh,
      ha_low: haLow,
      ha_close: haClose,
      ha_color: haColor,
    });
  }

  return result;
}
