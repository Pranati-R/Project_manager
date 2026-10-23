"""
Build the nginx-gateway Debian package with the Python standard library only (runs on
Windows or Linux; no dpkg-deb, WSL or Docker needed).

    python packaging/build_deb.py                 # version from packaging/VERSION
    python packaging/build_deb.py --version 0.1.1

Output: dist/nginx-gateway_<version>_all.deb (code, service, nginx-gateway-ctl).
Python packages are downloaded on the server by `nginx-gateway-ctl setup`, and later code
changes arrive with `nginx-gateway-ctl update-code` (from GitHub), so a new .deb is only
needed when the files under packaging/linux that dpkg installs change (service unit,
shims, sudo rule, maintainer scripts).
"""
import argparse
import gzip
import hashlib
import io
import os
import subprocess
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINUX = ROOT / "packaging" / "linux"
SRC_PREFIX = "usr/share/nginx-gateway/src"
PACKAGE = "nginx-gateway"

# nginx is deliberately not a dependency: installing it through apt would start its default
# site on port 80 (Apache's port) and fail. `nginx-gateway-ctl setup` installs it safely.
DEPENDS = ["python3 (>= 3.10)", "python3-venv", "git", "ca-certificates", "curl", "iproute2", "sudo", "adduser"]
SUGGESTS = ["nginx", "tailscale"]

# packaging/linux file -> (installed path, mode)
INSTALL = {
    "nginx-gateway-ctl.shim": ("usr/bin/nginx-gateway-ctl", 0o755),
    "nginx-gateway-helper.shim": ("usr/sbin/nginx-gateway-helper", 0o755),
    "nginx-gateway-manager.service": ("usr/lib/systemd/system/nginx-gateway-manager.service", 0o644),
    "nginx-gateway.conf.template": ("usr/share/nginx-gateway/nginx-gateway.conf.template", 0o644),
    "restart-targets.conf.template": ("usr/share/nginx-gateway/restart-targets.conf.template", 0o644),
    "sudoers": ("usr/share/nginx-gateway/sudoers", 0o440),
}
MAINTAINER_SCRIPTS = ["postinst", "prerm", "postrm"]
SOURCE_ROOTS = ["backend", "frontend", "packaging/linux", "examples", "docs", "README.md"]
EXCLUDE_PARTS = ("__pycache__", ".pytest_cache")


def source_files() -> list:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", *SOURCE_ROOTS],
            cwd=ROOT, check=True, capture_output=True,
        ).stdout.decode("utf-8")
        names = {n for n in out.split("\0") if n}
    except (OSError, subprocess.CalledProcessError):
        # Not a git checkout: walk the folders instead
        names = set()
        for top in SOURCE_ROOTS:
            p = ROOT / top
            if p.is_file():
                names.add(top)
            for dirpath, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_PARTS]
                for f in files:
                    names.add(Path(dirpath, f).relative_to(ROOT).as_posix())
    return sorted(n for n in names
                  if (ROOT / n).is_file() and not any(part in EXCLUDE_PARTS for part in n.split("/"))
                  and not n.endswith((".pyc", ".deb")))


def needs_lf(rel: str, data: bytes) -> bool:
    return rel.startswith("packaging/linux/") or data.startswith(b"#!") or rel.endswith((".py", ".sh", ".j2"))


def read(rel: str) -> bytes:
    data = (ROOT / rel).read_bytes()
    return data.replace(b"\r\n", b"\n") if needs_lf(rel, data) else data


