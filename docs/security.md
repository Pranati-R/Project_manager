# Security and isolation

## Who can do what

| Part | Runs as | Can |
|---|---|---|
| nginx | root master, `www-data` workers | serve the gateway; reads `gateway.conf` |
| Dashboard backend (FastAPI) | `nginx-gw` (system account, no shell) | read and write its own state in `/var/lib/nginx-gateway`; run **one** sudo command |
| `/usr/sbin/nginx-gateway-helper` | root, via `sudo -n` | fixed commands only: `apply`, `test-full`, `scan`, `restore <id>`, `status`, `backups`, `start`, `logs <source>`, `restart <allowlisted id>` |
| `nginx-gateway-ctl` | root, when you run it | setup, updates, user management |

**The sudo rule:** `/etc/sudoers.d/nginx-gateway` contains only
`nginx-gw ALL=(root) NOPASSWD: /usr/sbin/nginx-gateway-helper`.

**How the helper protects itself:**
- **No shell, no arbitrary arguments:** argparse with fixed choices, IDs checked against strict
  patterns, every subprocess an argument list.
- **No planted modules or environment:** it runs with the system `python3 -I` (isolated mode: no
  user site-packages, no `PYTHONPATH`, not the script's folder), uses the standard library only, and
  sudo resets the environment.
- **Root-owned code:** its code is under `/opt/nginx-gateway/app`, owned by root and not writable by
  `nginx-gw`.
- **A safe read of the staged config:** it reads the file the dashboard staged *once*, opening the
  folder and the file with `O_NOFOLLOW` (no symlink tricks), regular files of 1 MiB at most.

**Before nginx sees the config, it must pass `lint()`.** That is an allowlist of exactly what the
generator produces:
- only `gw_` maps, `gw_` log formats and `server` blocks at the top level
- `listen <addr>:<port>` without options, and never 80 or 443
- `proxy_pass` only to `http://<IP>:<port>`
- logs only to `/var/log/nginx/gateway-*.log`
- a fixed set of `proxy_*`, `sub_filter*`, `return`, `allow`/`deny` directives with checked values
- no `include`, `root`, `alias`, `load_module`, scripting or regex locations

So even a compromised dashboard cannot make nginx read files, run code or log anywhere else. It can
only proxy to IP addresses.

**What runs after lint:**
1. **The conflict scan:** `nginx -T` of the whole configuration must show no other site listening on
   the gateway's ports and no `gw_` names, and no other program may hold those ports.
2. A backup of the live file.
3. An atomic replace.
4. **`nginx -t` of the whole nginx configuration.**
5. A graceful `systemctl reload nginx`.
6. A check that nginx really listens on the new ports.

Any failure restores the previous file (and reloads again if needed). A stopped nginx is never
started without an explicit "Start nginx".

**Restarts:** apps can only be restarted if root lists them in
`/etc/nginx-gateway/restart-targets.conf`, as a systemd unit or Docker container name checked against
a strict pattern.

## Values in the config

Before anything is written, every value that reaches nginx is checked three times:
1. **By the models:** ID slug, path `^(/[a-z0-9][a-z0-9._-]*){1,4}$`, IP-literal hosts, integer ports
   and timeouts, size `^\d+[kmg]?$`, all matched in full.
2. **By the generator:** every interpolated token must match `[A-Za-z0-9._:/\[\]~-]+`.
3. **By the helper's linter.**

Notes and display names never go into directives.

## The dashboard

- **Where it listens:** `127.0.0.1:8790` only. nginx exposes it on the admin port (8281), which has
  the same "Allowed networks" (Tailscale and localhost by default). Or set Settings → Dashboard to
  "Only on 127.0.0.1" and use an SSH tunnel.
- **Its own origin:** being on its own port makes the dashboard a different origin from the projects
  on 8280. A project page cannot read dashboard responses or drive its API.
- **Logins:** scrypt-hashed passwords. Several administrators are allowed.

  > **Warning:** Change the default login. The default login `a@g.com` / `123456` is meant for the
  > first sign-in only; the dashboard shows a banner until you change it.

- **Sessions:**
  - stored server-side as random 256-bit tokens in an `HttpOnly`, `SameSite=Strict` cookie
  - bound to the client address nginx reports
  - expire after 1 hour idle or 12 hours in total
  - all of a user's other sessions end when their password changes
- **CSRF:** every request that changes something must send the session's token in `X-CSRF-Token`.
  There is no CORS, so other origins cannot send that header.
- **The cookie never reaches the apps:** the gateway removes `gwm_session` from every request it
  forwards. Cookies are not per port, so this matters.
- **Login throttling:** 5 failures in 15 minutes lock that address and that username for 5 minutes.
- **Security headers:** `Content-Security-Policy: default-src 'self'` (no inline scripts, no external
  resources), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, and no caching of
  API responses.
- **Audit log:** every change and login is appended to `/var/lib/nginx-gateway/audit.log`, visible
  under Logs.

## Transport

The gateway serves plain HTTP. Traffic between tailnet devices is already encrypted by WireGuard.
The "Allowed networks" rule keeps LAN or internet clients out even when the host firewall is open.
For HTTPS on your MagicDNS name, `tailscale cert` can issue a certificate. Wiring that into the
gateway is not part of this version.

## Isolation from everything else

| | |
|---|---|
| Added to nginx | `/etc/nginx/conf.d/nginx-gateway.conf` (one include line) and `/etc/nginx/nginx-gateway/` |
| Never edited | `nginx.conf`, `sites-available/*`, `sites-enabled/*`, other `conf.d/*`, certificates, the nginx package version, Apache, other systemd units, Docker, firewall rules (unless you run the ufw command yourself), your project folders |
| The one exception | on a *fresh* nginx install, after you confirm: the symlink `sites-enabled/default` (nginx's own default site on port 80, which Apache owns). It is recorded, and restored on uninstall if port 80 is free |
| Effect on other sites | none. The include adds only `gw_`-named maps and log formats and servers on the gateway's own ports; no global directives (gzip, proxy, body size, resolver…) |
| Reloads | graceful (`reload`, never `restart`); in-flight requests to other sites complete. Tested in `tests/e2e` with a slow request held across a reload |

`sudo nginx-gateway-ctl verify-isolation` compares the server with the baseline recorded before
setup:
- the hash of every file under `/etc/nginx` and `/etc/apache2`
- the listening ports and their programs
- the running services and Docker containers

It reports the gateway's own changes apart from anything else.
