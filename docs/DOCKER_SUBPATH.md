# Docker Compose apps under a gateway path

An app built with `docker compose up -d --build` usually assumes it lives at `/`. To serve it at
`http://<server>:8280/<project>/`, you tell the build its path. Then you add a project in the
gateway that forwards to the container. This page lists exactly which files change, with OccuSafe
(Vite + Python, port 8080) as the worked example.

**Why a rebuild is needed:** Vite and Next.js write the base path and every `VITE_*` /
`NEXT_PUBLIC_*` value into the JavaScript at **build time**. Changing `.env` and restarting does
nothing. The values must go in as build args, and the image must be rebuilt.

**No rebuild possible?** Give the app its own gateway port instead. In the dashboard, set app type
**Prebuilt app**, Exposure **Its own gateway port** (e.g. `8284`), frontend `127.0.0.1:<port>`, and
turn on **Pass the original Host header**. The app stays at `/`, so nothing in it changes.

---

## Vite in Docker: the files to change

| # | File | Change | Always? |
|---|---|---|---|
| 1 | `frontend/Dockerfile` | build with `--base ${VITE_BASE_PATH}` | yes |
| 2 | `docker-compose.yml` → frontend `build.args` | `VITE_BASE_PATH` plus every `VITE_*` URL, prefixed | yes |
| 3 | `docker-compose.yml` → backend `environment` | any URL the backend hands to the browser, prefixed | if it has one |
| 4 | `docker-compose.yml` → frontend `ports` | publish on `127.0.0.1` only | yes |
| 5 | frontend source | router `basename`, hard-coded `/api`, `/logo.png` in code | only if found |
| – | container `nginx.conf` | **no change**: the gateway removes the prefix (path mode `strip`) | – |

### Find the project folder first

```bash
docker ps --filter publish=8080                       # note the NAMES column
docker inspect <container-name> --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}'
```

Use the **container** name (e.g. `occusafe-frontend-1`), not the image name. Images don't carry
the Compose labels, so the image name prints nothing.

### See what the app needs

Run in the project folder. These commands only read files:

```bash
cat docker-compose.yml frontend/Dockerfile frontend/vite.config.*
grep -n '"build"' frontend/package.json
grep -rn "VITE_\|/api\|/ws\|BrowserRouter\|createBrowserRouter" frontend/src frontend/index.html | head -40
grep -rn 'src="/\|href="/' frontend/src | head -20
nginx-gateway-ctl vite-check frontend --prefix /occusafe/
```

The output answers four questions:
- Does the Dockerfile already take `ARG VITE_...` values?
- Does the code read its API address from an env var, or hard-code `/api`?
- Does it use a history router?
- Does the code reference files from `public/` with a leading `/`?

---

## Worked example: OccuSafe at `/occusafe`

Stack in `/opt/occusafe`:
- `frontend`: a Vite build served by nginx on port 80, published as `8080`. Its nginx forwards
  `/api`, `/ws` and `/webrtc`.
- `backend`: Python on port 5000, not published.
- `mediamtx`: camera streams.

The checks found:
- The services read `VITE_API_BASE_URL` and `VITE_WS_URL`.
- There is no React Router.
- `npm run build` is plain `vite build`.

Only two files change.

### `frontend/Dockerfile`

```dockerfile
# before
RUN npm run build

# after
ARG VITE_BASE_PATH=/
RUN npm run build -- --base ${VITE_BASE_PATH}
```

`npm run build -- …` appends the flag to the script, so this works for `vite build` and
`tsc && vite build` alike. The default `/` keeps a plain `docker build` working at the root.

### `docker-compose.yml`: frontend build args

```yaml
# before
    build:
      context: ./frontend

# after
    build:
      context: ./frontend
      args:
        VITE_BASE_PATH: /occusafe/
        VITE_API_BASE_URL: /occusafe/api
        VITE_WS_URL: /occusafe/ws/cameras
```

Each value is the old one with `/occusafe` in front. The Dockerfile already declared these `ARG`s;
without the compose args, the build used its defaults `/api` and `/ws/cameras`.

### `docker-compose.yml`: backend URL sent to the browser

```yaml
# before
      MEDIAMTX_WHEP_URL: /webrtc
# after
      MEDIAMTX_WHEP_URL: /occusafe/webrtc
```

The backend tells the browser where to fetch camera video. Look for every environment value that
starts with `/` and is used by the browser, not between containers. `MEDIAMTX_API_URL:
http://mediamtx:9997` is container-to-container, so it stays.

### `docker-compose.yml`: publish on localhost only

```yaml
# before
      - "${HTTP_PORT:-80}:80"
# after
      - "127.0.0.1:${HTTP_PORT:-80}:80"
```

Docker-published ports bypass `ufw`, so `0.0.0.0:8080` was reachable from any network. Bound to
`127.0.0.1`, only the gateway can reach it.

### Same edits with `sed`

