# Next.js

Use this page if your project uses **Next.js** (`next` in `package.json`).

## What this is for

Next.js has a built-in setting, `basePath`, that tells it where it lives. It then adds the path to
links, pages and its own files for you.

The path is saved **while building**, so after changing it you must build again.

## What changes

| Part | Change? |
|---|---|
| `next.config.js` | **Yes:** add `basePath` |
| Build and start commands | **Yes:** give them the path and rebuild |
| Your own `fetch('/api/...')` calls | **Yes:** add the path (Next.js does not) |
| Images written as `/logo.png` | **Yes:** add the path |
| Your backend | **No** |

## Before you start

- Your project path, here `/myapp`. For Next.js write it **without** a slash at the end.
- A free port, here `3000`.

## Step 1: Set `basePath`

Open `next.config.js` (or `.ts`). Read the path from an environment variable. Then the app still works
at `/` when you run it without the gateway.

```js
const nextConfig = {
  basePath: process.env.NEXT_BASE_PATH || '',
  env: { NEXT_PUBLIC_BASE_PATH: process.env.NEXT_BASE_PATH || '' },
}
module.exports = nextConfig
```

## Step 2: Build and start

```bash
cd ~/myapp
NEXT_BASE_PATH=/myapp npm run build
NEXT_BASE_PATH=/myapp npx next start -H 127.0.0.1 -p 3000
```

| Part | Meaning |
|---|---|
| `NEXT_BASE_PATH=/myapp` | Gives the path to the config file |
| `npm run build` | Builds the app, saving the path into it |
| `-H 127.0.0.1` | Only the gateway can reach the app |
| `-p 3000` | The port |

You should see `Ready` and an address on `127.0.0.1:3000`.

## Step 3: Add the path to your own requests

Next.js adds the path to **links, pages and its own files**. It does **not** add it to requests you
write yourself.

```js
// before
fetch('/api/items')
<Image src="/logo.png" alt="Logo" width={80} height={80} />

// after
fetch(`${process.env.NEXT_PUBLIC_BASE_PATH}/api/items`)
<Image src={`${process.env.NEXT_PUBLIC_BASE_PATH}/logo.png`} alt="Logo" width={80} height={80} />
```

To list every place that needs it, run on the server (read-only):

```bash
nginx-gateway-ctl vite-check ~/myapp --prefix /myapp/
```

> **Tip:** Many `fetch` calls, and no time to edit them all? Skip steps 1 to 3 and give the app its own
> gateway port instead. See [Apps you cannot change](cannot-change.md). Nothing in the app changes.

## Step 4: Add it in the dashboard

| Setting | Value |
|---|---|
| URL path | `/myapp` |
| App type | **Next.js** |
| Frontend port | `3000` |

The App type sets the path mode to `subpath`, because Next.js expects `/myapp` in every address.

## A backend with Next.js

- **Next.js proxies to it with `rewrites()`:** rewrites follow `basePath`, so you do nothing more.
- **The browser calls the backend directly:** add it as a **Separate API server** (API path `/api`).
  See [Backends and APIs](backends.md).

## Check it works

1. Press **Test** on the project.
2. Open `http://<server>:8280/myapp/`.
3. Open an inner page and refresh it.

## Common mistakes

| What you see | Cause | Fix |
|---|---|---|
| Home page works, images and data are missing | Your own requests have no path | Step 3 |
| Everything is a 404 | You did not rebuild after setting the path | Run the build again |
| 404 on `/` inside a Docker health check | With `basePath` the app has no page at `/` | Point the health check at `/myapp` |

## Next steps

- Running in Docker: [Docker and Compose](docker.md)
- Backends: [Backends and APIs](backends.md)
