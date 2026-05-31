import type { AuthStatusPayload, QrPollPayload, QrSession } from '../types';
import { apiRequest } from './apiClient';

export function fetchAuthStatus() {
  return apiRequest<AuthStatusPayload>('/auth/status');
}

export function startLocalApi() {
  return apiRequest<{ ok: boolean }>('/auth/api/start', { method: 'POST', body: {} });
}

export function startQrSession() {
  return apiRequest<QrSession>('/auth/qr/start', { method: 'POST', body: {} });
}

export function pollQrSession(key: string) {
  return apiRequest<QrPollPayload>('/auth/qr/poll', { params: { key } });
}
