import type { ChatMessage, ChatQueryPayload, ChatQueryResult } from '../types';
import { apiRequest } from './apiClient';
import { adaptChatRow } from './adapters';

type ChatApiPayload = {
  scope: string;
  total: number;
  rows: Record<string, unknown>[];
  page?: number;
  limit?: number;
};

export async function queryChatMessages(uid: string, payload: ChatQueryPayload, friendName: string): Promise<ChatQueryResult> {
  const result = await apiRequest<ChatApiPayload>(`/friends/${uid}/chat-messages/query`, {
    method: 'POST',
    body: payload as unknown as Record<string, unknown>,
  });
  const sortedRows = [...result.rows].sort((left, right) => {
    const leftTime = Number(left.msg_time_ms ?? 0);
    const rightTime = Number(right.msg_time_ms ?? 0);
    if (leftTime !== rightTime) return leftTime - rightTime;
    return String(left.msg_id ?? '').localeCompare(String(right.msg_id ?? ''));
  });

  return {
    scope: result.scope,
    total: result.total,
    page: result.page,
    limit: result.limit,
    rows: sortedRows.map((row) => adaptChatRow(row, friendName)),
  };
}

export function fetchChatActiveDates(uid: string) {
  return apiRequest<{ dates: string[] }>(`/friends/${uid}/chat-messages/active-dates`);
}

export async function fetchRecentSongMessages(uid: string, friendName: string, limit = 50): Promise<ChatMessage[]> {
  const result = await queryChatMessages(
    uid,
    {
      scope: 'all',
      msg_type: 'song',
      sender_scope: 'all',
      page: 1,
      limit,
    },
    friendName,
  );
  return result.rows;
}
