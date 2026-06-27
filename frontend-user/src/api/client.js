const DEFAULT_DEV_ACTOR_TOKEN = import.meta.env?.DEV ? 'operator-token' : '';

export async function requestJson(url, options = {}) {
  const response = await fetch(url, jsonRequestOptions(options));
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(errorMessage(payload, response.status));
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export function authHeaders() {
  let token = DEFAULT_DEV_ACTOR_TOKEN;
  try {
    token = globalThis.localStorage?.getItem('actor_token') || DEFAULT_DEV_ACTOR_TOKEN;
  } catch {
    token = DEFAULT_DEV_ACTOR_TOKEN;
  }
  return token ? { 'X-Actor-Token': token } : {};
}

function jsonRequestOptions(options) {
  const headers = new Headers(authHeaders());
  new Headers(options.headers || {}).forEach((value, key) => {
    headers.set(key, value);
  });
  if (options.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  return {
    ...options,
    headers,
  };
}

function errorMessage(payload, status) {
  const detail = payload && payload.detail;
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
    return detail.message;
  }
  if (typeof detail === 'string') {
    return detail;
  }
  if (payload && typeof payload.message === 'string') {
    return payload.message;
  }
  return `请求失败：${status}`;
}
