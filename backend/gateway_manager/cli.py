"""Command line for the manager (normally called through nginx-gateway-ctl).

    python -m gateway_manager init [--gateway-port N] [--admin-port N]
    python -m gateway_manager user add|passwd|remove|list [EMAIL] [--password-stdin]
    python -m gateway_manager config render|validate|apply|status
    python -m gateway_manager projects list|export|import FILE [--replace]
    python -m gateway_manager smoke-test [--host HOST ...]
    python -m gateway_manager vite-check DIR [--prefix /app/] [--json]
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys

from . import __version__


def _ctx():
    from .audit import Audit
    from .auth import UserStore
    from .config import load_config
    from .helper_client import make_helper
    from .service import GatewayService
    from .store import Store

    cfg = load_config()
    store = Store(cfg.state_file, cfg.history_dir)
    helper = make_helper(cfg)
    audit = Audit(cfg.audit_file)
    return cfg, store, UserStore(cfg.users_file), GatewayService(cfg, store, helper, audit), audit


def _password(args, prompt: str) -> str:
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass(prompt)
    if getpass.getpass("Repeat: ") != first:
        sys.exit("the passwords do not match")
    return first


def cmd_init(args) -> int:
    cfg, store, users, service, _ = _ctx()
    if store.exists():
        print(f"state: {cfg.state_file} already exists (kept)")
    else:
        overrides = {k: v for k, v in (("gateway_port", args.gateway_port), ("admin_port", args.admin_port)) if v}
        state = store.seed(cfg.seed_file if not args.no_seed else None, **overrides)
        print(f"state: created {cfg.state_file} with {len(state.projects)} example project(s)")
    if users.ensure_default():
        from .auth import DEFAULT_PASSWORD, DEFAULT_USER
        print(f"login: created {DEFAULT_USER} / {DEFAULT_PASSWORD} (change it in Settings or with: nginx-gateway-ctl passwd)")
    else:
        print("login: existing users kept")
    return 0


def cmd_user(args) -> int:
    from .auth import AuthError

    cfg, store, users, service, audit = _ctx()
    try:
        if args.action == "list":
            for u in users.list():
                print(u["username"] + ("   (default password)" if u["default_password"] else ""))
            return 0
        if not args.email:
            sys.exit("give the user's email")
        if args.action == "add":
            if users.exists(args.email):
                sys.exit(f"{args.email} already exists")
            users.set_password(args.email, _password(args, f"Password for {args.email}: "), create=True)
        elif args.action == "passwd":
            users.set_password(args.email, _password(args, f"New password for {args.email}: "))
        elif args.action == "remove":
            users.remove(args.email)
    except AuthError as e:
        sys.exit(str(e))
    audit.log("cli", "local", f"user-{args.action}", args.email)
    print("ok")
    return 0


def cmd_config(args) -> int:
    cfg, store, users, service, _ = _ctx()
    state = store.load()
    if args.action == "render":
        sys.stdout.write(service.render(state.settings, state.projects))
        return 0
    if args.action == "status":
        print(json.dumps(service.drift(state), indent=2))
        return 0
    if args.action == "ports":
        print(f"gateway={state.settings.gateway_port}")
        if state.settings.admin_mode == "dedicated_port":
            print(f"admin={state.settings.admin_port}")
        for p in state.projects:
            if p.enabled and p.dedicated_port:
                print(f"{p.id}={p.dedicated_port}")
        return 0
    check = service.check(state.settings, state.projects)
    for w in check.warnings:
        print(f"warning: {w.message}")
    if not check.ok:
        for e in check.errors:
            print(f"error: {e.message}" + (f"  [{e.project_id}]" if e.project_id else ""))
        return 1
    if args.action == "validate":
        print("the gateway config is valid" + ("" if check.nginx_ok else f" ({check.nginx_output})"))
        return 0
    result = service.apply(user="cli", ip="local")
    print(result.get("message", ""))
    for line in result.get("errors", []):
        print(f"  {line}")
    if result.get("output") and not result.get("ok"):
        print(result["output"])
    return 0 if result.get("ok") else 1


def cmd_projects(args) -> int:
    cfg, store, users, service, audit = _ctx()
    state = store.load()
    if args.action == "list":
        for p in state.projects:
            where = p.prefix if p.exposure.value == "path" else f":{p.dedicated_port}"
            api = f" api->{p.backend.hostport}" if p.backend else ""
            print(f"{'on ' if p.enabled else 'off'} {p.id:<24} {where:<24} -> {p.frontend.hostport} [{p.frontend.path_mode.value}]{api}")
        return 0
    if args.action == "export":
        print(json.dumps({"settings": state.settings.model_dump(mode="json"),
                          "projects": [p.model_dump(mode="json") for p in state.projects]}, indent=2))
        return 0
    from .models import Project
    from .service import ValidationFailed

    data = json.load(open(args.file, encoding="utf-8"))
    incoming = [Project.model_validate(p) for p in data.get("projects", [])]

    def mutate(st):
        if args.replace:
            st.projects = incoming
        else:
            by_id = {p.id: p for p in st.projects}
            by_id.update({p.id: p for p in incoming})
            st.projects = list(by_id.values())
    try:
        result = service.update(mutate, user="cli", ip="local", action="import")
    except ValidationFailed as e:
        for err in e.check.errors:
            print(f"error: {err.message}")
        return 1
    print(f"imported {len(incoming)} project(s); " + ((result.get("apply") or {}).get("message") or "saved"))
    return 0


def cmd_smoke_test(args) -> int:
    import httpx

    from .diagnostics import tailscale_info

    cfg, store, users, service, _ = _ctx()
    state = store.load()
    hosts = args.host or (["127.0.0.1"] + tailscale_info().get("ipv4", [])[:1])
    rows, failed = [], 0
    with httpx.Client(timeout=10.0, follow_redirects=False) as client:
        for host in hosts:
            try:
                r = client.get(f"http://{host}:{state.settings.gateway_port}/gateway-health")
                ok = r.status_code == 200
                rows.append((host, "(gateway health)", f"http://{host}:{state.settings.gateway_port}/gateway-health", r.status_code, ok))
            except httpx.HTTPError as e:
                rows.append((host, "(gateway health)", f"http://{host}:{state.settings.gateway_port}/", type(e).__name__, False))
            for p in state.projects:
                if not p.enabled:
                    continue
                port = p.dedicated_port if p.exposure.value == "port" else state.settings.gateway_port
                url = f"http://{host}:{port}{p.route_prefix}/"
                try:
                    r = client.get(url)
                    ok = r.status_code < 500 and r.status_code != 403
                    rows.append((host, p.id, url, r.status_code, ok))
                except httpx.HTTPError as e:
                    rows.append((host, p.id, url, type(e).__name__, False))
    width = max([len(r[2]) for r in rows] + [10])
    for host, pid, url, code, ok in rows:
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'}  {pid:<24} {url:<{width}}  {code}")
    projects = sum(1 for p in state.projects if p.enabled)
    print(f"\n{projects} enabled project(s) through gateway port {state.settings.gateway_port}: "
          + ("all reachable" if not failed else f"{failed} failure(s)"))
    return 1 if failed else 0


def cmd_vite_check(args) -> int:
    from .vite_check import analyze, format_report, report_dict

    rep = analyze(args.dir, args.prefix)
    print(json.dumps(report_dict(rep), indent=2) if args.json else format_report(rep))
    return 1 if any(f.level == "error" for f in rep.findings) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gateway-manager", description=f"Nginx Gateway Manager {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    i = sub.add_parser("init", help="create the state and the default login if missing")
    i.add_argument("--gateway-port", type=int)
    i.add_argument("--admin-port", type=int)
    i.add_argument("--no-seed", action="store_true", help="start without the example project")
    i.set_defaults(fn=cmd_init)

    u = sub.add_parser("user", help="manage dashboard logins")
    u.add_argument("action", choices=["add", "passwd", "remove", "list"])
    u.add_argument("email", nargs="?")
    u.add_argument("--password-stdin", action="store_true")
    u.set_defaults(fn=cmd_user)

    c = sub.add_parser("config", help="render, validate or apply the nginx config")
    c.add_argument("action", choices=["render", "validate", "apply", "status", "ports"])
    c.set_defaults(fn=cmd_config)

    pr = sub.add_parser("projects", help="list, export or import projects")
    pr.add_argument("action", choices=["list", "export", "import"])
    pr.add_argument("file", nargs="?")
    pr.add_argument("--replace", action="store_true")
    pr.set_defaults(fn=cmd_projects)

    s = sub.add_parser("smoke-test", help="request every enabled project through the gateway")
    s.add_argument("--host", action="append")
    s.set_defaults(fn=cmd_smoke_test)

    v = sub.add_parser("vite-check", help="read-only check of a Vite project for subpath readiness")
    v.add_argument("dir")
    v.add_argument("--prefix", default="/")
    v.add_argument("--json", action="store_true")
    v.set_defaults(fn=cmd_vite_check)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "projects" and args.action == "import" and not args.file:
        sys.exit("give the JSON file to import")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
