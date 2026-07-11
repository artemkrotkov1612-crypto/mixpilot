import { useState } from 'react';
import type { DragEvent, ReactNode } from 'react';
import { toast } from '../state/toasts';

interface DropZoneProps {
  onPaths: (paths: string[]) => void;
  children: ReactNode;
  compact?: boolean;
}

/** Приём файлов: перетаскивание или системный диалог по клику. */
export function DropZone({ onPaths, children, compact }: DropZoneProps) {
  const [drag, setDrag] = useState(false);

  const extractPaths = (e: DragEvent): string[] => {
    const bridge = window.mixpilot;
    if (!bridge) return [];
    return Array.from(e.dataTransfer.files)
      .map((f) => bridge.getPathForFile(f))
      .filter((p): p is string => Boolean(p));
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDrag(false);
    if (!window.mixpilot) {
      toast('Перетаскивание доступно в приложении, не в браузере');
      return;
    }
    const paths = extractPaths(e);
    if (paths.length > 0) onPaths(paths);
  };

  const onClick = async () => {
    if (!window.mixpilot) {
      toast('Выбор файлов доступен в приложении, не в браузере');
      return;
    }
    const paths = await window.mixpilot.pickFiles();
    if (paths.length > 0) onPaths(paths);
  };

  return (
    <button
      type="button"
      className={`dropzone ${drag ? 'drag' : ''}`}
      style={compact ? { padding: '18px 24px' } : undefined}
      onClick={() => void onClick()}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={onDrop}
    >
      {children}
    </button>
  );
}
