# Adding projects

In the dashboard: **Projects → Add project**.
1. **Name.** The ID and URL path fill themselves in.
2. **App type.** This sets the right proxy behaviour.
3. **Port.** Where the app listens on the server. Add a **Separate API server** if the backend is on
   its own port.
4. **Save and apply.**

The editor shows the exact nginx routes as you type. On save, the manager validates the project and
runs `nginx -t` on the whole configuration. Then it reloads nginx, and the new path is live. If
anything is wrong, nothing changes and the error shows next to the field.

Then press **Test** on the project. It reports these:
- **Reachability:** whether the app is reachable directly.
- **Exposure:** whether the app is bound to all interfaces (exposed without the gateway).
- **The gateway check:** whether the page loads through the gateway.
- **Asset paths:** whether the page's files stay under its path.

**Guide** shows the commands for that app.

The examples below are the three apps from the request. The notes come from running `vite-check`
on their source. The ports are examples: use the ones your apps listen on.

---

## Prajna: Vite dev server + FastAPI, on a path

`sql-llm/frontend` uses Vite 8 and React Router 7. Here is what `vite-check` found:

```
XX <BrowserRouter> without basename                         src/App.jsx:29
-- the API address comes from VITE_API_BASE: set it to /prajna/api (no code change)
!! the dev server listens on all interfaces by default      vite.config.js (VITE_HOST || '0.0.0.0')
!! hard-coded public file /logo.png (7 places)               src/pages/AuthPage.jsx:70, ...
```

**Dashboard settings:**
- path `/prajna`
- app type **Vite dev server**
- frontend `127.0.0.1:8200`
- separate API server `127.0.0.1:8201`, path `/api`, mode `/prefix/api/x → /api/x`

**Code (two small edits):**

```jsx
// src/App.jsx
<BrowserRouter basename={import.meta.env.BASE_URL}>
// every <img src="/logo.png">
<img src={`${import.meta.env.BASE_URL}logo.png`} />
```

**Start the frontend:** `--host` and `--port` override the defaults in its `vite.config`.

```bash
cd ~/sql-llm/frontend
VITE_API_BASE=/prajna/api npm run dev -- --base /prajna/ --host 127.0.0.1 --port 8200 --strictPort
```

**Start the backend** on `127.0.0.1:8201`. Its routes stay `/api/...`.

The result:

| Request | Goes to |
|---|---|
| `http://<server>:8280/prajna/` | the Vite dev server, with hot reload |
| `http://<server>:8280/prajna/api/...` | the backend, as `/api/...` |

For a production build use app type **Vite preview** with `vite build --base /prajna/` and
`vite preview --base /prajna/ …`. Or use **Built files from a static server** if something else
serves `dist/`.

## Meeting Transcriber: hash router + a backend with many routes

`Transcriber-meeting-initial/frontend` uses Vite 8, `<HashRouter>` and `base: './'`. It reads
`VITE_API_BASE_URL`. Its backend has many top-level routes: `/auth`, `/voice`, `/history`,
`/settings`, `/chat`, `/files`, `/mom`, `/ai-chat`, …

- The hash router already works under any path, so no basename change is needed.
- Give the backend **one** path and let the gateway strip it.

**Dashboard settings:**
- path `/meeting-transcriber`
- app type **Vite dev server**, frontend `127.0.0.1:8300`
- separate API server `127.0.0.1:8301`, path `/backend`, mode **`/prefix/api/x → /x`** (`strip_all`)
- Advanced: Timeout `7200`, Max upload `500m`, Health path `/health`

**Start:**

```bash
cd ~/Transcriber-meeting-initial/frontend
VITE_API_BASE_URL=/meeting-transcriber/backend \
  npm run dev -- --base /meeting-transcriber/ --host 127.0.0.1 --port 8300 --strictPort
```

`/meeting-transcriber/backend/auth/login` reaches the backend as `/auth/login`.

- **Production build:** `base: './'` plus the hash router means `npx vite build` works as is, with
  app type **Built files from a static server**.
- **Training modules:** `vite-check` also warns that `src/features/training/api/*.ts` default to
  `/api/training/...`. Check that they build their URL from `VITE_API_BASE_URL` too.

## Smart Finder: Next.js with many `/api` calls, on its own port

`info-ai/workspace` is Next.js 16. `vite-check` counts **52** `fetch('/api/...')` calls in
components. Next.js's `basePath` does not prefix `fetch()`, so a path would mean editing all of
them. The zero-change option is its own gateway port.

