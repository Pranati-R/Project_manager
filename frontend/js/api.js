// Calls to the manager API. URLs are relative ("api/..."), so the dashboard works on the
// admin port, behind any prefix, or through an SSH tunnel to 127.0.0.1:8790.

let csrf = null;

export function setCsrf(token) { csrf = token; }

export class ApiError extends Error {
  constructor(status, detail) {
    super((detail && detail.message) || `request failed (HTTP ${status})`);
    this.status = status;
    this.detail = detail || {};
  }
}

export async function api(method, path, body) {
  const opts = { method, headers: { Accept: 'application/json' }, credentials: 'same-origin' };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  if (method !== 'GET' && csrf) opts.headers['X-CSRF-Token'] = csrf;
  let res;
  try {
    res = await fetch('api/' + path, opts);
  } catch (e) {
    throw new ApiError(0, { message: 'cannot reach the manager; is nginx-gateway-manager running?' });
  }
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    let detail = data && data.detail;
    if (typeof detail === 'string') detail = { message: detail };
    if (Array.isArray(detail)) detail = { message: 'invalid request', errors: detail.map(e => ({ field: (e.loc || []).slice(1).join('.'), message: e.msg })) };
    if (res.status === 401) window.dispatchEvent(new CustomEvent('auth-required'));
    throw new ApiError(res.status, detail);
  }
  return data;
}

export const get = path => api('GET', path);
export const post = (path, body) => api('POST', path, body === undefined ? {} : body);
export const put = (path, body) => api('PUT', path, body);
export const del = path => api('DELETE', path);