class TarBuilder:
    def __init__(self, mtime: int):
        self.buf = io.BytesIO()
        self.gz = gzip.GzipFile(fileobj=self.buf, mode="wb", mtime=mtime, compresslevel=9)
        self.tar = tarfile.open(fileobj=self.gz, mode="w", format=tarfile.GNU_FORMAT)
        self.mtime = mtime
        self.dirs = set()
        self._dir(".")

    def _info(self, name: str, mode: int) -> tarfile.TarInfo:
        info = tarfile.TarInfo(name)
        info.mode, info.mtime = mode, self.mtime
        info.uid = info.gid = 0
        info.uname = info.gname = "root"
        return info

    def _dir(self, name: str) -> None:
        if name in self.dirs:
            return
        if name != ".":
            self._dir(name.rsplit("/", 1)[0])  # "./usr/bin" -> "./usr" -> "."
        info = self._info(name if name == "." else name + "/", 0o755)
        info.type = tarfile.DIRTYPE
        self.tar.addfile(info)
        self.dirs.add(name)

    def add(self, path: str, data: bytes, mode: int) -> None:
        name = "./" + path
        self._dir(name.rsplit("/", 1)[0])
        info = self._info(name, mode)
        info.size = len(data)
        self.tar.addfile(info, io.BytesIO(data))

    def finish(self) -> bytes:
        self.tar.close()
        self.gz.close()
        return self.buf.getvalue()


def ar_archive(members: list, mtime: int) -> bytes:
    out = io.BytesIO()
    out.write(b"!<arch>\n")
    for name, data in members:
        header = f"{name:<16}{mtime:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n"
        out.write(header.encode("ascii"))
        out.write(data)
        if len(data) % 2:
            out.write(b"\n")
    return out.getvalue()


def build(version: str, out_dir: Path) -> Path:
    mtime = int(time.time())
    data_tar = TarBuilder(mtime)
    md5sums = []
    installed_bytes = 0

    def add(path: str, data: bytes, mode: int) -> None:
        nonlocal installed_bytes
        data_tar.add(path, data, mode)
        md5sums.append(f"{hashlib.md5(data).hexdigest()}  {path}")
        installed_bytes += len(data)

    files = source_files()
    if "packaging/linux/nginx-gateway-ctl" not in files:
        sys.exit("packaging/linux/nginx-gateway-ctl is missing")
    for rel in files:
        data = read(rel)
        executable = data.startswith(b"#!") or rel == "packaging/linux/nginx-gateway-ctl"
        add(f"{SRC_PREFIX}/{rel}", data, 0o755 if executable else 0o644)
    for src, (dest, mode) in INSTALL.items():
        add(dest, read(f"packaging/linux/{src}"), mode)

    control = "\n".join([
        f"Package: {PACKAGE}",
        f"Version: {version}",
        "Architecture: all",
        "Maintainer: Vcode7 <vikaskag7@gmail.com>",
        f"Installed-Size: {installed_bytes // 1024 + 1}",
        f"Depends: {', '.join(DEPENDS)}",
        f"Suggests: {', '.join(SUGGESTS)}",
        "Section: web",
        "Priority: optional",
        "Homepage: https://github.com/Vcode7/nginx-gateway",
        "Description: Nginx reverse proxy gateway with a web dashboard",
        " One nginx port (8280) in front of many web apps, routed by URL path, with a",
        " dashboard (port 8281) to add, test and remove projects. Every change is checked",
        " with nginx -t before a graceful reload and rolled back on failure; Apache and",
        " other nginx sites are never touched. After installing run",
        " 'sudo nginx-gateway-ctl setup'; 'nginx-gateway-ctl update-code' pulls new code",
        " from GitHub.",
        "",
    ])
    control_tar = TarBuilder(mtime)
    control_tar.add("control", control.encode("utf-8"), 0o644)
    control_tar.add("md5sums", ("\n".join(md5sums) + "\n").encode("utf-8"), 0o644)
    for script in MAINTAINER_SCRIPTS:
        control_tar.add(script, read(f"packaging/linux/{script}"), 0o755)

    deb = ar_archive([
        ("debian-binary", b"2.0\n"),
        ("control.tar.gz", control_tar.finish()),
        ("data.tar.gz", data_tar.finish()),
    ], mtime)

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{PACKAGE}_{version}_all.deb"
    out.write_bytes(deb)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default=(ROOT / "packaging" / "VERSION").read_text().strip())
    ap.add_argument("--out", default=str(ROOT / "dist"))
    args = ap.parse_args()
    t0 = time.time()
    out = build(args.version, Path(args.out))
    print(f"{out}  ({out.stat().st_size / 1e3:.0f} kB, {time.time() - t0:.1f}s)")
    print("Install on the server:  sudo apt install ./" + out.name + "  &&  sudo nginx-gateway-ctl setup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
