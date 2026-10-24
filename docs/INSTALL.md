# Install, update and remove

The target is Ubuntu 22.04 or 24.04 with systemd. Python 3.10+ ships with both.

## 1. Put the code on GitHub

The installed system pulls its code from a git repository, the same way Smart Finder does.

```bash
git remote add origin https://github.com/Pranati-R/Project_manager.git
git push -u origin main
```

If you use another URL or branch, change `GIT_REPO_URL` and `GIT_BRANCH` in
`packaging/linux/nginx-gateway.conf.template` before building, or run `set-repo` on the server
after installing.

**Private repository:** `update-code` runs `git fetch` as root, so root needs read access. Either:

- **Deploy key:** a read-only deploy key on the repository, with the key in
  `/root/.ssh/id_ed25519`. Then run
  `sudo nginx-gateway-ctl set-repo git@github.com:Pranati-R/Project_manager.git`.
- **HTTPS token:** a fine-grained token with read access to that one repository:
  `sudo nginx-gateway-ctl set-repo https://<token>@github.com/Pranati-R/Project_manager.git`.
  The token is stored in `/etc/nginx-gateway/nginx-gateway.conf`, which is mode 644, so prefer the
  deploy key on shared servers.

## 2. Build the .deb

```bash
python packaging/build_deb.py                 # version from packaging/VERSION
python packaging/build_deb.py --version 0.1.1
```

This uses only the Python standard library, so it runs on Windows too. The result is
`dist/nginx-gateway_<version>_all.deb`, about 90 kB, containing the code, the service unit and
`nginx-gateway-ctl`.

## 3. Install

```bash
scp dist/nginx-gateway_0.1.0_all.deb server:
ssh server
sudo apt install ./nginx-gateway_0.1.0_all.deb
sudo nginx-gateway-ctl setup
```

`apt install` runs quickly and offline. It creates:
- the `nginx-gw` system account
- `/var/lib/nginx-gateway`
- `/etc/nginx-gateway/nginx-gateway.conf` and `restart-targets.conf`
- the sudo rule, which is checked with `visudo -c` first

`nginx` is deliberately **not** a package dependency. Installing it through apt would start its
default site on port 80, collide with Apache and fail.

`setup` (safe to run again; finished steps are skipped) goes through these steps:

1. **Checks the server.** Ubuntu, systemd, Python ≥ 3.10, which program owns port 80, whether
   nginx is installed, and whether ports 8280, 8281 and 8790 are free. It prints the full list of
   what it will add and asks before going on (`--yes` skips the question).
2. **Records a baseline** for `verify-isolation`: hashes of every file under `/etc/nginx` and
   `/etc/apache2`, the listening ports, the running services and the Docker containers.
3. **Backs up `/etc/nginx`** to `/var/backups/nginx-gateway/etc-nginx-<time>.tar.gz`.
4. **Installs nginx only if it is missing.** It uses a temporary `policy-rc.d`, so apt does not start
   nginx, then asks before disabling nginx's own default site (`sites-enabled/default`), which wants
   Apache's port 80. Only that symlink is removed, and it is noted in
   `/etc/nginx-gateway/install-manifest`. An nginx you already had is not upgraded and its files are
   not edited.
5. **Gets the code**:
   - `git clone` of `GIT_REPO_URL` into `/opt/nginx-gateway/app`, which is root-owned
   - the copy inside the package when GitHub is unreachable
6. **Creates the Python environment**: `/opt/nginx-gateway/venv` with the pinned packages from
   `backend/requirements.txt`.
7. **Creates the state.** `/var/lib/nginx-gateway/state.json` gets an example *Prajna* project
   (8200/8201) and `users.json` gets the default login **a@g.com / 123456**. Use
   `--gateway-port`/`--admin-port`/`--manager-port` to start on other ports (setup suggests a free one when a port is taken).
8. **Applies the config.** It writes `/etc/nginx/nginx-gateway/gateway.conf` and the one-line
   `/etc/nginx/conf.d/nginx-gateway.conf`, runs `nginx -t`, then reloads nginx. A freshly installed
   nginx is started. An existing nginx that was stopped is only started after you confirm, because
   that also starts its other sites.
9. **Starts `nginx-gateway-manager.service`** on 127.0.0.1:8790.
10. **Prints the addresses** and runs `verify-isolation`.

### Firewall and Tailscale

