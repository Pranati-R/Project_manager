# Getting started

This page explains how the gateway works and how to add a new project. It is the only page you need to
begin.

## What the gateway is

The gateway is **one front door for many projects**. It is one nginx program that listens on **one
port**, usually `8280`. Each project gets its own **path** after the port:

```
http://server:8280/shop/
http://server:8280/blog/
http://server:8280/notes/
```

Your projects keep running as they always did, each on its own port on `127.0.0.1` ("this same
computer"). The gateway reads the path of every request and forwards it to the right project.

```
 Browser  ->  http://server:8280/shop/products
                   |
            +------v-------+
            |   GATEWAY    |   /shop/  -> shop app   (127.0.0.1:5173)
            |  (port 8280) |   /blog/  -> blog app   (127.0.0.1:3000)
            +--------------+
```

Because the apps listen only on `127.0.0.1`, nobody can skip the gateway and open them directly. You
never edit nginx by hand: the dashboard writes the configuration, tests it, and only then applies it.
A bad change never goes live.

## What your project needs to know

| Part | Change needed? | Why |
|---|---|---|
| **Frontend** (Vite, Next.js, React, Vue, ...) | **Yes: tell it its path** | It writes links like `/assets/app.js`. Under the gateway they must be `/shop/assets/app.js`, or the page is blank. This is the **base path**. |
| **Backend** (FastAPI, Flask, Express, ...) | **No** | The gateway removes `/shop` before the request arrives. Your backend sees `/api/users`, as it always did. |
| **Docker** | **Rebuild with the path** | The path is saved while building. |

If an app cannot be changed at all, give it a **port of its own** instead of a path. See
[Apps you cannot change](cannot-change.md).

## Add a new project

You need a project that runs on the server, a login for this dashboard, and a **path** you choose (here
`/myapp`).

1. **Pick a free port** for the app, for example `5173`.
2. **Start the app on `127.0.0.1` with its path.** For a Vite app:

   ```bash
   cd ~/myapp
   npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort
   ```

   Other frameworks have an equivalent setting. See
   [Choose your project type](choose-type.md).
3. **Add it in the dashboard.** Open the **Projects** tab, press **Add project**, and fill in:
   - **Name:** `My App`. The ID and path fill in by themselves. Make the path `/myapp`.
   - **App type:** `Vite dev server`. This also sets how the path is passed on.
   - **Frontend port:** `5173`.
   - **Separate API server:** tick it only if you have a backend, and give its port.

   Press **Add and apply**. You should see "Saved and applied: nginx reloaded".
4. **Test it.** Press **Test** on the project row. Green ticks mean the app answers, the page loads
   through the gateway, and its files load from `/myapp/`.
   [Testing your project](testing.md) explains every message.
5. **Open it** with the **Open** button, or go to `http://<server>:8280/myapp/`.

## Where to go next

- Every form field: [Add a project: every field](project-fields.md)
- Add a backend: [Backends and APIs](backends.md)
- Docker project: [Docker and Compose](docker.md)
- Something went wrong: [Troubleshooting](troubleshooting.md)