```bash
cd /opt/occusafe
cp docker-compose.yml docker-compose.yml.bak
cp frontend/Dockerfile frontend/Dockerfile.bak

sed -i 's#^      context: ./frontend$#      context: ./frontend\n      args:\n        VITE_BASE_PATH: /occusafe/\n        VITE_API_BASE_URL: /occusafe/api\n        VITE_WS_URL: /occusafe/ws/cameras#' docker-compose.yml
sed -i 's#MEDIAMTX_WHEP_URL: /webrtc$#MEDIAMTX_WHEP_URL: /occusafe/webrtc#' docker-compose.yml
sed -i 's#- "${HTTP_PORT:-80}:80"#- "127.0.0.1:${HTTP_PORT:-80}:80"#' docker-compose.yml
sed -i 's#^RUN npm run build$#ARG VITE_BASE_PATH=/\nRUN npm run build -- --base ${VITE_BASE_PATH}#' frontend/Dockerfile

docker compose up -d --build
```

### Check the build

```bash
docker ps --filter name=occusafe-frontend                            # 127.0.0.1:8080->80/tcp
curl -s http://127.0.0.1:8080/ | grep -o '/occusafe/assets/[^"]*'   # the build uses the new path
curl -s http://127.0.0.1:8080/health                                # backend answers
```

### Gateway project

| Setting | Value |
|---|---|
| Path | `/occusafe` |
| App type | **Built files from a static server** (path mode `strip`) |
| Frontend | `127.0.0.1:8080` |
| Separate API server | none: the container's nginx already forwards `/api`, `/ws`, `/webrtc` |
| Advanced | Timeout `3600` (camera WebSocket), Max upload `25m`, Health path `/health` |

`/occusafe/api/x` reaches the container as `/api/x`, so its `nginx.conf` and the backend don't
change. WebSocket upgrades pass through every gateway route. WebRTC media still uses port 8189
directly, which is expected: only signalling goes through `/webrtc`.

The result is `http://<server>:8280/occusafe/`. `:8080` now answers only on the server itself.

**Undo:** copy the two `.bak` files back, then run `docker compose up -d --build`.

### Source changes OccuSafe did not need

Make these only if the checks above find them:

```tsx
<BrowserRouter basename={import.meta.env.BASE_URL}>                  // history router
const API = import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`   // hard-coded '/api'
<img src={`${import.meta.env.BASE_URL}logo.png`} />                  // public/ file used in code
```

A `<HashRouter>` needs no change. `index.html` and CSS references are rewritten by Vite.

---

## Next.js in Docker: different settings

The idea is the same: set the path at build time, then rebuild. The details differ.

| | Vite | Next.js |
|---|---|---|
| Where the path is set | `--base /occusafe/` | `basePath: '/occusafe'` in `next.config` (no trailing slash) |
| Build-time vars | `VITE_*` | `NEXT_PUBLIC_*` |
| Gateway path mode | `strip`: the container serves at `/` | **`subpath`**: Next.js expects `/occusafe` in every URL. App type **Next.js** sets this |
| Links, router, `/_next/static` | – | prefixed automatically |
| `fetch('/api/...')` | fixed by the API env var | **not** prefixed: edit each call |
| `<Image src="/logo.png">`, `<img>` | `BASE_URL` in code | **not** prefixed: add the base path |
| Container health check on `/` | unaffected | now returns 404: point it at `/occusafe` |

### Files to change

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

**Source**: every root-absolute `fetch` and public-file path:

```tsx
fetch(`${process.env.NEXT_PUBLIC_BASE_PATH}/api/items`)
<Image src={`${process.env.NEXT_PUBLIC_BASE_PATH}/logo.png`} ... />
```

To count them: `nginx-gateway-ctl vite-check <folder> --prefix /myapp/`. It recognises Next.js and
lists the `fetch('/api/...')` calls.

**Gateway:** path `/myapp`, app type **Next.js** (path mode `subpath`), frontend `127.0.0.1:3000`.

**Separate Python backend:**
- **Next.js `rewrites()` proxies `/api` to it:** rewrites follow `basePath` automatically, so there
  is nothing more to do.
- **The browser calls the backend directly:** publish the backend on `127.0.0.1:<port>`. Add it as
  a **Separate API server** with path `/api` and mode `/prefix/api/x → /api/x`.
- **An nginx in front of Next.js** (like OccuSafe's): with `subpath`, that nginx receives
  `/myapp/api/...`. Its `location` blocks would need the prefix, so it is simpler to drop that nginx
  and let the gateway route.

**Many `fetch` calls (dozens)?** The own-gateway-port option at the top needs no source changes.
Smart Finder uses it for that reason (see [ADDING_PROJECTS.md](ADDING_PROJECTS.md)).

---

## Checklist for any Compose app

1. Find the folder: `docker inspect <container> …working_dir`.
2. Back up `docker-compose.yml` and the frontend `Dockerfile`.
3. Pass the base path at build time:
   - Vite: `ARG VITE_BASE_PATH` + `--base`
   - Next.js: `ARG NEXT_BASE_PATH` + `basePath`
4. Prefix every browser-facing URL:
   - build args: `VITE_*` / `NEXT_PUBLIC_*`
   - backend env values that start with `/`
5. Publish the frontend on `127.0.0.1:<port>`.
6. Fix the source only where the checks find a router, a hard-coded `/api` or a `/file.png`.
7. Run `docker compose up -d --build`, then `curl` the container and look for `/<project>/` in the
   HTML.
8. Add the gateway project:
   - Vite build behind nginx: **static server**, `strip`
   - Next.js: **Next.js**, `subpath`
9. Press **Test**, then open the app and check the pages, the live updates and the uploads.
