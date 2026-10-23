# Vite (and other SPAs) under a gateway path

## Why it breaks

Vite assumes the app lives at `/` (`base: '/'`) and writes root-absolute URLs into the build:

```html
<script type="module" src="/assets/index-4f2a.js"></script>   <!-- index.html -->
```

The same root-absolute URLs appear in several other places:
- CSS `url(/assets/…)`
- the JS module-preload helper
- in dev mode: `/@vite/client`, `/src/main.tsx` and `/node_modules/.vite/deps/…`

Open the app at `http://server:8280/prajna/` and the browser asks for `/assets/index-4f2a.js`,
which is outside `/prajna/`, so no route matches. Two more things break:
- **React Router** without a `basename` sees the path `/prajna/settings` and shows its "not found"
  route.
- **Code like `fetch('/api/items')`** calls the gateway root instead of the project's API.

## Can nginx rewrite this instead?

**Only for simple sites, so it is not the default.** We tried each option:

| Option | Result |
|---|---|
| `sub_filter` on HTML/CSS/JS (`="/` → `="/prajna/`) | Fixes literal strings in responses. It cannot fix URLs the code *builds* at runtime (`fetch(base + '/x')`, the router, `new URL('/x', location)`), or minified chunks that join strings. It also needs uncompressed upstream responses and touches any text that happens to look like a URL. |
| Routing unprefixed requests by `Referer` or a cookie | Vite dev loads modules from modules, so their `Referer` is `/src/...`, not `/prajna/`. WebSocket handshakes carry no `Referer`. A cookie is shared by every tab, so two apps open at once fight over it. |
| Vite `base: './'` (relative) | Works for a production build that stays on one URL or uses a hash router. Deep links of a history-routed SPA (`/prajna/a/b`) resolve `./assets` to `/prajna/a/assets`. The dev server ignores it. |

That is why the gateway only offers rewriting as an opt-in, best-effort **`rewrite`** path mode, for
simple multi-page sites you cannot rebuild. The end-to-end test verifies that it rewrites `href`,
`src`, `url()` and `"/assets/` while leaving protocol-relative `//cdn…` URLs alone.

## The working approach: tell the app its base path

Vite accepts `--base` on the command line for `dev`, `build` and `preview`. That moves the assets,
the dev client and the hot-reload socket under the prefix, **without editing `vite.config`**. The
gateway then forwards the path to match the way the app is served. The dashboard's **App type**
choice sets this for you:

| How the app is served | Start / build it with | Gateway path mode | Host header to the app |
|---|---|---|---|
| `vite` dev server | `npm run dev -- --base /prajna/ --host 127.0.0.1 --port 8200 --strictPort` | `subpath`: forwards `/prajna/...` unchanged | `127.0.0.1:8200` |
| `vite preview` | `vite build --base /prajna/` then `vite preview --base /prajna/ --host 127.0.0.1 --port 8200` | `subpath` | `127.0.0.1:8200` |
| static files (Docker nginx, `serve -s`, Caddy) | `vite build --base /prajna/` | `strip`: forwards `/...` | original |
| files served by the app's own backend | `vite build --base /prajna/` | `strip` | original |
| Next.js | `basePath` in `next.config` + rebuild | `subpath` | original |
| prebuilt, cannot rebuild | (nothing) | its **own port** (served at `/`) | original |

**Why "Host 127.0.0.1:8200" for Vite.** Since Vite 6.0.9 (and 5.4.12), the dev and preview servers
reject requests whose `Host` is not localhost or an IP address. You would see "Blocked request.
This host is not allowed" when you browse by MagicDNS name. With the original Host header turned off
(the Vite preset does this), the gateway sends `Host: 127.0.0.1:<port>`, and Vite accepts it without
an `allowedHosts` change.

**Hot reload.** The Vite client opens its WebSocket at the page's own host and port plus the base
(`ws://server:8280/prajna/`), so it goes through the gateway. Every route forwards WebSocket
upgrades. Don't set `server.hmr.port`. If the browser console shows WebSocket errors anyway, add
`server.hmr.clientPort: 8280`. The end-to-end test runs a real Vite dev server under `/viteapp/` and
connects its HMR socket through the gateway.

### App changes, only where needed

Each is one line. Because `import.meta.env.BASE_URL` is `/` without the gateway, the same code still
works at the root and in local development.

1. **Client-side routing with history URLs:**

   ```tsx
   <BrowserRouter basename={import.meta.env.BASE_URL}>
   createBrowserRouter(routes, { basename: import.meta.env.BASE_URL })
   createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes })   // Vue
   ```

   A hash router (`<HashRouter>`, `createWebHashHistory()`) needs no change.

2. **API calls written as `/api/...`:**
   - If the app already reads its API address from an env var (`VITE_API_BASE`, `VITE_API_BASE_URL`,
     …), set that var instead: `VITE_API_BASE=/prajna/api`. No code change.
   - Otherwise:

     ```ts
     const API = import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`
     ```

   The gateway sends `/prajna/api/x` to the backend as `/api/x` (API mode `strip_prefix`), so the
   backend does not change.

3. **Files from `public/` referenced in code** (`'/logo.png'`): use
   `` `${import.meta.env.BASE_URL}logo.png` ``. References in `index.html` and CSS are rewritten by
   Vite automatically.

4. **Optional:** keep the base in `vite.config` instead of on the command line:
   `base: process.env.VITE_BASE_PATH ?? '/'`. See `examples/vite.config.example.ts`.

**Absolute API URLs** like `http://127.0.0.1:8000` work only on the server itself. A browser on
another device would call its *own* port 8000. Use a path on the gateway instead.

### Rebuild and restart

| Runtime | What to do |
|---|---|
| systemd | Put the variables in the unit (`sudo systemctl edit <unit>` → `[Service] Environment=VITE_BASE_PATH=/prajna/`), then `sudo systemctl restart <unit>`. Add the unit to `/etc/nginx-gateway/restart-targets.conf` to get a Restart button in the dashboard. |
| Docker | The base is baked in at build time. See `examples/Dockerfile.vite-subpath.example`: `docker build --build-arg VITE_BASE_PATH=/app/ …` and `docker run -p 127.0.0.1:8300:80 …`. |
| tmux | Stop the old process (Ctrl-C) and start it again with the command from the project's **Guide**. |

### Checking

- **Before:** `nginx-gateway-ctl vite-check <folder> --prefix /prajna/` reads the project and lists
  what will break. This covers base, router, root-absolute fetches, public files, API env vars,
  exposed dev-server hosts and HMR settings. It prints the commands; it never writes anything.
- **After:** use **Test** in the dashboard. It loads the page through the gateway and fails with the
  exact file when the page still points outside the prefix.

## Backends behind a prefix

- **One API root (`/api/...`):** API path `/api`, mode `strip_prefix`, so the backend sees `/api/x`.
- **Many top-level routes** (`/auth`, `/voice`, `/history`, …): give them one path, such as
  `/backend` in mode `strip_all`, so the backend sees `/auth/...`. Then point the app's API base at
  `/<project>/backend`.
- **FastAPI's `/docs`** behind the gateway needs `root_path` (`FastAPI(root_path="/prajna")`) so the
  OpenAPI URL is right. Routing works without it.
- **Streaming (SSE, token streams)** works because API routes have buffering off by default. Timeouts
  default to an hour per request. Raise **Timeout** for longer jobs.
