# Why apps break under a path, and the fix

Short version: **tell the frontend its base path** (for Vite: `--base /myapp/`). The step-by-step
version is in [GUIDE.md](GUIDE.md). This page explains *why*.

## Why it breaks

Vite assumes the app lives at `/`. It writes links that start with `/` into the page:

```html
<script type="module" src="/assets/index-4f2a.js"></script>
```

Open the app at `http://server:8280/myapp/` and the browser asks for `/assets/index-4f2a.js`. That
is outside `/myapp/`, so the gateway has no route for it and the page stays blank.

Two more things break the same way:
- **A router** without a `basename` sees the URL `/myapp/settings` and says "page not found".
- **Code like `fetch('/api/items')`** calls the gateway root instead of your project.

## Why the gateway does not just rewrite the links

We tried. It only works for very simple sites, so it is not the default.

| Idea | Why it fails |
|---|---|
| Rewrite `="/` to `="/myapp/` in responses | Cannot fix URLs the code builds while running (`fetch(base + '/x')`, routers), or minified code. It can also change text that only looks like a URL. |
| Guess the project from the `Referer` or a cookie | Vite dev loads modules from modules, so the `Referer` is not the project path. WebSocket handshakes send none. A cookie is shared by all tabs, so two apps fight. |
| Vite `base: './'` (relative links) | Fine for a hash router. Breaks on deep links such as `/myapp/a/b`, and the dev server ignores it. |

So the gateway offers rewriting only as an optional, best-effort path mode called **`rewrite`**, for
simple multi-page sites you cannot rebuild.

## The fix: tell the app where it lives

Vite accepts `--base` for `dev`, `build` and `preview`. It moves the assets, the dev client and hot
reload under the path, **without editing `vite.config`**. The gateway then forwards requests the way
the app is served. Picking the **App type** in the dashboard sets this for you.

| How the app is served | Start / build it with | Gateway path mode | Host header |
|---|---|---|---|
| `vite` dev server | `npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort` | `subpath`: `/myapp/...` is forwarded unchanged | `127.0.0.1:5173` |
| `vite preview` | `vite build --base /myapp/`, then `vite preview --base /myapp/ --host 127.0.0.1 --port 4173` | `subpath` | `127.0.0.1:4173` |
| Static files (Docker nginx, `serve -s`, Caddy) | `vite build --base /myapp/` | `strip`: `/myapp` is removed | original |
| Files served by your own backend | `vite build --base /myapp/` | `strip` | original |
| Next.js | `basePath` in `next.config`, rebuild | `subpath` | original |
| Cannot rebuild | nothing | its **own port** (served at `/`) | original |

**What do `subpath` and `strip` mean?**
- `subpath`: the gateway sends `/myapp/page` to the app as `/myapp/page`. The app knows its path.
- `strip`: the gateway sends `/myapp/page` to the app as `/page`. The app thinks it is at `/`.

**Why Vite gets "Host 127.0.0.1:5173".** Since Vite 6.0.9 (and 5.4.12), the dev and preview servers
refuse requests whose `Host` is not localhost or an IP address. You would see "Blocked request. This
host is not allowed". With **Pass the original Host header** turned off (the Vite types do this
for you), the gateway sends an IP and Vite accepts it. No `allowedHosts` change needed.

**Hot reload.** The Vite client opens its WebSocket on the page's own address plus the base
(`ws://server:8280/myapp/`), so it goes through the gateway. Don't set `server.hmr.port`. If the
browser console still shows WebSocket errors, add `server.hmr.clientPort: 8280`.

## Small code changes, only where needed

`import.meta.env.BASE_URL` is just `/` without the gateway, so the same code works in both places.

1. **A router with real URLs:**

   ```tsx
   <BrowserRouter basename={import.meta.env.BASE_URL}>
   createBrowserRouter(routes, { basename: import.meta.env.BASE_URL })
   createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes })   // Vue
   ```

   A hash router (`<HashRouter>`, `createWebHashHistory()`) needs no change.

2. **API calls written as `/api/...`.** If the app reads its API address from a variable
   (`VITE_API_BASE`, ...), set the variable to `/myapp/api`. No code change. Otherwise:

   ```ts
   const API = import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`
   ```

3. **Files from `public/` used in code** (`'/logo.png'`):
   `` `${import.meta.env.BASE_URL}logo.png` ``. Links in `index.html` and CSS are fixed by Vite.

4. **Optional:** put the base in `vite.config` instead of the command line:
   `base: process.env.VITE_BASE_PATH ?? '/'`. See `examples/vite.config.example.ts`.

**Full URLs like `http://127.0.0.1:8000`** only work on the server itself. A browser on another
device would call *its own* port 8000. Use a path on the gateway instead.

## Restart or rebuild

| How it runs | What to do |
|---|---|
| systemd | Put the variables in the service (`sudo systemctl edit <service>`, then `[Service]` `Environment=VITE_BASE_PATH=/myapp/`), then `sudo systemctl restart <service>`. |
| Docker | The base is saved at build time. Use `docker build --build-arg VITE_BASE_PATH=/myapp/ ...` (see `examples/Dockerfile.vite-subpath.example`). |
| tmux | Stop the old process (Ctrl-C) and start it again with the command from the project's **Guide**. |

## Checking

- **Before:** `nginx-gateway-ctl vite-check <folder> --prefix /myapp/` reads your project and lists
  what will break. It never changes anything.
- **After:** press **Test** in the dashboard. If the page still points outside the path, it names
  the exact file.

## Backends behind a path

**Your backend never needs a change.** The gateway removes the path first.

- **All routes under `/api`:** API path `/api`, mode `strip_prefix` (the backend sees `/api/x`).
- **Many top-level routes** (`/login`, `/users`, ...): give them one path such as `/backend`, mode
  `strip_all` (the backend sees `/login`). Point the frontend's API address at `/myapp/backend`.
- **FastAPI's `/docs` page** needs `FastAPI(root_path="/myapp")` to find its OpenAPI file. Normal
  routes work without it.
- **Streaming (SSE, token streams)** works because buffering is off for API routes. The default
  timeout is an hour per request. Raise **Timeout** for longer jobs.
