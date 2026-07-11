import { create } from 'zustand';
import { api } from '../api/client';
import type { Project, ProjectMode, RemixParams } from '../api/types';

interface ProjectsState {
  recent: Project[];
  refreshRecent: () => Promise<void>;
}

export const useProjects = create<ProjectsState>((set) => ({
  recent: [],
  refreshRecent: async () => {
    const res = await api<{ projects: Project[] }>('/projects', { query: { limit: 12 } });
    set({ recent: res.projects });
  },
}));

export const MODE_LABELS: Record<ProjectMode, string> = {
  remix: 'Ремикс',
  merge: 'Соединение',
  voice_cover: 'Кавер голосом',
  voice_self: 'Моя запись',
  voice_overbeat: 'Поверх бита',
};

export async function createProject(mode: ProjectMode): Promise<Project> {
  return api<Project>('/projects', { json: { mode } });
}

export async function loadProject(projectId: string): Promise<Project> {
  return api<Project>(`/projects/${projectId}`);
}

export async function attachTrack(projectId: string, trackId: string): Promise<Project> {
  return api<Project>(`/projects/${projectId}/tracks`, { json: { track_id: trackId } });
}

export async function detachTrack(projectId: string, trackId: string): Promise<Project> {
  return api<Project>(`/projects/${projectId}/tracks/${trackId}`, { method: 'DELETE' });
}

export async function saveProject(
  projectId: string,
  patch: { title?: string; params?: RemixParams },
): Promise<Project> {
  return api<Project>(`/projects/${projectId}`, { method: 'PATCH', json: patch });
}
