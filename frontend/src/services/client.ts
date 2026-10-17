/**
 * 统一 HTTP 客户端。
 * - 后端前缀固定 /api/v1（设计文档 §13.2）
 * - 携带 JWT（localStorage: osvis_token）与游客标识（X-Guest-Id）
 * - 两类响应：`{code,message,data}` 信封 与 裸 JSON（算法轨迹接口），分别用
 *   `requestData` / `requestRaw` 读取
 */

export const API_PREFIX = '/api/v1';

export const STORAGE_KEYS = {
  token: 'osvis_token',
  user: 'osvis_user',
  guestId: 'osvis_guest_id',
  theme: 'os_theme',
  speed: 'osvis_speed',
  volume: 'osvis_volume',
  muted: 'osvis_muted',
} as const;

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEYS.token);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) {
      localStorage.setItem(STORAGE_KEYS.token, token);
    } else {
      localStorage.removeItem(STORAGE_KEYS.token);
      localStorage.removeItem(STORAGE_KEYS.user);
    }
  } catch {
    /* 隐私模式下 localStorage 可能不可用，忽略 */
  }
}

export function getGuestId(): string {
  try {
    const existing = localStorage.getItem(STORAGE_KEYS.guestId);
    if (existing) return existing;
    const generated =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `g-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(STORAGE_KEYS.guestId, generated);
    return generated;
  } catch {
    return 'anonymous';
  }
}

/** 构造带鉴权与游客标识的请求头（chatApi 的 SSE 请求也复用）。 */
export function buildAuthHeaders(withBody: boolean): Headers {
  const headers = new Headers();
  headers.set('X-Guest-Id', getGuestId());
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (withBody) {
    headers.set('Content-Type', 'application/json');
  }
  return headers;
}

async function parseError(response: Response): Promise<ApiError> {
  let message = `请求失败（HTTP ${response.status}）`;
  let detail: unknown;
  try {
    const payload: unknown = await response.json();
    if (payload && typeof payload === 'object') {
      const record = payload as Record<string, unknown>;
      const rawDetail = record.detail;
      if (typeof record.message === 'string' && record.message && record.message !== 'ok') {
        message = record.message;
      } else if (typeof rawDetail === 'string') {
        message = rawDetail;
      }
      detail = rawDetail;
    }
  } catch {
    /* 非 JSON 响应体，保留默认信息 */
  }
  return new ApiError(message, response.status, detail);
}

export async function requestRaw<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const response = await fetch(`${API_PREFIX}${path}`, {
    ...init,
    method,
    headers: (() => {
      const headers = buildAuthHeaders(init.body != null);
      if (init.headers) {
        new Headers(init.headers).forEach((value, key) => headers.set(key, value));
      }
      return headers;
    })(),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  const text = await response.text();
  if (!text) {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

export interface Envelope<T> {
  code: number;
  message: string;
  data: T;
}

/** 读取 `{code,message,data}` 信封接口，直接返回 data。 */
export async function requestData<T>(path: string, init: RequestInit = {}): Promise<T> {
  const payload = await requestRaw<Envelope<T> | T>(path, init);
  if (payload && typeof payload === 'object' && 'data' in (payload as Record<string, unknown>)) {
    return (payload as Envelope<T>).data;
  }
  return payload as T;
}

export function postJson(body: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(body) };
}

export function putJson(body: unknown): RequestInit {
  return { method: 'PUT', body: JSON.stringify(body) };
}

export function getJson(): RequestInit {
  return { method: 'GET' };
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return String(error);
}
