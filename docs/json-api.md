# Project fields, JSON and API

For scripts and bulk import. You do not need this page to use the dashboard.

## Many projects at once (JSON)

`examples/projects-example.json` has three sample projects. On the server:

```bash
sudo nginx-gateway-ctl projects import /tmp/projects-example.json      # merge by id
sudo nginx-gateway-ctl projects import /tmp/projects.json --replace    # replace all
sudo nginx-gateway-ctl projects export > projects-backup.json
```

The `nginx-gw` account must be able to read the file, so `/tmp` works. In the dashboard use
**Settings -> Backup of the projects**. The import is checked and applied like any other change.

## Project fields

| Field | Values |
|---|---|
| `id` | `a-z 0-9 -`, 1-40 characters; cannot change later |
| `name` | display name |
| `enabled` | `true` / `false`; disabled paths answer 404 |
| `exposure` | `path` (default) or `port` |
| `prefix` | `/name` (up to 4 segments, lowercase), or `/` for one root app |
| `dedicated_port` | for `exposure: port`, 1024-65535 |
| `frontend` | `{host, port, path_mode}`; host is an IP; `path_mode`: `subpath`, `strip` or `rewrite` |
| `backend` | `{host, port, api_path, api_mode, buffering}`; `api_mode`: `strip_prefix`, `strip_all` or `preserve` |
| `pass_host_header` | `false` sends `Host: <app host:port>` (needed for Vite) |
| `read_timeout` | seconds, 5-86400 (WebSockets and long requests) |
| `max_body_size` | for example `100m` |
| `health_path` | for example `/health`, used by Test |
| `app_kind` | `vite_dev`, `vite_preview`, `static_dist`, `backend_served`, `nextjs`, `prebuilt` or `other` |
| `runtime` | `systemd`, `docker`, `tmux` or `other` (only used for the guide) |
| `restart_target` | an id from `restart-targets.conf` |
| `app_dir`, `notes` | used in the guide only |

A minimal project:

```json
{
  "projects": [
    {
      "id": "myapp",
      "name": "My App",
      "prefix": "/myapp",
      "frontend": { "host": "127.0.0.1", "port": 5173, "path_mode": "subpath" },
      "backend": { "host": "127.0.0.1", "port": 8000, "api_path": "/api", "api_mode": "strip_prefix" },
      "app_kind": "vite_dev",
      "pass_host_header": false
    }
  ]
}
```

## From scripts (API)

See `examples/api-requests.http`. In short:

1. `POST /api/auth/login` returns a session cookie plus a `csrf` token.
2. Every change sends that token back in the `X-CSRF-Token` header:
   - `POST /api/projects` adds a project
   - `PUT /api/projects/<id>` edits it
   - `DELETE /api/projects/<id>` removes it
   - `POST /api/projects/<id>/enable` and `/disable` switch it on and off
   - `POST /api/projects/<id>/test` runs the checks
   - `POST /api/config/apply` applies the config
