import { create } from 'zustand';

export type ToastKind = 'info' | 'ok' | 'err';

interface Toast {
  id: number;
  text: string;
  kind: ToastKind;
}

interface ToastsState {
  list: Toast[];
  push: (text: string, kind?: ToastKind) => void;
}

let nextId = 1;
const TTL_MS = 4200;

export const useToasts = create<ToastsState>((set) => ({
  list: [],
  push: (text, kind = 'info') => {
    const id = nextId++;
    set((s) => ({ list: [...s.list, { id, text, kind }] }));
    setTimeout(() => set((s) => ({ list: s.list.filter((t) => t.id !== id) })), TTL_MS);
  },
}));

export const toast = (text: string, kind: ToastKind = 'info') => useToasts.getState().push(text, kind);
