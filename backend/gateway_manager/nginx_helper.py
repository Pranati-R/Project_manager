#!/usr/bin/python3 -I
"""nginx-gateway-helper: the only part of the gateway manager that runs as root.

The dashboard backend runs as the unprivileged user nginx-gw and calls this through
`sudo -n /usr/sbin/nginx-gateway-helper <command>` (the only sudo rule it has). The
commands are fixed, arguments are validated, nothing goes through a shell, and every
config is checked by `lint()` (an allowlist of exactly what the generator produces) and
by a conflict scan before nginx sees it. Changes are applied with a graceful reload only
after `nginx -t` passes for the whole nginx config, and are rolled back on any failure.

Standard library only: it runs under the system python3 in isolated mode (-I). The
manager imports the same module for lint() so both sides apply identical rules.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import errno
import hashlib
import ipaddress
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time

PRODUCTION_LOG_DIR = "/var/log/nginx"
MAX_CONFIG_BYTES = 1 << 20
KEEP_BACKUPS = 30
BACKUP_ID_RE = re.compile(r"^\d{8}T\d{6}Z$")
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
LOG_NAME_RE = re.compile(r"^[a-z0-9-]{1,40}$")
UNIT_RE = re.compile(r"^[A-Za-z0-9@._-]{1,120}\.service$")
CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

STUB_TEXT = (
    "# Added by the nginx-gateway package: the routes managed in its dashboard.\n"
    "# Removed again by `apt remove nginx-gateway`. Do not edit.\n"
    "include /etc/nginx/nginx-gateway/*.conf;\n"
)


# ─────────────────────────────────────────────────────────────────────────────
# Linter: tokenizer, parser and the directive allowlist
# ─────────────────────────────────────────────────────────────────────────────

class ParseError(Exception):
    pass


def tokenize(text: str) -> list:
    """nginx config tokens as (kind, value, line); kind is word, str, {, } or ;"""
    tokens, i, line, n = [], 0, 1, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c in " \t\r":
            i += 1
        elif c == "#":
            while i < n and text[i] != "\n":
                i += 1
        elif c in "{};":
            tokens.append((c, c, line))
            i += 1
        elif c in "\"'":
            quote, start_line, buf = c, line, []
            i += 1
            while True:
                if i >= n:
                    raise ParseError(f"line {start_line}: unterminated string")
                ch = text[i]
                if ch == "\\" and i + 1 < n and text[i + 1] in (quote, "\\"):
                    buf.append(text[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    i += 1
                    break
                if ch == "\n":
                    line += 1
                buf.append(ch)
                i += 1
            tokens.append(("str", "".join(buf), start_line))
        else:
            start = i
            while i < n and text[i] not in " \t\r\n{};\"'#":
                i += 1
            if i < n and text[i] in "\"'":
                raise ParseError(f"line {line}: unexpected quote inside {text[start:i + 1]!r}")
            tokens.append(("word", text[start:i], line))
    return tokens


class Node:
    __slots__ = ("name", "args", "children", "line")

    def __init__(self, name, args, children, line):
        self.name, self.args, self.children, self.line = name, args, children, line


def parse(text: str) -> list:
    tokens = tokenize(text)
    pos = 0

    def block(depth: int) -> list:
        nonlocal pos
        nodes = []
        while pos < len(tokens):
            kind, value, line = tokens[pos]
            if kind == "}":
                if depth == 0:
                    raise ParseError(f"line {line}: unexpected }}")
                pos += 1
                return nodes
            if kind not in ("word", "str"):  # map keys may be quoted
                raise ParseError(f"line {line}: expected a directive name, got {value!r}")
            pos += 1
            args = []
            while True:
                if pos >= len(tokens):
                    raise ParseError(f"line {line}: directive {value!r} is not terminated")
                k, v, _ = tokens[pos]
                if k in ("word", "str"):
                    args.append(v)
                    pos += 1
                elif k == ";":
                    pos += 1
                    nodes.append(Node(value, args, None, line))
                    break
                elif k == "{":
                    pos += 1
                    nodes.append(Node(value, args, block(depth + 1), line))
                    break
                else:
                    raise ParseError(f"line {line}: unexpected }} in {value!r}")
        if depth != 0:
            raise ParseError("unbalanced braces: missing }")
        return nodes

    return block(0)


IP4 = r"\d{1,3}(?:\.\d{1,3}){3}"
IP6 = r"\[[0-9a-fA-F:.]+\]"
PROXY_PASS_RE = re.compile(rf"^http://(?:{IP4}|{IP6}):\d{{1,5}}(?:/[A-Za-z0-9._~/-]*)?$")
LISTEN_RE = re.compile(rf"^(?:({IP4}|{IP6}):)?(\d{{1,5}})$")
SIZE_RE = re.compile(r"^\d{1,5}[kmgKMG]?$")
TIME_RE = re.compile(r"^\d{1,6}(?:ms|s|m|h)?$")
PATH_RE = re.compile(r"^/[A-Za-z0-9._~/-]*$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9._:/\[\]~-]+$")
REDIRECT_TARGET_RE = re.compile(r"^/[A-Za-z0-9._~/-]*(?:\$is_args\$args)?$")
MAP_VALUE_RE = re.compile(r"^[A-Za-z0-9_$]*$")
GW_VAR_RE = re.compile(r"^\$gw_[a-z0-9_]{1,40}$")
GW_NAME_RE = re.compile(r"^gw_[a-z0-9_]{1,40}$")

HEADER_NAMES = {
    "Upgrade", "Connection", "Host", "X-Real-IP", "X-Forwarded-For", "X-Forwarded-Proto",
    "X-Forwarded-Host", "X-Forwarded-Port", "X-Forwarded-Prefix", "Cookie", "Accept-Encoding",
}
HEADER_VARS = {
    "$http_upgrade", "$gw_connection_upgrade", "$http_host", "$remote_addr",
    "$proxy_add_x_forwarded_for", "$scheme", "$server_port", "$gw_project_cookie",
}
MAP_SOURCES = {"$http_upgrade", "$http_cookie"}
SUB_FILTER_TYPES = {"text/css", "application/javascript", "text/javascript", "text/html"}
LOG_LEVELS = {"warn", "error", "crit", "alert", "emerg", "notice", "info"}
RETURN_CODES = {"200", "301", "302", "404", "503"}
ON_OFF = {"on", "off"}


def _ip_or_net(value: str) -> bool:
    if value == "all":
        return True
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return False


def _listen_port(arg: str):
    m = LISTEN_RE.fullmatch(arg)
    return int(m.group(2)) if m else None


def lint(text: str, log_dir: str = PRODUCTION_LOG_DIR) -> list:
    """Errors for anything the generator would never produce. An empty list means OK."""
    try:
        tree = parse(text)
    except ParseError as e:
        return [str(e)]
    log_re = re.compile("^" + re.escape(log_dir.rstrip("/")) + r"/gateway-[a-z0-9-]{1,40}\.(?:access|error)\.log$")
    errors = []

    def err(node, msg):
        errors.append(f"line {node.line}: {node.name}: {msg}")

    def nargs(node, *allowed):
        if len(node.args) not in allowed:
            err(node, f"expected {' or '.join(map(str, allowed))} argument(s), got {len(node.args)}")
            return False
        return True

    def simple(node):
        if node.children is not None:
            err(node, "must not have a block")
            return False
        return True

    def check_location_child(node):
        name, a = node.name, node.args
        if name != "location" and not simple(node):
            return
        if name == "proxy_pass":
            if nargs(node, 1) and not PROXY_PASS_RE.fullmatch(a[0]):
                err(node, f"target {a[0]!r} must be http://<IP>:<port>[/path]")
        elif name == "proxy_http_version":
            if nargs(node, 1) and a[0] not in ("1.0", "1.1"):
                err(node, "must be 1.0 or 1.1")
        elif name == "proxy_set_header":
            if nargs(node, 2):
                if a[0] not in HEADER_NAMES:
                    err(node, f"header {a[0]!r} is not allowed")
                elif not (a[1] in HEADER_VARS or a[1] == "" or TOKEN_RE.fullmatch(a[1])):
                    err(node, f"value {a[1]!r} is not allowed")
        elif name in ("proxy_connect_timeout", "proxy_read_timeout", "proxy_send_timeout"):
            if nargs(node, 1) and not TIME_RE.fullmatch(a[0]):
                err(node, "must be a time such as 60s")
        elif name in ("proxy_buffering", "sub_filter_once"):
            if nargs(node, 1) and a[0] not in ON_OFF:
                err(node, "must be on or off")
        elif name == "proxy_redirect":
            if len(a) == 1:
                if a[0] not in ("default", "off"):
                    err(node, "single argument must be default or off")
            elif nargs(node, 2):
                if not (PROXY_PASS_RE.fullmatch(a[0].rstrip("/")) or a[0] == "~^/(.*)$"):
                    err(node, f"source {a[0]!r} is not allowed")
                if not re.fullmatch(r"^/[A-Za-z0-9._~/-]*(?:\$1)?$", a[1]):
                    err(node, f"replacement {a[1]!r} is not allowed")
        elif name == "proxy_cookie_path":
            if nargs(node, 2) and not (PATH_RE.fullmatch(a[0]) and PATH_RE.fullmatch(a[1])):
                err(node, "paths must look like /prefix/")
        elif name == "client_max_body_size":
            if nargs(node, 1) and not SIZE_RE.fullmatch(a[0]):
                err(node, "must be a size such as 100m")
        elif name == "return":
            if nargs(node, 1, 2):
                if a[0] not in RETURN_CODES:
                    err(node, f"status {a[0]} is not allowed")
                elif len(a) == 2 and a[0] in ("301", "302") and not REDIRECT_TARGET_RE.fullmatch(a[1]):
                    err(node, f"redirect target {a[1]!r} is not allowed")
                elif len(a) == 2 and "$" in a[1] and a[0] not in ("301", "302"):
                    err(node, "response text must not contain variables")
        elif name == "default_type":
            if nargs(node, 1) and a[0] not in ("text/plain", "text/html"):
                err(node, "must be text/plain or text/html")
        elif name == "sub_filter":
            if nargs(node, 2) and any("$" in x or "\n" in x for x in a):
                err(node, "patterns must not contain variables or newlines")
        elif name == "sub_filter_types":
            if not a or any(x not in SUB_FILTER_TYPES for x in a):
                err(node, "unexpected MIME type")
        elif name == "location":
            err(node, "nested locations are not allowed")
        else:
            err(node, "directive is not allowed here")

    def check_server_child(node):
        name, a = node.name, node.args
        if name == "location":
            if node.children is None:
                err(node, "needs a block")
                return
            path = a[1] if len(a) == 2 and a[0] == "=" else (a[0] if len(a) == 1 else None)
            if path is None or not PATH_RE.fullmatch(path):
                err(node, f"only plain prefix or = locations are allowed, got {' '.join(a)!r}")
            for child in node.children:
                check_location_child(child)
            return
        if not simple(node):
            return
        if name == "listen":
            if nargs(node, 1):
                port = _listen_port(a[0])
                if port is None:
                    err(node, f"{a[0]!r} must be <address>:<port> with no extra parameters")
                elif port in (80, 443) or not (1 <= port <= 65535):
                    err(node, f"port {port} is not allowed")
        elif name == "server_name":
            if a != ["_"]:
                err(node, "only server_name _ is allowed")
        elif name == "absolute_redirect":
            if nargs(node, 1) and a[0] not in ON_OFF:
                err(node, "must be on or off")
        elif name in ("allow", "deny"):
            if nargs(node, 1) and not _ip_or_net(a[0]):
                err(node, f"{a[0]!r} is not an address or network")
        elif name == "access_log":
            if a == ["off"]:
                return
            if nargs(node, 2) and (not log_re.fullmatch(a[0]) or not GW_NAME_RE.fullmatch(a[1])):
                err(node, f"log must be {log_dir}/gateway-*.access.log with a gw_ format")
        elif name == "error_log":
            if nargs(node, 1, 2):
                if not log_re.fullmatch(a[0]):
                    err(node, f"log must be {log_dir}/gateway-*.error.log")
                if len(a) == 2 and a[1] not in LOG_LEVELS:
                    err(node, f"level {a[1]!r} is not allowed")
        elif name == "client_max_body_size":
            if nargs(node, 1) and not SIZE_RE.fullmatch(a[0]):
                err(node, "must be a size such as 100m")
        else:
            err(node, "directive is not allowed here")

    for node in tree:
        if node.name == "map":
            if node.children is None or not nargs(node, 2):
                if node.children is None:
                    err(node, "needs a block")
                continue
            if node.args[0] not in MAP_SOURCES or not GW_VAR_RE.fullmatch(node.args[1]):
                err(node, "only gw_ maps of $http_upgrade or $http_cookie are allowed")
            for entry in node.children:
                if entry.children is not None or len(entry.args) != 1 or not MAP_VALUE_RE.fullmatch(entry.args[0]):
                    err(entry, "unexpected map entry")
        elif node.name == "log_format":
            if not simple(node) or len(node.args) < 2 or not GW_NAME_RE.fullmatch(node.args[0]):
                err(node, "only gw_ log formats are allowed")
        elif node.name == "server":
            if node.children is None:
                err(node, "needs a block")
                continue
            if not any(c.name == "listen" for c in node.children):
                err(node, "every server needs a listen directive")
            for child in node.children:
                check_server_child(child)
        else:
            err(node, "directive is not allowed at the top level of the gateway config")
    return errors


def listen_ports(text: str) -> set:
    ports = set()
    try:
        tree = parse(text)
    except ParseError:
        return ports
    for node in tree:
        if node.name == "server" and node.children:
            for child in node.children:
                if child.name == "listen" and child.args:
                    port = _listen_port(child.args[0])
                    if port:
                        ports.add(port)
    return ports


# ─────────────────────────────────────────────────────────────────────────────
# Reading other nginx config and the system's listening sockets
# ─────────────────────────────────────────────────────────────────────────────

def split_dump(dump: str) -> list:
    """Split `nginx -T` output into (path, content) pairs."""
    parts = re.split(r"^# configuration file (.+?):\s*$", dump, flags=re.M)
    return [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def foreign_listen_ports(content: str) -> set:
    ports = set()
    cleaned = re.sub(r"(?m)^\s*#.*$", "", content)
    for m in re.finditer(r"(?:^|[;{}\s])listen\s+([^;]+);", cleaned):
        first = m.group(1).split()[0]
        if first.startswith("unix:"):
            continue
        pm = re.search(r":(\d+)$", first)
        if pm:
            ports.add(int(pm.group(1)))
        elif first.isdigit():
            ports.add(int(first))
        else:
            ports.add(80)  # address without a port
    return ports


def foreign_gw_names(content: str) -> set:
    names = set()
    cleaned = re.sub(r"(?m)^\s*#.*$", "", content)
    names.update(re.findall(r"\bmap\s+\S+\s+(\$gw_[A-Za-z0-9_]+)", cleaned))
    names.update(re.findall(r"\blog_format\s+(gw_[A-Za-z0-9_]+)", cleaned))
    return names


def parse_proc_net(text: str, ipv6: bool = False) -> list:
    """Listening TCP sockets in /proc/net/tcp{,6} as (address, port)."""
    out = []
    for row in text.splitlines()[1:]:
        cols = row.split()
        if len(cols) < 4 or cols[3] != "0A":  # 0A = LISTEN
            continue
        addr_hex, port_hex = cols[1].rsplit(":", 1)
        try:
            raw = bytes.fromhex(addr_hex)
            if ipv6:
                raw = b"".join(raw[i:i + 4][::-1] for i in range(0, 16, 4))
                addr = str(ipaddress.IPv6Address(raw))
            else:
                addr = str(ipaddress.IPv4Address(raw[::-1]))
        except ValueError:
            continue
        out.append((addr, int(port_hex, 16)))
    return out


def tail_lines(path: str, lines: int) -> list:
    """The last `lines` lines of a file, read backwards in blocks."""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        block, data = 65536, b""
        while size > 0 and data.count(b"\n") <= lines:
            step = min(block, size)
            size -= step
            f.seek(size)
            data = f.read(step) + data
    return data.decode("utf-8", "replace").splitlines()[-lines:]


def read_restart_targets(path: str) -> dict:
    """id -> (kind, name) from the root-owned allowlist; malformed lines are skipped."""
    targets = {}
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) != 3 or not SLUG_RE.fullmatch(parts[0]):
                    continue
                tid, kind, name = parts
                if kind == "systemd" and UNIT_RE.fullmatch(name):
                    targets[tid] = (kind, name)
                elif kind == "docker" and CONTAINER_RE.fullmatch(name):
                    targets[tid] = (kind, name)
    except FileNotFoundError:
        pass
    return targets


# ─────────────────────────────────────────────────────────────────────────────
# The system it acts on (subclassed by the development sandbox and the tests)
# ─────────────────────────────────────────────────────────────────────────────

class Env:
    staged_dir = "/var/lib/nginx-gateway/staging"
    staged_name = "gateway.conf"
    live_dir = "/etc/nginx/nginx-gateway"
    live_name = "gateway.conf"
    stub = "/etc/nginx/conf.d/nginx-gateway.conf"
    backups = "/var/backups/nginx-gateway"
    lock_file = "/run/nginx-gateway-helper.lock"
    restart_targets = "/etc/nginx-gateway/restart-targets.conf"
    log_dir = PRODUCTION_LOG_DIR
    nginx = "/usr/sbin/nginx"
    systemctl = "/usr/bin/systemctl"
    journalctl = "/usr/bin/journalctl"
    docker = "/usr/bin/docker"
    proc_net = "/proc/net"
    bind_wait_seconds = 5.0

    @property
    def live(self) -> str:
        return os.path.join(self.live_dir, self.live_name)

    def run(self, argv: list, timeout: int = 60) -> subprocess.CompletedProcess:
        env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"}
        try:
            return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
        except FileNotFoundError:
            return subprocess.CompletedProcess(argv, 127, "", f"{argv[0]}: not found")
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(argv, 124, "", f"{' '.join(argv)}: timed out after {timeout}s")

    def nginx_installed(self) -> bool:
        return os.path.isfile(self.nginx)

    def nginx_test(self):
        r = self.run([self.nginx, "-t"])
        return r.returncode == 0, (r.stdout + r.stderr).strip()

    def nginx_dump(self):
        r = self.run([self.nginx, "-T"])
        return r.returncode == 0, r.stdout, r.stderr.strip()

    def is_active(self) -> bool:
        return self.run([self.systemctl, "is-active", "--quiet", "nginx"]).returncode == 0

    def reload(self):
        r = self.run([self.systemctl, "reload", "nginx"], timeout=90)
        return r.returncode == 0, (r.stdout + r.stderr).strip()

    def start(self):
        r = self.run([self.systemctl, "start", "nginx"], timeout=90)
        return r.returncode == 0, (r.stdout + r.stderr).strip()

    def listening(self) -> set:
        ports = set()
        for name, v6 in (("tcp", False), ("tcp6", True)):
            try:
                with open(os.path.join(self.proc_net, name)) as f:
                    ports.update(p for _, p in parse_proc_net(f.read(), v6))
            except OSError:
                pass
        return ports

    def own_paths(self) -> set:
        return {os.path.realpath(self.live), os.path.realpath(self.stub) if self.stub else ""}

    def journal(self, unit: str, lines: int) -> list:
        r = self.run([self.journalctl, "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso"])
        return (r.stdout or r.stderr).splitlines()


class HelperFailure(Exception):
    def __init__(self, stage: str, message: str, **extra):
        super().__init__(message)
        self.result = {"ok": False, "stage": stage, "message": message, **extra}


class Lock:
    def __init__(self, path: str, timeout: float = 30.0):
        self.path, self.timeout, self.fd = path, timeout, None

    def __enter__(self):
        import fcntl  # Linux only; imported here so lint() can be used anywhere
        self._fcntl = fcntl
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError as e:
                if e.errno not in (errno.EAGAIN, errno.EACCES) or time.monotonic() > deadline:
                    os.close(self.fd)
                    raise HelperFailure("lock", "another gateway change is in progress; try again")
                time.sleep(0.2)

    def __exit__(self, *exc):
        self._fcntl.flock(self.fd, self._fcntl.LOCK_UN)
        os.close(self.fd)


# ─────────────────────────────────────────────────────────────────────────────
# Operations
# ─────────────────────────────────────────────────────────────────────────────

def read_staged(env: Env) -> str:
    """The staged config, opened without following symlinks anywhere we control."""
    try:
        dfd = os.open(env.staged_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as e:
        raise HelperFailure("read", f"cannot open the staging folder: {e.strerror}")
    try:
        fd = os.open(env.staged_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
    except OSError as e:
        raise HelperFailure("read", f"cannot open the staged config: {e.strerror}")
    finally:
        os.close(dfd)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise HelperFailure("read", "the staged config is not a regular file")
        if st.st_size > MAX_CONFIG_BYTES:
            raise HelperFailure("read", "the staged config is too large")
        data = os.read(fd, MAX_CONFIG_BYTES + 1)
    finally:
        os.close(fd)
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise HelperFailure("read", "the staged config is not UTF-8 text")


def read_live(env: Env):
    try:
        with open(env.live, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _write_atomic(directory: str, name: str, text: str, mode: int = 0o644) -> None:
    os.makedirs(directory, mode=0o755, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, os.path.join(directory, name))
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def conflicts(env: Env, text: str) -> list:
    """Reasons the config would collide with other nginx sites or programs."""
    problems = []
    new_ports = listen_ports(text)
    current = read_live(env)
    ours_now = listen_ports(current) if current else set()
    if env.nginx_installed():
        ok, dump, stderr = env.nginx_dump()
        if not ok:
            problems.append("the current nginx configuration does not pass `nginx -T`, so it cannot be "
                            "checked for conflicts. Fix it first:\n" + stderr)
        own = env.own_paths()
        for path, content in split_dump(dump):
            if os.path.realpath(path) in own:
                continue
            for port in sorted(foreign_listen_ports(content) & new_ports):
                problems.append(f"port {port} is already used by another nginx site ({path})")
            for name in sorted(foreign_gw_names(content)):
                problems.append(f"{name} is already defined in {path}")
    busy = env.listening()
    for port in sorted((new_ports - ours_now) & busy):
        problems.append(f"port {port} is already in use by another program")
    return problems


def _foreign_files(env: Env, output: str) -> list:
    own = env.own_paths()
    files = set(re.findall(r" in (/[^\s:]+):\d+", output))
    return sorted(f for f in files if os.path.realpath(f) not in own)


def _backup(env: Env, text: str) -> str:
    os.makedirs(env.backups, mode=0o700, exist_ok=True)
    bid = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(env.backups, f"gateway.conf.{bid}")
    if os.path.exists(path):  # two applies within a second
        time.sleep(1.1)
        return _backup(env, text)
    _write_atomic(env.backups, f"gateway.conf.{bid}", text, 0o600)
    names = sorted(n for n in os.listdir(env.backups) if n.startswith("gateway.conf.") and BACKUP_ID_RE.fullmatch(n[13:]))
    for old in names[:-KEEP_BACKUPS]:
        os.unlink(os.path.join(env.backups, old))
    return bid


class _Swap:
    """Put a config in place; put the previous one back unless committed."""

    def __init__(self, env: Env, text: str):
        self.env, self.text = env, text
        self.prev = read_live(env)
        self.stub_created = False

    def __enter__(self):
        if self.env.stub and not os.path.exists(self.env.stub):
            _write_atomic(os.path.dirname(self.env.stub), os.path.basename(self.env.stub), STUB_TEXT)
            self.stub_created = True
        _write_atomic(self.env.live_dir, self.env.live_name, self.text)
        self.committed = False
        return self

    def rollback(self):
        if self.prev is not None:
            _write_atomic(self.env.live_dir, self.env.live_name, self.prev)
        else:
            try:
                os.unlink(self.env.live)
            except FileNotFoundError:
                pass
        if self.stub_created:
            os.unlink(self.env.stub)

    def __exit__(self, exc_type, *rest):
        if not self.committed:
            self.rollback()


def _check(env: Env, text: str) -> None:
    errors = lint(text, env.log_dir)
    if errors:
        raise HelperFailure("lint", "the config contains something the gateway never generates", errors=errors)
    found = conflicts(env, text)
    if found:
        raise HelperFailure("conflicts", "the config would collide with something already on this server",
                            errors=found)


def apply_config(env: Env, text: str, source: str = "staged") -> dict:
    """Validate, install, test the full nginx config and reload; roll back on any failure."""
    _check(env, text)
    previous = read_live(env)
    if previous == text and env.is_active():
        return {"ok": True, "applied": False, "reloaded": False, "message": "already live; nothing to do"}
    backup = _backup(env, previous) if previous is not None else None
    with _Swap(env, text) as swap:
        ok, output = env.nginx_test()
        if not ok:
            foreign = _foreign_files(env, output)
            msg = "nginx -t failed; the previous config was kept"
            if foreign:
                msg += " (the error is in another site's file, which was not changed: " + ", ".join(foreign) + ")"
            raise HelperFailure("nginx-test", msg, output=output, foreign_files=foreign)
        if not env.is_active():
            swap.committed = True
            return {"ok": True, "applied": True, "reloaded": False, "nginx_active": False, "backup": backup,
                    "output": output, "source": source,
                    "message": "config installed and tested, but nginx is stopped: it takes effect when nginx starts"}
        ok, reload_out = env.reload()
        if not ok:
            swap.rollback()
            env.reload()
            swap.committed = True
            raise HelperFailure("reload", "nginx reload failed; the previous config was restored", output=reload_out)
        missing = _wait_ports(env, listen_ports(text))
        if missing:
            swap.rollback()
            env.reload()
            swap.committed = True
            raise HelperFailure("bind", "nginx could not listen on port(s) " + ", ".join(map(str, missing)) +
                                "; the previous config was restored. Is another program using them?",
                                ports=missing)
        swap.committed = True
    return {"ok": True, "applied": True, "reloaded": True, "nginx_active": True, "backup": backup,
            "output": output, "source": source, "message": "applied and nginx reloaded"}


def _wait_ports(env: Env, ports: set) -> list:
    deadline = time.monotonic() + env.bind_wait_seconds
    while True:
        missing = sorted(ports - env.listening())
        if not missing or time.monotonic() > deadline:
            return missing
        time.sleep(0.2)


def test_full(env: Env, text: str) -> dict:
    """Lint, conflict scan and `nginx -t` of the whole config; always restores the live file."""
    _check(env, text)
    with _Swap(env, text):
        ok, output = env.nginx_test()
    if not ok:
        raise HelperFailure("nginx-test", "nginx -t failed", output=output, foreign_files=_foreign_files(env, output))
    return {"ok": True, "output": output, "message": "the full nginx configuration is valid"}


def list_backups(env: Env) -> list:
    try:
        names = os.listdir(env.backups)
    except FileNotFoundError:
        return []
    out = []
    for n in sorted(names, reverse=True):
        if n.startswith("gateway.conf.") and BACKUP_ID_RE.fullmatch(n[13:]):
            st = os.stat(os.path.join(env.backups, n))
            out.append({"id": n[13:], "size": st.st_size, "mtime": int(st.st_mtime)})
    return out


def read_backup(env: Env, backup_id: str) -> str:
    if not BACKUP_ID_RE.fullmatch(backup_id):
        raise HelperFailure("args", "invalid backup id")
    try:
        with open(os.path.join(env.backups, f"gateway.conf.{backup_id}"), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise HelperFailure("args", f"no backup {backup_id}")


def status(env: Env) -> dict:
    live = read_live(env)
    ports = sorted(listen_ports(live)) if live else []
    info = {"ok": True, "nginx_installed": env.nginx_installed(), "nginx_active": False, "nginx_version": None,
            "sub_filter": None, "stub_present": bool(env.stub and os.path.exists(env.stub)),
            "live_present": live is not None,
            "live_sha256": hashlib.sha256(live.encode()).hexdigest() if live else None,
            "ports": ports, "ports_listening": sorted(set(ports) & env.listening())}
    if info["nginx_installed"]:
        r = env.run([env.nginx, "-V"])
        text = r.stderr + r.stdout
        m = re.search(r"nginx/(\S+)", text)
        info["nginx_version"] = m.group(1) if m else None
        info["sub_filter"] = "http_sub_module" in text
        info["nginx_active"] = env.is_active()
    return info


def logs(env: Env, source: str, name: str, lines: int) -> dict:
    lines = max(1, min(int(lines), 2000))
    if source in ("access", "error"):
        if not LOG_NAME_RE.fullmatch(name or ""):
            raise HelperFailure("args", "invalid log name")
        path = os.path.join(env.log_dir, f"gateway-{name}.{source}.log")
    elif source == "nginx-error":
        path = os.path.join(env.log_dir, "error.log")
    elif source == "journal":
        return {"ok": True, "lines": env.journal("nginx", lines)}
    elif source == "manager":
        return {"ok": True, "lines": env.journal("nginx-gateway-manager", lines)}
    else:
        raise HelperFailure("args", "unknown log source")
    try:
        return {"ok": True, "lines": tail_lines(path, lines), "path": path}
    except FileNotFoundError:
        return {"ok": True, "lines": [], "path": path, "message": "no log file yet"}


def restart_target(env: Env, target_id: str) -> dict:
    targets = read_restart_targets(env.restart_targets)
    if target_id not in targets:
        raise HelperFailure("args", f"{target_id!r} is not in {env.restart_targets}")
    kind, name = targets[target_id]
    argv = [env.systemctl, "restart", name] if kind == "systemd" else [env.docker, "restart", name]
    r = env.run(argv, timeout=180)
    if r.returncode != 0:
        raise HelperFailure("restart", f"restarting {name} failed", output=(r.stdout + r.stderr).strip())
    return {"ok": True, "message": f"restarted {kind} {name}"}


def start_nginx(env: Env) -> dict:
    ok, output = env.nginx_test()
    if not ok:
        raise HelperFailure("nginx-test", "nginx -t failed; nginx was not started", output=output)
    if env.is_active():
        return {"ok": True, "message": "nginx is already running"}
    ok, out = env.start()
    if not ok:
        raise HelperFailure("start", "nginx did not start", output=out)
    return {"ok": True, "message": "nginx started"}


# ─────────────────────────────────────────────────────────────────────────────
# Command line
# ─────────────────────────────────────────────────────────────────────────────

def run_command(env: Env, args) -> dict:
    cmd = args.command
    if cmd in ("apply", "test-full", "restore", "start"):
        with Lock(env.lock_file):
            if cmd == "apply":
                return apply_config(env, read_staged(env))
            if cmd == "test-full":
                return test_full(env, read_staged(env))
            if cmd == "restore":
                return apply_config(env, read_backup(env, args.backup_id), source=f"backup {args.backup_id}")
            return start_nginx(env)
    if cmd == "scan":
        text = read_staged(env)
        errors = lint(text, env.log_dir)
        return {"ok": not errors, "lint": errors, "conflicts": [] if errors else conflicts(env, text)}
    if cmd == "status":
        return status(env)
    if cmd == "backups":
        return {"ok": True, "backups": list_backups(env)}
    if cmd == "logs":
        return logs(env, args.source, args.name, args.lines)
    if cmd == "restart":
        return restart_target(env, args.target)
    raise HelperFailure("args", f"unknown command {cmd}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nginx-gateway-helper", description="Privileged nginx operations for the gateway manager")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("apply", help="lint, check and install the staged config, then reload nginx")
    sub.add_parser("test-full", help="run nginx -t with the staged config in place, then restore")
    sub.add_parser("scan", help="lint and conflict-scan the staged config without installing it")
    sub.add_parser("status", help="nginx state and the installed gateway config")
    sub.add_parser("backups", help="list saved configs")
    r = sub.add_parser("restore", help="re-apply a saved config")
    r.add_argument("backup_id")
    sub.add_parser("start", help="start nginx (after nginx -t)")
    lg = sub.add_parser("logs", help="tail a gateway log")
    lg.add_argument("source", choices=["access", "error", "nginx-error", "journal", "manager"])
    lg.add_argument("--name", default="")
    lg.add_argument("--lines", type=int, default=200)
    rs = sub.add_parser("restart", help="restart an app listed in restart-targets.conf")
    rs.add_argument("target")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if os.geteuid() != 0:
        print(json.dumps({"ok": False, "stage": "privileges", "message": "must run as root (through sudo)"}))
        return 1
    os.umask(0o022)
    try:
        result = run_command(Env(), args)
    except HelperFailure as e:
        result = e.result
    except Exception as e:  # never leak a traceback to the caller, but say what happened
        result = {"ok": False, "stage": "internal", "message": f"{type(e).__name__}: {e}"}
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
