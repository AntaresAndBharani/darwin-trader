import { describe, it, expect } from 'vitest';
import { computeHeikinAshi, OHLCBar } from './heikinAshi';

describe('computeHeikinAshi', () => {
  it('returns an empty array when given an empty list of bars', () => {
    expect(computeHeikinAshi([])).toEqual([]);
  });

  it('correctly initializes the first bar according to Scenario 8 seeding rule', () => {
    // HA_Open_0 = (Open_0 + Close_0) / 2 = (100 + 104) / 2 = 102.0
    // HA_Close_0 = (100 + 110 + 90 + 104) / 4 = 101.0
    // HA_High_0 = max(110, 102, 101) = 110.0
    // HA_Low_0 = min(90, 102, 101) = 90.0
    // HA_Color = 101.0 > 102.0 ? 'GREEN' : 'RED' => 'RED'
    const bars: OHLCBar[] = [
      {
        time: 1736121600,
        open: 100.0,
        high: 110.0,
        low: 90.0,
        close: 104.0,
      },
    ];

    const result = computeHeikinAshi(bars);
    expect(result).toHaveLength(1);
    expect(result[0].ha_open).toBeCloseTo(102.0, 5);
    expect(result[0].ha_close).toBeCloseTo(101.0, 5);
    expect(result[0].ha_high).toBeCloseTo(110.0, 5);
    expect(result[0].ha_low).toBeCloseTo(90.0, 5);
    expect(result[0].ha_color).toBe('RED');
  });

  it('correctly identifies a GREEN candle on single bar', () => {
    // Open = 10.0, Close = 13.0, High = 15.0, Low = 10.0
    // HA_Open = 11.5, HA_Close = 12.0 => GREEN
    const bars: OHLCBar[] = [
      {
        time: 1736121600,
        open: 10.0,
        high: 15.0,
        low: 10.0,
        close: 13.0,
      },
    ];

    const result = computeHeikinAshi(bars);
    expect(result[0].ha_open).toBeCloseTo(11.5, 5);
    expect(result[0].ha_close).toBeCloseTo(12.0, 5);
    expect(result[0].ha_color).toBe('GREEN');
  });

  it('matches recursive calculation against the fixed OHLC test fixture from strategy_engine', () => {
    // Exact fixture from strategy_engine/tests/test_heikin_ashi.py:
    // Bar 0: open 102.0, high 103.0, low 98.0, close 99.0
    // Bar 1: open 99.0, high 106.0, low 98.5, close 105.0
    const fixture: OHLCBar[] = [
      { time: '2025-02-24', open: 102.0, high: 103.0, low: 98.0, close: 99.0 },
      { time: '2025-03-03', open: 99.0, high: 106.0, low: 98.5, close: 105.0 },
    ];

    const result = computeHeikinAshi(fixture);
    expect(result).toHaveLength(2);

    // Bar 0:
    // HA_Open = (102 + 99) / 2 = 100.5
    // HA_Close = (102 + 103 + 98 + 99) / 4 = 100.5
    // HA_High = max(103, 100.5, 100.5) = 103.0
    // HA_Low = min(98, 100.5, 100.5) = 98.0
    // HA_Color = 100.5 > 100.5 ? 'GREEN' : 'RED' => 'RED'
    expect(result[0].ha_open).toBeCloseTo(100.5, 5);
    expect(result[0].ha_close).toBeCloseTo(100.5, 5);
    expect(result[0].ha_high).toBeCloseTo(103.0, 5);
    expect(result[0].ha_low).toBeCloseTo(98.0, 5);
    expect(result[0].ha_color).toBe('RED');

    // Bar 1:
    // HA_Open = (prev_ha_open + prev_ha_close) / 2 = (100.5 + 100.5) / 2 = 100.5
    // HA_Close = (99.0 + 106.0 + 98.5 + 105.0) / 4 = 102.125
    // HA_High = max(106.0, 100.5, 102.125) = 106.0
    // HA_Low = min(98.5, 100.5, 102.125) = 98.5
    // HA_Color = 102.125 > 100.5 => 'GREEN'
    expect(result[1].ha_open).toBeCloseTo(100.5, 5);
    expect(result[1].ha_close).toBeCloseTo(102.125, 5);
    expect(result[1].ha_high).toBeCloseTo(106.0, 5);
    expect(result[1].ha_low).toBeCloseTo(98.5, 5);
    expect(result[1].ha_color).toBe('GREEN');
  });

  it('ensures high and low boundaries expand when HA open/close exceeds candle extremities', () => {
    // Massive gap-up where previous candle was high, so HA_Open > current High
    const bars: OHLCBar[] = [
      { time: 1, open: 200, high: 210, low: 195, close: 205 }, // ha_open = 202.5, ha_close = 202.5
      { time: 2, open: 150, high: 155, low: 140, close: 145 }, // ha_open = 202.5 (higher than high 155!)
    ];

    const res = computeHeikinAshi(bars);
    // For bar 2:
    // ha_open = 202.5
    // ha_close = (150 + 155 + 140 + 145) / 4 = 147.5
    // ha_high = max(155, 202.5, 147.5) = 202.5
    // ha_low = min(140, 202.5, 147.5) = 140
    expect(res[1].ha_high).toBeCloseTo(202.5, 5);
    expect(res[1].ha_low).toBeCloseTo(140.0, 5);
  });

  it('preserves underlying bar metadata and does not mutate input', () => {
    const original: readonly OHLCBar[] = Object.freeze([
      Object.freeze({
        time: 100,
        open: 50,
        high: 60,
        low: 40,
        close: 55,
        symbol: 'EURUSD',
        tick_volume: 1200,
        spread: 2,
      }),
    ]);

    const res = computeHeikinAshi(original);
    expect(res[0].symbol).toBe('EURUSD');
    expect(res[0].tick_volume).toBe(1200);
    expect(res[0].spread).toBe(2);
    expect(res[0].open).toBe(50);
  });
});