nginx listens on `0.0.0.0:8280/8281` and **denies every client outside "Allowed networks"**. By
default those are Tailscale (`100.64.0.0/10`, `fd7a:115c:a1e0::/48`) and localhost. Other machines on
your LAN get 403.

nginx is deliberately not bound to the Tailscale IP. tailscaled can start after nginx at boot, the
bind would then fail, and nginx would refuse to start, taking your other sites down with it. If you
want that anyway, set `net.ipv4.ip_nonlocal_bind=1` and put the 100.x address in Settings → Listen
addresses.

With ufw active, allow the ports on the Tailscale interface only:

```bash
sudo ufw allow in on tailscale0 to any port 8280,8281 proto tcp
```

The gateway does not make the apps themselves private. An app that listens on `0.0.0.0:8200` can
still be reached directly. The dashboard's **Test** warns about this. Bind each app to `127.0.0.1`,
and for Docker publish `-p 127.0.0.1:8200:80`, because Docker-published ports bypass ufw.

## 4. Update

| What changed | How it gets to the server |
|---|---|
| Python, dashboard, nginx template, `nginx-gateway-ctl` | `git push`, then `sudo nginx-gateway-ctl update-code` |
| `requirements.txt` | the same; `update-code` reinstalls the packages |
| systemd unit, shims, sudo rule, `postinst`/`prerm`/`postrm` | build a new `.deb` (bump `packaging/VERSION`), then `sudo apt install ./nginx-gateway_<v>_all.deb` |

`update-code` goes through these steps:
1. Fetches the configured branch.
2. Lists what changes.
3. Switches the checkout and continues with the **new** version of `nginx-gateway-ctl`.
4. Reinstalls the Python packages if `requirements.txt` changed.
5. Restarts the manager and waits for `/api/health`.
6. Re-applies the nginx config. This runs the full lint, conflict scan and `nginx -t`; a no-op when
   nothing changed.

If any step fails, it resets to the previous commit and repeats the steps. The logs are in
`/var/log/nginx-gateway/update.log`.

```bash
sudo nginx-gateway-ctl update-code --check     # incoming commits and what they touch
sudo nginx-gateway-ctl update-code --branch dev
sudo nginx-gateway-ctl rollback                # previous commit (run again to go forward)
```

Projects, settings and logins live in `/var/lib/nginx-gateway` and are never touched by updates.

## 5. Uninstall

```bash
sudo apt remove nginx-gateway      # or: sudo nginx-gateway-ctl uninstall
sudo apt purge nginx-gateway       # also deletes projects, logins, settings and the nginx-gw account
```

`remove` does the following:
1. Backs up the gateway's two nginx paths (`/var/backups/nginx-gateway/removed-<time>.tar.gz`) and
   deletes them.
2. Runs `nginx -t` and reloads. If the test fails without those files, it puts them back so nginx
   keeps a valid config.
3. Re-enables nginx's default site if setup disabled it and port 80 is free.
4. Deletes `/opt/nginx-gateway` and the sudo rule.

nginx itself, its other sites and Apache stay as they are. Backups are kept.

## Files

| Path | What | Owner |
|---|---|---|
| `/etc/nginx/conf.d/nginx-gateway.conf` | `include /etc/nginx/nginx-gateway/*.conf;` | root |
| `/etc/nginx/nginx-gateway/gateway.conf` | generated routes (written only by the helper) | root |
| `/opt/nginx-gateway/app` | live code (git checkout) | root, not writable by nginx-gw |
| `/opt/nginx-gateway/venv`, `state/` | Python environment, setup stamps, isolation baseline | root |
| `/etc/nginx-gateway/nginx-gateway.conf` | repository, branch, manager port | root |
| `/etc/nginx-gateway/restart-targets.conf` | apps the dashboard may restart | root |
| `/var/lib/nginx-gateway/` | `state.json`, `users.json`, `audit.log`, `history/`, `staging/` | nginx-gw, 0750 |
| `/var/backups/nginx-gateway/` | last 30 gateway configs, `/etc/nginx` tarballs | root, 0700 |
| `/var/log/nginx/gateway-*.log` | gateway and dashboard access/error logs (rotated by nginx's logrotate) | nginx |
| `/var/log/nginx-gateway/` | setup and update logs | root |
| `/usr/bin/nginx-gateway-ctl`, `/usr/sbin/nginx-gateway-helper` | shims into the live code | root |
| `/etc/sudoers.d/nginx-gateway` | nginx-gw may run the helper, nothing else | root, 0440 |
