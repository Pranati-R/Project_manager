# Nginx Gateway Manager

One nginx port in front of all your web apps, with a dashboard to manage the routes.

```
browser on your tailnet
   │
   ├─ http://server:8280/prajna/               ─┐
   ├─ http://server:8280/meeting-transcriber/   ├─ nginx "gateway" server ─► 127.0.0.1:8200, :8201, :8300 …
   ├─ http://server:8282/  (app that needs /)  ─┘
   └─ http://server:8281/  dashboard ─► nginx ─► 127.0.0.1:8790 manager (FastAPI, user nginx-gw)
                                                     │ sudo, one fixed helper
                                                     ▼
                         /usr/sbin/nginx-gateway-helper: lint → backup → nginx -t → reload, or roll back
```

You add a project in the dashboard: its name, its URL path, and the port it runs on. The manager
then does the rest:
1. It generates the nginx routes for the project.
2. It checks them with `nginx -t` in a private sandbox.
3. It installs them and runs `nginx -t` again on the whole nginx configuration.
4. It reloads nginx gracefully.

If any step fails, the previous config stays live. You never edit nginx files by hand.

**Never touched:**
- Apache, which keeps port 80
- your other nginx sites
- your apps' processes

The only thing added to nginx is one include line, `/etc/nginx/conf.d/nginx-gateway.conf`, plus
its own folder, `/etc/nginx/nginx-gateway/`. `sudo nginx-gateway-ctl verify-isolation` proves this
at any time.

| Port | What | Reachable from |
|---|---|---|
| **8280** | the gateway: every project under its own path | your tailnet (`100.64.0.0/10`), localhost |
| **8281** | the dashboard (nginx → 127.0.0.1:8790) | your tailnet, localhost |
| 8282+ | optional: an app that only works at `/` gets its own port | your tailnet, localhost |
| 8790 | the manager backend | 127.0.0.1 only |

All of these can be changed in the dashboard (Settings).

## Install (Ubuntu)

1. **Build the package.** This works on Windows or Linux and needs no dpkg:

   ```bash
   python packaging/build_deb.py          # -> dist/nginx-gateway_0.1.0_all.deb
   ```

2. **Install it on the server:**

   ```bash
   sudo apt install ./nginx-gateway_0.1.0_all.deb
   sudo nginx-gateway-ctl setup           # shows what it will add, asks, then sets everything up
   ```

`setup` installs nginx if it is missing. It does this without letting nginx's default site grab
port 80 from Apache. It then:
- gets the code from GitHub, or uses the copy in the package
- creates a Python environment
- applies the gateway config
- starts the dashboard

At the end it prints the addresses:

```
  Projects   http://box.tail1234.ts.net:8280/
  Dashboard  http://box.tail1234.ts.net:8281/
  Login      a@g.com / 123456  (change it: Settings, or sudo nginx-gateway-ctl passwd)
```

**Install guide:** [docs/INSTALL.md](docs/INSTALL.md) covers every file setup touches, private repositories, firewall and uninstalling.

## Updating: push to GitHub, then run one command

The package works like Smart Finder's. The live code is a git checkout in `/opt/nginx-gateway/app`:

```bash
git push                                   # from your machine
sudo nginx-gateway-ctl update-code --check # on the server: what would change
sudo nginx-gateway-ctl update-code         # pull, reinstall packages if needed, restart, re-apply config
sudo nginx-gateway-ctl rollback            # back to the previous version if you need to
```

`update-code` restarts the manager and re-applies the nginx config. That config is tested first, so
a bad template never reaches the live nginx. If anything fails, the update rolls itself back. You
only need a new `.deb` when files that dpkg installs change: the systemd unit, the shims, the sudo
rule or the maintainer scripts. `update-code --check` tells you when that is the case.

The repository URL is set in `/etc/nginx-gateway/nginx-gateway.conf`
(`https://github.com/Pranati-R/Project_manager.git` by default). Change it with:

```bash
sudo nginx-gateway-ctl set-repo https://github.com/<you>/<repo>.git main
```

## Using it

