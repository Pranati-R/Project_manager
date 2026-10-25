# Testing your project

The **Test** button on each project is your best friend. It checks the app, then checks the whole route,
and tells you what to do when something is wrong.

## How to run it

On the **Projects** tab press **Test** on the project's row. A panel opens and runs the checks from the
server. Press **Run again** after you fix something.

The result at the top is one of:

| Result | Meaning |
|---|---|
| **all good** (green) | Everything works. |
| **works, with warnings** (yellow) | It works, but something should be improved. |
| **problems found** (red) | Something is broken. Read the red lines. |

## What each line means

| Line | Green means | If it is not green |
|---|---|---|
| **Frontend 127.0.0.1:PORT** | The app answers on that port. | The app is not running, or listens on another port or address. Start it, or fix the port in the project. |
| **Backend 127.0.0.1:PORT** | The backend answers. | Start the backend, or fix its port. |
| **Port PORT binding** | The app listens only on this computer. | Yellow: it listens on **all** addresses, so people can skip the gateway. Start it with `--host 127.0.0.1`. Red `::1`: it listens only on IPv6. Start it with `--host 127.0.0.1`. |
| **GET / through the gateway** | The page loads through the gateway. | `502` or `504`: nginx could not reach the app. `403` from Vite: turn off "Pass the original Host header". |
| **Base path** | All the page's files stay inside your project path. | Red: the page links files outside the path. Start or build the app with its base path. See [Vite](vite.md). |
| **Asset ...** | A file linked by the page is served. | The page links a file the app does not serve under this path. |
| **API through the gateway** | The API answers through the gateway. | Check the API path and the "What the API server sees" option in [Backends and APIs](backends.md). |

> **Tip:** Every red or yellow line has a short **hint** under it. It tells you what to do next.

## A check before you start

On the server, this command scans a frontend folder and lists what will break. It **only reads**; it
never changes anything.

```bash
nginx-gateway-ctl vite-check ~/myapp --prefix /myapp/
```

Its output uses these markers:

| Marker | Meaning |
|---|---|
| `ok` | Nothing to do. |
| `--` | Information. |
| `!!` | Should be improved. |
| `XX` | Will break under the path. Fix it. |

It also prints the commands to start or build the app with the right path.

## A check for every project at once

```bash
sudo nginx-gateway-ctl smoke-test
```

This opens every enabled project through the gateway port and reports which answer.

## Look at the logs

When Test says "502" or "404", the **Logs** tab shows the story. Choose **Gateway error log** to see why
nginx could not reach an app, or **Gateway access log** and type your path into the filter to see what
the browser asked for.

## Look in your browser

Press `F12` in the browser. The **Console** tab lists errors. The **Network** tab lists every request
with its status. A red `404` on `/assets/...` almost always means the base path is missing. See
[Troubleshooting](troubleshooting.md).

## Next steps

- [Troubleshooting](troubleshooting.md)
- [FAQ](faq.md)
