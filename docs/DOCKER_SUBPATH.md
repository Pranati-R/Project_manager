# Docker Compose apps under a gateway path

New to this? Read [GUIDE.md](GUIDE.md) first, section 7. This page lists exactly which files to
change, with a full worked example.

An app started with `docker compose up -d --build` usually assumes it lives at `/`. To serve it at
`http://<server>:8280/myapp/`, you tell the build its path, rebuild, and add a project in the
gateway.

**Why a rebuild?** Vite and Next.js write the base path and every `VITE_*` / `NEXT_PUBLIC_*` value
into the JavaScript **while building**. Changing `.env` and restarting does nothing. Pass the values
as build args and rebuild the image.

**Your backend container needs no code change.** The gateway removes `/myapp` before the request
arrives.

**Cannot rebuild?** Give the app its own gateway port: App type **Prebuilt app**, Exposure **Its own
gateway port** (for example `8284`), frontend `127.0.0.1:<port>`, and turn on **Pass the original
Host header**. The app stays at `/`, so nothing in it changes.

---

## Vite in Docker: files to change

| # | File | Change | Always? |
|---|---|---|---|
| 1 | `frontend/Dockerfile` | build with `--base ${VITE_BASE_PATH}` | yes |
| 2 | `docker-compose.yml`, frontend `build.args` | `VITE_BASE_PATH` plus every `VITE_*` URL, with the path in front | yes |
| 3 | `docker-compose.yml`, backend `environment` | any URL the backend hands to the *browser*, with the path in front | only if it has one |
| 4 | `docker-compose.yml`, frontend `ports` | publish on `127.0.0.1` only | yes |
| 5 | frontend source | router `basename`, hard-coded `/api`, `/logo.png` in code | only if found |
| - | container `nginx.conf` | **no change**: the gateway removes the path (mode `strip`) | - |

### Find the project folder

```bash
docker ps --filter publish=8080                       # note the NAMES column
docker inspect <container-name> --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}'
```

Use the **container** name, not the image name. Images do not carry the Compose labels.

### See what the app needs

These commands only read files:

```bash
cat docker-compose.yml frontend/Dockerfile frontend/vite.config.*
grep -n '"build"' frontend/package.json
grep -rn "VITE_\|/api\|/ws\|BrowserRouter\|createBrowserRouter" frontend/src frontend/index.html | head -40
grep -rn 'src="/\|href="/' frontend/src | head -20
nginx-gateway-ctl vite-check frontend --prefix /myapp/
```

They answer four questions:
- Does the Dockerfile already take `ARG VITE_...` values?
- Does the code read its API address from a variable, or hard-code `/api`?
- Does it use a router with real URLs?
- Does the code use files from `public/` with a leading `/`?

---

## Worked example: a Compose app at `/myapp`

A stack in `/opt/myapp`:
- `frontend`: a Vite build served by nginx on port 80, published as `8080`. Its nginx forwards
  `/api`, `/ws` and `/media`.
- `backend`: Python on port 5000, not published.

The checks found that the app reads `VITE_API_BASE_URL` and `VITE_WS_URL`, has no router, and builds
with plain `vite build`. So two files change.

### `frontend/Dockerfile`

```dockerfile
# before
RUN npm run build

# after
ARG VITE_BASE_PATH=/
RUN npm run build -- --base ${VITE_BASE_PATH}
```

`npm run build -- ...` adds the flag to the script, so it works for `vite build` and
`tsc && vite build` alike. The default `/` keeps a plain `docker build` working without the gateway.

### `docker-compose.yml`: frontend build args

```yaml
# before
    build:
      context: ./frontend

# after
    build:
      context: ./frontend
      args:
        VITE_BASE_PATH: /myapp/
        VITE_API_BASE_URL: /myapp/api
        VITE_WS_URL: /myapp/ws
```

Each value is the old one with `/myapp` in front.

### `docker-compose.yml`: a URL the backend sends to the browser

```yaml
# before
      MEDIA_URL: /media
# after
      MEDIA_URL: /myapp/media
```

Look for every setting that starts with `/` and is used by the **browser**. An address between
containers such as `http://db:5432` stays as it is.

### `docker-compose.yml`: publish on localhost only

```yaml
# before
      - "8080:80"
# after
      - "127.0.0.1:8080:80"
```

Ports published by Docker skip the firewall (`ufw`), so `0.0.0.0:8080` is reachable from any
network. Bound to `127.0.0.1`, only the gateway can reach it.

### Rebuild and check

```bash
cd /opt/myapp
cp docker-compose.yml docker-compose.yml.bak
cp frontend/Dockerfile frontend/Dockerfile.bak
# ...make the edits above...
docker compose up -d --build

docker ps --filter name=myapp-frontend                              # 127.0.0.1:8080->80/tcp
curl -s http://127.0.0.1:8080/ | grep -o '/myapp/assets/[^"]*'      # paths start with /myapp/
```

