# Apps you cannot change

Use this page when:

- the app is **prebuilt** and you cannot rebuild it,
- you do not have its source code,
- or it needs so many edits that changing it is not worth the time.

## The idea

Give the app its **own gateway port**. The app stays at `/` of that port, exactly as it expects. Nothing
in the app changes.

```
http://server:8280/shop/     -> a project with a path
http://server:8282/          -> the app that cannot be changed (its own port)
```

It is still behind nginx, and still private to your network.

## What changes

| Part | Change? |
|---|---|
| The app | **No** |
| The app's start command | Only: make it listen on `127.0.0.1` |
| The dashboard | A project with **Exposure: Its own gateway port** |

## Steps

### Step 1: Make the app listen on 127.0.0.1

Most apps have a setting for this (`--host 127.0.0.1`, an environment variable, or a config file). This
keeps the app reachable only through the gateway.

### Step 2: Add the project

| Setting | Value |
|---|---|
| App type | **Prebuilt app that cannot be rebuilt** |
| Exposure | **Its own gateway port** |
| Gateway port | An unused number, for example `8282` |
| Frontend port | The port the app listens on |
| Advanced: Pass the original Host header | On |

Choosing the App type fills in most of this.

### Step 3: Open it

```
http://<server>:8282/
```

## Good to know

- Every such app uses one extra port. Pick a free number each time.
- The dashboard refuses a port that another program or nginx site already uses.
- If you can change the app later, you can move it to a path at any time. Follow its setup page and
  switch **Exposure** back to **A URL path**.
- For simple multi-page websites there is also the path mode `rewrite`, which edits links on the fly.
  It is best effort and not recommended for apps with scripts that build their own links.

## Check it works

1. Press **Test** on the project.
2. Open `http://<server>:8282/`.

## Next steps

- [Dashboard tour](dashboard-tour.md)
- [Troubleshooting](troubleshooting.md)
