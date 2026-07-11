import { describe, expect, it } from 'vitest';
import { formatDuration } from './format';

describe('formatDuration', () => {
  it('минуты и секунды', () => {
    expect(formatDuration(222)).toBe('3:42');
    expect(formatDuration(0)).toBe('0:00');
    expect(formatDuration(59.6)).toBe('1:00');
  });

  it('часы', () => {
    expect(formatDuration(3725)).toBe('1:02:05');
  });

  it('некорректный ввод', () => {
    expect(formatDuration(NaN)).toBe('0:00');
    expect(formatDuration(-5)).toBe('0:00');
    expect(formatDuration(Infinity)).toBe('0:00');
  });
});