### Gateway project

| Setting | Value |
|---|---|
| Path | `/myapp` |
| App type | **Built files from a static server** (path mode `strip`) |
| Frontend | `127.0.0.1:8080` |
| Separate API server | none: the container's nginx already forwards `/api`, `/ws`, `/media` |
| Advanced | Timeout `3600` if you use WebSockets, Max upload as needed, Health path `/health` |

`/myapp/api/x` reaches the container as `/api/x`, so its `nginx.conf` and the backend do not change.
WebSocket upgrades pass through every gateway route.

The result is `http://<server>:8280/myapp/`. Port `8080` now answers only on the server itself.

**Undo:** copy the two `.bak` files back, then run `docker compose up -d --build`.

### Source changes only if the checks found them

```tsx
<BrowserRouter basename={import.meta.env.BASE_URL}>                  // router with real URLs
const API = import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`   // hard-coded '/api'
<img src={`${import.meta.env.BASE_URL}logo.png`} />                  // public/ file used in code
```

A `<HashRouter>` needs no change. Links in `index.html` and CSS are fixed by Vite.

---

## Next.js in Docker

Same idea (set the path at build time, then rebuild), different settings.

| | Vite | Next.js |
|---|---|---|
| Where the path is set | `--base /myapp/` | `basePath: '/myapp'` in `next.config` (no trailing slash) |
| Build-time variables | `VITE_*` | `NEXT_PUBLIC_*` |
| Gateway path mode | `strip`: the container serves at `/` | **`subpath`**: Next.js expects `/myapp` in every URL. App type **Next.js** sets this |
| Links, router, `/_next/static` | - | prefixed automatically |
| `fetch('/api/...')` | fixed by the API variable | **not** prefixed: edit each call |
| `<Image src="/logo.png">`, `<img>` | `BASE_URL` in code | **not** prefixed: add the base path |
| Container health check on `/` | unaffected | now returns 404: point it at `/myapp` |

**`next.config.js` / `next.config.ts`:**

```ts
const nextConfig = {
  basePath: process.env.NEXT_BASE_PATH || '',
  env: { NEXT_PUBLIC_BASE_PATH: process.env.NEXT_BASE_PATH || '' },
  // ...
}
```

**`Dockerfile`**, build stage, before `npm run build`:

```dockerfile
ARG NEXT_BASE_PATH=
ENV NEXT_BASE_PATH=${NEXT_BASE_PATH}
RUN npm run build
```

**`docker-compose.yml`:**

```yaml
    build:
      context: .
      args:
        NEXT_BASE_PATH: /myapp
    ports:
      - "127.0.0.1:3000:3000"
```

**Source**: every root-absolute `fetch` and public file:

```tsx
fetch(`${process.env.NEXT_PUBLIC_BASE_PATH}/api/items`)
<Image src={`${process.env.NEXT_PUBLIC_BASE_PATH}/logo.png`} ... />
```

To count them: `nginx-gateway-ctl vite-check <folder> --prefix /myapp/`.

**Gateway:** path `/myapp`, App type **Next.js** (path mode `subpath`), frontend `127.0.0.1:3000`.

**With a separate Python backend:**
- **Next.js `rewrites()` proxies `/api` to it:** rewrites follow `basePath`, so nothing more to do.
- **The browser calls the backend directly:** publish it on `127.0.0.1:<port>` and add it as a
  **Separate API server** with path `/api` and mode `/prefix/api/x -> /api/x`.
- **An nginx in front of Next.js:** with `subpath` it receives `/myapp/api/...`, so its `location`
  blocks would need the prefix. It is simpler to remove that nginx and let the gateway route.

**Dozens of `fetch` calls?** The own-gateway-port option (see the top of this page) needs no source
changes.

---

## Checklist for any Compose app

1. Find the folder: `docker inspect <container> ...working_dir`.
2. Back up `docker-compose.yml` and the frontend `Dockerfile`.
3. Pass the base path at build time:
   - Vite: `ARG VITE_BASE_PATH` + `--base`
   - Next.js: `ARG NEXT_BASE_PATH` + `basePath`
4. Add the path in front of every browser-facing URL:
   - build args: `VITE_*` / `NEXT_PUBLIC_*`
   - backend settings that start with `/`
5. Publish the frontend on `127.0.0.1:<port>`.
6. Fix the source only where the checks find a router, a hard-coded `/api` or a `/file.png`.
7. Run `docker compose up -d --build`, then `curl` the container and look for `/<project>/` in the
   HTML.
8. Add the gateway project:
   - Vite build behind nginx: **static server**, `strip`
   - Next.js: **Next.js**, `subpath`
9. Press **Test**, then open the app and check the pages, live updates and uploads.
