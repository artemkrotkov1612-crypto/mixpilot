import type { ReactNode } from 'react';

export function EmptyState({ icon, title, hint, action }: { icon: string; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="empty fade-in">
      <div className="icon">{icon}</div>
      <div style={{ fontWeight: 600, color: 'var(--text-1)' }}>{title}</div>
      {hint && <div className="small">{hint}</div>}
      {action}
    </div>
  );
}