**Dashboard settings:**
- Exposure **Its own gateway port** `8282`
- app type **Next.js**
- frontend `127.0.0.1:3000`
- Timeout `7200` (long searches), Max upload `100m` (it uploads 8 MB chunks)

**On the server**, make Smart Finder listen only locally. In `/etc/smartfinder/smartfinder.conf`, set
`FRONTEND_HOST=127.0.0.1`, then run `sudo smartfinder-ctl restart`.

The result is `http://<server>:8282/`: still through nginx, still Tailscale-only. Next.js's own
`/api` rewrite to its backend keeps working unchanged.

To restart it from the dashboard, allowlist the service:

```bash
echo 'smart-finder systemd smartfinder-frontend.service' | sudo tee -a /etc/nginx-gateway/restart-targets.conf
```

Then pick `smart-finder` as **Restart target** in the project's Advanced settings.

---

## Other app types

| App | Settings |
|---|---|
| Static site or SPA built with `--base /x/`, in Docker (`examples/Dockerfile.vite-subpath.example`) | path `/x`, **Built files from a static server** (mode `strip`), frontend `127.0.0.1:<published port>`; publish with `-p 127.0.0.1:PORT:80` |
| App that serves its built frontend itself (FastAPI `StaticFiles`, Express) | **Built files served by the app's own backend** (mode `strip`) |
| Prebuilt `.deb` app you cannot rebuild | **Prebuilt app** → Exposure *own port*. Or try path mode `rewrite` if it is a simple multi-page site |
| Exactly one app that must own `/` of the gateway port | path `/`. Other paths still win, and the landing page is replaced |

## Restart targets

The dashboard can restart only what root lists in `/etc/nginx-gateway/restart-targets.conf`. Edit it
with `sudo nginx-gateway-ctl restart-targets`.

```
# <id>               <systemd|docker>  <unit or container>
prajna-frontend      systemd           prajna-frontend.service
smart-finder         docker            smart-finder
```

## Many projects at once (JSON)

`examples/projects-example.json` contains all three projects above. Import it with:

```bash
sudo nginx-gateway-ctl projects import /tmp/projects-example.json      # merge by id
sudo nginx-gateway-ctl projects import /tmp/projects.json --replace    # replace all
sudo nginx-gateway-ctl projects export > projects-backup.json
```

The `nginx-gw` account must be able to read the file, so `/tmp` works. You can also use **Settings →
Import** in the dashboard. The import is validated and applied like any other change.

### Project fields

| Field | Values |
|---|---|
| `id` | `a-z 0-9 -`, 1–40 characters; cannot change later |
| `name` | display name |
| `enabled` | `true` / `false`; disabled paths answer 404 |
| `exposure` | `path` (default) or `port` |
| `prefix` | `/name` (up to 4 segments, lowercase), or `/` for one root app |
| `dedicated_port` | for `exposure: port`, 1024–65535 |
| `frontend` | `{host, port, path_mode}`; host is an IP; `path_mode`: `subpath`, `strip` or `rewrite` |
| `backend` | `{host, port, api_path, api_mode, buffering}`; `api_mode`: `strip_prefix`, `strip_all` or `preserve` |
| `pass_host_header` | `false` sends `Host: <app host:port>` (needed for Vite) |
| `read_timeout` | seconds, 5–86400 (WebSockets and long requests) |
| `max_body_size` | e.g. `100m` |
| `health_path` | e.g. `/health`, used by Test |
| `app_kind` | `vite_dev`, `vite_preview`, `static_dist`, `backend_served`, `nextjs`, `prebuilt` or `other` |
| `runtime` | `systemd`, `docker`, `tmux` or `other` (only used for the guide) |
| `restart_target` | an id from `restart-targets.conf` |
| `app_dir`, `notes` | used in the guide only |

## From scripts (API)

See `examples/api-requests.http`. In short:
1. `POST /api/auth/login` returns a session cookie plus a `csrf` token.
2. Every change sends that token back in the `X-CSRF-Token` header:
   - `POST /api/projects` adds a project
   - `PUT /api/projects/<id>` edits it
   - `DELETE /api/projects/<id>` removes it
   - `POST /api/projects/<id>/enable` and `/disable` switch it on and off
   - `POST /api/projects/<id>/test` runs the checks
   - `POST /api/config/apply` applies the config
