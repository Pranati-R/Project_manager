# Docker and Compose

Use this page if your project runs in **Docker** (`docker run`) or **Docker Compose**
(`docker compose up`).

## The one rule

> **Warning:** The base path is saved **while the image is built**. Changing a `.env` file and
> restarting does nothing. You must pass the path as a **build argument** and **rebuild the image**.

## What changes

| Part | Change? |
|---|---|
| Frontend Dockerfile | **Yes:** accept the path and use it when building |
| `docker-compose.yml` | **Yes:** pass the path as a build argument, publish the port on `127.0.0.1` |
| Backend container | **No code change** |
| nginx file inside the container | **No** |
| Source code | Only if the app has a router or `/api` calls (see [Vite](vite.md)) |

## Vite in Docker

### Step 1: Dockerfile

Take the path as an argument and use it in the build:

```dockerfile
# before
RUN npm run build

# after
ARG VITE_BASE_PATH=/
RUN npm run build -- --base ${VITE_BASE_PATH}
```

The default `/` means a plain `docker build` still works without the gateway.

### Step 2: docker-compose.yml

Pass the path (and any API address your app reads) as build arguments:

```yaml
services:
  frontend:
    build:
      context: ./frontend
      args:
        VITE_BASE_PATH: /myapp/
        VITE_API_BASE_URL: /myapp/api      # only if your app reads an address like this
```

Each value is the old one with `/myapp` in front.

### Step 3: Publish on 127.0.0.1 only

```yaml
    ports:
      - "127.0.0.1:8080:80"      # not "8080:80"
```

> **Why?** Docker ports skip the firewall. With `127.0.0.1` in front, only the gateway can use the port.

### Step 4: Rebuild and start

```bash
docker compose up -d --build
```

### Step 5: Check the build

```bash
curl -s http://127.0.0.1:8080/ | grep -o '/myapp/assets/[^"]*'
```

You should see paths that start with `/myapp/`. If you see `/assets/`, the path did not reach the build.

### Step 6: Add it in the dashboard

| Setting | Value |
|---|---|
| URL path | `/myapp` |
| App type | **Built files from a static server** |
| Frontend port | `8080` |

Do **not** edit the nginx file inside the container. The gateway removes `/myapp` first.

## Next.js in Docker

Same idea, different names.

**`next.config.js`:** as on the [Next.js](nextjs.md) page.

**Dockerfile**, in the build stage before `npm run build`:

```dockerfile
ARG NEXT_BASE_PATH=
ENV NEXT_BASE_PATH=${NEXT_BASE_PATH}
RUN npm run build
```

**docker-compose.yml:**

```yaml
    build:
      context: .
      args:
        NEXT_BASE_PATH: /myapp
    ports:
      - "127.0.0.1:3000:3000"
```

Then `docker compose up -d --build`. In the dashboard use App type **Next.js** and port `3000`.

## Backend containers

Again: **no code change**.

- If only other containers use the backend, do not publish its port at all.
- If the browser calls it directly, publish it on `127.0.0.1` and add it as a **Separate API server**.
  See [Backends and APIs](backends.md).
- Look for backend settings that are **addresses for the browser** and start with `/`, for example
  `MEDIA_URL: /media`. Put the path in front (`/myapp/media`). Addresses between containers, such as
  `http://db:5432`, stay as they are.

## Plain `docker run`

```bash
docker build --build-arg VITE_BASE_PATH=/myapp/ -t myapp .
docker run -d --name myapp --restart unless-stopped -p 127.0.0.1:8080:80 myapp
```

A ready Dockerfile is in `examples/Dockerfile.vite-subpath.example`.

## Find a project's folder

If you do not remember where the Compose project lives:

```bash
docker ps --filter publish=8080
docker inspect <container-name> --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}'
```

Use the **container** name from the first command, not the image name.

## See what your app needs (read-only)

```bash
cat docker-compose.yml frontend/Dockerfile
grep -rn "VITE_\|/api\|BrowserRouter" frontend/src | head -40
nginx-gateway-ctl vite-check frontend --prefix /myapp/
```

## Undo

Before editing, copy the files:

```bash
cp docker-compose.yml docker-compose.yml.bak
cp frontend/Dockerfile frontend/Dockerfile.bak
```

To undo, copy them back and run `docker compose up -d --build`.

## Checklist

- [ ] The Dockerfile accepts the base path as an `ARG` and uses it in the build.
- [ ] `docker-compose.yml` passes the path in `build.args`.
- [ ] Every browser-facing address has the path in front.
- [ ] The port is published as `127.0.0.1:PORT:...`.
- [ ] You ran `docker compose up -d --build`.
- [ ] `curl` shows `/myapp/` in the HTML.
- [ ] The project is added and **Test** is green.

## Common mistakes

| What you see | Cause | Fix |
|---|---|---|
| Changed `.env`, nothing happened | The path is saved at build time | Pass a build argument and rebuild |
| Blank page, 404 on `/assets/...` | The image was built without the path | Rebuild with `--build-arg` or `build.args` |
| App still opens at `server:8080` from another computer | Port published on all addresses | Use `127.0.0.1:8080:80` |

## Next steps

- [Testing your project](testing.md)
- [Troubleshooting](troubleshooting.md)
