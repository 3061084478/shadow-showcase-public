import type { MusicRelationData, RelationExportPayload } from '../types';
import { apiRequest } from './apiClient';
import { adaptFriendRelation, adaptSelfRelation } from './adapters';

export async function fetchFriendRelation(uid: string): Promise<MusicRelationData> {
  const payload = await apiRequest<Record<string, unknown>>(`/friends/${uid}/relation`);
  return adaptFriendRelation(payload);
}

export async function fetchSelfRelation(): Promise<MusicRelationData> {
  const payload = await apiRequest<Record<string, unknown>>('/relation/self');
  return adaptSelfRelation(payload);
}

export function exportFriendRelation(uid: string) {
  return apiRequest<RelationExportPayload>(`/friends/${uid}/relation/export`, {
    method: 'POST',
    body: {},
  });
}

export function exportSelfRelation() {
  return apiRequest<RelationExportPayload>('/relation/self/export', {
    method: 'POST',
    body: {},
  });
}
