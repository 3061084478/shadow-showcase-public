const DEFAULT_API_BASE = 'http://127.0.0.1:8787';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 500) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function resolveApiBase() {
  const envValue = import.meta.env.VITE_SHADOW_API_BASE;
  return typeof envValue === 'string' && envValue.trim() ? envValue.trim().replace(/\/$/, '') : DEFAULT_API_BASE;
}

export const API_BASE = resolveApiBase();

type RequestOptions = {
  method?: 'GET' | 'POST';
  params?: Record<string, string | number | boolean | undefined | null>;
  body?: Record<string, unknown>;
};

function buildUrl(path: string, params?: RequestOptions['params']) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(`${API_BASE}${normalizedPath}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') return;
      url.searchParams.set(key, String(value));
    });
  }
  return url.toString();
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(buildUrl(path, options.params), {
    method: options.method ?? (options.body ? 'POST' : 'GET'),
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  let payload: unknown = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message =
      payload && typeof payload === 'object' && 'error' in payload && typeof payload.error === 'string'
        ? payload.error
        : `请求失败：${response.status}`;
    throw new ApiError(message, response.status);
  }

  if (payload && typeof payload === 'object' && 'error' in payload && typeof payload.error === 'string') {
    throw new ApiError(payload.error, response.status);
  }

  return payload as T;
}
