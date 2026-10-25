# Choose your project type

Find your project in the table, then open its page. Each page has the same layout: what changes, the
steps, the dashboard settings, and how to check it.

## Find your page

| My project is... | Go to |
|---|---|
| A **Vite** app (React, Vue, Svelte, ...) | [Vite](vite.md) |
| A **Next.js** app | [Next.js](nextjs.md) |
| **Angular**, **Create React App**, **Vue CLI**, **SvelteKit**, **Nuxt**, or plain HTML | [Other frontends](other-frontends.md) |
| Only a **backend** or API (FastAPI, Flask, Express, Django, ...) | [Backends and APIs](backends.md) |
| A frontend **and** a backend | Set up the frontend from its page, then add the backend from [Backends and APIs](backends.md) |
| Running in **Docker** or **Docker Compose** | [Docker and Compose](docker.md) |
| An app I **cannot change** or rebuild | [Apps you cannot change](cannot-change.md) |

## Not sure? Answer these questions

**1. Is it a frontend, a backend, or both?**
A frontend shows pages in the browser. A backend answers API calls. Many projects have both. Set up
each part with its own page.

**2. How is the frontend started?**
Look in `package.json` under `"scripts"`.

- A script that runs `vite` -> [Vite](vite.md)
- A script that runs `next` -> [Next.js](nextjs.md)
- `ng` -> Angular, `react-scripts` -> Create React App, `vue-cli-service` -> Vue CLI,
  `nuxt` -> Nuxt: all in [Other frontends](other-frontends.md)

**3. Does it run in Docker?**
If you start it with `docker compose up` or `docker run`, also read [Docker and Compose](docker.md).

**4. Can I change and rebuild it?**
If not, or if it has far too many places to edit, use [Apps you cannot change](cannot-change.md).

## What each choice sets in the dashboard

The **App type** field in the dashboard sets the right options for you.

| App type in the dashboard | Use it for |
|---|---|
| Vite dev server | `npm run dev` |
| Vite preview | `vite build` then `vite preview` |
| Built files from a static server | A built `dist/` folder served by nginx, `serve`, Caddy, Docker |
| Built files served by the app's own backend | Your FastAPI or Express app serves the built files |
| Next.js | `next start` or `next dev` |
| Prebuilt app that cannot be rebuilt | Gets its own gateway port |
| Something else | You choose the path mode yourself |

> **Tip:** Still unsure? Pick the closest App type and press **Test**. It tells you what is wrong and
> what to do.
