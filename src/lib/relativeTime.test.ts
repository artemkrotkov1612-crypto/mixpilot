import { describe, expect, it } from 'vitest';
import { formatRelative } from './relativeTime';

const NOW = new Date('2026-07-11T12:00:00Z');

describe('formatRelative', () => {
  it('свежие метки', () => {
    expect(formatRelative('2026-07-11T11:59:40Z', NOW)).toBe('только что');
    expect(formatRelative('2026-07-11T11:45:00Z', NOW)).toBe('15 мин назад');
    expect(formatRelative('2026-07-11T09:00:00Z', NOW)).toBe('3 ч назад');
  });

  it('вчера и старше', () => {
    expect(formatRelative('2026-07-10T13:00:00Z', NOW)).toBe('вчера');
    const older = formatRelative('2026-07-01T10:00:00Z', NOW);
    expect(older).toMatch(/^\d{2}\.\d{2}$/);
  });

  it('некорректный ввод', () => {
    expect(formatRelative('not-a-date', NOW)).toBe('');
  });
});
