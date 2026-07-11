/** ISO-дата -> «только что», «5 мин назад», «2 ч назад», «вчера», «12.07».
 * «Вчера» — по календарным суткам (23:50 вчера ≠ «23 ч назад»).
 */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return '';
  const diffS = Math.max(0, (now.getTime() - then.getTime()) / 1000);
  if (diffS < 60) return 'только что';
  if (diffS < 3600) return `${Math.floor(diffS / 60)} мин назад`;

  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const dayDiff = Math.round((startOfDay(now) - startOfDay(then)) / 86_400_000);
  if (dayDiff === 0) return `${Math.floor(diffS / 3600)} ч назад`;
  if (dayDiff === 1) return 'вчера';

  const dd = String(then.getDate()).padStart(2, '0');
  const mm = String(then.getMonth() + 1).padStart(2, '0');
  return `${dd}.${mm}`;
}
