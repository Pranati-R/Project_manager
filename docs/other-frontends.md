# Other frontends

Use this page for Angular, Create React App, Vue CLI, SvelteKit, Nuxt, or plain HTML and static sites.

## The idea

Every frontend has **one setting** for its base path. You set it, **build again**, and serve the built
files. Then the gateway removes the project path for you.

## Find your framework

| Framework | Setting for the path `/myapp/` |
|---|---|
| Angular | `ng build --base-href /myapp/` |
| Create React App | `PUBLIC_URL=/myapp npm run build` |
| Vue CLI | `publicPath: '/myapp/'` in `vue.config.js` |
| SvelteKit | `kit: { paths: { base: '/myapp' } }` in `svelte.config.js` |
| Nuxt | `app: { baseURL: '/myapp/' }` in `nuxt.config` |
| Plain HTML | Use relative links (`css/style.css`, not `/css/style.css`) |

> **Note:** Some settings take a slash at the end and some do not. Copy the table exactly.

## Steps

1. Set the base path using the table above.
2. Build the app (`npm run build`, or the command for your framework).
3. Serve the built folder (`dist/`, `build/` or similar) with any static server.
4. Add the project in the dashboard:

| Setting | Value |
|---|---|
| URL path | `/myapp` |
| App type | **Built files from a static server** |
| Frontend port | The port of your static server |

The static server keeps serving the files as if it lived at `/`. The gateway removes `/myapp` before
the request reaches it.

## Plain HTML and static sites

Links in plain HTML pages must not start with a slash.

```html
<!-- works under /myapp/ -->
<link rel="stylesheet" href="css/style.css">
<img src="images/logo.png">

<!-- breaks under /myapp/ : the slash means "the top of the site" -->
<link rel="stylesheet" href="/css/style.css">
```

If you cannot edit the pages, see [Apps you cannot change](cannot-change.md).

## Routers and API calls

The same two rules apply to every framework:

- If the app has pages with real addresses (`/settings`), give its router the base path.
- If the code calls `/api/...`, either read the API address from an environment variable or add the
  base path in code.

[Vite](vite.md) shows both fixes in detail. The ideas are identical in other frameworks.

## Check it works

1. Press **Test** on the project.
2. Open `http://<server>:8280/myapp/`.
3. Open an inner page and refresh it.

## Next steps

- [Backends and APIs](backends.md)
- [Troubleshooting](troubleshooting.md)
