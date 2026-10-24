# Troubleshooting

Start with **Test** on the project. It checks the app directly, then through the gateway, and names
the problem. These commands help:

```bash
sudo nginx-gateway-ctl status                 # services, ports, projects, code version
sudo nginx-gateway-ctl logs error -f          # gateway error log (+ nginx's error.log)
sudo nginx-gateway-ctl logs manager           # dashboard backend
sudo nginx-gateway-ctl smoke-test             # every enabled project through the gateway port
sudo nginx -t                                 # the whole nginx configuration
```

## The page or a route

| Symptom | Cause | Fix |
|---|---|---|
| **502 Bad Gateway** | The app is not running, or it listens on another port/address | Start it. Test shows "connection refused" and the port it tried |
| 502, but the app runs | It listens on `::1` only. Node 17+ resolves `localhost` to IPv6, and the gateway connects to 127.0.0.1 | Start it with `--host 127.0.0.1`, or set the project's host to `::1` |
| **504** | The app accepted the connection but did not answer in time | Check the app; raise the project's Timeout for slow requests |
| **Blank page**, console shows 404s for `/assets/...` | The app was built/started for `/` | Start/build with `--base /prefix/`; see [VITE_BASE_PATH.md](VITE_BASE_PATH.md). Test names the files |
| Page loads, but navigation shows "not found" | React Router has no basename | `basename={import.meta.env.BASE_URL}` |
| Page loads, API calls 404 at `/api/...` | Root-absolute API URLs | Set the app's API env var (`VITE_API_BASE=/prefix/api`) or build URLs from `BASE_URL` |
| "Blocked request. This host is not allowed" | Vite's host check (Vite ≥ 6.0.9) | Turn off "Pass the original Host header" for the project (the Vite preset does) |
| Hot reload does not connect | `server.hmr.port` is set in vite.config | Remove it, or set `hmr.clientPort: 8280` |
| **403 Forbidden** from nginx | Your device is not in "Allowed networks" | Connect through Tailscale, or add the network in Settings |
| WebSocket closes after ~1 h | Timeout | Raise the project's Timeout |
| Streaming answers arrive all at once | Buffering | Leave "Buffer API responses" off for that API |
| **413 Request Entity Too Large** | Upload larger than the limit | Raise Max upload on the project (or the default in Settings) |
| `/prefix` without a slash | It redirects to `/prefix/` (301) | expected |
| The app works directly on its port from another machine | It listens on `0.0.0.0` | Bind it to 127.0.0.1; for Docker use `-p 127.0.0.1:PORT:...` (Docker ports bypass ufw) |

## Saving and applying

| Message | Meaning |
|---|---|
| "the change was not saved: prefix … is already used" | Two projects cannot share a path |
| "port 8282 is already used by another nginx site (/etc/nginx/sites-enabled/x)" | Another site of yours listens there; choose another port. The gateway never takes over another site's port |
| "port N is already in use by another program" | Pick another port (`ss -ltnp 'sport = :N'` shows who) |
| "nginx -t failed … (the error is in another site's file …)" | Another site's config is broken. Nothing was changed; fix that file (`sudo nginx -t` shows it) |
| Banner: "saved but could not be applied" | The previous config is still live. **Details** shows nginx's output; **Retry apply** or **Revert to last applied** |
| Banner: "nginx is stopped" | The config is installed and tested; **Start nginx** starts nginx with all its enabled sites |
| "the sudo rule for nginx-gw is missing" | `/etc/sudoers.d/nginx-gateway` is gone; reinstall the `.deb` |

## Restore an older gateway config

The last 30 versions of `gateway.conf` are kept. Use **Nginx config → Backups → Restore** in the
dashboard (it is tested with `nginx -t` first), or from a shell:

```bash
sudo ls /var/backups/nginx-gateway/
sudo nginx-gateway-helper restore 20261023T101500Z
```

After a restore the dashboard shows "not applied" until you apply again, because the projects
weren't changed.

## Installation

| Symptom | Fix |
|---|---|
| `apt install nginx` failed earlier with "bind() to 0.0.0.0:80 failed" | Apache owns :80 and nginx's default site wants it. `sudo rm /etc/nginx/sites-enabled/default && sudo dpkg --configure -a`; `nginx-gateway-ctl setup` avoids this by itself |
| Setup stops with "port 8790 is already used by: python3" (or 8280/8281) | Another program has that port. Run setup again with the option it names, e.g. `sudo nginx-gateway-ctl setup --manager-port 8791`; nothing was changed |
| Setup warns "your nginx.conf does not include /etc/nginx/conf.d/*.conf" | Your nginx.conf is custom. Add `include /etc/nginx/conf.d/*.conf;` inside `http { }`, then `sudo nginx-gateway-ctl apply` |
| `update-code` "could not fetch" | Private repository; see INSTALL.md (deploy key or token) |
| `update-code` rolled back | The new code failed a step; the reason is in `/var/log/nginx-gateway/update.log`. Fix it, push, run again |
| Dashboard does not open | `nginx-gateway-ctl status`; the manager must be `active` and port 8281 `up`. Or use an SSH tunnel: `ssh -L 8790:127.0.0.1:8790 server`, then `http://127.0.0.1:8790/` |

## Lost the password

```bash
sudo nginx-gateway-ctl passwd a@g.com      # or another admin's email
sudo nginx-gateway-ctl user list
```

Five wrong passwords in 15 minutes lock that address and that account for 5 minutes.

## Prove nothing else changed

```bash
sudo nginx-gateway-ctl verify-isolation
```

This lists every difference since setup in nginx and Apache files, listening ports, running services
and containers. Changes made by the gateway are listed separately from anything else.
