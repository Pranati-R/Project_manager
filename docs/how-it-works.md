# How it works

Read this page once. After it, every other page makes sense.

## One door, many paths

The gateway is one program (nginx) that listens on **one port**, usually `8280`. Each project has its
own **path** after the port.

```
 Your browser
      |
      |  http://server:8280/shop/
      v
+---------------------------+
|  GATEWAY  (port 8280)     |      "/shop/"  -> goes to the shop project
|                           |      "/blog/"  -> goes to the blog project
+------+----------+---------+      "/notes/" -> goes to the notes project
       |          |
       v          v
  shop app     blog app           (each one listens on 127.0.0.1)
  port 5173    port 3000
```

Your apps run as they always did. The gateway sits in front and forwards visitors.

## The journey of one request

You open `http://server:8280/shop/products` in your browser.

1. The browser sends the request to the server, port `8280`.
2. The gateway reads the path. It starts with `/shop`, so this belongs to the **shop** project.
3. The gateway passes the request to the shop app at `127.0.0.1:5173`.
4. The app answers. The gateway sends the answer back to your browser.

> **Why?** `127.0.0.1` means "this same computer". Your app listens there, so **only the gateway can
> reach it**. Nobody can skip the gateway and open the app directly from another computer.

## The problem: apps think they live at `/`

Most web apps are built as if they own the whole address: `http://server/`. Inside, they write links
that start with a slash:

```html
<script src="/assets/app.js"></script>
```

Under the gateway the app lives at `/shop/`, not `/`. The browser then asks for `/assets/app.js`, which
is **outside** `/shop/`. The gateway has no project for it, so the file is not found and you see a
blank page.

```
App lives at:   http://server:8280/shop/
Page asks for:  http://server:8280/assets/app.js        <- wrong place, 404
It should ask:  http://server:8280/shop/assets/app.js   <- right place
```

The fix is simple: **tell the frontend its home is `/shop/`**. This is called the **base path**. Every
framework has a setting for it. For Vite it is `--base /shop/`.

## What changes, and what does not

| Part | Change needed? | Why |
|---|---|---|
| **Frontend** (Vite, Next.js, React, Vue, ...) | **Yes: the base path** | It writes links, so it must know its home |
| **Backend** (FastAPI, Flask, Express, Django, ...) | **No** | The gateway removes the path before the request arrives (see below) |
| **nginx** | **No** | The dashboard writes and tests it for you |
| **Docker** | **Rebuild with the path** | The path is saved while building |

## Why your backend needs no change

A backend answers requests such as `/api/users`. The browser asks the gateway for
`/shop/api/users`. The gateway **removes** `/shop` and passes `/api/users` to your backend.

```
Browser asks:      /shop/api/users
Gateway forwards:  /api/users        <- exactly what your backend already expects
```

Your backend never sees `/shop`. You keep the code exactly as it is.

> **Warning:** The only time a backend needs a change is when **the backend itself writes links or
> redirects**, for example `redirect("/login")` or HTML pages with `<a href="/login">`. Those links must
> include the path. Backends that only return JSON are never affected.

## Two path modes: `subpath` and `strip`

When you add a project, the dashboard needs to know whether to **remove** the path or **keep** it. That
is the **path mode**.

| Mode | The gateway sends `/shop/page` to the app as | Use it when |
|---|---|---|
| `strip` | `/page` (path removed) | The app thinks it lives at `/`. For example built files served by nginx or by your backend |
| `subpath` | `/shop/page` (path kept) | The app knows its path. For example the Vite dev server, or Next.js |

You do not choose this by hand. The **App type** you pick in the dashboard sets it for you.

## Your own port: the shortcut

If an app cannot be changed, the gateway can give it a **port of its own** (for example `8282`). Then
the app lives at `/` of that port, and nothing in it changes.

```
http://server:8282/    -> the app that cannot be changed
```

See [Apps you cannot change](cannot-change.md).

## Summary

1. The gateway is one door with many paths.
2. Apps listen on `127.0.0.1`, so only the gateway reaches them.
3. The **frontend** must know its base path. The **backend** does not.
4. The **App type** in the dashboard sets the rest.

## Next steps

- [Quick start](quick-start.md)
- [Choose your project type](choose-type.md)
- Unknown word? See the [Glossary](glossary.md)
