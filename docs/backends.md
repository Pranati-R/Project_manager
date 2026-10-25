# Backends and APIs

Use this page for a backend written in any language: FastAPI, Flask, Django, Express, Spring, Go,
PHP, and so on.

## The short answer

> **Note:** **You do not change your backend.** Not one line. The gateway removes the project path
> before the request reaches it.

```
Browser asks:      /myapp/api/users
Gateway forwards:  /api/users          <- what your backend already handles
```

## What changes

| Part | Change? |
|---|---|
| Backend code | **No** |
| Backend routes | **No** |
| Backend port | **No** (but make it listen on `127.0.0.1`) |
| The **frontend's** API address | **Yes:** it must call `/myapp/api/...` (see below) |

## Before you start

- Your backend runs and listens on a port (here `8000`).
- You know the first part of its routes, for example `/api`.

## Step 1: Listen on 127.0.0.1

Make the backend listen on `127.0.0.1` so only the gateway can reach it.

```bash
# FastAPI / Uvicorn
uvicorn main:app --host 127.0.0.1 --port 8000

# Flask
flask run --host 127.0.0.1 --port 8000

# Django
python manage.py runserver 127.0.0.1:8000

# Express (Node): in code
app.listen(8000, '127.0.0.1')
```

## Step 2: Add it to the project

In the dashboard, open your project (or add a new one). Tick **Separate API server** and fill in:

| Field | Value |
|---|---|
| API host | `127.0.0.1` |
| API port | `8000` |
| API path | see the table below |
| What the API server sees | see the table below |

### Which API path?

| Your backend routes look like... | API path | What the API server sees |
|---|---|---|
| All start with `/api` (`/api/users`, `/api/login`) | `/api` | `/prefix/api/x -> /api/x` |
| Many different starts (`/login`, `/users`, `/files`) | `/backend` (any name) | `/prefix/api/x -> /x` |

**Example 1: routes start with `/api`.** Browser asks `/myapp/api/users`. Your backend gets
`/api/users`.

**Example 2: many top-level routes.** With API path `/backend`, the browser asks
`/myapp/backend/login` and your backend gets `/login`.

Both examples leave your backend untouched.

## Step 3: Point the frontend at the API

The frontend now calls `/myapp/api/...` (example 1) or `/myapp/backend/...` (example 2).

- Frontend reads its API address from an environment variable: set it. For example
  `VITE_API_BASE=/myapp/api`.
- Otherwise build the address from the base path. See [Vite](vite.md), "Fix 2".

## Backend only (no frontend)

You can serve a backend alone. The dashboard calls the main app the "frontend", but any web server
works there.

| Setting | Value |
|---|---|
| URL path | `/myapi` |
| App type | **Something else** |
| Frontend port | your backend's port |
| Path mode | `strip` |

Then `http://<server>:8280/myapi/users` reaches your code as `/users`.

## WebSockets and streaming

Both work with **no extra setup**: live chat, notifications, and streamed answers (SSE) pass through.
Responses are not held back, so streams arrive as they are produced.

For long jobs raise **Timeout** in the project's Advanced settings (default: one hour). For large
uploads raise **Max upload**.

## FastAPI's `/docs` page

FastAPI shows interactive docs at `/docs`. Behind the gateway, that page needs to know the path to find
its own description file:

```python
app = FastAPI(root_path="/myapp")
```

Your normal API routes work without this. It only fixes the `/docs` page.

## The one exception

If your backend **writes web pages or redirects itself**, those addresses need the path too.

```python
return redirect("/login")          # sends the browser to the gateway root: wrong
return redirect("/myapp/login")    # right
```

Look for this in server-rendered HTML (Flask templates, Django templates, PHP pages) and in
`redirect(...)` calls. Backends that only return JSON are not affected.

## Check it works

1. Press **Test**. The API line should be green. Set **Health path** (for example `/health`) in
   Advanced for a stronger check.
2. Open `http://<server>:8280/myapp/api/health` in your browser. You should see your backend's answer.

## Common mistakes

| What you see | Cause | Fix |
|---|---|---|
| 404 from the API | Wrong "What the API server sees" | Pick the other option in the table above |
| API works on the server but not in the browser | Frontend calls `http://127.0.0.1:8000` | Use a path (`/myapp/api`) |
| 502 Bad Gateway | The backend is not running or listens elsewhere | Start it on `127.0.0.1:<port>` |
| Redirects go to the wrong place | The backend writes its own redirects | See "The one exception" |

## Next steps

- [Docker and Compose](docker.md) for backends in containers
- [Testing your project](testing.md)
