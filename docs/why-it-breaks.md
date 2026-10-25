# Why apps break under a path

For the curious. You do not need this page to set up a project, but it explains **why** the setup pages
ask for what they ask for.

## What goes wrong

Frontend tools such as Vite assume your app lives at `/`. They write addresses that start with a slash
into the built page:

```html
<script type="module" src="/assets/index-4f2a.js"></script>
```

Open the app at `http://server:8280/myapp/` and the browser asks for `/assets/index-4f2a.js`. That is
**outside** `/myapp/`. The gateway has no project for it, so the page stays blank.

Two more things break the same way:

- **A router** without a `basename` sees the address `/myapp/settings`, finds no page with that name,
  and shows "not found".
- **Code like `fetch('/api/items')`** calls the gateway root instead of your project.

## Why not let nginx fix the links?

We tried. It only works for very simple sites, so it is not the default.

| Idea | Why it fails |
|---|---|
| Rewrite `="/` to `="/myapp/` in every response | It cannot fix addresses your code builds while running (`fetch(base + '/x')`, routers) or minified code. It can also change text that only looks like an address. |
| Guess the project from the `Referer` or a cookie | Vite loads modules from modules, so the `Referer` is not the project path. WebSocket handshakes send none. A cookie is shared by all tabs, so two apps open at once fight. |
| Use relative links (`base: './'`) | Fine for a hash router. Breaks on deep links such as `/myapp/a/b`, and the dev server ignores it. |

So the gateway offers rewriting only as an optional path mode called `rewrite`, for simple multi-page
sites you cannot rebuild.

## The fix that works: tell the app where it lives

Vite accepts `--base` for `dev`, `build` and `preview`. It moves the files, the dev client and hot
reload under the path. No `vite.config` edit is needed. The gateway then forwards requests the way the
app is served.

| How the app is served | Start or build it with | Path mode | Host header |
|---|---|---|---|
| Vite dev server | `npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort` | `subpath` | `127.0.0.1:5173` |
| `vite preview` | `vite build --base /myapp/`, then `vite preview --base /myapp/ ...` | `subpath` | `127.0.0.1:4173` |
| Static files (nginx, `serve -s`, Docker) | `vite build --base /myapp/` | `strip` | original |
| Files served by your own backend | `vite build --base /myapp/` | `strip` | original |
| Next.js | `basePath` in `next.config`, rebuild | `subpath` | original |
| Cannot rebuild | nothing | its **own port** | original |

### What `subpath` and `strip` mean

- `subpath`: the gateway sends `/myapp/page` to the app as `/myapp/page`. The app knows its path.
- `strip`: the gateway sends `/myapp/page` to the app as `/page`. The app thinks it lives at `/`.

### Why Vite gets `Host: 127.0.0.1:5173`

Since Vite 6.0.9 (and 5.4.12), the dev and preview servers refuse requests whose `Host` is not
localhost or an IP address. You would see "Blocked request. This host is not allowed". With **Pass
the original Host header** turned off (the Vite App types do this), the gateway sends an IP address,
and Vite accepts it. No `allowedHosts` change is needed.

### Hot reload

The Vite client opens its WebSocket on the page's own address plus the base
(`ws://server:8280/myapp/`), so it goes through the gateway. Do not set `server.hmr.port`. If the
browser console still shows WebSocket errors, add `server.hmr.clientPort: 8280` to `vite.config`.

## Full addresses do not work

An address such as `http://127.0.0.1:8000` works only on the server itself. A browser on another
device would call **its own** port 8000. Always use a path on the gateway.

## Why the backend is different

A backend does not write links into pages. It only answers requests. So when the gateway removes the
project path before the request arrives, the backend works unchanged. The gateway can do this because
it controls the request. It cannot control what a **page** does after it reaches the browser, and that
is why the frontend must know its base path.

## Next steps

- [Vite](vite.md) or [Next.js](nextjs.md) for the steps
- [Troubleshooting](troubleshooting.md)
