"""The in-dashboard docs: the API, and that docs/ is consistent (nav.json, files, links)."""
import json
import re
from pathlib import Path

from test_api import ctx, login  # noqa: F401  (ctx is a fixture)

DOCS = Path(__file__).resolve().parents[2] / "docs"
LINK_RE = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")


def nav():
    return json.loads((DOCS / "nav.json").read_text(encoding="utf-8"))


def pages():
    return [p for g in nav()["groups"] for p in g["pages"]]


def test_docs_need_login(ctx):  # noqa: F811
    client, _, _ = ctx
    assert client.get("/api/docs").status_code == 401
    assert client.get("/api/docs/getting-started").status_code == 401


def test_index_and_page(ctx):  # noqa: F811
    client, _, _ = ctx
    login(client)
    index = client.get("/api/docs").json()
    assert [g["title"] for g in index["groups"]][0] == "Getting started"
    page = client.get("/api/docs/vite").json()
    assert page["slug"] == "vite" and page["markdown"].startswith("# Vite")


def test_unknown_slug_and_traversal_are_404(ctx):  # noqa: F811
    client, _, _ = ctx
    login(client)
    for slug in ("nope", "..%2f..%2fetc%2fpasswd", "nav.json", "vite.md"):
        assert client.get(f"/api/docs/{slug}").status_code == 404, slug


def test_nav_is_consistent():
    slugs = [p["slug"] for p in pages()]
    assert len(slugs) == len(set(slugs)), "duplicate slug"
    files = [p["file"] for p in pages()]
    assert len(files) == len(set(files)), "a file is listed twice"
    for p in pages():
        assert re.fullmatch(r"[a-z0-9-]+", p["slug"]), p["slug"]
        assert (DOCS / p["file"]).is_file(), p["file"]
        assert p["title"] and p["summary"]
    on_disk = {f.name for f in DOCS.glob("*.md")}
    assert on_disk == set(files), f"not in nav.json: {on_disk - set(files)}; missing: {set(files) - on_disk}"


def test_internal_links_resolve():
    files = {p["file"] for p in pages()}
    broken = []
    for p in pages():
        text = (DOCS / p["file"]).read_text(encoding="utf-8")
        text = re.sub(r"```.*?```", "", text, flags=re.S)  # code blocks may show example links
        for target in LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if target not in files:
                broken.append(f"{p['file']} -> {target}")
    assert not broken, broken


def test_pages_have_a_title_heading():
    for p in pages():
        first = (DOCS / p["file"]).read_text(encoding="utf-8").lstrip().splitlines()[0]
        assert first.startswith("# "), p["file"]


def test_example_json_files_are_valid():
    examples = DOCS.parent / "examples"
    for name in ("seed-projects.json", "projects-example.json"):
        data = json.loads((examples / name).read_text(encoding="utf-8"))
        assert data["projects"], name
