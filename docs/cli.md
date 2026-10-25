# Command line

`nginx-gateway-ctl` is the tool for the server administrator. Most commands need `sudo`.

## Setup and updates

| Command | What it does |
|---|---|
| `setup [--yes] [--gateway-port N] [--admin-port N] [--manager-port N]` | Installs nginx if needed, gets the code, starts the dashboard. Safe to run again. |
| `update-code [--check] [--branch B]` | Pulls the latest code from GitHub, restarts the manager and re-applies the config. Rolls back by itself if a step fails. |
| `rollback` | Goes back to the code before the last update. |
| `set-repo <url> [branch]` | Changes where the code comes from. |
| `uninstall [--purge]` | Removes the package. nginx and its other sites stay. |

## Running

| Command | What it does |
|---|---|
| `status` | Services, ports, projects and the code version. |
| `start`, `stop`, `restart` | The dashboard service. |
| `logs [manager\|nginx\|access\|error\|setup\|update] [-f]` | Shows logs. `-f` follows them live. |
| `apply` | Regenerates and applies the nginx config from the saved projects. |
| `smoke-test` | Requests every enabled project through the gateway port. |
| `verify-isolation` | Shows that nothing outside the gateway changed since setup. |

## Projects and logins

| Command | What it does |
|---|---|
| `projects list` | Lists the projects. |
| `projects export` | Prints the projects as JSON. |
| `projects import <file> [--replace]` | Imports projects (merge by id, or replace all). |
| `passwd [email]` | Sets a dashboard password (default user `a@g.com`). |
| `user add\|remove\|list [email]` | Manages administrators. |
| `restart-targets` | Edits the list of apps the dashboard may restart. |
| `vite-check <dir> [--prefix /app/]` | Read-only check of a frontend folder for running under a path. |
| `version` | Prints the version. |

## Examples

```bash
sudo nginx-gateway-ctl status
sudo nginx-gateway-ctl logs error -f
nginx-gateway-ctl vite-check ~/myapp --prefix /myapp/
sudo nginx-gateway-ctl update-code --check
```
