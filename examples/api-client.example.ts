// API calls that follow the app's base path.
//
// Without the gateway:  BASE_URL = "/"         -> /api/items         (Vite dev proxy or same server)
// Behind the gateway:   BASE_URL = "/prajna/"  -> /prajna/api/items  -> nginx -> backend /api/items
//
// VITE_API_BASE still wins when set, e.g. VITE_API_BASE=/prajna/api.
export const API_BASE: string =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/+$/, '') ||
  `${import.meta.env.BASE_URL}api`

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: 'same-origin' })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

// WebSockets and server-sent events: build the URL from the page's own address, so they
// go through the gateway port too.
export function socketUrl(path: string): string {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}${API_BASE}${path}`
}
export const events = () => new EventSource(`${API_BASE}/events`)

// Files from public/: never '/logo.svg', always
export const logo = `${import.meta.env.BASE_URL}logo.svg`
