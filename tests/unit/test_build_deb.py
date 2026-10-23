"""The .deb builder: control data, maintainer scripts and the installed file list."""
import gzip
import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packaging"))
import build_deb  # noqa: E402


def read_ar(data: bytes) -> dict:
    assert data[:8] == b"!<arch>\n"
    pos, members = 8, {}
    while pos < len(data):
        header = data[pos:pos + 60]
        name = header[:16].decode().strip()
        size = int(header[48:58].decode().strip())
        members[name] = data[pos + 60:pos + 60 + size]
        pos += 60 + size + (size % 2)
    return members


def tar_members(blob: bytes) -> dict:
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(blob))) as t:
        return {m.name: (m, t.extractfile(m).read() if m.isfile() else None) for m in t.getmembers()}


def test_build(tmp_path):
    deb = build_deb.build("9.9.9", tmp_path)
    assert deb.name == "nginx-gateway_9.9.9_all.deb"
    ar = read_ar(deb.read_bytes())
    assert list(ar) == ["debian-binary", "control.tar.gz", "data.tar.gz"]
    assert ar["debian-binary"] == b"2.0\n"

    control = tar_members(ar["control.tar.gz"])
    text = control["./control"][1].decode()
    assert "Package: nginx-gateway" in text and "Version: 9.9.9" in text and "Architecture: all" in text
    depends = next(line for line in text.splitlines() if line.startswith("Depends:"))
    assert "nginx" not in depends  # installed safely by setup instead (port 80 belongs to Apache)
    for script in ("postinst", "prerm", "postrm"):
        info, body = control[f"./{script}"]
        assert info.mode == 0o755 and body.startswith(b"#!/bin/sh") and b"\r\n" not in body

    data = tar_members(ar["data.tar.gz"])
    names = set(data)
    for path in ("./usr/bin/nginx-gateway-ctl", "./usr/sbin/nginx-gateway-helper",
                 "./usr/lib/systemd/system/nginx-gateway-manager.service",
                 "./usr/share/nginx-gateway/sudoers",
                 "./usr/share/nginx-gateway/src/backend/gateway_manager/nginx_helper.py",
                 "./usr/share/nginx-gateway/src/backend/requirements.txt",
                 "./usr/share/nginx-gateway/src/frontend/index.html",
                 "./usr/share/nginx-gateway/src/packaging/linux/nginx-gateway-ctl",
                 "./usr/share/nginx-gateway/src/examples/seed-projects.json"):
        assert path in names, path
    assert not any("/tests/" in n or "__pycache__" in n for n in names)
    assert data["./usr/bin/nginx-gateway-ctl"][0].mode == 0o755
    assert data["./usr/share/nginx-gateway/src/packaging/linux/nginx-gateway-ctl"][0].mode == 0o755
    assert all(m.uid == 0 and m.gid == 0 for m, _ in data.values())
    sh = data["./usr/share/nginx-gateway/src/packaging/linux/nginx-gateway-ctl"][1]
    assert b"\r\n" not in sh


def test_shell_scripts_parse():
    for name in ("nginx-gateway-ctl", "postinst", "prerm", "postrm", "nginx-gateway-ctl.shim", "nginx-gateway-helper.shim"):
        path = ROOT / "packaging" / "linux" / name
        shell = "bash" if name == "nginx-gateway-ctl" else "sh"
        r = subprocess.run([shell, "-n", str(path)], capture_output=True, text=True)
        assert r.returncode == 0, (name, r.stderr)
