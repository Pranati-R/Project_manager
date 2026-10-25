# Cheat sheet

Everything on one page. Replace `/myapp/` with your path.

## Frontends

| Framework | Base path setting | Rebuild? | App type in the dashboard |
|---|---|---|---|
| Vite dev server | `npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort` | no | Vite dev server |
| Vite preview | `vite build --base /myapp/` then `vite preview --base /myapp/` | yes | Vite preview |
| Vite, built files | `vite build --base /myapp/` | yes | Built files from a static server |
| Next.js | `basePath: '/myapp'` in `next.config` | yes | Next.js |
| Angular | `ng build --base-href /myapp/` | yes | Built files from a static server |
| Create React App | `PUBLIC_URL=/myapp npm run build` | yes | Built files from a static server |
| Vue CLI | `publicPath: '/myapp/'` | yes | Built files from a static server |
| SvelteKit | `kit.paths.base: '/myapp'` | yes | Built files from a static server |
| Nuxt | `app.baseURL: '/myapp/'` | yes | Built files from a static server |
| Plain HTML | relative links (`css/a.css`) | no | Built files from a static server |
| Cannot change it | nothing | no | Prebuilt app (own port) |

## Backends

| Backend | Change in code | Start it with |
|---|---|---|
| FastAPI | none (`root_path` only for `/docs`) | `uvicorn main:app --host 127.0.0.1 --port 8000` |
| Flask | none | `flask run --host 127.0.0.1 --port 8000` |
| Django | none | `python manage.py runserver 127.0.0.1:8000` |
| Express | none | `app.listen(8000, '127.0.0.1')` |
| Any other | none | listen on `127.0.0.1` |

**API path in the dashboard:**

| Backend routes | API path | What the API server sees |
|---|---|---|
| All start with `/api` | `/api` | `/prefix/api/x -> /api/x` |
| Many different starts | `/backend` | `/prefix/api/x -> /x` |

## Docker

| Framework | Dockerfile | Compose |
|---|---|---|
| Vite | `ARG VITE_BASE_PATH=/` then `npm run build -- --base ${VITE_BASE_PATH}` | `build.args: VITE_BASE_PATH: /myapp/` |
| Next.js | `ARG NEXT_BASE_PATH=` and `ENV NEXT_BASE_PATH=${NEXT_BASE_PATH}` | `build.args: NEXT_BASE_PATH: /myapp` |

Always: `ports: "127.0.0.1:PORT:..."` and `docker compose up -d --build`.

## Code fixes (only if needed)

```jsx
// router with real URLs
<BrowserRouter basename={import.meta.env.BASE_URL}>

// API calls
const API = import.meta.env.VITE_API_BASE || `${import.meta.env.BASE_URL}api`

// public files
<img src={`${import.meta.env.BASE_URL}logo.png`} />

// Next.js
fetch(`${process.env.NEXT_PUBLIC_BASE_PATH}/api/items`)
```

## Path modes

| Mode | `/myapp/page` reaches the app as | For |
|---|---|---|
| `subpath` | `/myapp/page` | Vite dev, Vite preview, Next.js |
| `strip` | `/page` | built files, your own backend |
| `rewrite` | `/page` + links edited | simple multi-page sites (best effort) |

## When something is wrong

| Symptom | First thing to check |
|---|---|
| Blank page, 404 on `/assets/...` | Base path missing or not rebuilt |
| Inner pages say "not found" | Router `basename` |
| Data calls fail | API address or `/api` in code |
| 502 | App not running or wrong port |
| 403 from Vite | Turn off "Pass the original Host header" |
| 403 from nginx | Your network is not allowed |

More: [Troubleshooting](troubleshooting.md).
