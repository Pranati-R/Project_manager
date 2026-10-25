# Add a project: every field

This page explains each field in the **Add project** form. Most of the time the **App type** fills the
hard ones in for you, so you only need this page when you are curious or something looks wrong.

## The form from top to bottom

### Name and ID

| Field | Meaning |
|---|---|
| **Name** | The name shown in the list, for example `My Shop`. |
| **ID** | A short label used in log names, for example `my-shop`. It fills in by itself and **cannot be changed later**. Lowercase letters, digits and dashes only. |

### How is the frontend served? (App type)

Choose the closest match. It sets the path mode, the Host header option and, for prebuilt apps, the
port exposure.

| App type | Pick it when | It sets |
|---|---|---|
| **Vite dev server** | You run `npm run dev` | path mode `subpath`, Host header off |
| **Vite preview** | You run `vite build` then `vite preview` | `subpath`, Host header off |
| **Built files from a static server** | A server (nginx, serve, Docker) serves a built folder | `strip` |
| **Built files served by the app's own backend** | Your backend serves the built folder | `strip` |
| **Next.js** | You run `next start` or `next dev` | `subpath` |
| **Prebuilt app that cannot be rebuilt** | You cannot change the app | its own gateway port |
| **Something else** | None of the above | you choose |

### Where on the gateway

| Choice | Meaning |
|---|---|
| **A URL path on port 8280** (recommended) | The project lives at `http://server:8280/<path>/`. |
| **Its own gateway port** | The project lives at the site root of a port of its own, for example `8282`. For apps that only work at `/`. |

| Field | Meaning |
|---|---|
| **URL path** | For example `/shop`. Lowercase letters, digits, `.`, `_`, `-`. Up to four parts. Two projects cannot share a path. Use `/` for one app that must own the root of the gateway. |
| **Gateway port for this app** | The port number when you chose "Its own gateway port". Between 1024 and 65535, and unused. |

### The app (upstream)

| Field | Meaning |
|---|---|
| **Frontend host** | Where the app runs. Almost always `127.0.0.1`. It must be an IP address, not a name. |
| **Frontend port** | The port the app listens on. |
| **Path mode** | `subpath` keeps the project path when forwarding, `strip` removes it, `rewrite` removes it and edits links on the fly (simple pages only). The App type sets it. |

### Separate API server

Tick it when your backend has its own port. See [Backends and APIs](backends.md).

| Field | Meaning |
|---|---|
| **API host / API port** | Where the backend listens. |
| **API path** | The part after the project path that goes to the backend, for example `/api`. |
| **What the API server sees** | `/prefix/api/x -> /api/x` keeps the API path. `/prefix/api/x -> /x` removes it too. `unchanged` keeps even the project path. |
| **Buffer API responses** | Leave **off**. Off lets streamed answers (live text, notifications) arrive piece by piece. |

### Advanced

| Field | Meaning |
|---|---|
| **Pass the original Host header** | On: the app receives the address the visitor typed. Off: the app receives `127.0.0.1:port`. **Turn it off for Vite**, which blocks unknown host names. The Vite App types do this for you. |
| **Timeout (s)** | How long a request may take before the gateway gives up. Default 3600 (one hour). Raise it for long jobs and WebSockets. |
| **Max upload** | Largest upload allowed, for example `100m`. Empty uses the default in Settings. |
| **Health path** | A page of your backend that answers when it is healthy, for example `/health`. **Test** uses it. |
| **Runs as** | How the app is started (systemd, Docker, tmux, other). Only used to write a better Guide. |
| **Restart target** | Lets the dashboard restart the app. See below. |
| **App folder** | The folder of the project, for example `/home/me/my-app`. Only used in Guide commands. |
| **Notes** | Anything you want to remember. |
| **Enabled** | Off keeps the settings but makes the path answer 404. |

## Restart targets

The **Restart** button works only for apps that an administrator has listed. This stops the dashboard
from restarting anything it likes.

On the server:

```bash
sudo nginx-gateway-ctl restart-targets
```

This opens the list. Each line is `<id> <systemd|docker> <service or container name>`:

```
myapp-frontend   systemd   myapp-frontend.service
myapp-api        docker    myapp-api
```

Then pick the id as **Restart target** in the project's Advanced settings.

## What happens when you save

1. Your values are checked. A mistake shows next to the field.
2. The configuration is tested in a private sandbox.
3. The whole nginx configuration is tested.
4. nginx is reloaded gently (visitors are not cut off).

If anything fails, the old configuration stays live.

## Next steps

- [Testing your project](testing.md)
- [Cheat sheet](cheat-sheet.md)
