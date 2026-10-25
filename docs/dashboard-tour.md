# Dashboard tour

A quick walk through every part of the dashboard. The tabs are in the bar at the top.

## The top bar

| Item | What it shows |
|---|---|
| **nginx badge** | Green when nginx is running. Red when it is stopped. |
| **not applied** (yellow) | You saved changes that nginx does not use yet. Click it to review and apply. |
| **Address badge** | The gateway address. Click to open it. |
| Moon icon | Switches between light and dark. |
| Door icon | Signs you out. |

Coloured **banners** under the bar tell you when something needs attention, such as a default password
or a stopped nginx. They have buttons to fix the problem.

## Projects

Your main page. Each row is one project.

```
(green dot)  Shop                 /shop -> 127.0.0.1:5173   [subpath]
             shop                 /shop/api -> 127.0.0.1:8000
                                  [on/off] Open  Test  Guide  Restart  Edit  Delete
```

| Part | Meaning |
|---|---|
| **Green dot** | The app answers on its port. Red: it does not. |
| **/shop -> 127.0.0.1:5173** | The route: the path on the left goes to the app on the right. |
| **subpath / strip prefix** | The path mode ([How it works](how-it-works.md)). |
| **On/off switch** | Switches the route on or off without deleting it. A disabled path shows 404. |
| **Open** | Opens the project in a new tab. |
| **Test** | Checks the app and the route. See [Testing your project](testing.md). |
| **Guide** | Shows the exact commands for this project, written from its settings. |
| **Restart** (circular arrow) | Restarts the app. Appears only if an administrator allowed it. |
| **Edit / Delete** | Change the settings, or remove the route. Delete never touches the app itself. |

Press **Add project** at the top right to create one.

## Add project / Edit project

A form on the left, with a live preview of the generated nginx routes on the right. Every field is
explained in [Add a project: every field](project-fields.md).

When you press **Add and apply**, the dashboard:

1. checks your values,
2. tests the whole nginx configuration,
3. reloads nginx.

If any step fails, the old configuration stays live and the message appears next to the field.

## Nginx config

For people who want to see what the dashboard wrote. You never need to edit it.

| Tab or button | What it does |
|---|---|
| **Changes** | What would change in the live file. |
| **Generated** | The new configuration the dashboard built from your projects. |
| **Live** | The configuration nginx is using right now. |
| **Validate** | Tests the new config in a private sandbox. |
| **Full nginx -t** | Tests the whole nginx setup with your config in place. Nothing is reloaded. |
| **Apply and reload** | Puts the config live. |
| **Backups** | The last 30 live versions. **Restore** goes back to one (tested first). |

## Logs

Read-only views of what happened. Choose a source from the list.

| Source | Use it to see |
|---|---|
| Gateway access log | Every request that came in, with its status number (200, 404, 502) |
| Gateway error log | Why nginx could not reach an app |
| Dashboard access / error log | Requests to this dashboard |
| nginx error.log | Errors from all nginx sites |
| nginx / Manager service journal | Start and stop messages |
| Audit trail | Who changed what, and when |

The filter box narrows the lines. Type your project path (for example `/shop`) or a status number
(`502`). Switch on **Auto-refresh** to watch new lines arrive.

## Settings

| Section | What it does |
|---|---|
| **Gateway** | The gateway port, the dashboard port, allowed networks, default upload size, the landing page, auto-apply. Change these only if you know why. |
| **Account** | Change your password. |
| **Administrators** | Add or remove people who can sign in. |
| **Backup of the projects** | Export your projects to a JSON file, or import them. See [Project fields, JSON and API](json-api.md). |
| **About** | Version number and where the restart list lives. |

> **Warning:** The first login is `a@g.com` / `123456`. Change the password in **Settings -> Account**
> right away. The dashboard shows a yellow banner until you do.

## Docs

This documentation. The left list has every page. The box at the top searches all pages.

## Next steps

- [Add a project: every field](project-fields.md)
- [Testing your project](testing.md)
