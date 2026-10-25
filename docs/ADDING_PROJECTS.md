# Adding projects

New here? Read **[GUIDE.md](GUIDE.md)** first. It explains what to change in your app, step by step.
This page covers the dashboard form, ready-made recipes, and the JSON/API formats.

## Add a project in the dashboard

**Projects -> Add project**:
1. **Name.** The ID and URL path fill themselves in.
2. **App type.** This sets the right options for you.
3. **Frontend port.** The port your app listens on. Tick **Separate API server** if the backend has
   its own port.
4. **Add and apply.**

The editor shows the nginx routes as you type. On save, the manager checks the project and tests the
whole nginx configuration. Only then does it go live. If anything is wrong, nothing changes and the
error shows next to the field.

Then press **Test**. It reports:
- **Reachability:** does the app answer directly?
- **Exposure:** is the app listening on all interfaces (reachable without the gateway)?
- **Gateway check:** does the page load through the gateway?
- **Asset paths:** do the page's files load from the right path?

**Guide** shows the exact commands for your app.

---

## Recipes

The ports and names are examples. Use your own.

### Recipe 1: Vite frontend + backend with `/api` routes

- Path `/myapp`, App type **Vite dev server**, frontend port `5173`
- **Separate API server**: port `8000`, path `/api`, mode `/prefix/api/x -> /api/x`

Start the frontend:

```bash
VITE_API_BASE=/myapp/api npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort
```

(`VITE_API_BASE` is only needed if your app reads its API address from a variable like this.)

Start the backend on `127.0.0.1:8000` as you always do. **Its code does not change.**

| Browser asks for | Goes to |
|---|---|
| `http://<server>:8280/myapp/` | the Vite app |
| `http://<server>:8280/myapp/api/users` | the backend, as `/api/users` |

For a production build use App type **Vite preview**, or **Built files from a static server** if
something else serves `dist/`.

### Recipe 2: Frontend + backend with many top-level routes

Your backend has routes like `/login`, `/users`, `/files`, `/history`. Give them all one path and
let the gateway remove it.

- Path `/myapp`, App type **Vite dev server**, frontend port `5173`
- **Separate API server**: port `8000`, path `/backend`, mode **`/prefix/api/x -> /x`**

```bash
VITE_API_BASE_URL=/myapp/backend npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort
```

`/myapp/backend/login` reaches the backend as `/login`. The backend does not change.

If the app uses a hash router (`/#/page`) it needs no router change either.

### Recipe 3: Next.js with a lot of `fetch('/api/...')` calls

`basePath` does not add the path to your own `fetch()` calls, so a path would mean editing every
one. The no-change way is a port of its own.

- Exposure **Its own gateway port** `8282`, App type **Next.js**, frontend port `3000`
- Make the app listen on `127.0.0.1` only.

Open `http://<server>:8282/`. It is still behind nginx. Nothing in the app changes.

### Recipe 4: A built site in Docker

- Build with the base path: `docker build --build-arg VITE_BASE_PATH=/myapp/ -t myapp .`
- Run: `docker run -d --name myapp --restart unless-stopped -p 127.0.0.1:8300:80 myapp`
- Dashboard: path `/myapp`, App type **Built files from a static server**, frontend port `8300`

For Docker Compose see [DOCKER_SUBPATH.md](DOCKER_SUBPATH.md).

### Other app types

| App | Settings |
|---|---|
| App that serves its own built frontend (FastAPI `StaticFiles`, Express) | **Built files served by the app's own backend** (mode `strip`) |
| Prebuilt app you cannot rebuild | **Prebuilt app**, Exposure *its own gateway port* |
| One app that must own `/` of the gateway port | path `/`. Other paths still win, and the landing page is replaced |

---

## Restart targets

The dashboard can restart only what an administrator lists in
`/etc/nginx-gateway/restart-targets.conf`. Edit it with `sudo nginx-gateway-ctl restart-targets`.

```
# <id>               <systemd|docker>  <service or container>
myapp-frontend       systemd           myapp-frontend.service
myapp-api            docker            myapp-api
```

Then pick the id as **Restart target** in the project's Advanced settings.

## Many projects at once (JSON)

`examples/projects-example.json` has three sample projects. Import it with:

```bash
sudo nginx-gateway-ctl projects import /tmp/projects-example.json      # merge by id
sudo nginx-gateway-ctl projects import /tmp/projects.json --replace    # replace all
sudo nginx-gateway-ctl projects export > projects-backup.json
```

The `nginx-gw` account must be able to read the file, so `/tmp` works. You can also use **Settings ->
Import** in the dashboard. The import is checked and applied like any other change.

### Project fields

| Field | Values |
|---|---|
| `id` | `a-z 0-9 -`, 1-40 characters; cannot change later |
| `name` | display name |
| `enabled` | `true` / `false`; disabled paths answer 404 |
| `exposure` | `path` (default) or `port` |
| `prefix` | `/name` (up to 4 segments, lowercase), or `/` for one root app |
| `dedicated_port` | for `exposure: port`, 1024-65535 |
| `frontend` | `{host, port, path_mode}`; host is an IP; `path_mode`: `subpath`, `strip` or `rewrite` |
| `backend` | `{host, port, api_path, api_mode, buffering}`; `api_mode`: `strip_prefix`, `strip_all` or `preserve` |
| `pass_host_header` | `false` sends `Host: <app host:port>` (needed for Vite) |
| `read_timeout` | seconds, 5-86400 (WebSockets and long requests) |
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