- **Projects.** Each row shows whether the app is up and its route (`/prajna → 127.0.0.1:8200`, API
  `/prajna/api → :8201`), with an on/off switch and these buttons:
  - **Test** checks the app directly, then through the gateway. It also loads the page's files
    through the gateway to catch base-path problems.
  - **Guide** shows exact commands for this app.
  - **Edit**, **Delete**, and **Restart** (for apps you allowlist).
- **Add project.** Pick how the frontend is served:
  - Vite dev server
  - Vite preview
  - static build
  - Next.js
  - a prebuilt app

  The right proxy settings are filled in for you, and a live preview shows the nginx routes that
  will be generated.
- **Nginx config.** See the generated file, its diff against the live one, validate with `nginx -t`,
  apply, or restore one of the last 30 versions.
- **Logs.** Gateway access and error logs, nginx's own logs, and an audit trail of who changed what.
- **Settings.** Ports, allowed networks, auto-apply, passwords, administrators, and import/export.

## Vite apps under a path

This is the part that usually breaks. Vite builds for `/` by default, so under `/prajna/` the page
asks for `/assets/…` and misses. Rewriting those URLs in nginx can't be done safely (the docs
explain why). Instead, the app is started or built with `--base /prajna/`, and the gateway forwards
the path to match. This usually takes **no file changes**: only the start command, plus an env var
when the app reads its API address from one. **[docs/VITE_BASE_PATH.md](docs/VITE_BASE_PATH.md)**
has the details.

To see exactly what a project needs, run this. It only reads files:

```bash
nginx-gateway-ctl vite-check ~/sql-llm/frontend --prefix /prajna/
```

[docs/ADDING_PROJECTS.md](docs/ADDING_PROJECTS.md) walks through Prajna, Meeting Transcriber and
Smart Finder.

## Command reference

```
nginx-gateway-ctl setup | update-code [--check] | rollback | set-repo URL [BRANCH] | uninstall [--purge]
nginx-gateway-ctl status | start | stop | restart | logs [manager|nginx|access|error] [-f]
nginx-gateway-ctl apply | smoke-test | verify-isolation
nginx-gateway-ctl projects list|export|import FILE | passwd [EMAIL] | user add|remove|list
nginx-gateway-ctl restart-targets | vite-check DIR --prefix /app/ | version
```

## Development and tests

```bash
python -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/python -m pytest                 # unit tests; e2e runs when an nginx binary is found

# Run the dashboard locally against a private sandbox nginx (no root, nothing system-wide)
GWM_STATE_DIR=.dev-state GWM_HELPER_MODE=sandbox GWM_NGINX_BIN=$(which nginx) PYTHONPATH=backend \
  .venv/bin/python -m uvicorn gateway_manager.main:create_app --factory --port 8790
```

The end-to-end test `tests/e2e/test_gateway_e2e.py` starts a real nginx and several mock apps. It
checks that every project is reachable through **one gateway port**, covering:
- each path mode
- query strings and request bodies
- WebSockets
- forwarded headers
- the dashboard cookie never reaching the apps
- the rewrite mode and the dedicated and admin ports

It also proves isolation and recovery:
- a pre-existing nginx site stays untouched, even mid-reload
- port collisions are refused
- a rejected config leaves the gateway running

With Node available (`npm install` in `tests/fixtures/vite-app`), it also runs a real Vite dev
server under `/viteapp/`, including hot-reload WebSockets through the gateway.

**Without a local nginx:**

```bash
apt-get download nginx-core && dpkg -x nginx-core_*.deb /tmp/ngx
GW_NGINX_BIN=/tmp/ngx/usr/sbin/nginx pytest
```

## More

- [docs/INSTALL.md](docs/INSTALL.md): install, update, uninstall, files and firewall
- [docs/ADDING_PROJECTS.md](docs/ADDING_PROJECTS.md): worked examples and the JSON/API formats
- [docs/VITE_BASE_PATH.md](docs/VITE_BASE_PATH.md): why subpaths break and how to fix them
- [docs/DOCKER_SUBPATH.md](docs/DOCKER_SUBPATH.md): which files to change for a Docker Compose app (Vite or Next.js), with OccuSafe as the example
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/SECURITY.md](docs/SECURITY.md): privilege separation, auth and isolation
