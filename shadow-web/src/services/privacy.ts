import type { PrivacySettingsPayload, UnknownFlushPayload } from '../types';
import { apiRequest } from './apiClient';

export function fetchPrivacySettings() {
  return apiRequest<PrivacySettingsPayload>('/settings/privacy');
}

export function updatePrivacySettings(allow_unknown_song_contribution: boolean) {
  return apiRequest<PrivacySettingsPayload>('/settings/privacy', {
    method: 'POST',
    body: { allow_unknown_song_contribution },
  });
}

export function flushUnknownSongs() {
  return apiRequest<UnknownFlushPayload>('/unknown-song/flush', {
    method: 'POST',
    body: {},
  });
}
