import type { ShadowBuildResult, ShadowCandidate, ShadowPlaylistTrack, ShadowTarget, ShadowTargetOption } from '../types';
import { apiRequest } from './apiClient';
import { adaptShadowCandidate, adaptShadowTarget, adaptShadowTargetOptions } from './adapters';

type ShadowTargetsPayload = {
  current_target: Record<string, unknown> | null;
  playlists: Record<string, unknown>[];
  current_tracks?: Record<string, unknown>[];
};

function adaptPlaylistTrack(row: Record<string, unknown>): ShadowPlaylistTrack | null {
  const id = String(row.id ?? '').trim();
  if (!id) return null;
  const artists = Array.isArray(row.ar) ? row.ar : Array.isArray(row.artists) ? row.artists : [];
  const artist = artists
    .map((item) => {
      if (!item || typeof item !== 'object') return '';
      return String((item as Record<string, unknown>).name ?? '').trim();
    })
    .filter(Boolean)
    .join(' / ');
  return {
    id,
    name: String(row.name ?? '').trim() || id,
    artist,
  };
}

export async function fetchShadowTargets(): Promise<{ currentTarget: ShadowTarget | null; playlists: ShadowTargetOption[]; currentTracks: ShadowPlaylistTrack[] }> {
  const payload = await apiRequest<ShadowTargetsPayload>('/shadow/targets');
  return {
    currentTarget: adaptShadowTarget(payload.current_target),
    playlists: adaptShadowTargetOptions(payload.playlists),
    currentTracks: (payload.current_tracks || []).map((row) => adaptPlaylistTrack(row)).filter(Boolean) as ShadowPlaylistTrack[],
  };
}

export function setShadowTarget(payload: { strategy: string; playlist_id?: string; playlist_name?: string; is_private?: boolean }) {
  return apiRequest<ShadowTarget>('/shadow/target', {
    method: 'POST',
    body: payload as unknown as Record<string, unknown>,
  });
}

export async function fetchShadowCandidates(
  uid: string,
  payload: { scope: string; keyword?: string; known_only?: boolean; limit?: number; page?: number; date?: string; start_date?: string; end_date?: string },
): Promise<ShadowCandidate[]> {
  const result = await apiRequest<{ rows: Record<string, unknown>[] }>(`/friends/${uid}/shadow/candidates/query`, {
    method: 'POST',
    body: payload as unknown as Record<string, unknown>,
  });
  const sortedRows = [...(result.rows || [])].sort((left, right) => {
    const leftTime = Number(left.msg_time_ms ?? 0);
    const rightTime = Number(right.msg_time_ms ?? 0);
    if (leftTime !== rightTime) return leftTime - rightTime;
    return String(left.msg_id ?? '').localeCompare(String(right.msg_id ?? ''));
  });
  return sortedRows.map((row) => adaptShadowCandidate(row));
}

export function fetchShadowActiveDates(uid: string) {
  return apiRequest<{ dates: string[] }>(`/friends/${uid}/shared-songs/active-dates`);
}

export function buildShadowPlaylist(
  uid: string,
  payload: {
    playlist_id?: string;
    playlist_name?: string;
    song_ids?: string[];
    anchor_index?: number;
    max_gap_hours?: number;
    max_songs?: number;
    apply_sequence_rules?: boolean;
    overwrite?: boolean;
  },
) {
  return apiRequest<ShadowBuildResult>(`/friends/${uid}/shadow/build`, {
    method: 'POST',
    body: payload as unknown as Record<string, unknown>,
  });
}
