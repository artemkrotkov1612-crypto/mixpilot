import { useToasts } from '../state/toasts';

export function Toasts() {
  const list = useToasts((s) => s.list);
  if (list.length === 0) return null;
  return (
    <div className="toasts">
      {list.map((t) => (
        <div key={t.id} className={`toast ${t.kind === 'info' ? '' : t.kind}`}>
          {t.text}
        </div>
      ))}
    </div>
  );
}
