# Vite (React, Vue, Svelte, ...)

Use this page if your frontend is built with **Vite**. You can tell by a `vite.config.js` file or
`"vite"` in `package.json`.

## What this is for

Vite writes links that start with `/`. Behind the gateway the app lives at `/myapp/`, so those links
miss. The fix is one flag: `--base /myapp/`.

## What changes

| Part | Change? |
|---|---|
| Your Vite command | **Yes:** add `--base /myapp/` |
| `vite.config.js` | **No** (optional, see below) |
| Router code | Only if you use a router with real URLs |
| Code that writes `/api/...` or `/logo.png` | Only if you have such code |
| Your backend | **No** |

## Before you start

- You know your project path. Here it is `/myapp`.
- You picked a free port. Here it is `5173`.

## Option A: the dev server (`npm run dev`)

Good for learning and small internal projects. Hot reload keeps working.

```bash
cd ~/myapp
npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort
```

| Flag | Why |
|---|---|
| `--base /myapp/` | The base path. Keep the slash at both ends. |
| `--host 127.0.0.1` | Only the gateway can reach the app. |
| `--port 5173` | The port you put in the dashboard. |
| `--strictPort` | Fail instead of silently choosing another port. |

**Dashboard:** App type **Vite dev server**, Frontend port `5173`.

## Option B: build, then serve the files

Good for production. First build with the base path:

```bash
npx vite build --base /myapp/
```

This creates the `dist/` folder. Serve it with any static server (nginx, `serve -s dist`, Caddy, a
Docker image, or your own backend).

**Dashboard:**

- A static server serves `dist/`: App type **Built files from a static server**
- Your own backend serves `dist/`: App type **Built files served by the app's own backend**

The server keeps serving the files as usual. The gateway removes `/myapp` first.

## Option C: `vite preview`

```bash
npx vite build --base /myapp/
npx vite preview --base /myapp/ --host 127.0.0.1 --port 4173
```

**Dashboard:** App type **Vite preview**, Frontend port `4173`.

## Small code fixes (only if needed)

These are safe without the gateway too. `import.meta.env.BASE_URL` is `/` when you run the app on its
own, and `/myapp/` behind the gateway.

### Fix 1: a router with real URLs

If your app has pages like `/settings` or `/profile/5`:

```jsx
// React Router
<BrowserRouter basename={import.meta.env.BASE_URL}>

// React Router, data router
createBrowserRouter(routes, { basename: import.meta.env.BASE_URL })

// Vue Router
createRouter({ history: createWebHistory(import.meta.env.BASE_URL), routes })
```

A **hash router** (addresses like `/#/settings`) needs no change.

> **Why?** Without a basename the router sees `/myapp/settings`, finds no page with that name, and
> shows "not found".

### Fix 2: API calls written as `/api/...`

If your code calls `fetch('/api/items')`, the request goes to the gateway root, not to your project.

If the app reads its API address from an **environment variable** (look for `VITE_API_BASE` or similar),
set it when you start the app. **No code change.**

```bash
VITE_API_BASE=/myapp/api npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort
```

Otherwise change the code once:

```js
const API = import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`
fetch(`${API}/items`)
```

> **Warning:** Do not use full addresses like `http://127.0.0.1:8000`. They work only on the server
> itself. On another computer the browser would call its **own** port 8000. Use a path instead.

### Fix 3: files from `public/` used in code

```jsx
<img src={`${import.meta.env.BASE_URL}logo.png`} />
```

Links written in `index.html` and CSS are fixed by Vite automatically.

## Optional: set the base in `vite.config`

Instead of typing `--base` each time:

```js
// vite.config.js
export default defineConfig({
  base: process.env.VITE_BASE_PATH ?? '/',
})
```

Then start with `VITE_BASE_PATH=/myapp/ npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`.
Without the variable the app uses `/`, as before.

## Check it works

1. Press **Test** on the project. The "Base path" line should be green.
2. Open `http://<server>:8280/myapp/`.
3. Click to an inner page and press refresh. It should still load.

To scan your project folder for problems **before** you start, run this on the server (it only reads
files, it never changes anything):

```bash
nginx-gateway-ctl vite-check ~/myapp --prefix /myapp/
```

## Common mistakes

| What you see | Cause | Fix |
|---|---|---|
| Blank page, console shows 404 for `/assets/...` | `--base` missing | Start or build with `--base /myapp/` |
| Home page works, inner pages say "not found" | Router has no basename | Fix 1 |
| Page loads, data fails with 404 | Code calls `/api/...` | Fix 2 |
| "Blocked request. This host is not allowed" | Vite checks host names | In the project's Advanced settings turn **off** "Pass the original Host header" |
| Built it, still wrong | You did not rebuild | Run `vite build --base /myapp/` again |

## Next steps

- Add a backend: [Backends and APIs](backends.md)
- Running in Docker: [Docker and Compose](docker.md)
- All fields explained: [Add a project: every field](project-fields.md)
