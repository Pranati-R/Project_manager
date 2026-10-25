# FAQ

Quick answers to the questions students ask most.

## The basics

### Do I have to change my backend?

**No.** The gateway removes the project path before the request reaches your backend. The only
exception is a backend that writes its own links or redirects. See [Backends and APIs](backends.md).

### Do I have to change my frontend?

Usually **only the base path**: one flag or one setting. It depends on the framework. See
[Choose your project type](choose-type.md).

### What is a "base path"?

The address your frontend lives at. Behind the gateway it is your project path, for example `/shop/`.
See [How it works](how-it-works.md).

### Do I need to know nginx?

No. The dashboard writes and tests the nginx settings for you.

### Can two projects use the same path?

No. Each path belongs to one project. The dashboard refuses a duplicate.

### Can I use any path I like?

Lowercase letters, digits, `.`, `_` and `-`, up to four parts, for example `/team/shop`.

## Ports and access

### Why should my app listen on 127.0.0.1?

`127.0.0.1` means "this computer only". The app can then be reached only through the gateway, which
checks who is allowed in. If it listened on all addresses, anyone on the network could skip the gateway.

### Which port should I choose for my app?

Any free number above 1024 that no other program uses, for example `5173`, `3000`, `8000`. The dashboard
warns you if a port is taken.

### Who can open my projects?

Only devices on your private network (Tailscale) and the server itself. Everyone else gets "403
Forbidden". An administrator can change this in **Settings -> Allowed networks**.

### Does it work without Tailscale?

Yes, if the administrator adds your network under **Settings -> Allowed networks**.

## Building and running

### Why do I have to rebuild?

Frameworks such as Vite and Next.js write the base path into the built files. Changing the setting
afterwards changes nothing until you build again. In Docker you also rebuild the **image**.

### Does my app still work on my own computer after these changes?

Yes. The recommended setups default to `/` when you do not pass a base path, so
`npm run dev` on your laptop behaves as before.

### I changed `.env` and nothing happened.

In a build-time framework the value was saved when you built. Build again. In Docker, pass it as a
build argument. See [Docker and Compose](docker.md).

### Why does the page work but refresh gives "not found"?

Your router does not know the base path. See [Vite](vite.md), "Fix 1".

### Does hot reload work?

Yes, with the Vite dev server. It goes through the gateway.

### Do WebSockets and streaming work?

Yes, with no extra setup.

## The dashboard

### I made a mistake. Can I undo it?

Yes. Every live configuration is backed up (the last 30). Go to **Nginx config -> Backups -> Restore**.
The dashboard also never applies a configuration that fails its tests.

### What does "not applied" mean?

You saved a change, but nginx is not using it yet (automatic applying is off, or a backup was
restored). Open **Nginx config** and press **Apply and reload**.

### Will adding a project break my other websites?

No. The gateway only adds its own ports and never edits other nginx or Apache sites. An administrator
can prove it with `sudo nginx-gateway-ctl verify-isolation`.

### I forgot my password.

Ask an administrator to run `sudo nginx-gateway-ctl passwd <email>` on the server.

## Still stuck?

Open [Troubleshooting](troubleshooting.md) or read [Why apps break under a path](why-it-breaks.md).
