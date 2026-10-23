#!/usr/bin/python3 -I
"""Prove that the gateway changed nothing else on the server.

    python3 -I isolation.py snapshot DIR    record the baseline (run once, before setup)
    python3 -I isolation.py compare DIR     compare the server now with that baseline

The baseline holds a sha256 of every file under /etc/nginx and /etc/apache2, the
listening TCP sockets with their programs, the running systemd services and the running
Docker containers. `compare` lists every difference, and separates what belongs to the
gateway (its include stub, /etc/nginx/nginx-gateway/, its ports, its own service) from
anything else. Read-only: it never changes the system. Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # nginx_helper, same root-owned folder
import nginx_helper  # noqa: E402

WATCHED = ("/etc/nginx", "/etc/apache2")
OUR_FILES = ("/etc/nginx/conf.d/nginx-gateway.conf", "/etc/nginx/nginx-gateway/")
OUR_UNITS = {"nginx-gateway-manager.service"}
LIVE_CONFIG = "/etc/nginx/nginx-gateway/gateway.conf"
MANIFEST = "/etc/nginx-gateway/install-manifest"


def _run(argv: list) -> str:
    if not shutil.which(argv[0]):
        return ""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def file_hashes() -> dict:
    out = {}
    for top in WATCHED:
        for root, dirs, files in os.walk(top):
            dirs.sort()
            for name in sorted(files) + [d for d in dirs if os.path.islink(os.path.join(root, d))]:
                path = os.path.join(root, name)
                if os.path.islink(path):
                    out[path] = "link:" + os.readlink(path)
                    continue
                try:
                    with open(path, "rb") as f:
                        out[path] = hashlib.sha256(f.read()).hexdigest()
                except OSError as e:
                    out[path] = f"unreadable:{e.errno}"
    return out


def listeners() -> list:
    rows = []
    for line in _run(["ss", "-ltnpH"]).splitlines():
        cols = line.split()
        if len(cols) < 4:
            continue
        local = cols[3]
        addr, _, port = local.rpartition(":")
        procs = re.findall(r'\("([^"]+)"', line)
        rows.append({"addr": addr.strip("[]").split("%")[0], "port": int(port) if port.isdigit() else 0,
                     "process": procs[0] if procs else "?"})
    return sorted(rows, key=lambda r: (r["port"], r["addr"]))


def units() -> list:
    out = _run(["systemctl", "list-units", "--type=service", "--state=running", "--no-legend", "--plain"])
    return sorted(line.split()[0] for line in out.splitlines() if line.strip())


def containers() -> list:
    out = _run(["docker", "ps", "--format", "{{.Names}}"])
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def collect() -> dict:
    return {"taken": time.strftime("%Y-%m-%d %H:%M:%S %Z"), "files": file_hashes(), "listeners": listeners(),
            "units": units(), "containers": containers(),
            "docker": bool(shutil.which("docker")), "nginx_installed": os.path.isdir("/etc/nginx")}


def snapshot(directory: str) -> int:
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = os.path.join(directory, "baseline.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(collect(), f, indent=1)
    dump = _run(["nginx", "-T"])
    if dump:
        with open(os.path.join(directory, "nginx-T.txt"), "w", encoding="utf-8") as f:
            f.write(dump)
    print(f"baseline saved: {path}")
    return 0


def _manifest() -> dict:
    out = {}
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    out[k] = v
    except OSError:
        pass
    return out


def _ours(path: str) -> bool:
    return path == OUR_FILES[0] or path.startswith(OUR_FILES[1])


def compare(directory: str, manager_port: int = 8790) -> int:
    try:
        with open(os.path.join(directory, "baseline.json"), encoding="utf-8") as f:
            base = json.load(f)
    except OSError:
        print(f"no baseline in {directory}; run setup first (it records one)")
        return 2
    now = collect()
    manifest = _manifest()
    fresh_nginx = manifest.get("NGINX_INSTALLED_BY_US") == "1"
    default_off = manifest.get("DEFAULT_SITE_DISABLED") == "1"
    try:
        with open(LIVE_CONFIG, encoding="utf-8") as f:
            our_ports = nginx_helper.listen_ports(f.read())
    except OSError:
        our_ports = set()

    ours, other = [], []
    bf, nf = base["files"], now["files"]
    for path in sorted(set(bf) | set(nf)):
        if bf.get(path) == nf.get(path):
            continue
        change = "added" if path not in bf else "removed" if path not in nf else "changed"
        line = f"{change:<8} {path}"
        if _ours(path):
            ours.append(line)
        elif fresh_nginx and not base.get("nginx_installed") and path.startswith("/etc/nginx/") and change == "added":
            ours.append(line + "   (nginx was installed by setup)")
        elif default_off and path == "/etc/nginx/sites-enabled/default" and change == "removed":
            ours.append(line + "   (default site on :80 disabled at setup; Apache owns :80)")
        else:
            other.append(line)

    key = lambda r: (r["addr"], r["port"])
    bl = {key(r): r for r in base["listeners"]}
    nl = {key(r): r for r in now["listeners"]}
    for k in sorted(set(nl) - set(bl)):
        r = nl[k]
        line = f"new port {r['addr']}:{r['port']} ({r['process']})"
        if (r["port"] in our_ports and r["process"] == "nginx") or \
                (r["port"] == manager_port and r["addr"] == "127.0.0.1"):
            ours.append(line)
        else:
            other.append(line)
    for k in sorted(set(bl) - set(nl)):
        r = bl[k]
        other.append(f"port no longer listening {r['addr']}:{r['port']} (was {r['process']})")

    for unit in sorted(set(now["units"]) - set(base["units"])):
        (ours if unit in OUR_UNITS or (fresh_nginx and unit == "nginx.service") else other).append(f"service started  {unit}")
    for unit in sorted(set(base["units"]) - set(now["units"])):
        other.append(f"service stopped  {unit}")
    for name in sorted(set(base["containers"]) - set(now["containers"])):
        other.append(f"container stopped {name}")
    for name in sorted(set(now["containers"]) - set(base["containers"])):
        other.append(f"container started {name}")

    print(f"Compared with the baseline taken {base.get('taken')}:\n")
    print("Gateway's own changes (expected):")
    print("\n".join(f"  {x}" for x in ours) if ours else "  none")
    print("\nAnything else:")
    if other:
        print("\n".join(f"  {x}" for x in other))
        print("\nThese were not made by the gateway's files or ports. If you changed them yourself since "
              "the baseline, that is expected; otherwise look into them.")
        return 1
    print("  none\n\n✔ no existing nginx/Apache file, port, service or container changed")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2 or argv[0] not in ("snapshot", "compare"):
        print(__doc__)
        return 2
    if os.geteuid() != 0:
        print("run as root: sudo nginx-gateway-ctl verify-isolation")
        return 2
    if argv[0] == "snapshot":
        return snapshot(argv[1])
    port = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 8790
    return compare(argv[1], port)


if __name__ == "__main__":
    sys.exit(main())
