# Put any project on the gateway: a step-by-step guide

This page is for you if you have a web project and want it to open at an address like
`http://server:8280/myapp/`. You do not need to know nginx.

---

## 1. The idea

The gateway is **one door** (port `8280`). Each project gets its own **path** behind that door:

```
http://server:8280/shop/       ->  your "shop" project
http://server:8280/blog/       ->  your "blog" project
http://server:8280/notes/      ->  your "notes" project
```

Your project keeps running on its own port, for example `127.0.0.1:5173`. The gateway forwards
the browser to it.

There is only one thing to remember:

> A web page normally thinks it lives at `/`. Behind the gateway it lives at `/myapp/`.
> So the **frontend** must be told: "your home is `/myapp/`".

That is called the **base path**. Everything else is automatic.

---

## 2. What you change, and what you do not

| Part | Do you change it? |
|---|---|
| **Backend** (FastAPI, Flask, Express, Django, Spring, ...) | **No. Nothing.** The gateway removes `/myapp` before it reaches your backend, so your routes stay exactly as they are. |
| **nginx** | **No.** The dashboard writes and tests it for you. |
| **Frontend** (Vite, Next.js, React, Vue, ...) | **Yes, but only the base path.** It is usually one flag or one setting. See step 4. |
| **Docker** | Pass the base path when you *build* the image, then rebuild. See section 7. |

Example: your backend has the route `/api/users`. In the browser people call
`/myapp/api/users`. The gateway forwards it to your backend as `/api/users`. The backend never
knows about `/myapp`.

> **Small exception.** If your backend creates web pages or redirects itself (for example
> `redirect("/login")`, or server-rendered HTML with `<a href="/login">`), those links also need
> the prefix. Pure APIs that only return JSON are never affected.

---

## 3. Choose your project type

Find the row that matches your project and jump to its section.

