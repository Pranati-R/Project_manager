# Glossary

Short, plain explanations of the words used in these docs. They are in alphabetical order.

## API

A set of addresses your backend answers, for example `/api/users`. Your frontend calls them to get or
save data. See [Backends and APIs](backends.md).

## Backend

The part of your project that runs on the server: it talks to the database and answers API calls.
Examples: FastAPI, Flask, Express, Django, Spring.

## Base path

The address your frontend lives at. Without the gateway it is `/`. With the gateway it is your project
path, for example `/shop/`. Telling the frontend its base path is **the** step that makes projects work
under the gateway. See [How it works](how-it-works.md).

## Build

Turning your source code into the final files for production (for example into a `dist/` folder).
Some settings, like the base path, are saved **during the build**, so you must build again after
changing them.

## Dev server

A program that runs your app while you work, with hot reload (`npm run dev`). Not for production use,
but fine for learning and small internal projects.

## Docker image and container

An **image** is a packaged copy of your app. A **container** is a running copy of an image. When you
change a setting that is saved at build time, you must build a new image.

## Docker Compose

A file (`docker-compose.yml`) that describes several containers, so that `docker compose up` starts
them all. See [Docker and Compose](docker.md).

## Environment variable

A named setting given to a program from outside, for example `VITE_API_BASE=/myapp/api`. It lets you
change behaviour without editing code.

## Frontend

The part of your project that runs in the browser: pages, buttons, forms. Examples: React, Vue,
Svelte, Angular, Next.js.

## Gateway

The single door in front of all your projects. See [Welcome](welcome.md).

## Hot reload

The browser updates by itself when you save a file. It works through the gateway.

## localhost / 127.0.0.1

Both mean "this same computer". An app listening on `127.0.0.1` can be reached only from the computer
it runs on. For us, that means **only the gateway can reach it**, which is what we want.

## nginx

The well-known web server program that the gateway is made of. The dashboard writes its settings for
you, so you never edit nginx files by hand.

## Path (URL path)

The part of an address after the port. In `http://server:8280/shop/cart`, the path is `/shop/cart`.
The first part (`/shop`) is the **project path** you choose.

## Path mode

How the gateway passes the path to your app: `strip` removes the project path, `subpath` keeps it.
See [How it works](how-it-works.md).

## Port

A number that tells the computer which program should get a request. One computer can run many
programs, each on its own port (`5173`, `8000`, `8280`).

## Prefix

Another word for the project path. The dashboard sometimes calls it the prefix.

## Proxy (reverse proxy)

A program that receives requests and passes them to another program. The gateway is a reverse proxy.

## Router (client-side routing)

The part of a frontend that shows different pages without reloading, for example React Router or Vue
Router. If it uses real addresses (`/settings`), it needs to know the base path.

## Static files

Files that do not change per visitor: HTML, CSS, JavaScript, images. A built frontend is a folder of
static files.

## Tailnet / Tailscale

A private network between your devices. The gateway only answers devices on it, so strangers on the
internet cannot open your projects.

## WebSocket

A connection that stays open so the server can send data at any moment (live chat, hot reload). The
gateway supports it with no extra setup.
