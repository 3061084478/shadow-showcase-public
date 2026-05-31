import type { ArchiveSummary, BootstrapSyncStatus, FriendListItemLite } from '../types';
import { apiRequest } from './apiClient';
import { adaptFriend } from './adapters';

type FriendRow = {
  uid: string;
  nickname: string;
  avatar_url: string;
  synced_at: string;
  friend_name?: string;
  last_used_at?: string;
  is_pinned?: boolean;
};

export async function fetchFriends(): Promise<FriendListItemLite[]> {
  const payload = await apiRequest<{ friends: FriendRow[] }>('/friends');
  return payload.friends.map((friend) => adaptFriend(friend));
}

export async function syncFriends(): Promise<FriendListItemLite[]> {
  const payload = await apiRequest<{ friends: FriendRow[] }>('/friends/sync', { method: 'POST', body: {} });
  return payload.friends.map((friend) => adaptFriend(friend));
}

export async function fetchRecentFriends(): Promise<FriendListItemLite[]> {
  const payload = await apiRequest<{ friends: FriendRow[] }>('/friends/recent');
  return payload.friends.map((friend) => adaptFriend(friend));
}

export async function rememberFriend(uid: string): Promise<FriendListItemLite[]> {
  const payload = await apiRequest<{ friends: FriendRow[] }>(`/friends/${uid}/remember`, { method: 'POST', body: {} });
  return payload.friends.map((friend) => adaptFriend(friend));
}

export async function pinRecentFriend(uid: string): Promise<FriendListItemLite[]> {
  const payload = await apiRequest<{ friends: FriendRow[] }>(`/friends/${uid}/recent/pin`, { method: 'POST', body: {} });
  return payload.friends.map((friend) => adaptFriend(friend));
}

export async function unpinRecentFriend(uid: string): Promise<FriendListItemLite[]> {
  const payload = await apiRequest<{ friends: FriendRow[] }>(`/friends/${uid}/recent/unpin`, { method: 'POST', body: {} });
  return payload.friends.map((friend) => adaptFriend(friend));
}

export function fetchArchiveSummary(uid: string) {
  return apiRequest<ArchiveSummary>(`/friends/${uid}/archive/summary`);
}

export function rebuildFriendArchive(uid: string) {
  return apiRequest<Record<string, unknown>>(`/friends/${uid}/archive/rebuild`, {
    method: 'POST',
    body: {},
  });
}

export function syncFriendRecent(uid: string, pages = 3, limit = 50) {
  return apiRequest<Record<string, unknown>>(`/friends/${uid}/archive/sync-recent`, {
    method: 'POST',
    params: { pages, limit },
    body: {},
  });
}

function hasCompletedArchive(summary?: ArchiveSummary) {
  const backfillStatus = String(summary?.backfill_status?.status ?? '').trim().toLowerCase();
  return Boolean(
    summary?.newest_archived_time
      || summary?.oldest_archived_time
      || summary?.backfill_status?.last_backfill_at
      || backfillStatus === 'completed',
  );
}

export async function fetchFriendsWithSummary(): Promise<FriendListItemLite[]> {
  const [friends, recentFriends] = await Promise.all([fetchFriends(), fetchRecentFriends().catch(() => [])]);
  const summaries = await Promise.all(
    friends.map(async (friend) => {
      try {
        const summary = await fetchArchiveSummary(friend.friend_uid);
        return { uid: friend.friend_uid, summary };
      } catch {
        return { uid: friend.friend_uid, summary: undefined };
      }
    }),
  );

  const summaryMap = new Map<string, ArchiveSummary | undefined>(summaries.map((item) => [item.uid, item.summary] as const));
  const recentMap = new Map<string, FriendListItemLite>(recentFriends.map((friend) => [friend.friend_uid, friend] as const));
  return friends.map((friend) => {
    const summary = summaryMap.get(friend.friend_uid);
    const recent = recentMap.get(friend.friend_uid);
    return {
      ...friend,
      is_pinned: recent?.is_pinned ?? false,
      last_synced_at: recent?.last_synced_at ?? friend.last_synced_at,
      archive_status: hasCompletedArchive(summary) ? 'ready' : 'never_archived',
      friend_sync_status: hasCompletedArchive(summary) ? 'ok' : 'needs_sync',
      message_count: Number(summary?.message_count ?? friend.message_count ?? 0),
      shared_song_count: Number(summary?.shared_song_count ?? friend.shared_song_count ?? 0),
      genre_unknown_count: Number(summary?.unknown_song_count ?? 0),
    };
  });
}

export function startBootstrapSync() {
  return apiRequest<BootstrapSyncStatus>('/sync/bootstrap', {
    method: 'POST',
    body: {},
  });
}

export function fetchBootstrapSyncStatus() {
  return apiRequest<BootstrapSyncStatus>('/sync/bootstrap/status');
}
