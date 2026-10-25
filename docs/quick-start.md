# Quick start

Put your first project on the gateway in about 10 minutes.

This page uses a **Vite** frontend as the example, because it is the most common. If your project is
something else, the steps are the same and only step 2 changes. See
[Choose your project type](choose-type.md).

## Before you start

- Your project runs on the server (you have its folder, for example `~/myapp`).
- You are signed in to this dashboard.
- You chose a **path** for it. In this page we use `/myapp`.

## Step 1: Find the port

Every app listens on a **port**. Pick a free number (for example `5173`). You will use it twice: when
you start the app and when you add it in the dashboard.

## Step 2: Start your app with its path

In the project folder, start the app and tell it its path with `--base`:

```bash
cd ~/myapp
npm run dev -- --base /myapp/ --host 127.0.0.1 --port 5173 --strictPort
```

What each part means:

| Part | Meaning |
|---|---|
| `--base /myapp/` | The app's home is `/myapp/` (keep the slash at both ends) |
| `--host 127.0.0.1` | Only this computer, and so the gateway, can reach the app |
| `--port 5173` | The port number from step 1 |
| `--strictPort` | Stop with an error instead of silently using another port |

You should see a line like `Local: http://127.0.0.1:5173/myapp/`.

> **Tip:** Using Next.js, Angular, Docker or something else? Skip to
> [Choose your project type](choose-type.md), then come back to step 3.

## Step 3: Add the project in the dashboard

1. Open the **Projects** tab and press **Add project**.
2. **Name:** `My App`. The ID and the path (`/my-app`) fill in by themselves. Change the path to
   `/myapp` so it matches step 2.
3. **App type:** `Vite dev server`.
4. **Frontend port:** `5173`.
5. If you have a separate backend, tick **Separate API server** and fill in its port. See
   [Backends and APIs](backends.md).
6. Press **Add and apply**.

You should see a green message: "Saved and applied: nginx reloaded".

> **Note:** Before anything goes live, the dashboard checks your settings and tests the whole nginx
> configuration. If something is wrong, **nothing changes** and the message tells you what to fix.

## Step 4: Test it

On the project row press **Test**. You should see green ticks for:

- the app answers directly
- the page loads through the gateway
- the page's files load from `/myapp/`

If something is red or yellow, the message tells you what to do. [Testing your project](testing.md)
explains each message.

## Step 5: Open it

Press **Open** on the project row, or go to:

```
http://<server>:8280/myapp/
```

The page should load. Click around, and press refresh on an inner page to confirm it still works.

## You are done

Your project is online. Next:

- Add a backend: [Backends and APIs](backends.md)
- Understand the form: [Add a project: every field](project-fields.md)
- Something went wrong: [Troubleshooting](troubleshooting.md)

## Checklist

- [ ] The app listens on `127.0.0.1`, not on all addresses.
- [ ] The app was started with its base path.
- [ ] The project is added and **Test** is green.
- [ ] The page opens at `http://<server>:8280/myapp/`.
