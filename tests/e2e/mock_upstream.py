"""Small stand-in apps for the end-to-end test: each says who it is and what it received."""
from __future__ import annotations

import asyncio
import threading
import time

import uvicorn
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.routing import Route, WebSocketRoute

LEGACY_HTML = """<!doctype html><html><head>
<link rel="stylesheet" href="/style.css"><script src="/assets/app.js"></script>
<script src="//cdn.example.com/lib.js"></script><style>body{background:url(/img/bg.png)}</style>
</head><body><a href='/about'>About</a></body></html>"""


def make_app(name: str, html: str | None = None) -> Starlette:
    async def http(request):
        body = await request.body()
        path = request.url.path
        if path.endswith("/slow"):
            await asyncio.sleep(2.0)
            return PlainTextResponse(f"{name}: slow done")
        if html is not None and path in ("/", "/index.html"):
            return HTMLResponse(html)
        if path.endswith(".css"):
            return PlainTextResponse("a{background:url(/img/x.png)}", media_type="text/css")
        return JSONResponse({
            "app": name,
            "path": path,
            "raw_path": request.scope.get("raw_path", b"").decode(),
            "query": request.url.query,
            "method": request.method,
            "body": body.decode(errors="replace"),
            "headers": dict(request.headers),
        })

    async def ws(websocket):
        await websocket.accept()
        try:
            while True:
                msg = await websocket.receive_text()
                await websocket.send_text(f"{name}:{websocket.url.path}:{msg}")
        except Exception:
            pass

    methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
    return Starlette(routes=[WebSocketRoute("/{path:path}", ws), Route("/{path:path}", http, methods=methods)])


class ServerThread:
    def __init__(self, app, port: int):
        self.port = port
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                                    lifespan="off", ws="websockets"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> "ServerThread":
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError(f"mock app on {self.port} did not start")
            time.sleep(0.02)
        return self

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(5)