| My project is... | Go to |
|---|---|
| A **Vite** app (React, Vue, Svelte, ...) running with `npm run dev` | [4A](#4a-vite-dev-server) |
| A **Vite** app that I build, then serve the built files | [4B](#4b-vite-build-and-serve-the-files) |
| A **Next.js** app | [4C](#4c-nextjs) |
| Another frontend (Angular, Create React App, Vue CLI, SvelteKit, Nuxt) | [4D](#4d-other-frontends) |
| Only a **backend** or API (no separate frontend) | [5](#5-backend-only-projects) |
| Running in **Docker** or **Docker Compose** | [7](#7-docker-and-docker-compose) |
| **I cannot change or rebuild** the app | [8](#8-i-cannot-change-the-app) |

---

## 4. Frontend: tell the app its base path

In every example below, replace `/myapp/` with your own path.

### 4A. Vite dev server

Start it with `--base`:

```bash
npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort
```

What each part does:

| Flag | Why |
|---|---|
| `--base /myapp/` | The base path. Keep the slash at both ends. |
| `--host 127.0.0.1` | Only the gateway on this server can reach the app. |
| `--port 5173` | The port you will type into the dashboard. |
| `--strictPort` | Fails instead of silently picking another port. |

You do **not** need to edit `vite.config.js`. Hot reload keeps working.

Dashboard settings: App type **Vite dev server**, Frontend port `5173`.

### 4B. Vite: build and serve the files

Build with `--base`:

```bash
npx vite build --base /myapp/
```

Then serve the `dist/` folder with anything (nginx in Docker, `serve`, your own backend).

- If a **static server** serves `dist/`, choose App type **Built files from a static server**.
- If **your backend** serves `dist/`, choose **Built files served by the app's own backend**.
- If you use `vite preview`, run `npx vite preview --base /myapp/ --host 127.0.0.1 --port 4173`
  and choose **Vite preview**.

The server keeps serving the files at its own `/`. The gateway removes `/myapp` for you.

### 4C. Next.js

Next.js has a setting called `basePath`. Put it in `next.config.js` (or `.ts`):

```js
const nextConfig = {
  basePath: process.env.NEXT_BASE_PATH || '',
  env: { NEXT_PUBLIC_BASE_PATH: process.env.NEXT_BASE_PATH || '' },
}
module.exports = nextConfig
```

Note: for Next.js, write the path **without** a trailing slash (`/myapp`).

Then **build again** (the value is baked in at build time) and start:

```bash
NEXT_BASE_PATH=/myapp npm run build
NEXT_BASE_PATH=/myapp npx next start -H 127.0.0.1 -p 3000
```

Next.js adds the prefix to links, pages, and its own files. It does **not** add it to your own
`fetch('/api/...')` calls or to images written as `/logo.png`. Add it yourself:

```js
fetch(`${process.env.NEXT_PUBLIC_BASE_PATH}/api/items`)
```

Dashboard settings: App type **Next.js**.

> **Too many `fetch('/api/...')` calls to edit?** Use the no-change option in
> [section 8](#8-i-cannot-change-the-app): give the app its own gateway port.

### 4D. Other frontends

All of them have one setting for the base path. Build again after you set it.

| Framework | Setting |
|---|---|
| Angular | `ng build --base-href /myapp/` |
| Create React App | `PUBLIC_URL=/myapp npm run build` |
| Vue CLI | `publicPath: '/myapp/'` in `vue.config.js` |
| SvelteKit | `kit: { paths: { base: '/myapp' } }` in `svelte.config.js` |
| Nuxt | `app: { baseURL: '/myapp/' }` in `nuxt.config` |

When the app is built and served as files, use App type **Built files from a static server**.

### Two small code fixes (only if your app needs them)

Skip these if you do not use them. Both are safe when running without the gateway too, because
`BASE_URL` is just `/` there.

**1. If you use a router with real URLs** (`/settings`, `/profile/5`), give it the base:

```jsx
// React Router
<BrowserRouter basename={import.meta.env.BASE_URL}>

// Vue Router
createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes })
```

A hash router (`/#/settings`) needs no change.

**2. If your code writes root URLs** such as `fetch('/api/items')` or `<img src="/logo.png">`:

```jsx
const API = `${import.meta.env.BASE_URL}api`      // instead of '/api'
fetch(`${API}/items`)
<img src={`${import.meta.env.BASE_URL}logo.png`} />
```

Tip: if your app already reads its API address from an environment variable (for example
`VITE_API_BASE`), just set that variable to `/myapp/api`. No code change at all.

---

## 5. Backend-only projects

Nothing to change in the backend. In the dashboard:

1. Add the project with the path you want (for example `/myapi`).
2. Put your backend's port in the **Frontend port** box. (The dashboard calls the main app the
   "frontend", but any web server works there.)
3. App type **Something else**, Path mode **strip**.
4. Make the backend listen on `127.0.0.1` (not `0.0.0.0`), so only the gateway can reach it.

The gateway removes the prefix, so `/myapi/users` reaches your code as `/users`.

**Frontend and backend on different ports?** Tick **Separate API server** and fill in:

| Your backend has... | API path | "What the API server sees" |
|---|---|---|
| Routes that all start with `/api` | `/api` | `/prefix/api/x -> /api/x` |
| Many routes (`/login`, `/users`, `/files`, ...) | `/backend` (any name) | `/prefix/api/x -> /x` |

In the second case, point your frontend at `/myapp/backend` (for example with an env variable).

Nice to know:
- **WebSockets and streaming** (live chat, token streams) work with no extra setup.
- **FastAPI's `/docs` page** needs `FastAPI(root_path="/myapp")` to load correctly. Your normal API
  routes work without it.
- **Long jobs?** Raise **Timeout** in the project's Advanced settings. **Big uploads?** Raise
  **Max upload**.

---

## 6. Add the project in the dashboard

Open the dashboard, then **Projects -> Add project**:

1. **Name.** The ID and URL path fill in by themselves.
2. **App type.** Pick the type from section 4. This sets the right options for you.
3. **Frontend port.** The port your app listens on.
4. *(Optional)* **Separate API server**, if the backend has its own port (see section 5).
5. Press **Add and apply**.

The dashboard checks everything before it goes live. If something is wrong, nothing changes and the
message shows next to the field.

Then press **Test**. It tells you whether the app answers, and whether the page loads its files
from the right path. The **Guide** button shows the exact commands for your project.

Finally open `http://<server>:8280/myapp/`.

---

## 7. Docker and Docker Compose

Docker has one rule that surprises everyone:

> The base path is written into the frontend **while it is being built**. Changing `.env` and
> restarting does **nothing**. You must pass the path as a *build argument* and **rebuild the image**.

There are three small changes.

### Vite in Docker

**1. Dockerfile**: take the path as an argument and use it in the build:

```dockerfile
# before
RUN npm run build

# after
ARG VITE_BASE_PATH=/
RUN npm run build -- --base ${VITE_BASE_PATH}
```

The default `/` means a plain `docker build` still works without the gateway.

**2. `docker-compose.yml`**: pass the value in `build.args`:

```yaml
services:
  frontend:
    build:
      context: ./frontend
      args:
        VITE_BASE_PATH: /myapp/
        VITE_API_BASE_URL: /myapp/api      # only if your app reads an API address like this
```

**3. Publish the port on `127.0.0.1` only:**

```yaml
    ports:
      - "127.0.0.1:8080:80"      # not "8080:80"
```

(Docker ports bypass the firewall. With `127.0.0.1` in front, only the gateway can use them.)

Rebuild and start:

```bash
docker compose up -d --build
```

Check that the build worked:

```bash
curl -s http://127.0.0.1:8080/ | grep -o '/myapp/assets/[^"]*'
```

You should see paths that start with `/myapp/`.

Dashboard settings: path `/myapp`, App type **Built files from a static server**, frontend port
`8080`.

Do **not** edit the nginx file inside the container. The gateway removes `/myapp` before the
request arrives.

### Next.js in Docker

**1. `next.config.js`**: same as section 4C.

**2. Dockerfile**, before `npm run build`:

```dockerfile
ARG NEXT_BASE_PATH=
ENV NEXT_BASE_PATH=${NEXT_BASE_PATH}
RUN npm run build
```

**3. `docker-compose.yml`:**

```yaml
    build:
      context: .
      args:
        NEXT_BASE_PATH: /myapp
    ports:
      - "127.0.0.1:3000:3000"
```

Then `docker compose up -d --build`. Dashboard: App type **Next.js**, frontend port `3000`.

### The backend in Docker

Again: **no change**. Do not publish its port at all if only other containers use it. If the
*browser* calls it directly, publish it on `127.0.0.1` and use **Separate API server**.

One thing to look for: any backend setting that is a **URL for the browser** and starts with `/`
(for example `MEDIA_URL: /video`). Add the prefix there (`/myapp/video`). Addresses between
containers (`http://db:5432`) are never changed.

Full details with a complete worked example: [DOCKER_SUBPATH.md](DOCKER_SUBPATH.md).

---

## 8. I cannot change the app

Maybe it is prebuilt, or has too many places to edit. There is a no-change option:

**Give the app its own gateway port.** The app stays at `/`, on a port of its own, still behind
nginx and still private to your network.

Dashboard settings:
- App type **Prebuilt app**
- Exposure **Its own gateway port**, for example `8282`
- Frontend port: the port the app listens on
- Open `http://<server>:8282/`

Still make the app listen on `127.0.0.1` so it cannot be reached around the gateway.

---

## 9. Before you say "done": checklist

- [ ] The app listens on `127.0.0.1`, not `0.0.0.0`.
- [ ] The frontend knows its base path (flag, setting, or build argument).
- [ ] You rebuilt, if the app is built (Next.js, Docker, `vite build`).
- [ ] The project is added in the dashboard and **Test** is green.
- [ ] You opened `http://<server>:8280/myapp/` and clicked through the pages.
- [ ] You refreshed on an inner page (for example `/myapp/settings`) and it still loads.

To list problems before you start, run this on the server. It only reads your files:

```bash
nginx-gateway-ctl vite-check ~/path/to/frontend --prefix /myapp/
```

---

## 10. Something is wrong

| What you see | Why | Fix |
|---|---|---|
| Blank white page, console shows 404 for `/assets/...` | The frontend still thinks it lives at `/` | Set the base path (section 4) and rebuild |
| The home page works, but `/myapp/settings` says "not found" | The router does not know the base | Add `basename` (section 4, fix 1) |
| Page loads, but data calls fail (404) | The code calls `/api/...` and skips the prefix | Section 4, fix 2, or set the API env variable |
| "Blocked request. This host is not allowed" (Vite) | Vite rejects unknown host names | In the project's Advanced settings turn **off** "Pass the original Host header" |
| Changes to `.env` do nothing in Docker | The path is baked in at build time | Rebuild the image with the build arg |
| Large upload or long job fails | Gateway limits | Raise **Max upload** or **Timeout** in Advanced |
| Anything else | | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |

---

## Quick reference

| Project | Base path setting | App type in dashboard |
|---|---|---|
| Vite, `npm run dev` | `--base /myapp/` | Vite dev server |
| Vite, `vite preview` | `--base /myapp/` on build and preview | Vite preview |
| Vite, built files | `vite build --base /myapp/` | Built files from a static server |
| Next.js | `basePath: '/myapp'`, rebuild | Next.js |
| Docker | build argument, rebuild image | same as the app inside |
| Backend (any language) | **nothing** | add it as the API server |
| Cannot change the app | **nothing**, use its own port | Prebuilt app |
