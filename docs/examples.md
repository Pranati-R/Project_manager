# Examples

Ready-made recipes. The names and ports are examples. Use your own.

## Recipe 1: Vite frontend and a backend with `/api` routes

**Dashboard**

- Path `/myapp`, App type **Vite dev server**, Frontend port `5173`
- **Separate API server:** port `8000`, API path `/api`, `/prefix/api/x -> /api/x`

**Start the frontend**

```bash
VITE_API_BASE=/myapp/api npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort
```

(`VITE_API_BASE` is only needed if your app reads its API address from a variable like this.)

**Start the backend** on `127.0.0.1:8000` as always. Its code does not change.

| Browser asks for | Goes to |
|---|---|
| `http://<server>:8280/myapp/` | the Vite app |
| `http://<server>:8280/myapp/api/users` | the backend, as `/api/users` |

For a production build use App type **Vite preview**, or **Built files from a static server** when
something else serves `dist/`.

## Recipe 2: Frontend and a backend with many top-level routes

Your backend has routes such as `/login`, `/users`, `/files`. Give them one path and let the gateway
remove it.

**Dashboard**

- Path `/myapp`, App type **Vite dev server**, Frontend port `5173`
- **Separate API server:** port `8000`, API path `/backend`, `/prefix/api/x -> /x`

```bash
VITE_API_BASE_URL=/myapp/backend npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort
```

`/myapp/backend/login` reaches the backend as `/login`. The backend does not change.

If the app uses a hash router (`/#/page`) it needs no router change either.

## Recipe 3: Next.js with a lot of `fetch('/api/...')` calls

`basePath` does not add the path to your own `fetch()` calls, so a path would mean editing every one.
The no-change way is a port of its own.

- Exposure **Its own gateway port** `8282`, App type **Next.js**, Frontend port `3000`
- Make the app listen on `127.0.0.1` only

Open `http://<server>:8282/`. Nothing in the app changes.

## Recipe 4: A built site in Docker

```bash
docker build --build-arg VITE_BASE_PATH=/myapp/ -t myapp .
docker run -d --name myapp --restart unless-stopped -p 127.0.0.1:8300:80 myapp
```

**Dashboard:** path `/myapp`, App type **Built files from a static server**, Frontend port `8300`.

More in [Docker and Compose](docker.md).

## Recipe 5: A Compose app, front to back

A stack in `/opt/myapp`:

- `frontend`: a Vite build served by nginx on port 80, published as `8080`. Its nginx forwards `/api`,
  `/ws` and `/media`.
- `backend`: Python on port 5000, not published.

Two files change.

**`frontend/Dockerfile`**

```dockerfile
ARG VITE_BASE_PATH=/
RUN npm run build -- --base ${VITE_BASE_PATH}
```

**`docker-compose.yml`**

```yaml
services:
  frontend:
    build:
      context: ./frontend
      args:
        VITE_BASE_PATH: /myapp/
        VITE_API_BASE_URL: /myapp/api
        VITE_WS_URL: /myapp/ws
    ports:
      - "127.0.0.1:8080:80"
  backend:
    environment:
      MEDIA_URL: /myapp/media      # an address for the browser: path added
      DB_URL: http://db:5432       # between containers: unchanged
```

Rebuild with `docker compose up -d --build`.

**Dashboard:** path `/myapp`, App type **Built files from a static server**, Frontend port `8080`, no
separate API server (the container's nginx already forwards `/api`, `/ws` and `/media`), Timeout `3600`
if you use WebSockets.

## Other app types

| App | Settings |
|---|---|
| App that serves its own built frontend (FastAPI `StaticFiles`, Express) | **Built files served by the app's own backend** (mode `strip`) |
| Prebuilt app you cannot rebuild | **Prebuilt app**, Exposure *its own gateway port* |
| One app that must own `/` of the gateway port | path `/`. Other paths still win, and the landing page is replaced |

## Import several projects at once

`examples/projects-example.json` holds three sample projects. See
[Project fields, JSON and API](json-api.md).
